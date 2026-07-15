"""Визуальная тема и встроенные SVG-иконки Network Launcher."""

from __future__ import annotations

import os
import sys

from PyQt5.QtCore import QByteArray, QSize, Qt
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer


COLORS = {
    "window": "#0D1017",
    "surface": "#151A24",
    "surface_alt": "#1A202C",
    "border": "#273143",
    "text": "#F4F7FB",
    "muted": "#8F9BAD",
    "accent": "#5B8CFF",
    "accent_hover": "#719CFF",
    "success": "#37C88A",
    "warning": "#F3B64C",
    "danger": "#FF667A",
}


DARK_QSS = """
QMainWindow, QDialog {
    background: #0D1017;
}
QWidget {
    color: #F4F7FB;
    font-family: "Segoe UI";
    font-size: 13px;
}
QWidget#appRoot, QWidget#tabPage, QScrollArea#pageScroll,
QScrollArea#pageScroll > QWidget > QWidget {
    background: #0D1017;
}
QFrame#header, QFrame#card, QFrame#statusCard, QFrame#urlCard {
    background: #151A24;
    border: 1px solid #273143;
    border-radius: 14px;
}
QFrame#statusCard[tone="success"] { border-color: #246C54; }
QFrame#statusCard[tone="warning"] { border-color: #705B2C; }
QFrame#statusCard[tone="danger"] { border-color: #7B3543; }
QFrame#statusCard[tone="info"] { border-color: #385A9D; }
QLabel#appTitle {
    color: #FFFFFF;
    font-size: 21px;
    font-weight: 700;
}
QLabel#subtitle, QLabel#caption, QLabel#statusTitle {
    color: #8F9BAD;
}
QLabel#sectionTitle {
    color: #F4F7FB;
    font-size: 15px;
    font-weight: 650;
}
QLabel#statusValue {
    color: #F4F7FB;
    font-size: 16px;
    font-weight: 650;
}
QLabel#stateBadge {
    background: #252C39;
    border: 1px solid #364156;
    border-radius: 12px;
    color: #AEB8C8;
    font-weight: 600;
    padding: 5px 11px;
}
QLabel#stateBadge[state="starting"] {
    background: #342C1C;
    border-color: #705B2C;
    color: #F3C568;
}
QLabel#stateBadge[state="running"] {
    background: #16352B;
    border-color: #246C54;
    color: #5CDFAC;
}
QLabel#stateBadge[state="error"] {
    background: #3B2027;
    border-color: #7B3543;
    color: #FF8A9A;
}
QLabel#publicUrlLabel {
    color: #C9D4E7;
    font-size: 14px;
}
QLabel#publicUrlLabel a { color: #76A0FF; text-decoration: none; }
QLineEdit, QPlainTextEdit, QSpinBox, QComboBox {
    background: #10141C;
    border: 1px solid #303B4F;
    border-radius: 9px;
    color: #F4F7FB;
    padding: 8px 10px;
    selection-background-color: #5B8CFF;
}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #5B8CFF;
}
QLineEdit:read-only { color: #C2CBD9; background: #121720; }
QPlainTextEdit {
    font-family: "Consolas";
    font-size: 12px;
}
QSpinBox::up-button, QSpinBox::down-button { width: 18px; border: none; }
QComboBox::drop-down { border: none; width: 28px; }
QComboBox QAbstractItemView {
    background: #1A202C;
    border: 1px solid #303B4F;
    selection-background-color: #2D4E8B;
    outline: none;
}
QPushButton {
    background: #202735;
    border: 1px solid #344056;
    border-radius: 9px;
    color: #E7ECF4;
    font-weight: 600;
    min-height: 20px;
    padding: 8px 13px;
}
QPushButton:hover { background: #293244; border-color: #45546D; }
QPushButton:pressed { background: #1B2230; }
QPushButton:disabled {
    background: #171C25;
    border-color: #252C38;
    color: #596476;
}
QPushButton#primaryButton {
    background: #5B8CFF;
    border-color: #5B8CFF;
    color: #FFFFFF;
    font-size: 14px;
    padding: 10px 18px;
}
QPushButton#primaryButton:hover { background: #719CFF; border-color: #719CFF; }
QPushButton#primaryButton:disabled { background: #293854; border-color: #293854; color: #72809A; }
QPushButton#dangerButton {
    background: #3B2027;
    border-color: #7B3543;
    color: #FF9AA7;
    font-size: 14px;
    padding: 10px 18px;
}
QPushButton#dangerButton:hover { background: #4C2630; border-color: #A34455; }
QPushButton#iconButton { min-width: 20px; padding: 7px; }
QTabWidget::pane { border: 0; background: #0D1017; top: -1px; }
QTabBar::tab {
    background: transparent;
    border: 0;
    border-bottom: 2px solid transparent;
    color: #8F9BAD;
    font-weight: 600;
    min-width: 110px;
    padding: 11px 16px;
}
QTabBar::tab:hover { color: #D8DFEA; }
QTabBar::tab:selected { color: #FFFFFF; border-bottom-color: #5B8CFF; }
QGroupBox {
    background: #151A24;
    border: 1px solid #273143;
    border-radius: 14px;
    font-size: 15px;
    font-weight: 650;
    margin-top: 12px;
    padding: 20px 14px 14px 14px;
}
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 7px; }
QCheckBox { color: #C9D2E0; spacing: 8px; }
QCheckBox::indicator {
    background: #10141C;
    border: 1px solid #3B485E;
    border-radius: 5px;
    height: 17px;
    width: 17px;
}
QCheckBox::indicator:checked { background: #5B8CFF; border-color: #5B8CFF; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 3px; }
QScrollBar::handle:vertical { background: #303A4D; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #202735; border: 1px solid #3A465C; color: #F4F7FB; padding: 5px; }
"""


_ICON_PATHS = {
    "folder": '<path d="M3 6.5h6l2 2h10v9.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M3 9h18"/>',
    "play": '<path d="M8 5.5v13l10-6.5z"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "copy": '<rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "external": '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6"/>',
    "refresh": '<path d="M20 7v5h-5"/><path d="M18.2 16A8 8 0 1 1 19 8l1 4"/>',
    "file": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h4M9 12h6M9 16h6"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6"/>',
    "terminal": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M12 15h5"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.6 9a2.5 2.5 0 1 1 4.5 1.5c-.9 1.1-2.1 1.5-2.1 3"/><path d="M12 17h.01"/>',
}


def svg_icon(name: str, color: str = "#DCE5F3", size: int = 20) -> QIcon:
    """Создаёт QIcon из компактного SVG без зависимости от иконочных шрифтов."""
    paths = _ICON_PATHS[name]
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round">{paths}</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def resource_path(*parts: str) -> str:
    """Путь к ресурсу в исходниках или внутри PyInstaller bundle."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        base = bundle_root
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(base, *parts)


def app_icon() -> QIcon:
    return QIcon(resource_path("assets", "network_launcher.ico"))
