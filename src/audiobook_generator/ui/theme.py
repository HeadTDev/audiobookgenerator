"""Dark theme: palette, style sheet and the small icons the style sheet needs."""
import os
import tempfile

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtSvg import QSvgRenderer

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.svg")

BG = "#16171a"
SURFACE = "#1e2024"
SURFACE_HOVER = "#262930"
BORDER = "#2d3038"
TEXT = "#e6e7ea"
MUTED = "#8b909a"
ACCENT = "#f2b705"
ACCENT_HOVER = "#ffc928"
ACCENT_TEXT = "#16171a"
SUCCESS = "#3fb950"
DANGER = "#f85149"
WARNING = "#d29922"
INFO = "#58a6ff"

_ICON_DIR = os.path.join(tempfile.gettempdir(), "audiobook_generator_icons")


def _save_icon(name, paint):
    path = os.path.join(_ICON_DIR, name)
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    paint(painter)
    painter.end()
    pixmap.save(path, "PNG")
    return path.replace("\\", "/")


def _paint_arrow(painter):
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(MUTED))
    painter.drawPolygon(QPolygonF([QPointF(4, 6), QPointF(12, 6), QPointF(8, 11)]))


def _paint_check(painter):
    pen = QPen(QColor(ACCENT_TEXT), 2.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline(QPolygonF([QPointF(3.5, 8.5), QPointF(6.5, 11.5), QPointF(12.5, 4.5)]))


def build_stylesheet():
    os.makedirs(_ICON_DIR, exist_ok=True)
    arrow = _save_icon("arrow.png", _paint_arrow)
    check = _save_icon("check.png", _paint_check)
    return f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 10pt;
}}
QToolTip {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 6px;
}}

/* ---------- Layout areas ---------- */
#header {{
    background-color: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}
#appTitle {{
    font-size: 13pt;
    font-weight: 600;
    background: transparent;
}}
#headerInfo {{
    color: {MUTED};
    background: transparent;
}}
#sidebar {{
    background-color: {SURFACE};
    border-right: 1px solid {BORDER};
}}
#sidebar QLabel {{
    background-color: transparent;
}}
#sectionLabel {{
    color: {MUTED};
    font-size: 8pt;
    font-weight: 600;
    letter-spacing: 1px;
    padding-top: 6px;
}}
#fieldLabel {{
    color: {MUTED};
    font-size: 9pt;
}}
#card {{
    background-color: {BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
#summaryMain {{
    font-size: 12pt;
    font-weight: 600;
}}
#summaryDetail {{
    color: {MUTED};
}}
#playerBar, #progressArea {{
    background-color: {SURFACE};
    border-top: 1px solid {BORDER};
}}
#playerBar QLabel, #progressArea QLabel {{
    background-color: transparent;
}}
#etaLabel, #mutedLabel {{
    color: {MUTED};
}}
#playerTitle {{
    color: {TEXT};
    font-size: 9pt;
    font-weight: 600;
}}
#timeLabel {{
    color: {MUTED};
    font-size: 9pt;
    min-width: 44px;
}}

/* ---------- Inputs ---------- */
QLineEdit, QComboBox {{
    background-color: {BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_TEXT};
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit[readOnly="true"] {{
    color: {MUTED};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: url("{arrow}");
    width: 16px;
    height: 16px;
}}
QComboBox QAbstractItemView {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_TEXT};
    outline: none;
}}

