from pathlib import Path
from typing import List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from dj_clipper.models.clip_model import ClipCandidate
from dj_clipper.core.track_utils import clean_track_name


def _fmt_ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:01d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _fmt_dur(seconds: float) -> str:
    s = int(round(seconds))
    if s < 60:
        return f"{s}s"
    m, rem = divmod(s, 60)
    return f"{m}m{rem}s" if rem else f"{m}m"


class ClipCard(QFrame):
    """
    Thumbnail card for one ClipCandidate. Displays:
      - JPEG thumbnail (or placeholder)
      - Clip number + timestamp
      - Track labels (pre → post) when fingerprint mode ran
      - Track-label edit button (when playlist was provided)
      - Keep / Bin toggle

    Emits:
      selected(ClipCandidate)  — when the card body is clicked
      kept_changed()           — when the keep/bin state changes
    """

    selected     = pyqtSignal(object)   # ClipCandidate
    kept_changed = pyqtSignal()

    def __init__(
        self,
        candidate: ClipCandidate,
        video_duration: float = 0.0,
        track_names: List[str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.candidate = candidate
        self._video_duration = video_duration
        self._track_names: List[str] = track_names or []

        self.setFixedWidth(160)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._apply_frame_style(selected=False)

        # ── Thumbnail ──────────────────────────────────────────────────────
        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(144, 81)   # 16:9 at 144 px wide
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet("background: #222; border-radius: 4px;")
        self._set_thumbnail(candidate.thumbnail_path)

        # ── Info labels ────────────────────────────────────────────────────
        self._num_label = QLabel(self._num_text(candidate))
        self._num_label.setStyleSheet(
            "font-weight: bold; color: #eee; font-size: 12px;"
        )

        self._ts_label = QLabel(_fmt_ts(candidate.start_time))
        self._ts_label.setStyleSheet("color: #999; font-size: 10px;")

        # ── Track label + edit button ──────────────────────────────────────
        self._track_label = QLabel()
        self._track_label.setWordWrap(True)
        self._track_label.setStyleSheet(
            "color: #7ec8e3; font-size: 9px; line-height: 1.3;"
        )
        self._update_track_label(candidate)

        self._edit_track_btn = QPushButton("✎")
        self._edit_track_btn.setFixedSize(18, 18)
        self._edit_track_btn.setToolTip("Edit track labels")
        self._edit_track_btn.setStyleSheet(
            "background:transparent;color:#555;border:none;font-size:11px;padding:0;"
        )
        self._edit_track_btn.clicked.connect(self._on_edit_tracks)
        self._edit_track_btn.setVisible(bool(self._track_names))

        track_row = QHBoxLayout()
        track_row.setContentsMargins(0, 0, 0, 0)
        track_row.setSpacing(2)
        track_row.addWidget(self._track_label)
        track_row.addWidget(
            self._edit_track_btn, alignment=Qt.AlignmentFlag.AlignTop
        )

        # ── Keep / Bin toggle ──────────────────────────────────────────────
        self._toggle_btn = QPushButton()
        self._toggle_btn.setFixedHeight(26)
        self._toggle_btn.clicked.connect(self._on_toggle)
        self._update_toggle_style()

        # ── Layout ────────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        layout.addWidget(self._thumb_label)
        layout.addWidget(self._num_label)
        layout.addWidget(self._ts_label)
        layout.addLayout(track_row)
        layout.addWidget(self._toggle_btn)

    # ── Public API ─────────────────────────────────────────────────────────

    @staticmethod
    def _num_text(candidate) -> str:
        dur = candidate.end_time - candidate.start_time
        return f"Clip {candidate.rank}  ·  {_fmt_dur(dur)}"

    def refresh(self) -> None:
        """Re-read candidate and update all display labels."""
        self._num_label.setText(self._num_text(self.candidate))
        self._ts_label.setText(_fmt_ts(self.candidate.start_time))
        self._update_track_label(self.candidate)

    def set_selected(self, selected: bool) -> None:
        self._apply_frame_style(selected)

    def update_thumbnail(self, path: str) -> None:
        self.candidate.thumbnail_path = Path(path)
        self._set_thumbnail(path)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _apply_frame_style(self, selected: bool) -> None:
        border = "#4a9eff" if selected else "#333"
        self.setStyleSheet(f"""
            ClipCard {{
                background: #1e1e1e;
                border: 2px solid {border};
                border-radius: 6px;
            }}
        """)

    def _set_thumbnail(self, path) -> None:
        if path and Path(path).exists():
            pix = QPixmap(str(path)).scaled(
                144, 81,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._thumb_label.setPixmap(pix)
        else:
            self._thumb_label.setText("No preview")
            self._thumb_label.setStyleSheet(
                "background: #222; color: #555; font-size: 10px; border-radius: 4px;"
            )

    def _update_track_label(self, candidate) -> None:
        pre  = clean_track_name(candidate.pre_track)  if candidate.pre_track  else None
        post = clean_track_name(candidate.post_track) if candidate.post_track else None
        has_tracks = bool(self._track_names)
        if pre and post:
            self._track_label.setText(f"{pre}\n  ↓\n{post}")
            self._track_label.setVisible(True)
        elif pre:
            self._track_label.setText(f"← {pre}")
            self._track_label.setVisible(True)
        elif post:
            self._track_label.setText(f"→ {post}")
            self._track_label.setVisible(True)
        elif has_tracks:
            self._track_label.setText("No ID")
            self._track_label.setStyleSheet("color: #555; font-size: 9px;")
            self._track_label.setVisible(True)
        else:
            self._track_label.setVisible(False)
        if hasattr(self, "_edit_track_btn"):
            self._edit_track_btn.setVisible(has_tracks)

    def _on_edit_tracks(self) -> None:
        from PyQt6.QtWidgets import QDialog
        from dj_clipper.ui.widgets.track_edit_dialog import TrackEditDialog
        dialog = TrackEditDialog(
            self._track_names,
            self.candidate.pre_track,
            self.candidate.post_track,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            pre, post = dialog.result_tracks()
            self.candidate.pre_track  = pre
            self.candidate.post_track = post
            self._track_label.setStyleSheet(
                "color: #7ec8e3; font-size: 9px; line-height: 1.3;"
            )
            self._update_track_label(self.candidate)

    def _on_toggle(self) -> None:
        self.candidate.kept = not self.candidate.kept
        self._update_toggle_style()
        self.kept_changed.emit()

    def _update_toggle_style(self) -> None:
        if self.candidate.kept:
            self._toggle_btn.setText("Keep ✓")
            self._toggle_btn.setStyleSheet(
                "background: #2a6e2a; color: #9ef09e; border: none;"
                "border-radius: 4px; font-size: 11px;"
            )
        else:
            self._toggle_btn.setText("Bin ✗")
            self._toggle_btn.setStyleSheet(
                "background: #6e2a2a; color: #f09e9e; border: none;"
                "border-radius: 4px; font-size: 11px;"
            )

    def mousePressEvent(self, event) -> None:
        self.selected.emit(self.candidate)
        super().mousePressEvent(event)
