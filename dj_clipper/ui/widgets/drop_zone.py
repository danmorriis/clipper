from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import QLabel


class _BaseDropZone(QLabel):
    """Shared drag-and-drop styling and boilerplate."""

    def _apply_style(self, active: bool) -> None:
        border_color = "#4a9eff" if active else "#555"
        bg_color = "#1e2a3a" if active else "#1a1a1a"
        self.setStyleSheet(f"""
            QLabel {{
                border: 2px dashed {border_color};
                border-radius: 8px;
                background: {bg_color};
                color: #aaa;
                font-size: 14px;
            }}
        """)

    def dragLeaveEvent(self, event) -> None:
        self._apply_style(active=False)


class DropZone(_BaseDropZone):
    """
    Drag-and-drop target for a video file. Also opens a file dialog on click.
    Emits video_dropped(Path) when a valid video file is accepted.
    """

    video_dropped = pyqtSignal(Path)

    _VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".mts"}

    _DEFAULT_HTML = (
        '<span style="font-size:18px;font-weight:bold;color:#ddd;">Video</span>'
        '<br><span style="font-size:12px;color:#888;">Drop here or click to browse</span>'
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setText(self._DEFAULT_HTML)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self._apply_style(active=False)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and Path(urls[0].toLocalFile()).suffix.lower() in self._VIDEO_EXTENSIONS:
                event.acceptProposedAction()
                self._apply_style(active=True)
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        self._apply_style(active=False)
        urls = event.mimeData().urls()
        if urls:
            path = Path(urls[0].toLocalFile())
            if path.suffix.lower() in self._VIDEO_EXTENSIONS:
                loaded_html = (
                    f'<span style="font-size:18px;font-weight:bold;color:#ddd;">Video</span>'
                    f'<br><span style="font-size:11px;color:#7ec8e3;">✓ {path.name}</span>'
                )
                self.setText(loaded_html)
                self.video_dropped.emit(path)
                event.acceptProposedAction()
                return
        event.ignore()

    def mousePressEvent(self, event) -> None:
        from PyQt6.QtWidgets import QFileDialog
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Open DJ Video",
            "",
            "Video Files (*.mp4 *.mov *.avi *.mkv *.m4v *.mts);;All Files (*)",
        )
        if path_str:
            path = Path(path_str)
            loaded_html = (
                f'<span style="font-size:18px;font-weight:bold;color:#ddd;">Video</span>'
                f'<br><span style="font-size:11px;color:#7ec8e3;">✓ {path.name}</span>'
            )
            self.setText(loaded_html)
            self.video_dropped.emit(path)


class PlaylistDropZone(_BaseDropZone):
    """
    Drag-and-drop target for a playlist file (.m3u, .m3u8, .txt).
    Also opens a file dialog on click.
    Emits playlist_dropped(Path) when a valid playlist file is accepted.
    """

    playlist_dropped = pyqtSignal(Path)

    _PLAYLIST_EXTENSIONS = {".m3u", ".m3u8", ".txt"}

    _DEFAULT_HTML = (
        '<span style="font-size:18px;font-weight:bold;color:#ddd;">Playlist</span>'
        '<br><span style="font-size:12px;color:#888;">Drop .m3u8 or .txt here, or click to browse</span>'
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setText(self._DEFAULT_HTML)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self._apply_style(active=False)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and Path(urls[0].toLocalFile()).suffix.lower() in self._PLAYLIST_EXTENSIONS:
                event.acceptProposedAction()
                self._apply_style(active=True)
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        self._apply_style(active=False)
        urls = event.mimeData().urls()
        if urls:
            path = Path(urls[0].toLocalFile())
            if path.suffix.lower() in self._PLAYLIST_EXTENSIONS:
                loaded_html = (
                    f'<span style="font-size:18px;font-weight:bold;color:#ddd;">Playlist</span>'
                    f'<br><span style="font-size:11px;color:#7ec8e3;">✓ {path.name}</span>'
                )
                self.setText(loaded_html)
                self.playlist_dropped.emit(path)
                event.acceptProposedAction()
                return
        event.ignore()

    def mousePressEvent(self, event) -> None:
        from PyQt6.QtWidgets import QFileDialog
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Select Playlist",
            "",
            "Playlist files (*.m3u *.m3u8 *.txt);;All files (*)",
        )
        if path_str:
            path = Path(path_str)
            loaded_html = (
                f'<span style="font-size:18px;font-weight:bold;color:#ddd;">Playlist</span>'
                f'<br><span style="font-size:11px;color:#7ec8e3;">✓ {path.name}</span>'
            )
            self.setText(loaded_html)
            self.playlist_dropped.emit(path)
