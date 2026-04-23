import threading
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from dj_clipper.config import THUMBNAIL_SEEK_OFFSET
from dj_clipper.core.clip_exporter import extract_thumbnail
from dj_clipper.models.clip_model import ClipCandidate
from dj_clipper.models.session_model import SessionState
from dj_clipper.workers.thumbnail_worker import ThumbnailWorker
from dj_clipper.ui.widgets.clip_card import ClipCard
from dj_clipper.ui.widgets.video_player import VideoPlayer
from dj_clipper.ui.widgets.manual_clip_dialog import ManualClipDialog


def _fmt_ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:01d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


class _AddClipTile(QFrame):
    """The '+' card in the grid that opens the manual clip dialog."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(160)
        self.setMinimumHeight(120)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            _AddClipTile {
                background: #1a1a1a;
                border: 2px dashed #444;
                border-radius: 6px;
            }
        """)
        plus = QLabel("+")
        plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus.setStyleSheet("font-size: 40px; color: #555;")
        lbl = QLabel("Add Custom Clip")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("font-size: 10px; color: #555;")
        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(plus)
        layout.addWidget(lbl)
        layout.addStretch()

    def enterEvent(self, event):
        self.setStyleSheet("""
            _AddClipTile {
                background: #1e1e1e;
                border: 2px dashed #4a9eff;
                border-radius: 6px;
            }
        """)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet("""
            _AddClipTile {
                background: #1a1a1a;
                border: 2px dashed #444;
                border-radius: 6px;
            }
        """)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class ReviewPanel(QWidget):
    """
    Screen 2: scrollable clip card grid on the left + video player on the right.

    Features
    --------
    • Spacebar toggles play/pause on the video player
    • "Generate N more" appends clips to the end without re-sorting or re-ranking
    • "+" tile opens ManualClipDialog
    • Edit-clip trim bar inside the video player (iOS-style)
    • "X selected" header counts kept clips in real time
    """

    back_requested   = pyqtSignal()
    export_requested = pyqtSignal(object)  # SessionState

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session: Optional[SessionState] = None
        self._cards: Dict[int, ClipCard] = {}   # rank → card
        self._selected_card: Optional[ClipCard] = None
        self._cancel_event: threading.Event = threading.Event()
        self._next_all_idx: int = 0

        self.setStyleSheet("background: #181818; color: #ddd;")

        # ── Spacebar shortcut ──────────────────────────────────────────────
        spacebar = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        spacebar.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        spacebar.activated.connect(lambda: self._player.toggle_playback())

        # ── Top bar ────────────────────────────────────────────────────────
        self._back_btn = QPushButton("← Back")
        self._back_btn.setFixedWidth(90)
        self._back_btn.clicked.connect(self._on_back)

        self._clip_count_label = QLabel("Clips")
        self._clip_count_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #eee;"
        )

        self._selection_label = QLabel("")
        self._selection_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #9ef09e;"
        )

        self._keep_all_btn = QPushButton("Keep All")
        self._keep_all_btn.clicked.connect(self._on_keep_all)
        self._bin_all_btn  = QPushButton("Bin All")
        self._bin_all_btn.clicked.connect(self._on_bin_all)

        self._gen_more_btn = QPushButton("Generate 5 more")
        self._gen_more_btn.setEnabled(False)
        self._gen_more_btn.setStyleSheet("""
            QPushButton {
                background: #2a3a1a; color: #9ef09e;
                border: 1px solid #4a7a2a; border-radius: 5px;
                padding: 4px 10px; font-size: 12px;
            }
            QPushButton:disabled { background: #2a2a2a; color: #555; border-color: #333; }
            QPushButton:hover:enabled { background: #3a5a2a; }
        """)
        self._gen_more_btn.clicked.connect(self._on_generate_more)

        self._export_btn = QPushButton("Export →")
        self._export_btn.setEnabled(False)
        self._export_btn.setFixedHeight(36)
        self._export_btn.setStyleSheet("""
            QPushButton {
                background: #2b5ea7; color: #fff;
                border: none; border-radius: 5px;
                font-size: 14px; font-weight: bold; padding: 0 16px;
            }
            QPushButton:disabled { background: #333; color: #666; }
            QPushButton:hover:enabled { background: #3a74cc; }
        """)
        self._export_btn.clicked.connect(self._on_export)

        top_bar = QHBoxLayout()
        top_bar.addWidget(self._back_btn)
        top_bar.addWidget(self._clip_count_label)
        top_bar.addSpacing(12)
        top_bar.addWidget(self._selection_label)
        top_bar.addStretch()
        top_bar.addWidget(self._gen_more_btn)
        top_bar.addWidget(self._keep_all_btn)
        top_bar.addWidget(self._bin_all_btn)
        top_bar.addSpacing(16)
        top_bar.addWidget(self._export_btn)

        # ── Left: clip card scroll area ────────────────────────────────────
        self._card_container = QWidget()
        self._card_layout    = _TwoColumnLayout(self._card_container)
        self._card_container.setStyleSheet("background: #1a1a1a;")

        scroll = QScrollArea()
        scroll.setWidget(self._card_container)
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(380)
        scroll.setStyleSheet("background: #1a1a1a; border: none;")

        self._add_tile = _AddClipTile()
        self._add_tile.clicked.connect(self._on_add_manual_clip)

        # ── Right: video player + clip info ────────────────────────────────
        self._player = VideoPlayer()
        self._player.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._player.trim_applied.connect(self._on_trim_applied)

        self._clip_info_label = QLabel("Select a clip to preview")
        self._clip_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._clip_info_label.setStyleSheet("color: #888; font-size: 13px;")

        right_col = QVBoxLayout()
        right_col.addWidget(self._player)
        right_col.addWidget(self._clip_info_label)
        right_col.addStretch()

        # ── Main layout ────────────────────────────────────────────────────
        content = QHBoxLayout()
        content.addWidget(scroll)
        content.addLayout(right_col)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        root.addLayout(top_bar)
        root.addLayout(content)

        for btn in (self._back_btn, self._keep_all_btn, self._bin_all_btn):
            self._apply_btn_style(btn)

    def _apply_btn_style(self, btn: QPushButton) -> None:
        btn.setStyleSheet("""
            QPushButton {
                background: #2a2a2a; color: #ccc;
                border: 1px solid #444; border-radius: 5px;
                padding: 4px 10px; font-size: 13px;
            }
            QPushButton:hover { background: #333; }
        """)

    # ── Grid helpers ──────────────────────────────────────────────────────────

    def _place_add_tile(self) -> None:
        count = self._card_layout._count
        row, col = divmod(count, 2)
        self._card_layout._grid.addWidget(self._add_tile, row, col)
        self._add_tile.setParent(self._card_container)
        self._add_tile.show()

    def _remove_add_tile(self) -> None:
        self._card_layout._grid.removeWidget(self._add_tile)
        self._add_tile.hide()

    # ── Session loading ───────────────────────────────────────────────────────

    def load_session(self, session: SessionState) -> None:
        self._session = session
        self._cards.clear()
        self._selected_card = None
        self._cancel_event  = threading.Event()
        self._next_all_idx  = len(session.candidates)

        self._remove_add_tile()
        while self._card_layout.count():
            item = self._card_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        self._clip_count_label.setText(f"{len(session.candidates)} Clips")
        self._export_btn.setEnabled(False)

        for candidate in session.candidates:
            self._add_card(candidate)

        self._place_add_tile()
        self._update_generate_more_btn()
        self._update_selection_label()
        self._update_export_btn()
        self._start_thumbnail_worker()

    def _add_card(self, candidate: ClipCandidate) -> ClipCard:
        """Create a card for the candidate, wire its signals, add to grid."""
        card = ClipCard(
            candidate,
            video_duration=self._session.video_duration,
            track_names=self._session.resolved_track_names,
        )
        card.selected.connect(self._on_card_selected)
        card.kept_changed.connect(self._on_kept_changed)
        self._cards[candidate.rank] = card
        self._card_layout.addWidget(card)
        return card

    # ── Generate more ─────────────────────────────────────────────────────────

    def _on_generate_more(self) -> None:
        if not self._session:
            return
        more = self._session.all_candidates[
            self._next_all_idx: self._next_all_idx + 5
        ]
        if not more:
            return
        self._next_all_idx += len(more)

        # Assign sequential ranks continuing from the current highest —
        # do NOT re-sort or re-rank existing clips.
        next_rank = max(self._cards.keys(), default=0) + 1
        for i, c in enumerate(more):
            c.rank = next_rank + i
            self._session.candidates.append(c)

        self._remove_add_tile()
        for candidate in more:
            self._add_card(candidate)
        self._place_add_tile()

        self._update_generate_more_btn()
        self._clip_count_label.setText(
            f"{len(self._session.candidates)} Clips"
        )
        self._update_export_btn()
        self._update_selection_label()
        self._start_thumbnail_worker()

    def _rebuild_cards(self) -> None:
        """Full rebuild (used after back-navigation or session reload)."""
        self._remove_add_tile()
        self._selected_card = None
        while self._card_layout.count():
            item = self._card_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        for candidate in self._session.candidates:
            card = self._add_card(candidate)
            if candidate.thumbnail_path and candidate.thumbnail_path.exists():
                card.update_thumbnail(str(candidate.thumbnail_path))

        self._place_add_tile()
        self._start_thumbnail_worker()

    def _start_thumbnail_worker(self) -> None:
        if not self._session:
            return
        pending = [
            c for c in self._session.candidates
            if not (c.thumbnail_path and c.thumbnail_path.exists())
        ]
        if not pending:
            return
        from dj_clipper.models.session_model import SessionState as _SS
        proxy = _SS.__new__(_SS)
        proxy.__dict__.update(self._session.__dict__)
        proxy.candidates = pending
        worker = ThumbnailWorker(proxy, self._cancel_event)
        worker.signals.thumbnail_ready.connect(self._on_thumbnail_ready)
        from PyQt6.QtCore import QThreadPool
        QThreadPool.globalInstance().start(worker)

    def _update_generate_more_btn(self) -> None:
        if (
            not self._session
            or self._session.settings.clip_all
            or self._session.settings.manual_timestamps
        ):
            self._gen_more_btn.setVisible(False)
            return
        remaining = len(self._session.all_candidates) - self._next_all_idx
        if remaining > 0:
            n = min(5, remaining)
            self._gen_more_btn.setText(f"Generate {n} more")
            self._gen_more_btn.setVisible(True)
            self._gen_more_btn.setEnabled(True)
        else:
            self._gen_more_btn.setVisible(False)

    # ── Manual clip ───────────────────────────────────────────────────────────

    def _on_add_manual_clip(self) -> None:
        if not self._session:
            return
        next_rank = max(self._cards.keys(), default=0) + 1
        dialog = ManualClipDialog(
            self._session.video_path,
            self._session.video_duration,
            next_rank,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            candidate = dialog.clip_candidate()
            self._session.candidates.append(candidate)
            self._remove_add_tile()
            card = self._add_card(candidate)
            self._place_add_tile()
            self._clip_count_label.setText(
                f"{len(self._session.candidates)} Clips"
            )
            self._update_export_btn()
            self._update_selection_label()
            self._generate_manual_thumbnail(candidate, card)

    def _generate_manual_thumbnail(
        self, candidate: ClipCandidate, card: ClipCard
    ) -> None:
        from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal as _sig

        session = self._session

        class _Signals(QObject):
            done = _sig(int, str)

        class _Worker(QRunnable):
            def __init__(self, signals):
                super().__init__()
                self.signals = signals

            def run(self):
                try:
                    thumb_dir = session.session_temp_dir / "thumbnails"
                    thumb_dir.mkdir(parents=True, exist_ok=True)
                    seek = candidate.start_time + THUMBNAIL_SEEK_OFFSET
                    path = thumb_dir / f"thumb_{candidate.rank:03d}.jpg"
                    extract_thumbnail(
                        video_path=session.video_path,
                        time_seconds=seek,
                        output_path=path,
                    )
                    candidate.thumbnail_path = path
                    self.signals.done.emit(candidate.rank, str(path))
                except Exception:
                    pass

        signals = _Signals()
        signals.done.connect(self._on_thumbnail_ready)
        worker = _Worker(signals)
        QThreadPool.globalInstance().start(worker)

    # ── Card interaction ──────────────────────────────────────────────────────

    def _on_thumbnail_ready(self, rank: int, path: str) -> None:
        card = self._cards.get(rank)
        if card:
            card.update_thumbnail(path)

    def _on_card_selected(self, candidate: ClipCandidate) -> None:
        if self._selected_card:
            self._selected_card.set_selected(False)
        card = self._cards.get(candidate.rank)
        if card:
            card.set_selected(True)
            self._selected_card = card

        if self._session:
            self._player.load(
                str(self._session.video_path),
                start_ms=int(candidate.start_time * 1000),
                end_ms=int(candidate.end_time * 1000),
                show_edit_btn=not candidate.is_manual,
            )

        self._clip_info_label.setText(
            f"Clip {candidate.rank}  —  "
            f"@ {_fmt_ts(candidate.start_time)}  |  "
            f"{candidate.end_time - candidate.start_time:.0f}s"
        )

        self._update_export_btn()

    def _on_trim_applied(self, start_s: float, end_s: float) -> None:
        """Update the candidate when the user applies a trim in the player."""
        if not self._selected_card:
            return
        cand = self._selected_card.candidate
        cand.start_time = start_s
        cand.end_time   = end_s
        self._selected_card.refresh()
        self._clip_info_label.setText(
            f"Clip {cand.rank}  —  "
            f"@ {_fmt_ts(start_s)}  |  {end_s - start_s:.0f}s"
        )

    def _on_kept_changed(self) -> None:
        self._update_selection_label()
        self._update_export_btn()

    def _on_keep_all(self) -> None:
        for card in self._cards.values():
            card.candidate.kept = True
            card._update_toggle_style()
        self._update_selection_label()
        self._update_export_btn()

    def _on_bin_all(self) -> None:
        for card in self._cards.values():
            card.candidate.kept = False
            card._update_toggle_style()
        self._update_selection_label()
        self._update_export_btn()

    def _update_selection_label(self) -> None:
        if not self._session:
            self._selection_label.setText("")
            return
        n = sum(1 for c in self._session.candidates if c.kept)
        self._selection_label.setText(f"{n} selected" if n else "0 selected")

    def _update_export_btn(self) -> None:
        if self._session:
            has_kept = any(c.kept for c in self._session.candidates)
            self._export_btn.setEnabled(has_kept)

    def _on_export(self) -> None:
        self._player.stop()
        self.export_requested.emit(self._session)

    def _on_back(self) -> None:
        reply = QMessageBox.question(
            self,
            "Go Back?",
            "Going back will clear the current analysis. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._cancel_event.set()
            self._player.stop()
            self.back_requested.emit()


class _TwoColumnLayout:
    """Two-column grid layout helper."""

    def __init__(self, parent: QWidget):
        from PyQt6.QtWidgets import QGridLayout
        self._grid  = QGridLayout(parent)
        self._grid.setContentsMargins(8, 8, 8, 8)
        self._grid.setSpacing(8)
        self._count = 0

    def addWidget(self, widget: QWidget) -> None:
        row, col = divmod(self._count, 2)
        self._grid.addWidget(widget, row, col)
        self._count += 1

    def count(self) -> int:
        return self._count

    def takeAt(self, index: int):
        item = self._grid.itemAt(index)
        if item:
            self._grid.removeItem(item)
            self._count = max(0, self._count - 1)
        return item
