"""Точка входа Network Launcher."""

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from .gui import DARK_QSS, HAS_WEBENGINE, MainWindow
from .ui_theme import app_icon


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    if HAS_WEBENGINE:
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Network Launcher")
    app.setOrganizationName("Network Launcher")
    app.setWindowIcon(app_icon())
    app.setStyleSheet(DARK_QSS)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
