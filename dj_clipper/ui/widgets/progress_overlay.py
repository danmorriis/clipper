import threading

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)


class ProgressOverlay(QDialog):
    """
    Modal progress dialog shown during long-running worker tasks.
    Cancel button sets the shared cancel_event so workers can exit gracefully.
    """

    def __init__(self, title: str, cancel_event: threading.Event, parent=None):
        super().__init__(parent)
        self._cancel_event = cancel_event

        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        self._status_label = QLabel("Starting…")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet("color: #ccc; font-size: 13px;")

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 4px;
                background: #1a1a1a;
                text-align: center;
                color: #ccc;
            }
            QProgressBar::chunk {
                background: #4a9eff;
                border-radius: 3px;
            }
        """)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(100)
        self._cancel_btn.clicked.connect(self._on_cancel)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(self._status_label)
        layout.addWidget(self._bar)
        layout.addWidget(self._cancel_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setStyleSheet("background: #222;")

    def update_progress(self, percent: int, message: str) -> None:
        self._bar.setValue(percent)
        self._status_label.setText(message)

    def _on_cancel(self) -> None:
        self._cancel_event.set()
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText("Cancelling…")
        self._status_label.setText("Cancelling — please wait…")
