"""
N-option sliding toggle (iOS-style pill).

Usage:
    toggle = SlidingToggle(["Top # Clips", "All Transitions", "Specific Times"])
    toggle.toggled.connect(lambda idx: ...)
"""

from typing import List

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import QWidget


class SlidingToggle(QWidget):
    """
    A pill-shaped toggle that slides between N labelled options.
    Emits toggled(int) with the index of the selected option.
    Click anywhere in an option's section to select it.
    """

    toggled = pyqtSignal(int)

    def __init__(self, options: List[str], parent=None):
        super().__init__(parent)
        self._options = options
        self._n = len(options)
        self._index = 0
        self._slide = 0.0   # animation position: 0.0 → n-1

        self.setFixedHeight(34)
        self.setFixedWidth(max(220, self._n * 100))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._anim = QPropertyAnimation(self, b"slide_pos", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    # ── Qt property (drives the animation) ───────────────────────────────────

    def _get_slide(self) -> float:
        return self._slide

    def _set_slide(self, value: float) -> None:
        self._slide = value
        self.update()

    slide_pos = pyqtProperty(float, fget=_get_slide, fset=_set_slide)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def current_index(self) -> int:
        return self._index

    # ── Events ────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        section_w = self.width() / self._n
        new_idx = int(event.position().x() / section_w)
        new_idx = max(0, min(self._n - 1, new_idx))
        if new_idx != self._index:
            self._index = new_idx
            self._anim.stop()
            self._anim.setStartValue(self._slide)
            self._anim.setEndValue(float(new_idx))
            self._anim.start()
            self.toggled.emit(new_idx)
        super().mousePressEvent(event)

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        from PyQt6.QtCore import QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        section_w = w / self._n
        r = h / 2.0

        # Outer track
        track = QPainterPath()
        track.addRoundedRect(0, 0, w, h, r, r)
        p.setPen(QColor("#383838"))
        p.setBrush(QColor("#252525"))
        p.drawPath(track)

        # Sliding pill (occupies one section)
        margin = 3.0
        pill_w = section_w - margin * 2
        pill_x = margin + self._slide * section_w
        pill = QPainterPath()
        pill.addRoundedRect(pill_x, margin, pill_w, h - margin * 2,
                            r - margin, r - margin)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2b5ea7"))
        p.drawPath(pill)

        # Labels — brightness fades by distance from the pill centre
        font = self.font()
        font.setPointSize(10)
        font.setBold(True)
        p.setFont(font)

        for i, label in enumerate(self._options):
            dist = abs(self._slide - i)
            brightness = int(255 * max(0.35, 1.0 - dist * 0.65))
            p.setPen(QColor(brightness, brightness, brightness))
            p.drawText(
                QRectF(i * section_w, 0, section_w, h),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )

        p.end()
