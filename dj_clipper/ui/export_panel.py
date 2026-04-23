import shutil
import subprocess
import threading
from datetime import date
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dj_clipper.config import TEMP_DIR
from dj_clipper.models.clip_model import TrackMatch
from dj_clipper.models.session_model import SessionState
from dj_clipper.workers.export_worker import ExportWorker
from dj_clipper.ui.widgets.progress_overlay import ProgressOverlay


class ExportPanel(QWidget):
    """Screen 3: output folder, export progress log, track ID results."""

    back_requested = pyqtSignal()
    export_complete = pyqtSignal(object)  # SessionState

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session: Optional[SessionState] = None
        self._cancel_event: Optional[threading.Event] = None
        self._overlay: Optional[ProgressOverlay] = None

        self.setStyleSheet("background: #181818; color: #ddd;")

        # ── Top bar ──
        back_btn = QPushButton("← Back")
        back_btn.setFixedWidth(90)
        back_btn.clicked.connect(self.back_requested)
        back_btn.setStyleSheet(
            "background:#2a2a2a;color:#ccc;border:1px solid #444;"
            "border-radius:5px;padding:4px 10px;font-size:13px;"
        )

        clear_btn = QPushButton("Clear Temp Files")
        clear_btn.setFixedWidth(130)
        clear_btn.setStyleSheet(
            "background:#3a2a2a;color:#f09e9e;border:1px solid #664444;"
            "border-radius:5px;padding:4px 10px;font-size:12px;"
        )
        clear_btn.clicked.connect(self._on_clear_temp)

        top_bar = QHBoxLayout()
        top_bar.addWidget(back_btn)
        top_bar.addStretch()
        top_bar.addWidget(clear_btn)

        # ── Output folder ──
        out_label = QLabel("Output folder:")
        out_label.setStyleSheet("font-size: 13px;")

        default_out = Path.home() / "Desktop" / f"DJ_Clips_{date.today().isoformat()}"
        self._out_edit = QLineEdit(str(default_out))
        self._out_edit.setStyleSheet(
            "background:#222;color:#ddd;border:1px solid #444;border-radius:4px;padding:4px;"
        )
        out_browse = QPushButton("Browse")
        out_browse.setFixedWidth(80)
        out_browse.setStyleSheet(
            "background:#2a2a2a;color:#ccc;border:1px solid #444;"
            "border-radius:4px;padding:4px;font-size:12px;"
        )
        out_browse.clicked.connect(self._browse_output)

        out_row = QHBoxLayout()
        out_row.addWidget(self._out_edit)
        out_row.addWidget(out_browse)

        # ── Export button ──
        self._export_btn = QPushButton("Export Clips")
        self._export_btn.setFixedHeight(42)
        self._export_btn.setStyleSheet("""
            QPushButton {
                background: #2b5ea7;
                color: #fff;
                border: none;
                border-radius: 6px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton:hover { background: #3a74cc; }
            QPushButton:disabled { background: #333; color: #666; }
        """)
        self._export_btn.clicked.connect(self._on_export)

        # ── Progress log ──
        log_label = QLabel("Export log:")
        log_label.setStyleSheet("font-size: 13px; color: #aaa;")
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(
            "background:#111;color:#ccc;border:1px solid #333;"
            "border-radius:4px;font-family:monospace;font-size:12px;"
        )

        # ── Open folder button ──
        self._open_btn = QPushButton("Open Output Folder")
        self._open_btn.setVisible(False)
        self._open_btn.setFixedHeight(36)
        self._open_btn.setStyleSheet(
            "background:#2a6e2a;color:#9ef09e;border:none;border-radius:5px;"
            "font-size:13px;font-weight:bold;"
        )
        self._open_btn.clicked.connect(self._on_open_folder)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 24)
        layout.setSpacing(12)
        layout.addLayout(top_bar)
        layout.addWidget(out_label)
        layout.addLayout(out_row)
        layout.addWidget(self._export_btn)
        layout.addWidget(log_label)
        layout.addWidget(self._log)
        layout.addWidget(self._open_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def load_session(self, session: SessionState) -> None:
        self._session = session
        self._log.clear()
        self._open_btn.setVisible(False)
        self._export_btn.setEnabled(True)

        # Show which tracks were identified during analysis
        has_transitions = any(
            c.pre_track or c.post_track for c in session.candidates
        )
        if has_transitions:
            self._log.append("[Track identification from analysis:]")
            for c in session.kept_clips:
                pre = c.pre_track or "unknown"
                post = c.post_track or "unknown"
                self._log.append(
                    f"  Clip {c.rank} @ {self._fmt_ts(c.start_time)}: "
                    f"{pre} → {post}"
                )
            self._log.append("")

    def _fmt_ts(self, seconds: float) -> str:
        s = int(seconds)
        return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"

    def _browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self._out_edit.setText(folder)

    def _on_export(self) -> None:
        self._session.output_dir = Path(self._out_edit.text().strip())
        self._log.clear()
        if any(c.pre_track or c.post_track for c in self._session.candidates):
            self.load_session(self._session)  # re-show track info
        self._open_btn.setVisible(False)
        self._export_btn.setEnabled(False)

        self._cancel_event = threading.Event()
        self._overlay = ProgressOverlay("Exporting Clips", self._cancel_event, self)

        worker = ExportWorker(self._session, self._cancel_event)
        worker.signals.progress.connect(self._overlay.update_progress)
        worker.signals.clip_done.connect(self._on_clip_done)
        worker.signals.finished.connect(self._on_export_done)
        worker.signals.error.connect(self._on_export_error)
        worker.signals.cancelled.connect(self._on_export_cancelled)

        from PyQt6.QtCore import QThreadPool
        QThreadPool.globalInstance().start(worker)
        self._overlay.exec()

    def _on_clip_done(self, index: int, clip_path: str, matches: List[TrackMatch]) -> None:
        name = Path(clip_path).name
        self._log.append(f"[✓] Exported {name}")
        for m in matches:
            self._log.append(f'      Track: "{m.track_name}"  (confidence: {m.confidence:.2f})')

    def _on_export_done(self, session: SessionState) -> None:
        if self._overlay:
            self._overlay.accept()
        self._log.append("\n[✓] Export complete.")
        self._open_btn.setVisible(True)
        self.export_complete.emit(session)

    def _on_export_error(self, message: str) -> None:
        if self._overlay:
            self._overlay.reject()
        self._export_btn.setEnabled(True)
        QMessageBox.critical(self, "Export Failed", message)

    def _on_export_cancelled(self) -> None:
        if self._overlay:
            self._overlay.reject()
        self._export_btn.setEnabled(True)
        self._log.append("[cancelled]")

    def _on_open_folder(self) -> None:
        if self._session and self._session.output_dir:
            subprocess.run(["open", str(self._session.output_dir)])

    def _on_clear_temp(self) -> None:
        size_mb = 0.0
        if TEMP_DIR.exists():
            for f in TEMP_DIR.rglob("*"):
                if f.is_file():
                    size_mb += f.stat().st_size / 1024 / 1024
        reply = QMessageBox.question(
            self,
            "Clear Temp Files",
            f"Delete all temporary files ({size_mb:.0f} MB)?\n\n"
            "This will remove extracted audio from any completed sessions.\n"
            "The current session's files will also be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if TEMP_DIR.exists():
                shutil.rmtree(TEMP_DIR, ignore_errors=True)
            TEMP_DIR.mkdir(parents=True, exist_ok=True)
            self._log.append("[✓] Temp files cleared.")
