from PyQt6.QtCore import QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from dj_clipper.ui.widgets.trim_bar import TrimBar

_EDIT_CTX_SECS = 180.0   # ±3 minutes of context in edit mode


def _fmt_time(ms: int) -> str:
    s = ms // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


class _AspectVideoWidget(QVideoWidget):
    """
    QVideoWidget that tells Qt's layout engine its preferred height so the
    allocated space always matches the video's native aspect ratio — no
    letterbox / black bars.  Defaults to 16:9; updates when metadata loads.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ratio = 9.0 / 16.0   # H/W ratio; updated from media metadata
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def update_ratio(self, w: int, h: int) -> None:
        if w > 0 and h > 0:
            self._ratio = h / w
            self.updateGeometry()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return max(120, int(width * self._ratio))

    def sizeHint(self) -> QSize:
        w = self.width() if self.width() > 10 else 640
        return QSize(w, self.heightForWidth(w))


class VideoPlayer(QWidget):
    """
    Embeddable video player with optional trim-edit mode.

    Normal mode
    -----------
    • load(path, start_ms, end_ms, autoplay=True) — loads a clip window
    • Slider scrubs within clip; auto-pauses at end_ms
    • "Edit Clip" button appears once a clip is loaded

    Edit mode  (entered via the Edit Clip button)
    ----------
    • Full ±3-min context loaded for scrubbing
    • iOS-style TrimBar shows draggable start/end handles
    • Apply / Cancel buttons; trim_applied(start_s, end_s) emitted on Apply

    Other
    -----
    • toggle_playback()  — for external spacebar binding
    """

    trim_applied = pyqtSignal(float, float)   # (new_start_s, new_end_s)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._start_ms: int  = 0
        self._end_ms:   int  = 0
        self._autoplay_on_load: bool = False
        self._in_edit_mode:     bool = False
        self._orig_start_ms:    int  = 0
        self._orig_end_ms:      int  = 0
        self._trim_start_s:     float = 0.0
        self._trim_end_s:       float = 0.0
        self._min_clip_s:       float = 15.0
        self._max_clip_s:       float = 60.0

        # ── Media engine ──────────────────────────────────────────────────
        self._player   = QMediaPlayer()
        self._audio    = QAudioOutput()
        self._player.setAudioOutput(self._audio)
        self._audio.setVolume(1.0)

        # ── Video surface ─────────────────────────────────────────────────
        self._video_widget = _AspectVideoWidget()
        self._player.setVideoOutput(self._video_widget)

        # ── Playback controls ─────────────────────────────────────────────
        self._play_btn  = QPushButton("▶")
        self._play_btn.setFixedWidth(36)
        self._stop_btn  = QPushButton("■")
        self._stop_btn.setFixedWidth(36)
        self._time_label = QLabel("--:-- / --:--")
        self._slider    = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 1000)

        for btn in (self._play_btn, self._stop_btn):
            btn.setStyleSheet(
                "background:#2a2a2a;color:#ccc;border:1px solid #444;"
                "border-radius:3px;font-size:13px;"
            )

        ctrl = QHBoxLayout()
        ctrl.setSpacing(6)
        ctrl.addWidget(self._play_btn)
        ctrl.addWidget(self._stop_btn)
        ctrl.addWidget(self._time_label)
        ctrl.addWidget(self._slider)

        # ── Normal-mode footer (Edit Clip button) ─────────────────────────
        self._edit_btn = QPushButton("✂  Edit Clip")
        self._edit_btn.setVisible(False)
        self._edit_btn.setStyleSheet(
            "background:#2a2a2a;color:#ccc;border:1px solid #444;"
            "border-radius:4px;padding:3px 10px;font-size:12px;"
        )
        normal_footer = QHBoxLayout()
        normal_footer.addStretch()
        normal_footer.addWidget(self._edit_btn)

        # ── Trim bar (edit mode) ──────────────────────────────────────────
        self._trim_bar = TrimBar()
        self._trim_bar.setVisible(False)

        # ── Lock button (edit mode, between trim bar and action bar) ──────
        self._lock_btn = QPushButton("🔒")
        self._lock_btn.setCheckable(True)
        self._lock_btn.setChecked(False)
        self._lock_btn.setVisible(False)
        self._lock_btn.setFixedSize(28, 28)
        self._lock_btn.setStyleSheet("""
            QPushButton {
                background: #2a2a2a; color: #aaa;
                border: 1px solid #444; border-radius: 4px;
                font-size: 14px; padding: 0;
            }
            QPushButton:hover { background: #333; color: #ddd; }
            QPushButton:checked {
                background: #3a2a1a; color: #f0b96e;
                border-color: #7a5a2a;
            }
            QPushButton:checked:hover { background: #4a3a2a; }
        """)
        self._lock_btn.toggled.connect(self._on_lock_toggled)

        # ── Edit action bar ───────────────────────────────────────────────
        self._cancel_trim_btn = QPushButton("Cancel")
        self._apply_trim_btn  = QPushButton("Apply")
        self._trim_info_label = QLabel("")
        self._trim_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._trim_info_label.setStyleSheet("color:#aaa;font-size:12px;")

        for btn, style in (
            (self._cancel_trim_btn,
             "background:#2a2a2a;color:#ccc;border:1px solid #444;"
             "border-radius:4px;padding:3px 12px;font-size:12px;"),
            (self._apply_trim_btn,
             "background:#2b5ea7;color:#fff;border:none;"
             "border-radius:4px;padding:3px 16px;font-size:12px;font-weight:bold;"),
        ):
            btn.setStyleSheet(style)

        edit_bar = QHBoxLayout()
        edit_bar.addWidget(self._cancel_trim_btn)
        edit_bar.addStretch()
        edit_bar.addWidget(self._trim_info_label)
        edit_bar.addStretch()
        edit_bar.addWidget(self._apply_trim_btn)

        self._edit_action_widget = QWidget()
        self._edit_action_widget.setLayout(edit_bar)
        self._edit_action_widget.setVisible(False)

        # ── Root layout ───────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._video_widget)
        layout.addLayout(ctrl)
        layout.addLayout(normal_footer)
        layout.addWidget(self._trim_bar)
        layout.addWidget(self._lock_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._edit_action_widget)

        # ── Connections ───────────────────────────────────────────────────
        self._play_btn.clicked.connect(self._on_play)
        self._stop_btn.clicked.connect(self._on_stop)
        self._slider.valueChanged.connect(self._on_slider_value_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)

        self._edit_btn.clicked.connect(self._on_edit_clicked)
        self._apply_trim_btn.clicked.connect(self._apply_trim)
        self._cancel_trim_btn.clicked.connect(self._cancel_trim)

        self._trim_bar.trim_start_changed.connect(self._on_trim_start_changed)
        self._trim_bar.trim_end_changed.connect(self._on_trim_end_changed)
        self._trim_bar.clip_bounds_committed.connect(self._on_clip_bounds_committed)
        # Click-to-preview: seek the player but don't change the clip window
        self._trim_bar.seek_requested.connect(
            lambda t: self._player.setPosition(int(t * 1000))
        )

        self.setStyleSheet("background: #111; color: #ccc;")

    # ── Public API ────────────────────────────────────────────────────────────

    def load(
        self,
        path: str,
        start_ms: int = 0,
        end_ms: int = 0,
        autoplay: bool = True,
        show_edit_btn: bool = True,
    ) -> None:
        """
        Load a clip segment.  Resets any ongoing edit session.
        Pass show_edit_btn=False to hide the Edit Clip button (e.g. manual clips).
        """
        if self._in_edit_mode:
            self._exit_edit_mode(restore=False)

        self._start_ms = start_ms
        self._end_ms   = end_ms if end_ms > start_ms else start_ms

        self._slider.blockSignals(True)
        self._slider.setValue(0)
        self._slider.blockSignals(False)
        self._update_time_label(start_ms)

        new_url = QUrl.fromLocalFile(path)
        if self._player.source() == new_url:
            self._autoplay_on_load = False
            self._player.setPosition(start_ms)
            if autoplay:
                self._player.play()
        else:
            self._autoplay_on_load = autoplay
            self._player.setSource(new_url)
            self._player.setPosition(start_ms)

        self._edit_btn.setVisible(show_edit_btn)

    def toggle_playback(self) -> None:
        """Toggle play/pause — call this from the spacebar shortcut."""
        self._on_play()

    def set_clip_limits(self, min_s: float, max_s: float) -> None:
        """Update min/max clip duration constraints for the trim bar."""
        self._min_clip_s = min_s
        self._max_clip_s = max_s
        if self._in_edit_mode:
            self._trim_bar.set_limits(min_s, max_s)

    def stop(self) -> None:
        self._player.stop()

    # ── Edit mode ─────────────────────────────────────────────────────────────

    def _on_edit_clicked(self) -> None:
        path = self._player.source().toLocalFile()
        if not path:
            return
        clip_start = self._start_ms / 1000.0
        clip_end   = self._end_ms   / 1000.0
        video_dur  = self._player.duration() / 1000.0
        if video_dur <= 0:
            video_dur = clip_end + _EDIT_CTX_SECS

        ctx_start = max(0.0, clip_start - _EDIT_CTX_SECS)
        ctx_end   = min(video_dur, clip_end + _EDIT_CTX_SECS)

        self._orig_start_ms = self._start_ms
        self._orig_end_ms   = self._end_ms
        self._trim_start_s  = clip_start
        self._trim_end_s    = clip_end
        self._in_edit_mode  = True

        # Show trim UI — _start_ms/_end_ms stay as the clip window so the
        # timeline slider always reflects the clip duration, not the context.
        self._edit_btn.setVisible(False)
        self._trim_bar.setup(ctx_start, ctx_end, clip_start, clip_end)
        self._max_clip_s = 60.0
        self._trim_bar.set_limits(self._min_clip_s, self._max_clip_s)
        self._trim_bar.setVisible(True)
        self._lock_btn.blockSignals(True)
        self._lock_btn.setChecked(False)
        self._lock_btn.blockSignals(False)
        self._lock_btn.setText("🔒")
        self._lock_btn.setVisible(True)
        self._edit_action_widget.setVisible(True)
        self._update_trim_info_label()
        self._player.setPosition(self._start_ms)
        self._player.play()

    def _exit_edit_mode(self, restore: bool) -> None:
        self._in_edit_mode = False
        self._trim_bar.setVisible(False)
        self._trim_bar.set_unlocked(False)
        self._lock_btn.setVisible(False)
        self._edit_action_widget.setVisible(False)
        self._edit_btn.setVisible(True)

        if restore:
            self._start_ms = self._orig_start_ms
            self._end_ms   = self._orig_end_ms
            self._player.setPosition(self._orig_start_ms)

    def _apply_trim(self) -> None:
        start_s = self._trim_bar.trim_start
        end_s   = self._trim_bar.trim_end
        self._exit_edit_mode(restore=False)
        # Update clip window to trimmed bounds
        self._start_ms = int(start_s * 1000)
        self._end_ms   = int(end_s   * 1000)
        self._player.setPosition(self._start_ms)
        self._player.play()
        self.trim_applied.emit(start_s, end_s)

    def _cancel_trim(self) -> None:
        self._exit_edit_mode(restore=True)
        self._player.play()

    def _on_lock_toggled(self, checked: bool) -> None:
        if checked:
            self._max_clip_s = float('inf')
            self._lock_btn.setText("🔓")
        else:
            self._max_clip_s = 60.0
            self._lock_btn.setText("🔒")
        self._trim_bar.set_limits(self._min_clip_s, self._max_clip_s)
        self._trim_bar.set_unlocked(checked)

    def _on_trim_start_changed(self, t: float) -> None:
        self._trim_start_s = t
        self._update_trim_info_label()

    def _on_trim_end_changed(self, t: float) -> None:
        self._trim_end_s = t
        self._update_trim_info_label()

    def _on_clip_bounds_committed(self, start_s: float, end_s: float) -> None:
        """
        Called when the user releases a trim handle or the whole bar.
        Update the player's clip window to the new boundaries and play from
        the new start so the preview immediately reflects the selection.
        """
        self._start_ms = int(start_s * 1000)
        self._end_ms   = int(end_s   * 1000)
        self._trim_start_s = start_s
        self._trim_end_s   = end_s
        self._slider.blockSignals(True)
        self._slider.setValue(0)
        self._slider.blockSignals(False)
        self._player.setPosition(self._start_ms)
        self._player.play()

    def _update_trim_info_label(self) -> None:
        dur = self._trim_bar.trim_end - self._trim_bar.trim_start
        self._trim_info_label.setText(f"Clip duration: {dur:.1f}s")

    # ── Playback controls ─────────────────────────────────────────────────────

    def _on_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            if self._player.position() >= self._end_ms:
                self._player.setPosition(self._start_ms)
            self._player.play()

    def _on_stop(self) -> None:
        self._player.stop()
        self._player.setPosition(self._start_ms)

    # ── Slider ────────────────────────────────────────────────────────────────

    def _on_slider_value_changed(self, value: int) -> None:
        if self._end_ms > self._start_ms:
            duration = self._end_ms - self._start_ms
            pos = self._start_ms + int(value / 1000 * duration)
        else:
            pos = self._start_ms
        self._player.setPosition(pos)
        if self._player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self._player.play()

    # ── Player signals ────────────────────────────────────────────────────────

    def _on_media_status_changed(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            if self._autoplay_on_load:
                self._autoplay_on_load = False
                self._player.setPosition(self._start_ms)
                self._player.play()
            # Update video widget aspect ratio from metadata
            try:
                from PyQt6.QtMultimedia import QMediaMetaData
                res = self._player.metaData().value(QMediaMetaData.Key.Resolution)
                if res and res.width() > 0:
                    self._video_widget.update_ratio(res.width(), res.height())
            except Exception:
                pass

    def _on_position_changed(self, pos_ms: int) -> None:
        self._update_time_label(pos_ms)
        if self._end_ms > self._start_ms:
            duration = self._end_ms - self._start_ms
            elapsed  = pos_ms - self._start_ms
            pct = max(0, min(1000, int(elapsed / duration * 1000)))
            self._slider.blockSignals(True)
            self._slider.setValue(pct)
            self._slider.blockSignals(False)
            # Auto-pause at end of clip (in both normal and edit mode)
            if pos_ms >= self._end_ms:
                self._player.pause()

        # Update trim bar playhead in edit mode
        if self._in_edit_mode:
            self._trim_bar.set_playhead(pos_ms / 1000.0)

    def _on_state_changed(self, state) -> None:
        self._play_btn.setText(
            "⏸" if state == QMediaPlayer.PlaybackState.PlayingState else "▶"
        )

    def _update_time_label(self, pos_ms: int) -> None:
        # _start_ms/_end_ms always reflect the clip window (even in edit mode),
        # so this label always shows elapsed/total for the current clip.
        elapsed = max(0, pos_ms - self._start_ms)
        total   = max(0, self._end_ms - self._start_ms)
        self._time_label.setText(f"{_fmt_time(elapsed)} / {_fmt_time(total)}")

    # ── Aspect ratio ──────────────────────────────────────────────────────────

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        video_h = self._video_widget.heightForWidth(width)
        # Add approximate height of controls below the video
        return video_h + 80
