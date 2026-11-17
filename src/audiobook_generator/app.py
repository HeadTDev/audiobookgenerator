"""Application entry point: creates the Qt application and shows the main window."""
import sys

from PySide6.QtWidgets import QApplication

from audiobook_generator.ui import theme
from audiobook_generator.ui.main_window import MainWindow


def main():
    if sys.platform == "win32":
        # Own taskbar identity, so Windows shows the app logo instead of python.exe's icon.
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "AudiobookGenerator.App"
        )
    app = QApplication(sys.argv)
    app.setApplicationName("Audiobook Generator")
    app.setWindowIcon(theme.app_icon())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
