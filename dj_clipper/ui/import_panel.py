import re
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dj_clipper.config import MIN_VIDEO_DURATION
from dj_clipper.core.audio_extractor import get_video_duration
from dj_clipper.models.session_model import AnalysisSettings, SessionState
from dj_clipper.workers.analysis_worker import AnalysisWorker
from dj_clipper.ui.widgets.drop_zone import DropZone, PlaylistDropZone
from dj_clipper.ui.widgets.progress_overlay import ProgressOverlay
from dj_clipper.ui.widgets.sliding_toggle import SlidingToggle

_MODE_TOP_N    = 0
_MODE_ALL      = 1
_MODE_TIMESLOT = 2

_SCORE_DESC = "Top clips determined by confidence in track match against provided playlist"


# Accepts d:dd, dd:dd (mm:ss) or d:dd:dd, dd:dd:dd (hh:mm:ss).
# Each component after the first must be exactly 2 digits.
_TS_RE = re.compile(r'^\d{1,2}:\d{2}(:\d{2})?$')


def _parse_timestamps(text: str) -> tuple[list[float], list[str]]:
    """
    Parse a block of text containing timestamps.
    Accepts hh:mm:ss or mm:ss, comma or newline delimited.

    Returns (valid_seconds, malformed_tokens) where malformed_tokens is a
    list of raw strings that did not match the expected format.
    """
    tokens = re.split(r'[,\n]+', text)
    valid: list[float] = []
    malformed: list[str] = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if not _TS_RE.match(token):
            malformed.append(token)
            continue
        parts = token.split(':')
        try:
            if len(parts) == 2:
                m, s = int(parts[0]), float(parts[1])
                valid.append(m * 60.0 + s)
            elif len(parts) == 3:
                h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
                valid.append(h * 3600.0 + m * 60.0 + s)
        except (ValueError, IndexError):
            malformed.append(token)
    return sorted(set(valid)), malformed


