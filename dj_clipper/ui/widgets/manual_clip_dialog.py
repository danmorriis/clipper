"""
Dialog for creating a manual clip from the session video.

The user scrubs to any point in the video and sets a clip duration (4–60s).
The player updates and begins playing automatically whenever either slider is
released — no "Load Preview" button needed.
"""

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
)

from dj_clipper.models.clip_model import ClipCandidate
from dj_clipper.ui.widgets.video_player import VideoPlayer

_MIN_DURATION = 4.0
_MAX_DURATION = 60.0


def _fmt_ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:01d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


class ManualClipDialog(QDialog):
    """
    Modal dialog: scrub the full video + set clip duration → Add Clip.

    Both sliders auto-update the player on release so you can hear exactly
    what will be in the clip without pressing any extra button.

    Usage:
        dialog = ManualClipDialog(video_path, video_duration, next_rank, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            candidate = dialog.clip_candidate()
    """

    def __init__(
        self,
        video_path: Path,
        video_duration: float,
        next_rank: int,
        parent=None,
    ):
        super().__init__(parent)
        self._video_path = video_path
        self._video_duration = max(video_duration, 1.0)
        self._next_rank = next_rank
        self._clip_start: float = 0.0
        self._clip_end: float = min(30.0, self._video_duration)

        self.setWindowTitle("Create Manual Clip")
        self.setMinimumWidth(580)
        self.setStyleSheet("background: #181818; color: #ddd;")

        # ── Video player ──────────────────────────────────────────────────────
        self._player = VideoPlayer(self)
        self._player.setMinimumHeight(260)

        # ── Position slider ───────────────────────────────────────────────────
        pos_label = QLabel("Clip start position:")
        pos_label.setStyleSheet("font-size: 12px; color: #aaa;")

        self._pos_slider = QSlider(Qt.Orientation.Horizontal)
        max_start = max(0, int((self._video_duration - _MIN_DURATION) * 10))
        self._pos_slider.setRange(0, max_start)
        self._pos_slider.setValue(0)

        self._pos_ts_label = QLabel(_fmt_ts(0.0))
        self._pos_ts_label.setFixedWidth(70)
        self._pos_ts_label.setStyleSheet("font-size: 12px; color: #eee;")

        pos_row = QHBoxLayout()
        pos_row.addWidget(self._pos_slider)
        pos_row.addWidget(self._pos_ts_label)

        # ── Duration slider ───────────────────────────────────────────────────
        dur_label = QLabel("Clip duration:")
        dur_label.setStyleSheet("font-size: 12px; color: #aaa;")

        self._dur_slider = QSlider(Qt.Orientation.Horizontal)
        self._dur_slider.setRange(int(_MIN_DURATION), int(_MAX_DURATION))
        self._dur_slider.setValue(30)

        self._dur_val_label = QLabel("30s")
        self._dur_val_label.setFixedWidth(40)
        self._dur_val_label.setStyleSheet("font-size: 12px; color: #eee;")

        dur_row = QHBoxLayout()
        dur_row.addWidget(self._dur_slider)
        dur_row.addWidget(self._dur_val_label)

        # ── Clip window summary ───────────────────────────────────────────────
        self._window_label = QLabel()
        self._window_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._window_label.setStyleSheet(
            "font-size: 12px; color: #7ec8e3; padding: 4px; "
            "background: #1e1e2e; border-radius: 4px;"
        )
        self._compute_window()
        self._update_window_label()

        # ── Dialog buttons ────────────────────────────────────────────────────
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("Add Clip")
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
            "background:#2b5ea7;color:#fff;border:none;border-radius:4px;"
            "padding:5px 18px;font-size:13px;font-weight:bold;"
        )
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(
            "background:#2a2a2a;color:#ccc;border:1px solid #444;"
            "border-radius:4px;padding:5px 14px;font-size:12px;"
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)

        # ── Layout ────────────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(self._player)
        layout.addWidget(pos_label)
        layout.addLayout(pos_row)
        layout.addWidget(dur_label)
        layout.addLayout(dur_row)
        layout.addWidget(self._window_label)
        layout.addWidget(btn_box)

        # ── Connections ───────────────────────────────────────────────────────
        # valueChanged updates labels live while dragging
        self._pos_slider.valueChanged.connect(self._on_pos_value_changed)
        self._dur_slider.valueChanged.connect(self._on_dur_value_changed)
        # sliderReleased fires on both drag-release and click — reload player then
        self._pos_slider.sliderReleased.connect(self._reload_player)
        self._dur_slider.sliderReleased.connect(self._reload_player)

        # Load initial preview
        self._reload_player()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _compute_window(self) -> None:
        start = self._pos_slider.value() / 10.0
        dur = float(self._dur_slider.value())
        end = start + dur
        if end > self._video_duration:
            end = self._video_duration
            start = max(0.0, end - dur)
        self._clip_start = start
        self._clip_end = end

    def _update_window_label(self) -> None:
        dur = self._clip_end - self._clip_start
        self._window_label.setText(
            f"{_fmt_ts(self._clip_start)}  →  {_fmt_ts(self._clip_end)}   ({dur:.0f}s)"
        )

    def _on_pos_value_changed(self, value: int) -> None:
        """Update the timestamp label live as the slider moves."""
        self._pos_ts_label.setText(_fmt_ts(value / 10.0))
        self._compute_window()
        self._update_window_label()

    def _on_dur_value_changed(self, value: int) -> None:
        """Update the duration label live as the slider moves."""
        self._dur_val_label.setText(f"{value}s")
        self._compute_window()
        self._update_window_label()

    def _reload_player(self) -> None:
        """Seek the player to the current clip window and start playing."""
        self._compute_window()
        self._update_window_label()
        self._player.load(
            str(self._video_path),
            start_ms=int(self._clip_start * 1000),
            end_ms=int(self._clip_end * 1000),
            autoplay=True,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def clip_candidate(self) -> ClipCandidate:
        """Call after exec() == Accepted to retrieve the new ClipCandidate."""
        self._compute_window()
        mid = (self._clip_start + self._clip_end) / 2.0
        return ClipCandidate(
            rank=self._next_rank,
            start_time=self._clip_start,
            end_time=self._clip_end,
            transition_peak_time=mid,
            score=0.0,
            kept=True,
            is_manual=True,
        )
