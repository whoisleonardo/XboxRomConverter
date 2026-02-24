"""
main.py – ROMTool application entry point.
Bootstraps the PySide6 QApplication and launches the main window.
"""

import sys
import os

# ── PyInstaller binary path resolution ──────────────────────────────────────
if hasattr(sys, "_MEIPASS"):
    BASE_PATH = sys._MEIPASS
else:
    BASE_PATH = os.path.abspath(".")

# Expose globally so services can import it
os.environ["ROMTOOL_BASE"] = BASE_PATH

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from main_window import MainWindow


def main() -> None:
    # High-DPI support (PySide6 >= 6.4 handles this automatically,
    # but we set the attribute for older 6.x builds just in case)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("ROMTool")
    app.setApplicationDisplayName("ROMTool – Xbox ISO Utility")
    app.setOrganizationName("ROMTool")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