class ImportPanel(QWidget):
    """Screen 1: drop zones + clip settings + Create Clips."""

    analysis_complete = pyqtSignal(object)  # SessionState

    def __init__(self, parent=None):
        super().__init__(parent)
        self._video_path: Path | None = None
        self._video_duration: float = 0.0
        self._playlist_path: Path | None = None
        self._cancel_event: threading.Event | None = None
        self._overlay: ProgressOverlay | None = None

        self.setStyleSheet("background: #181818; color: #ddd;")

        # ── Title ──────────────────────────────────────────────────────────────
        title = QLabel("DJ Clipper")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #fff;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ── Drop zones ─────────────────────────────────────────────────────────
        self._drop_zone = DropZone()
        self._drop_zone.setMinimumHeight(110)
        self._drop_zone.video_dropped.connect(self._on_video_dropped)

        self._playlist_zone = PlaylistDropZone()
        self._playlist_zone.setMinimumHeight(110)
        self._playlist_zone.playlist_dropped.connect(self._on_playlist_dropped)

        # ── Clip duration (centred) ────────────────────────────────────────────
        dur_label = QLabel("Clip Duration:")
        dur_label.setStyleSheet("font-size: 13px;")
        self._dur_group = QButtonGroup(self)
        dur_row = QHBoxLayout()
        dur_row.addStretch()
        dur_row.addWidget(dur_label)
        for secs in (30, 45, 60):
            btn = QRadioButton(f"{secs}s")
            btn.setStyleSheet("font-size: 13px; margin-right: 10px;")
            self._dur_group.addButton(btn, secs)
            dur_row.addWidget(btn)
            if secs == 45:
                btn.setChecked(True)
        dur_row.addStretch()

        # ── Mode toggle (centred) ──────────────────────────────────────────────
        self._mode_toggle = SlidingToggle(["Top # Clips", "All Transitions", "Specific Times"])
        self._mode_toggle.toggled.connect(self._on_mode_changed)
        toggle_row = QHBoxLayout()
        toggle_row.addStretch()
        toggle_row.addWidget(self._mode_toggle)
        toggle_row.addStretch()

        # ── Clip count (centred, hidden in All Transitions mode) ───────────────
        self._count_widget = QWidget()
        count_vbox = QVBoxLayout(self._count_widget)
        count_vbox.setContentsMargins(0, 0, 0, 0)
        count_vbox.setSpacing(4)

        count_title = QLabel("Number of Clips:")
        count_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count_title.setStyleSheet("font-size: 13px; color: #aaa;")

        self._count_slider = QSlider(Qt.Orientation.Horizontal)
        self._count_slider.setRange(5, 20)
        self._count_slider.setValue(10)
        self._count_slider.setTickInterval(5)
        self._count_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._count_slider.setFixedWidth(200)
        self._count_value_label = QLabel("10")
        self._count_value_label.setStyleSheet("font-size: 13px; min-width: 28px;")
        self._count_slider.valueChanged.connect(
            lambda v: self._count_value_label.setText(str(v))
        )

        slider_row = QHBoxLayout()
        slider_row.addStretch()
        slider_row.addWidget(self._count_slider)
        slider_row.addWidget(self._count_value_label)
        slider_row.addStretch()

        count_vbox.addWidget(count_title)
        count_vbox.addLayout(slider_row)

        # ── Mode area: fixed-height container so music folder never shifts ────────
        # Score label + count widget live inside; their visibility toggles but the
        # container's height stays constant, pinning the music folder in place.
        self._score_label = QLabel(_SCORE_DESC)
        self._score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._score_label.setWordWrap(True)
        self._score_label.setStyleSheet(
            "font-size: 11px; color: #666; font-style: italic;"
        )

        # ── Timeslot input (shown only in Specific Times mode) ─────────────────
        self._timeslot_widget = QWidget()
        ts_vbox = QVBoxLayout(self._timeslot_widget)
        ts_vbox.setContentsMargins(0, 0, 0, 0)
        ts_vbox.setSpacing(4)
        ts_label = QLabel("Enter timestamps (hh:mm:ss or mm:ss, comma or newline separated):")
        ts_label.setStyleSheet("font-size: 11px; color: #aaa;")
        ts_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._timeslot_edit = QTextEdit()
        self._timeslot_edit.setFixedHeight(72)
        self._timeslot_edit.setPlaceholderText("e.g.  00:45:10, 01:14:00, 30:15\nor one per line")
        self._timeslot_edit.setStyleSheet(
            "background:#222; color:#ddd; border:1px solid #444;"
            "border-radius:4px; padding:4px; font-size:12px;"
        )
        self._ts_error_label = QLabel("")
        self._ts_error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ts_error_label.setWordWrap(True)
        self._ts_error_label.setStyleSheet(
            "font-size: 10px; color: #e05555; padding: 0;"
        )
        self._ts_error_label.setVisible(False)

        ts_vbox.addWidget(ts_label)
        ts_vbox.addWidget(self._timeslot_edit)
        ts_vbox.addWidget(self._ts_error_label)
        self._timeslot_widget.setVisible(False)

        self._timeslot_edit.textChanged.connect(self._validate_timestamps)

        self._mode_area = QWidget()
        self._mode_area.setFixedHeight(148)
        mode_area_vbox = QVBoxLayout(self._mode_area)
        mode_area_vbox.setContentsMargins(0, 4, 0, 4)
        mode_area_vbox.setSpacing(6)
        mode_area_vbox.addWidget(self._score_label)
        mode_area_vbox.addWidget(self._count_widget)
        mode_area_vbox.addWidget(self._timeslot_widget)
        mode_area_vbox.addStretch()

        # ── Music folder (persisted) ───────────────────────────────────────────
        sr_row = QHBoxLayout()
        sr_icon = QLabel("Music folder:")
        sr_icon.setStyleSheet("font-size: 13px; min-width: 80px;")
        self._sr_edit = QLineEdit("Not set")
        self._sr_edit.setReadOnly(True)
        self._sr_edit.setStyleSheet(
            "background:#222;color:#666;border:1px solid #333;"
            "border-radius:4px;padding:3px 6px;font-size:12px;"
        )
        sr_browse = QPushButton("Browse")
        self._style_small_btn(sr_browse)
        sr_browse.clicked.connect(self._browse_search_root)
        sr_row.addWidget(sr_icon)
        sr_row.addWidget(self._sr_edit)
        sr_row.addWidget(sr_browse)
        self._restore_search_root()

        # ── Action button ──────────────────────────────────────────────────────
        self._find_btn = QPushButton("Create Clips")
        self._find_btn.setEnabled(False)
        self._find_btn.setFixedHeight(44)
        self._find_btn.setStyleSheet("""
            QPushButton {
                background: #2b5ea7;
                color: #fff;
                border: none;
                border-radius: 6px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton:disabled { background: #333; color: #666; }
            QPushButton:hover:enabled { background: #3a74cc; }
        """)
        self._find_btn.clicked.connect(self._on_find_clips)

        # ── Layout ─────────────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 24)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(self._drop_zone)
        layout.addWidget(self._playlist_zone)
        layout.addLayout(dur_row)
        layout.addSpacing(10)         # extra gap between clip duration and toggle
        layout.addLayout(toggle_row)
        layout.addWidget(self._mode_area)
        layout.addStretch(1)          # equal stretch above music folder
        layout.addLayout(sr_row)
        layout.addStretch(1)          # equal stretch below music folder
        layout.addWidget(self._find_btn)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _style_small_btn(self, btn: QPushButton) -> None:
        btn.setFixedWidth(70)
        btn.setStyleSheet(
            "background:#2a2a2a;color:#ccc;border:1px solid #444;"
            "border-radius:4px;padding:3px;font-size:12px;"
        )

    # ── Timestamp validation ──────────────────────────────────────────────────

    def _validate_timestamps(self) -> None:
        """
        Called on every keystroke in the timestamp box and whenever a video
        is dropped.  Highlights the box red and shows an error label for any
        token with a bad format or any timestamp that exceeds the video duration.
        """
        if self._mode_toggle.current_index != _MODE_TIMESLOT:
            return

        text = self._timeslot_edit.toPlainText()
        timestamps, malformed = _parse_timestamps(text)

        def _fmt(t: float) -> str:
            s = int(t)
            return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"

        errors: list[str] = []

        if malformed:
            bad = ",  ".join(f'"{t}"' for t in malformed)
            errors.append(f"Invalid format (use mm:ss or hh:mm:ss):  {bad}")

        if self._video_duration > 0 and timestamps:
            out_of_bounds = [t for t in timestamps if t >= self._video_duration]
            if out_of_bounds:
                dur_str = _fmt(self._video_duration)
                bad_str = ",  ".join(_fmt(t) for t in out_of_bounds)
                errors.append(f"Exceeds video length ({dur_str}):  {bad_str}")

        if errors:
            self._timeslot_edit.setStyleSheet(
                "background:#222; color:#ddd; border:2px solid #cc3333;"
                "border-radius:4px; padding:4px; font-size:12px;"
            )
            self._ts_error_label.setText("\n".join(errors))
            self._ts_error_label.setVisible(True)
        else:
            self._timeslot_edit.setStyleSheet(
                "background:#222; color:#ddd; border:1px solid #444;"
                "border-radius:4px; padding:4px; font-size:12px;"
            )
            self._ts_error_label.setVisible(False)

    # ── Mode toggle ───────────────────────────────────────────────────────────

    def _on_mode_changed(self, idx: int) -> None:
        # Toggle inner widgets — _mode_area keeps its fixed height so the
        # music folder row doesn't move.
        self._score_label.setVisible(idx == _MODE_TOP_N)
        self._count_widget.setVisible(idx == _MODE_TOP_N)
        self._timeslot_widget.setVisible(idx == _MODE_TIMESLOT)
        if idx == _MODE_ALL:
            self._find_btn.setText("Clip All Transitions")
        elif idx == _MODE_TIMESLOT:
            self._find_btn.setText("Clip Timeslots")
        else:
            self._find_btn.setText("Create Clips")

    # ── Drop / browse handlers ────────────────────────────────────────────────

    def _on_video_dropped(self, path: Path) -> None:
        try:
            duration = get_video_duration(path)
        except Exception:
            QMessageBox.warning(self, "Invalid File", "Could not read video duration.")
            return
        if duration < MIN_VIDEO_DURATION:
            QMessageBox.warning(
                self,
                "Video Too Short",
                f"Video is only {duration:.0f}s. Minimum is {MIN_VIDEO_DURATION}s (5 min).",
            )
            return
        self._video_path = path
        self._video_duration = duration
        self._find_btn.setEnabled(True)
        # Re-run validation in case timestamps were entered before the video was dropped
        self._validate_timestamps()

    def _on_playlist_dropped(self, path: Path) -> None:
        self._playlist_path = path

    def _restore_search_root(self) -> None:
        saved = QSettings("DJClipper", "DJClipper").value("search_root", "")
        if saved:
            self._sr_edit.setText(saved)
            self._sr_edit.setStyleSheet(
                "background:#222;color:#ddd;border:1px solid #444;"
                "border-radius:4px;padding:3px 6px;font-size:12px;"
            )

    def _browse_search_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Music Root Folder")
        if folder:
            self._sr_edit.setText(folder)
            self._sr_edit.setStyleSheet(
                "background:#222;color:#ddd;border:1px solid #444;"
                "border-radius:4px;padding:3px 6px;font-size:12px;"
            )
            s = QSettings("DJClipper", "DJClipper")
            s.setValue("search_root", folder)
            s.sync()

    # ── Analysis ──────────────────────────────────────────────────────────────

    def _on_find_clips(self) -> None:
        mode = self._mode_toggle.current_index
        clip_all = (mode == _MODE_ALL)
        clip_duration = float(self._dur_group.checkedId())
        n_clips = self._count_slider.value()

        sr_text = self._sr_edit.text().strip()
        search_root = Path(sr_text) if sr_text and sr_text != "Not set" else None

        # Parse and validate timestamps if in timeslot mode
        manual_timestamps: list[float] = []
        if mode == _MODE_TIMESLOT:
            manual_timestamps, malformed = _parse_timestamps(self._timeslot_edit.toPlainText())
            if malformed:
                QMessageBox.warning(
                    self, "Invalid Timestamps",
                    "Some entries have an invalid format and were ignored.\n"
                    "Use mm:ss or hh:mm:ss with exactly 2 digits for minutes and seconds.\n\n"
                    + "\n".join(f'  "{t}"' for t in malformed)
                )
                return
            if not manual_timestamps:
                QMessageBox.warning(
                    self, "No Timestamps",
                    "Please enter at least one valid timestamp (e.g. 1:23:45 or 23:45)."
                )
                return
            if self._video_duration > 0:
                out_of_bounds = [t for t in manual_timestamps if t >= self._video_duration]
                if out_of_bounds:
                    # Validation highlight is already shown; just surface a message
                    def _fmt(t: float) -> str:
                        s = int(t)
                        return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
                    QMessageBox.warning(
                        self, "Invalid Timestamps",
                        "One or more timestamps exceed the video duration and cannot be used:\n\n"
                        + "\n".join(_fmt(t) for t in out_of_bounds)
                        + f"\n\nVideo length: {_fmt(self._video_duration)}"
                    )
                    return

        session = SessionState(
            video_path=self._video_path,
            settings=AnalysisSettings(
                clip_duration=clip_duration,
                n_clips=n_clips,
                clip_all=clip_all,
                manual_timestamps=manual_timestamps,
            ),
            playlist_path=self._playlist_path,
            search_root=search_root,
        )

        self._cancel_event = threading.Event()
        self._overlay = ProgressOverlay("Analyzing Video", self._cancel_event, self)

        worker = AnalysisWorker(session, self._cancel_event)
        worker.signals.progress.connect(self._overlay.update_progress)
        worker.signals.finished.connect(self._on_analysis_done)
        worker.signals.error.connect(self._on_analysis_error)
        worker.signals.cancelled.connect(self._overlay.reject)

        from PyQt6.QtCore import QThreadPool
        QThreadPool.globalInstance().start(worker)
        self._overlay.exec()

    def _on_analysis_done(self, session: SessionState) -> None:
        if self._overlay:
            self._overlay.accept()
        if not session.candidates:
            QMessageBox.warning(
                self, "No Clips Found",
                "No transition moments were detected.\n\n"
                "Try providing a playlist for fingerprint-based detection, "
                "or try a longer video with more dynamic mixing.",
            )
            return
        self.analysis_complete.emit(session)

    def _on_analysis_error(self, message: str) -> None:
        if self._overlay:
            self._overlay.reject()
        QMessageBox.critical(self, "Analysis Failed", message)
