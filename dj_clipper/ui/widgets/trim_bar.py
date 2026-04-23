"""
iOS-style clip trim bar with draggable start/end handles.

Layout (70 px tall):
  ┌─────────────────────────────────────────────────────────────────┐ ← 0
  │ 0:09:45 (context start)            0:15:15 (context end) small │ ← top labels
  │  [▐ dim ▌][====== selected clip region ======][▐ dim ▌]        │ ← bar
  │           0:12:10                  0:12:55                      │ ← handle labels
  └─────────────────────────────────────────────────────────────────┘ ← 70

Call setup() to configure the context window and initial handle positions.
Call set_limits(min_s, max_s) to update duration constraints.
"""

from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import QWidget

_BAR_TOP  = 14.0   # y-offset of the main bar (leaves room for context labels above)
_BAR_H    = 34.0   # height of the bar rectangle
_HANDLE_W = 14.0   # handle width in pixels
_HIT_R    = 20     # mouse hit radius for handle detection (px)

_DEFAULT_MIN_CLIP = 15.0   # seconds
_DEFAULT_MAX_CLIP = 60.0   # seconds


def _fmt_ts(t: float) -> str:
    s = int(t)
    return f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


class TrimBar(QWidget):
    """
    Horizontal trim bar for editing clip boundaries.

    Signals
    -------
    trim_start_changed(float)       emitted continuously while dragging start handle
    trim_end_changed(float)         emitted continuously while dragging end handle
    seek_requested(float)           emitted on click outside the clip region (preview)
    clip_bounds_committed(float, float)  emitted on any drag release (new start, end)
    """

    trim_start_changed    = pyqtSignal(float)
    trim_end_changed      = pyqtSignal(float)
    seek_requested        = pyqtSignal(float)
    clip_bounds_committed = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx_start:  float = 0.0
        self._ctx_end:    float = 100.0
        self._trim_start: float = 10.0
        self._trim_end:   float = 55.0
        self._playhead:   float = 10.0
        self._min_clip:   float = _DEFAULT_MIN_CLIP
        self._max_clip:   float = _DEFAULT_MAX_CLIP

        self._drag: str | None = None
        self._drag_origin_t:     float = 0.0
        self._drag_origin_start: float = 0.0
        self._drag_origin_end:   float = 0.0
        self._unlocked: bool = False

        self.setFixedHeight(70)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ── Public API ────────────────────────────────────────────────────────────

    def setup(
        self,
        ctx_start: float,
        ctx_end: float,
        trim_start: float,
        trim_end: float,
    ) -> None:
        self._ctx_start  = ctx_start
        self._ctx_end    = ctx_end
        self._trim_start = trim_start
        self._trim_end   = trim_end
        self._playhead   = trim_start
        self.update()

    def set_limits(self, min_clip: float, max_clip: float) -> None:
        self._min_clip = min_clip
        self._max_clip = max_clip
        self.update()

    def set_unlocked(self, unlocked: bool) -> None:
        self._unlocked = unlocked
        self.update()

    def set_playhead(self, t: float) -> None:
        self._playhead = max(self._ctx_start, min(self._ctx_end, t))
        self.update()

    @property
    def trim_start(self) -> float:
        return self._trim_start

    @property
    def trim_end(self) -> float:
        return self._trim_end

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def _t_to_x(self, t: float) -> float:
        span = self._ctx_end - self._ctx_start
        if span <= 0:
            return _HANDLE_W / 2
        usable = self.width() - _HANDLE_W
        frac = (t - self._ctx_start) / span
        return _HANDLE_W / 2 + frac * usable

    def _x_to_t(self, x: float) -> float:
        usable = self.width() - _HANDLE_W
        if usable <= 0:
            return self._ctx_start
        frac = (x - _HANDLE_W / 2) / usable
        t = self._ctx_start + frac * (self._ctx_end - self._ctx_start)
        return max(self._ctx_start, min(self._ctx_end, t))

    # ── Mouse events ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        x = event.position().x()
        sx = self._t_to_x(self._trim_start)
        ex = self._t_to_x(self._trim_end)
        ds = abs(x - sx)
        de = abs(x - ex)
        if ds < _HIT_R and ds <= de:
            self._drag = 'start'
        elif de < _HIT_R:
            self._drag = 'end'
        elif sx <= x <= ex:
            self._drag = 'bar'
            self._drag_origin_t     = self._x_to_t(x)
            self._drag_origin_start = self._trim_start
            self._drag_origin_end   = self._trim_end
        else:
            self.seek_requested.emit(self._x_to_t(x))

    def mouseMoveEvent(self, event) -> None:
        if self._drag is None:
            return
        t = self._x_to_t(event.position().x())

        if self._drag == 'start':
            # Clamp: respect context, min gap, and max clip length
            min_t = max(self._ctx_start, self._trim_end - self._max_clip)
            max_t = self._trim_end - self._min_clip
            t = max(min_t, min(max_t, t))
            self._trim_start = t
            self.trim_start_changed.emit(t)

        elif self._drag == 'end':
            # Clamp: respect context, min gap, and max clip length
            min_t = self._trim_start + self._min_clip
            max_t = min(self._ctx_end, self._trim_start + self._max_clip)
            t = max(min_t, min(max_t, t))
            self._trim_end = t
            self.trim_end_changed.emit(t)

        elif self._drag == 'bar':
            duration  = self._drag_origin_end - self._drag_origin_start
            delta     = t - self._drag_origin_t
            new_start = self._drag_origin_start + delta
            new_start = max(self._ctx_start, min(self._ctx_end - duration, new_start))
            new_end   = new_start + duration
            self._trim_start = new_start
            self._trim_end   = new_end
            self.trim_start_changed.emit(new_start)
            self.trim_end_changed.emit(new_end)

        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag in ('start', 'end', 'bar'):
            self.clip_bounds_committed.emit(self._trim_start, self._trim_end)
        self._drag = None

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w  = float(self.width())
        sx = self._t_to_x(self._trim_start)
        ex = self._t_to_x(self._trim_end)

        # ── Context boundary labels (top, at far left and right) ───────────
        font_small = self.font()
        font_small.setPointSize(9)
        p.setFont(font_small)
        p.setPen(QColor("#cccccc"))
        ctx_label_y  = 1.0
        ctx_label_h  = 11.0
        ctx_label_w  = 70.0

        p.drawText(
            QRectF(0, ctx_label_y, ctx_label_w, ctx_label_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            _fmt_ts(self._ctx_start),
        )
        p.drawText(
            QRectF(w - ctx_label_w, ctx_label_y, ctx_label_w, ctx_label_h),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            _fmt_ts(self._ctx_end),
        )

        # ── Full track background ──────────────────────────────────────────
        p.setPen(Qt.PenStyle.NoPen)
        track = QPainterPath()
        track.addRoundedRect(0, _BAR_TOP, w, _BAR_H, 5, 5)
        p.setBrush(QColor("#222222"))
        p.drawPath(track)

        # ── Selected clip region (between handles) ─────────────────────────
        clip_rect = QPainterPath()
        clip_rect.addRect(sx, _BAR_TOP, ex - sx, _BAR_H)
        p.setBrush(QColor("#703a1e") if self._unlocked else QColor("#1e3f70"))
        p.drawPath(clip_rect)

        # ── Dim overlays for outside-clip regions ──────────────────────────
        p.setBrush(QColor(0, 0, 0, 150))
        if sx > 0:
            left = QPainterPath()
            left.addRoundedRect(0, _BAR_TOP, sx, _BAR_H, 5, 5)
            p.drawPath(left)
        if ex < w:
            right = QPainterPath()
            right.addRoundedRect(ex, _BAR_TOP, w - ex, _BAR_H, 5, 5)
            p.drawPath(right)

        # ── Border around selected region ──────────────────────────────────
        p.setPen(QColor("#ff9a4a") if self._unlocked else QColor("#4a9eff"))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(sx, _BAR_TOP, ex - sx, _BAR_H))

        # ── Handles ────────────────────────────────────────────────────────
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffffff"))
        hw = _HANDLE_W
        lh = QPainterPath()
        lh.addRoundedRect(sx - hw / 2, _BAR_TOP, hw, _BAR_H, 4, 4)
        p.drawPath(lh)
        rh = QPainterPath()
        rh.addRoundedRect(ex - hw / 2, _BAR_TOP, hw, _BAR_H, 4, 4)
        p.drawPath(rh)

        # ── Grip dots on handles ───────────────────────────────────────────
        p.setBrush(QColor("#666"))
        mid_y = _BAR_TOP + _BAR_H / 2
        for dy in (-5.0, 0.0, 5.0):
            p.drawEllipse(QRectF(sx - 2, mid_y + dy - 1.5, 4, 3))
            p.drawEllipse(QRectF(ex - 2, mid_y + dy - 1.5, 4, 3))

        # ── Playhead ───────────────────────────────────────────────────────
        if self._ctx_start <= self._playhead <= self._ctx_end:
            ph_x = self._t_to_x(self._playhead)
            p.setBrush(QColor("#ffffff"))
            p.setPen(Qt.PenStyle.NoPen)
            tri = QPainterPath()
            tri.moveTo(ph_x - 4, _BAR_TOP - 2)
            tri.lineTo(ph_x + 4, _BAR_TOP - 2)
            tri.lineTo(ph_x, _BAR_TOP + 6)
            tri.closeSubpath()
            p.drawPath(tri)
            p.setPen(QColor(255, 255, 255, 200))
            p.drawLine(int(ph_x), int(_BAR_TOP + 6), int(ph_x), int(_BAR_TOP + _BAR_H))

        # ── Handle timestamp labels (bottom) ───────────────────────────────
        font_lbl = self.font()
        font_lbl.setPointSize(8)
        p.setFont(font_lbl)
        p.setPen(QColor("#aaaaaa"))

        lbl_y = _BAR_TOP + _BAR_H + 4
        lbl_h = 12.0
        lbl_w = 64.0

        # Start handle label (clamped to widget)
        lx = max(0.0, min(sx - lbl_w / 2, w - lbl_w))
        p.drawText(
            QRectF(lx, lbl_y, lbl_w, lbl_h),
            Qt.AlignmentFlag.AlignCenter,
            _fmt_ts(self._trim_start),
        )

        # End handle label (avoid overlapping start label)
        rx = max(lx + lbl_w + 4, min(ex - lbl_w / 2, w - lbl_w))
        p.drawText(
            QRectF(rx, lbl_y, lbl_w, lbl_h),
            Qt.AlignmentFlag.AlignCenter,
            _fmt_ts(self._trim_end),
        )

        p.end()