/* ---------- Buttons ---------- */
QPushButton, QToolButton {{
    background-color: {SURFACE_HOVER};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 12px;
}}
QPushButton:hover, QToolButton:hover {{
    border-color: {MUTED};
}}
QPushButton:pressed, QToolButton:pressed {{
    background-color: {BG};
}}
QPushButton:disabled, QToolButton:disabled {{
    color: #5a5e66;
    border-color: {SURFACE_HOVER};
}}
#primaryButton {{
    background-color: {ACCENT};
    color: {ACCENT_TEXT};
    border: none;
    font-weight: 600;
    padding: 10px 12px;
}}
#primaryButton:hover {{
    background-color: {ACCENT_HOVER};
}}
#primaryButton:disabled {{
    background-color: #4a4126;
    color: #8a7f5f;
}}
#dangerButton {{
    background-color: transparent;
    color: {DANGER};
    border: 1px solid {DANGER};
    padding: 8px 12px;
}}
#dangerButton:hover {{
    background-color: rgba(248, 81, 73, 0.12);
}}
#dangerButton:disabled {{
    color: #5a5e66;
    border-color: {SURFACE_HOVER};
}}
#filterButton {{
    background-color: transparent;
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 12px;
    color: {MUTED};
}}
#filterButton:checked {{
    background-color: {SURFACE_HOVER};
    border-color: {ACCENT};
    color: {TEXT};
}}
#linkButton {{
    background: transparent;
    border: none;
    color: {MUTED};
    padding: 4px 2px;
    text-align: left;
}}
#linkButton:hover {{
    color: {TEXT};
}}
#playButton {{
    border-radius: 19px;
    min-width: 38px;
    max-width: 38px;
    min-height: 38px;
    max-height: 38px;
    padding: 0;
    background-color: {ACCENT};
    border: none;
}}
#playButton:hover {{
    background-color: {ACCENT_HOVER};
}}
#playButton:pressed {{
    background-color: #d9a200;
}}
#playButton:disabled {{
    background-color: {SURFACE_HOVER};
    color: #5a5e66;
}}

#skipButton {{
    padding: 4px 8px;
    min-width: 34px;
    color: {MUTED};
}}
#rateCombo {{
    min-width: 48px;
}}

/* ---------- Sliders ---------- */
QSlider::groove:horizontal {{
    height: 4px;
    background: {BORDER};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {TEXT};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: {ACCENT_HOVER};
}}
QSlider::sub-page:horizontal:disabled {{
    background: {BORDER};
}}

/* ---------- File table ---------- */
QTableWidget {{
    background-color: {BG};
    border: none;
    gridline-color: transparent;
    outline: none;
}}
QTableWidget::item {{
    border-bottom: 1px solid {SURFACE};
    padding: 0 6px;
}}
QTableWidget::item:hover {{
    background-color: {SURFACE};
}}
QTableWidget::item:selected {{
    background-color: transparent;
    color: {TEXT};
}}
QTableWidget::indicator, QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {MUTED};
    border-radius: 4px;
    background-color: {BG};
}}
QTableWidget::indicator:checked, QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
    image: url("{check}");
}}
QHeaderView::section {{
    background-color: {BG};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 8px 6px;
    font-size: 8pt;
    font-weight: 600;
}}
QHeaderView::section:hover {{
    color: {TEXT};
}}

/* ---------- Progress & log ---------- */
QProgressBar {{
    background-color: {BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    height: 20px;
    text-align: center;
    color: {TEXT};
    font-size: 9pt;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 5px;
}}
QTextEdit {{
    background-color: {BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 9pt;
    padding: 4px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {MUTED};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
"""


def logo_pixmap(size):
    """The app logo rendered crisply at `size` px (SVG, so every size stays sharp)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(LOGO_PATH).render(painter)
    painter.end()
    return pixmap


def _media_icon(paint):
    """Icon drawn at 64 px so it stays crisp when Qt scales it down (incl. HiDPI)."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(ACCENT_TEXT))
    paint(painter)
    painter.end()
    return QIcon(pixmap)


def play_icon():
    def paint(painter):
        # Rounded triangle, nudged right so it looks optically centred in the circle.
        path = QPainterPath()
        path.moveTo(20, 10)
        path.lineTo(54, 32)
        path.lineTo(20, 54)
        path.closeSubpath()
        stroke = QPen(QColor(ACCENT_TEXT), 8)
        stroke.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(stroke)
        painter.drawPath(path)

    return _media_icon(paint)


def pause_icon():
    def paint(painter):
        painter.drawRoundedRect(QRectF(14, 8, 13, 48), 4, 4)
        painter.drawRoundedRect(QRectF(37, 8, 13, 48), 4, 4)

    return _media_icon(paint)


def app_icon():
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(size))
    return icon


def cleanup_icons():
    for name in ("arrow.png", "check.png"):
        try:
            os.remove(os.path.join(_ICON_DIR, name))
        except OSError:
            pass
