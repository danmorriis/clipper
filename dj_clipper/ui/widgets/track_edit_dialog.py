"""
Small dialog for correcting the pre/post track labels on a ClipCandidate.
Opened from ClipCard when the user clicks the edit (✎) button.
"""

from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

_NONE_LABEL = "— Unknown / Clear —"


class TrackEditDialog(QDialog):
    """
    Two combo boxes (Track A → Track B) pre-populated from the resolved
    playlist.  Returns the chosen (pre, post) strings via result().
    """

    def __init__(
        self,
        track_names: List[str],
        current_pre: Optional[str],
        current_post: Optional[str],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit Track Labels")
        self.setMinimumWidth(340)
        self.setStyleSheet("background: #1e1e1e; color: #ddd;")

        options = [_NONE_LABEL] + track_names

        # ── Track A ───────────────────────────────────────────────────────────
        pre_label = QLabel("Track A  (playing before the transition):")
        pre_label.setStyleSheet("font-size: 12px; color: #aaa; margin-top: 4px;")

        self._pre_combo = QComboBox()
        self._pre_combo.addItems(options)
        self._pre_combo.setStyleSheet(
            "background:#2a2a2a;color:#eee;border:1px solid #444;"
            "border-radius:4px;padding:4px;font-size:12px;"
        )
        self._pre_combo.setCurrentIndex(
            options.index(current_pre) if current_pre in options else 0
        )

        # ── Track B ───────────────────────────────────────────────────────────
        post_label = QLabel("Track B  (playing after the transition):")
        post_label.setStyleSheet("font-size: 12px; color: #aaa; margin-top: 8px;")

        self._post_combo = QComboBox()
        self._post_combo.addItems(options)
        self._post_combo.setStyleSheet(
            "background:#2a2a2a;color:#eee;border:1px solid #444;"
            "border-radius:4px;padding:4px;font-size:12px;"
        )
        self._post_combo.setCurrentIndex(
            options.index(current_post) if current_post in options else 0
        )

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        btn_box.button(QDialogButtonBox.StandardButton.Save).setStyleSheet(
            "background:#2b5ea7;color:#fff;border:none;border-radius:4px;"
            "padding:5px 18px;font-size:12px;font-weight:bold;"
        )
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(
            "background:#2a2a2a;color:#ccc;border:1px solid #444;"
            "border-radius:4px;padding:5px 14px;font-size:12px;"
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(6)
        layout.addWidget(pre_label)
        layout.addWidget(self._pre_combo)
        layout.addWidget(post_label)
        layout.addWidget(self._post_combo)
        layout.addSpacing(8)
        layout.addWidget(btn_box)

    def result_tracks(self) -> Tuple[Optional[str], Optional[str]]:
        """Call after exec() == Accepted. Returns (pre_track, post_track); None = cleared."""
        pre = self._pre_combo.currentText()
        post = self._post_combo.currentText()
        return (
            None if pre == _NONE_LABEL else pre,
            None if post == _NONE_LABEL else post,
        )
