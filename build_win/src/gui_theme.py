"""
gui_theme.py - GUI 共用配色、樣式與基礎小元件。
"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter
from PyQt6.QtWidgets import QCheckBox, QComboBox, QFrame, QLabel, QLineEdit, QWidget

C = {
    "bg": "#0d1117",
    "panel": "#161b22",
    "header": "#161b22",
    "sidebar": "#0d1117",
    "surface": "#21262d",
    "border": "#30363d",
    "text": "#e6edf3",
    "subtext": "#8b949e",
    "green": "#3fb950",
    "green_l": "#56d364",
    "red": "#f85149",
    "red_l": "#ff7b72",
    "blue": "#58a6ff",
    "blue_l": "#79c0ff",
    "yellow": "#d29922",
    "yellow_l": "#e3b341",
    "orange": "#f0883e",
    "purple": "#bc8cff",
    "badge_ready": "#4d3800",
    "badge_in": "#033a16",
    "badge_out": "#3d1a78",
    "badge_cancel": "#4a0900",
    "badge_dim": "#1c2128",
    "badge_order": "#1a3a5c",
}

FONT_MAIN = "微軟正黑體"
FONT_MONO = "Consolas"

LIMIT_UP_SIGNAL_LABELS = {
    "ask_at_limit": "賣一價=漲停",
    "bid_at_limit": "買一價=漲停",
    "last_at_limit": "最新成交=漲停",
    "trade_bid_at_limit": "成交 bid=漲停",
    "trade_ask_at_limit": "成交 ask=漲停",
    "trade_flag_price": "API 漲停價旗標",
    "trade_flag_bid": "API 漲停買價旗標",
    "trade_flag_ask": "API 漲停賣價旗標",
    "trade_at_ask": "成交貼近賣方",
    "trade_at_bid": "成交貼近買方",
    "ask_empty": "無委賣檔",
    "bid_empty": "無委買檔",
    "ask_qty_zero": "賣一量=0/無委賣",
    "bid_qty_positive": "買一量>0",
}


def _font(size: int = 10, bold: bool = False) -> QFont:
    font = QFont(FONT_MAIN, size)
    if bold:
        font.setBold(True)
    return font


def _label(text: str, color: str = None, size: int = 10, bold: bool = False) -> QLabel:
    label = QLabel(text)
    label.setFont(_font(size, bold))
    label.setStyleSheet(f"color: {color or C['text']}; background: transparent;")
    return label


def _entry(width: int = 90, password: bool = False) -> QLineEdit:
    entry = QLineEdit()
    entry.setFixedWidth(width)
    entry.setFixedHeight(26)
    entry.setFont(_font(9))
    if password:
        entry.setEchoMode(QLineEdit.EchoMode.Password)
    entry.setStyleSheet(
        f"""
        QLineEdit {{
            background-color: {C['surface']};
            color: {C['text']};
            border: 1px solid {C['border']};
            border-radius: 4px;
            padding: 2px 6px;
        }}
        QLineEdit:focus {{ border: 1px solid {C['blue']}; }}
    """
    )
    return entry


def _combo(items: list, width: int = 90) -> QComboBox:
    combo = QComboBox()
    combo.setFixedWidth(width)
    combo.setFixedHeight(26)
    combo.setFont(_font(9))
    combo.addItems(items)
    combo.setStyleSheet(
        f"""
        QComboBox {{
            background-color: {C['surface']};
            color: {C['text']};
            border: 1px solid {C['border']};
            border-radius: 4px;
            padding: 2px 6px;
        }}
        QComboBox::drop-down {{ border: none; width: 18px; }}
        QComboBox QAbstractItemView {{
            background-color: {C['surface']};
            color: {C['text']};
            selection-background-color: {C['blue']};
            border: 1px solid {C['border']};
        }}
    """
    )
    return combo


def _checkbox(text: str, size: int = 9) -> QCheckBox:
    checkbox = QCheckBox(text)
    checkbox.setFont(_font(size))
    checkbox.setStyleSheet(
        f"""
        QCheckBox {{
            color: {C['text']};
            background: transparent;
            spacing: 5px;
        }}
        QCheckBox::indicator {{
            width: 13px; height: 13px;
            border: 1px solid {C['border']};
            border-radius: 2px;
            background-color: {C['surface']};
        }}
        QCheckBox::indicator:checked {{
            background-color: {C['blue']};
            border-color: {C['blue']};
        }}
    """
    )
    return checkbox


def _divider() -> QFrame:
    frame = QFrame()
    frame.setFixedHeight(1)
    frame.setStyleSheet(f"background-color: {C['border']};")
    return frame


def _section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setFont(_font(9, bold=True))
    label.setStyleSheet(
        f"color: {C['subtext']}; background: transparent; padding: 8px 0 3px 0;"
    )
    return label


def _sep_bar() -> QLabel:
    label = QLabel("|")
    label.setStyleSheet(f"color: {C['border']}; background: transparent;")
    label.setFont(_font(9))
    return label


def _scroll_style() -> str:
    return f"""
        QScrollBar:vertical {{
            background: {C['bg']};
            width: 6px; margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {C['surface']};
            border-radius: 3px;
            min-height: 20px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            background: {C['bg']};
            height: 6px;
        }}
        QScrollBar::handle:horizontal {{
            background: {C['surface']};
            border-radius: 3px;
            min-width: 20px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    """


def _table_style() -> str:
    return f"""
        QTableWidget {{
            background-color: {C['panel']};
            color: {C['text']};
            gridline-color: {C['border']};
            border: none;
            font-family: {FONT_MAIN};
            font-size: 9pt;
        }}
        QTableWidget::item {{ padding: 2px 4px; }}
        QTableWidget::item:selected {{
            background-color: {C['surface']};
            color: {C['text']};
        }}
        QHeaderView::section {{
            background-color: {C['bg']};
            color: {C['subtext']};
            font-family: {FONT_MAIN};
            font-size: 9pt;
            border: none;
            border-right: 1px solid {C['border']};
            border-bottom: 1px solid {C['border']};
            padding: 4px 6px;
        }}
        {_scroll_style()}
    """


def _panel_frame() -> QFrame:
    frame = QFrame()
    frame.setStyleSheet(
        f"""
        QFrame {{
            background-color: {C['panel']};
            border: 1px solid {C['border']};
            border-radius: 6px;
        }}
    """
    )
    return frame


class ToggleButton(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None, initial: bool = True):
        super().__init__(parent)
        self._on = initial
        self.setFixedSize(46, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, _event):
        self._on = not self._on
        self.update()
        self.toggled.emit(self._on)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill = QColor(C["green"] if self._on else C["surface"])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(0, 0, 46, 24, 12, 12)
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawEllipse(QPoint(30 if self._on else 16, 12), 9, 9)

    @property
    def value(self) -> bool:
        return self._on

    def set(self, val: bool):
        if self._on != val:
            self._on = val
            self.update()
