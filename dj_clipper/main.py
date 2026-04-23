import atexit
import shutil
import subprocess
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from dj_clipper.config import TEMP_DIR
from dj_clipper.ui.main_window import MainWindow


def check_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("DJ Clipper")

    if not check_ffmpeg():
        QMessageBox.critical(
            None,
            "FFmpeg Not Found",
            "FFmpeg and ffprobe must be on your PATH.\n\nInstall with: brew install ffmpeg",
        )
        sys.exit(1)

    # Wipe any temp data left by a previous crashed session —
    # nothing in TEMP_DIR is reused across restarts.
    shutil.rmtree(TEMP_DIR, ignore_errors=True)

    # Clean up temp files on clean exit too
    atexit.register(shutil.rmtree, TEMP_DIR, True)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
