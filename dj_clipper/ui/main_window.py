from PyQt6.QtWidgets import QMainWindow, QStackedWidget

from dj_clipper.models.session_model import SessionState
from dj_clipper.ui.import_panel import ImportPanel
from dj_clipper.ui.review_panel import ReviewPanel
from dj_clipper.ui.export_panel import ExportPanel


class MainWindow(QMainWindow):
    """
    Top-level window. Uses QStackedWidget to switch between three screens:
      0 — ImportPanel  (drop video + settings)
      1 — ReviewPanel  (clip grid + video preview)
      2 — ExportPanel  (output folder + progress log)
    """

    _IMPORT = 0
    _REVIEW = 1
    _EXPORT = 2

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DJ Clipper")
        self.setMinimumSize(1000, 660)

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._import_panel = ImportPanel()
        self._review_panel = ReviewPanel()
        self._export_panel = ExportPanel()

        self._stack.addWidget(self._import_panel)   # index 0
        self._stack.addWidget(self._review_panel)   # index 1
        self._stack.addWidget(self._export_panel)   # index 2

        # Wire navigation signals
        self._import_panel.analysis_complete.connect(self._go_to_review)
        self._review_panel.back_requested.connect(self._go_to_import)
        self._review_panel.export_requested.connect(self._go_to_export)
        self._export_panel.back_requested.connect(self._go_to_review_from_export)

        self._stack.setCurrentIndex(self._IMPORT)

        # Dark window chrome
        self.setStyleSheet("QMainWindow { background: #181818; }")

    def _go_to_review(self, session: SessionState) -> None:
        self._review_panel.load_session(session)
        self._stack.setCurrentIndex(self._REVIEW)

    def _go_to_export(self, session: SessionState) -> None:
        self._export_panel.load_session(session)
        self._stack.setCurrentIndex(self._EXPORT)

    def _go_to_import(self) -> None:
        self._stack.setCurrentIndex(self._IMPORT)

    def _go_to_review_from_export(self) -> None:
        # Return to review without re-running analysis; session is unchanged
        self._stack.setCurrentIndex(self._REVIEW)
