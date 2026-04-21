"""
gui.py — 台股漲停自動交易系統 主視窗
使用 PyQt6，介面與原 tkinter 版完全一致。
"""
from __future__ import annotations
import queue
import threading
from typing import Dict, Optional
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QLineEdit, QCheckBox, QGroupBox, QScrollArea, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollBar,
    QMessageBox, QHBoxLayout, QVBoxLayout, QGridLayout, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QSize, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush

from config import TradingConfig
from engine import TradingEngine

# ──────────────────────────────────────────────
#  Catppuccin Mocha 調色盤
# ──────────────────────────────────────────────
C = {
    "base":    "#1e1e2e",
    "mantle":  "#181825",
    "crust":   "#11111b",
    "surface0":"#313244",
    "surface1":"#45475a",
    "surface2":"#585b70",
    "overlay0":"#6c7086",
    "overlay1":"#7f849c",
    "text":    "#cdd6f4",
    "subtext0":"#a6adc8",
    "blue":    "#89b4fa",
    "green":   "#a6e3a1",
    "red":     "#f38ba8",
    "yellow":  "#f9e2af",
    "peach":   "#fab387",
    "mauve":   "#cba6f7",
    "teal":    "#94e2d5",
}

LOG_Q: queue.Queue = queue.Queue()

FONT_MAIN = "微軟正黑體"
FONT_MONO = "Consolas"


def _qss_bg(color: str) -> str:
    return f"background-color: {color};"


def _font(size=10, bold=False):
    f = QFont(FONT_MAIN, size)
    if bold:
        f.setBold(True)
    return f


# ──────────────────────────────────────────────────────────────
#  ToggleButton — iOS 風格 toggle switch
# ──────────────────────────────────────────────────────────────

class ToggleButton(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None, initial=True):
        super().__init__(parent)
        self._on = initial
        self.setFixedSize(42, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        self._on = not self._on
        self.update()
        self.toggled.emit(self._on)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        fill = QColor(C["blue"] if self._on else C["surface0"])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(fill))

        # pill background
        p.drawRoundedRect(0, 0, 42, 22, 11, 11)

        # knob
        knob_color = QColor(C["base"])
        p.setBrush(QBrush(knob_color))
        x = 28 if self._on else 14
        p.drawEllipse(QPoint(x, 11), 8, 8)

    @property
    def value(self) -> bool:
        return self._on

    def set(self, val: bool):
        if self._on != val:
            self._on = val
            self.update()


# ──────────────────────────────────────────────────────────────
#  小工具函數
# ──────────────────────────────────────────────────────────────

def _label(text, color=None, size=10, bold=False) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(_font(size, bold))
    lbl.setStyleSheet(f"color: {color or C['text']}; background: transparent;")
    return lbl


def _entry(width=160, password=False, readonly=False) -> QLineEdit:
    e = QLineEdit()
    e.setFixedWidth(width)
    e.setFont(_font(10))
    if password:
        e.setEchoMode(QLineEdit.EchoMode.Password)
    if readonly:
        e.setReadOnly(True)
    e.setStyleSheet(f"""
        QLineEdit {{
            background-color: {C['surface0']};
            color: {C['text']};
            border: 1px solid {C['surface1']};
            border-radius: 4px;
            padding: 3px 6px;
        }}
        QLineEdit:focus {{
            border: 1px solid {C['blue']};
        }}
        QLineEdit:read-only {{
            color: {C['overlay0']};
        }}
    """)
    return e


def _group_box(title: str) -> QGroupBox:
    gb = QGroupBox(f"  {title}  ")
    gb.setFont(_font(10, bold=True))
    gb.setStyleSheet(f"""
        QGroupBox {{
            color: {C['blue']};
            background-color: {C['base']};
            border: 1px solid {C['surface0']};
            border-radius: 6px;
            margin-top: 10px;
            padding-top: 6px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }}
    """)
    return gb


def _scroll_style() -> str:
    return f"""
        QScrollBar:vertical {{
            background: {C['mantle']};
            width: 8px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {C['surface1']};
            border-radius: 4px;
            min-height: 20px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar:horizontal {{
            background: {C['mantle']};
            height: 8px;
        }}
        QScrollBar::handle:horizontal {{
            background: {C['surface1']};
            border-radius: 4px;
            min-width: 20px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
        }}
    """


def _table_style(style_name: str = "") -> str:
    return f"""
        QTableWidget {{
            background-color: {C['base']};
            color: {C['text']};
            gridline-color: {C['surface0']};
            border: none;
            font-family: {FONT_MAIN};
            font-size: 9pt;
        }}
        QTableWidget::item:selected {{
            background-color: {C['surface0']};
            color: {C['text']};
        }}
        QHeaderView::section {{
            background-color: {C['mantle']};
            color: {C['overlay0']};
            font-family: {FONT_MAIN};
            font-size: 9pt;
            font-weight: bold;
            border: none;
            padding: 4px;
        }}
        {_scroll_style()}
    """


# ──────────────────────────────────────────────────────────────
#  主視窗
# ──────────────────────────────────────────────────────────────

class App(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("台股漲停自動交易系統 v1.0")
        self.resize(980, 700)
        self.setMinimumSize(860, 600)
        self.setStyleSheet(f"background-color: {C['crust']};")

        self.cfg = TradingConfig.load()
        self.engine: Optional[TradingEngine] = None
        self._running = False
        self._trade_count = 0
        self._buy_count = 0
        self._sell_count = 0
        self._log_lines = 0

        self._fields: Dict[str, QLineEdit] = {}
        self._checks: Dict[str, QCheckBox] = {}
        self._toggles: Dict[str, ToggleButton] = {}

        self._build_ui()
        self._apply_config(self.cfg)
        self._start_polling()

    # ══════════════════════════════════════════
    #  UI 建立
    # ══════════════════════════════════════════

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        self._main_layout = QVBoxLayout(central)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        self._build_titlebar()
        self._build_tabbar()
        self._build_pages()
        self._switch_tab("settings")

    # ── 標題列 ───────────────────────────────
    def _build_titlebar(self):
        bar = QFrame()
        bar.setFixedHeight(50)
        bar.setStyleSheet(f"background-color: {C['mantle']};")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(8)

        icon_lbl = QLabel("▲")
        icon_lbl.setFont(QFont("Segoe UI Emoji", 16))
        icon_lbl.setStyleSheet(f"color: {C['text']}; background: transparent;")
        layout.addWidget(icon_lbl)

        title_lbl = QLabel("台股漲停自動交易系統 v1.0")
        title_lbl.setFont(_font(12, bold=True))
        title_lbl.setStyleSheet(f"color: {C['text']}; background: transparent;")
        layout.addWidget(title_lbl)
        layout.addStretch()

        # 狀態燈
        self.status_dot = QLabel("●")
        self.status_dot.setFont(QFont("Arial", 13))
        self.status_dot.setStyleSheet(f"color: {C['red']}; background: transparent;")
        layout.addWidget(self.status_dot)

        self.status_text = QLabel("未連線")
        self.status_text.setFont(_font(10))
        self.status_text.setStyleSheet(f"color: {C['overlay0']}; background: transparent;")
        layout.addWidget(self.status_text)

        layout.addSpacing(12)

        self.btn_stop = QPushButton("■  停止")
        self.btn_stop.setFont(_font(10, bold=True))
        self.btn_stop.setFixedHeight(34)
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['red']};
                color: {C['base']};
                border: none;
                border-radius: 4px;
                padding: 0 16px;
            }}
            QPushButton:hover {{ background-color: #ff9999; }}
            QPushButton:disabled {{ background-color: {C['surface0']}; color: {C['overlay0']}; }}
        """)
        self.btn_stop.clicked.connect(self._stop_trading)
        layout.addWidget(self.btn_stop)

        self.btn_start = QPushButton("▶  啟動交易")
        self.btn_start.setFont(_font(10, bold=True))
        self.btn_start.setFixedHeight(34)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['green']};
                color: {C['base']};
                border: none;
                border-radius: 4px;
                padding: 0 16px;
            }}
            QPushButton:hover {{ background-color: {C['teal']}; }}
            QPushButton:disabled {{ background-color: {C['surface0']}; color: {C['overlay0']}; }}
        """)
        self.btn_start.clicked.connect(self._start_trading)
        layout.addWidget(self.btn_start)

        self._main_layout.addWidget(bar)

        # 分隔線
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {C['surface0']};")
        self._main_layout.addWidget(sep)

    # ── 分頁列 ───────────────────────────────
    def _build_tabbar(self):
        bar = QFrame()
        bar.setFixedHeight(38)
        bar.setStyleSheet(f"background-color: {C['mantle']};")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tab_btns: Dict[str, QLabel] = {}
        tabs = [
            ("settings", "⚙  設定"),
            ("monitor",  "●  即時監控"),
            ("log",      "≡  系統日誌"),
            ("trades",   "☆  交易紀錄"),
        ]
        for key, text in tabs:
            btn = QLabel(text)
            btn.setFont(_font(10, bold=True))
            btn.setStyleSheet(f"color: {C['overlay0']}; background: transparent; padding: 0 18px;")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn.setFixedHeight(38)
            btn.mousePressEvent = lambda e, k=key: self._switch_tab(k)
            layout.addWidget(btn)
            self._tab_btns[key] = btn

        layout.addStretch()
        self._main_layout.addWidget(bar)

        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background-color: {C['surface0']};")
        self._main_layout.addWidget(sep2)

    def _switch_tab(self, key: str):
        for k, btn in self._tab_btns.items():
            if k == key:
                btn.setStyleSheet(f"color: {C['blue']}; background: transparent; padding: 0 18px;")
            else:
                btn.setStyleSheet(f"color: {C['overlay0']}; background: transparent; padding: 0 18px;")
        for k, frame in self._pages.items():
            frame.setVisible(k == key)

    # ── 分頁容器 ─────────────────────────────
    def _build_pages(self):
        container = QWidget()
        container.setStyleSheet(f"background-color: {C['crust']};")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._pages: Dict[str, QWidget] = {}
        for key in ("settings", "monitor", "log", "trades"):
            page = QWidget()
            page.setStyleSheet(f"background-color: {C['base']};")
            layout.addWidget(page)
            self._pages[key] = page

        self._build_settings(self._pages["settings"])
        self._build_monitor(self._pages["monitor"])
        self._build_log(self._pages["log"])
        self._build_trades(self._pages["trades"])

        self._main_layout.addWidget(container, 1)

    # ══════════════════════════════════════════
    #  設定頁
    # ══════════════════════════════════════════

    def _build_settings(self, parent: QWidget):
        outer = QVBoxLayout(parent)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background-color: {C['base']}; }}
            {_scroll_style()}
        """)
        outer.addWidget(scroll)

        inner = QWidget()
        inner.setStyleSheet(f"background-color: {C['base']};")
        scroll.setWidget(inner)

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(0)

        # ── 帳號設定 ──────────────────────────
        gb, gl = self._group(layout, "■  券商帳號")
        self._frow(gl, 0, "API Key",        "api_id")
        self._frow(gl, 1, "Secret Key",     "api_key", password=True)
        self._frow(gl, 2, "憑證路徑（選填）", "broker_cert_path", width=280)

        # ── 功能 1 ────────────────────────────
        gb1, gl1 = self._group(layout, "① 時間 + 委賣篩選（10點前漲停才進場）", toggle_key="f1_enabled")
        self._frow(gl1, 0, "進場截止時間（HH:MM）",             "entry_before_time")
        self._frow(gl1, 1, "漲停委賣張數上限（低於此數才進場）", "ask_queue_threshold")

        # ── 功能 2 ────────────────────────────
        _, gl2 = self._group(layout, "② 市場選擇")
        self._cbox(gl2, 0, "上市（TSE）", "market_twse")
        self._cbox(gl2, 1, "上櫃（OTC）", "market_tpex")

        # ── 功能 3 ────────────────────────────
        _, gl3 = self._group(layout, "③ 每隻股票投入金額（元）")
        self._frow(gl3, 0, "金額（元）", "per_stock_amount")
        note = _label("計算說明：依漲停價自動計算張數", C["overlay0"])
        gl3.addWidget(note, 1, 0, 1, 2)

        # ── 功能 4 ────────────────────────────
        _, gl4 = self._group(layout, "④ 持倉出場：委買漲停 → 市價賣出", toggle_key="f4_enabled")
        note4 = _label("買進後，若委買價達到漲停（市場打開），立即市價賣出。", C["overlay0"])
        gl4.addWidget(note4, 0, 0, 1, 2)

        # ── 功能 5 ────────────────────────────
        _, gl5 = self._group(layout, "⑤ 持倉出場：1秒成交量爆量賣出", toggle_key="f5_enabled")
        self._frow(gl5, 0, "1秒成交張數門檻（超過則市價賣出）", "volume_spike_sell_threshold")

        # ── 功能 6 ────────────────────────────
        _, gl6 = self._group(layout, "⑥ 委託中取消：1秒成交量爆量取消委託", toggle_key="f6_enabled")
        self._frow(gl6, 0, "1秒成交張數門檻（超過則取消委託）", "volume_spike_cancel_threshold")

        # ── 功能 7 ────────────────────────────
        _, gl7 = self._group(layout, "⑦ 只買起漲第幾根 K 棒", toggle_key="f7_enabled")
        self._frow(gl7, 0, "最多第幾根（1=只買第1根，2=第1或第2根）", "candle_limit")

        # ── 功能 8 ────────────────────────────
        _, gl8 = self._group(layout, "⑧ 當天成交量門檻（幾張以上才進場）", toggle_key="f8_enabled")
        self._frow(gl8, 0, "當天最低成交量（張，低於不進場）", "daily_volume_min")

        # ── 功能 9 ────────────────────────────
        _, gl9 = self._group(layout, "⑨ 股價區間篩選", toggle_key="f9_enabled")
        self._frow(gl9, 0, "最低股價（元）", "price_min")
        self._frow(gl9, 1, "最高股價（元）", "price_max")

        # ── 功能 10 ───────────────────────────
        _, gl10 = self._group(layout, "⑩ 委賣價 + 即時成交量雙重確認進場", toggle_key="f10_enabled")
        self._frow(gl10, 0, "委賣價必須 ≤ 漲停價 × 倍率（1.0 = 恰好漲停）", "ask_price_ratio")
        self._frow(gl10, 1, "該檔 1 秒內成交量必須達到（張）才進場",          "entry_volume_confirm")
        note10 = _label("兩條件須同時成立才進場，可搭配功能①使用。", C["overlay0"])
        gl10.addWidget(note10, 2, 0, 1, 2)

        # ── 功能 11 ───────────────────────────
        _, gl11 = self._group(layout, "⑪ 排除特殊股（處置股、注意股、限當沖股）", toggle_key="f11_enabled")
        note11 = _label("啟用後，處置股、注意股、限制當沖股票一律不進場。", C["overlay0"])
        gl11.addWidget(note11, 0, 0, 1, 2)

        # ── 功能 12 ───────────────────────────
        _, gl12 = self._group(layout, "⑫ 開盤漲停已賣出 → 當天不再追", toggle_key="f12_enabled")
        note12 = _label("開盤即漲停的股票，當天賣出後不再重新進場（防止反覆追高）。", C["overlay0"])
        gl12.addWidget(note12, 0, 0, 1, 2)

        # ── 功能 13 ───────────────────────────
        _, gl13 = self._group(layout, "⑬ 限制每天最大成交檔數", toggle_key="f13_enabled")
        self._frow(gl13, 0, "每天最多成交幾檔（達到後停止新進場）", "daily_max_trades")

        # ── 底部按鈕 ──────────────────────────
        btn_widget = QWidget()
        btn_widget.setStyleSheet(f"background-color: {C['base']};")
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(16, 4, 16, 16)
        btn_layout.setSpacing(10)

        save_btn = QPushButton("✔  儲存設定")
        save_btn.setFont(_font(11, bold=True))
        save_btn.setFixedHeight(36)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['blue']};
                color: {C['base']};
                border: none;
                border-radius: 4px;
                padding: 0 20px;
            }}
            QPushButton:hover {{ background-color: {C['mauve']}; }}
        """)
        save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(save_btn)

        reset_btn = QPushButton("↩  還原預設")
        reset_btn.setFont(_font(10))
        reset_btn.setFixedHeight(36)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['surface0']};
                color: {C['text']};
                border: none;
                border-radius: 4px;
                padding: 0 14px;
            }}
            QPushButton:hover {{ background-color: {C['surface1']}; }}
        """)
        reset_btn.clicked.connect(self._reset_settings)
        btn_layout.addWidget(reset_btn)

        self.save_status_lbl = _label("✓ 設定已儲存", C["green"])
        self.save_status_lbl.setVisible(False)
        btn_layout.addWidget(self.save_status_lbl)

        btn_layout.addStretch()
        layout.addWidget(btn_widget)

    def _group(self, parent_layout: QVBoxLayout, title: str,
               toggle_key: str = "") -> tuple:
        gb = _group_box(title)

        gl = QGridLayout(gb)
        gl.setContentsMargins(10, 6, 10, 10)
        gl.setSpacing(4)
        gl.setColumnStretch(1, 1)

        if toggle_key:
            tog = ToggleButton(gb)
            self._toggles[toggle_key] = tog
            gl.addWidget(tog, 0, 2, 1, 1,
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        wrapper = QWidget()
        wrapper.setStyleSheet(f"background-color: {C['base']};")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(16, 0, 16, 10)
        wl.setSpacing(0)
        wl.addWidget(gb)

        parent_layout.addWidget(wrapper)
        return gb, gl

    def _frow(self, grid: QGridLayout, row: int, lbl_text: str, key: str,
              width: int = 160, password: bool = False):
        lbl = _label(lbl_text + " ：")
        grid.addWidget(lbl, row, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        e = _entry(width=width, password=password)
        self._fields[key] = e
        grid.addWidget(e, row, 1, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

    def _cbox(self, grid: QGridLayout, row: int, lbl_text: str, key: str):
        cb = QCheckBox(lbl_text)
        cb.setFont(_font(10))
        cb.setStyleSheet(f"""
            QCheckBox {{
                color: {C['text']};
                background: transparent;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border: 1px solid {C['surface1']};
                border-radius: 3px;
                background-color: {C['surface0']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {C['blue']};
                border-color: {C['blue']};
            }}
        """)
        self._checks[key] = cb
        grid.addWidget(cb, row, 0, 1, 2)

    # ── 設定讀寫 ─────────────────────────────
    def _apply_config(self, cfg: TradingConfig):
        f = self._fields
        c = self._checks
        t = self._toggles

        f["api_id"].setText(cfg.api_id)
        f["api_key"].setText(cfg.api_key)
        f["broker_cert_path"].setText(cfg.broker_cert_path)
        f["entry_before_time"].setText(cfg.entry_before_time)
        f["ask_queue_threshold"].setText(str(cfg.ask_queue_threshold))
        c["market_twse"].setChecked(cfg.market_twse)
        c["market_tpex"].setChecked(cfg.market_tpex)
        f["per_stock_amount"].setText(str(cfg.per_stock_amount))
        f["volume_spike_sell_threshold"].setText(str(cfg.volume_spike_sell_threshold))
        f["volume_spike_cancel_threshold"].setText(str(cfg.volume_spike_cancel_threshold))
        f["candle_limit"].setText(str(cfg.candle_limit))
        f["daily_volume_min"].setText(str(cfg.daily_volume_min))
        f["price_min"].setText(str(cfg.price_min))
        f["price_max"].setText(str(cfg.price_max))
        f["ask_price_ratio"].setText(str(cfg.ask_price_ratio))
        f["entry_volume_confirm"].setText(str(cfg.entry_volume_confirm))

        t["f1_enabled"].set(cfg.f1_enabled)
        t["f4_enabled"].set(cfg.f4_enabled)
        t["f5_enabled"].set(cfg.f5_enabled)
        t["f6_enabled"].set(cfg.f6_enabled)
        t["f7_enabled"].set(cfg.f7_enabled)
        t["f8_enabled"].set(cfg.f8_enabled)
        t["f9_enabled"].set(cfg.f9_enabled)
        t["f10_enabled"].set(cfg.f10_enabled)
        t["f11_enabled"].set(cfg.f11_enabled)
        t["f12_enabled"].set(cfg.f12_enabled)
        t["f13_enabled"].set(cfg.f13_enabled)
        f["daily_max_trades"].setText(str(cfg.daily_max_trades))

    def _collect_config(self) -> TradingConfig:
        f = self._fields
        c = self._checks
        t = self._toggles

        def g(k): return f[k].text()
        def ni(k):
            try: return int(float(g(k)))
            except: return 0
        def nf(k):
            try: return float(g(k))
            except: return 0.0

        return TradingConfig(
            api_id              = g("api_id"),
            api_key             = g("api_key"),
            broker_cert_path    = g("broker_cert_path"),
            f1_enabled          = t["f1_enabled"].value,
            entry_before_time   = g("entry_before_time"),
            ask_queue_threshold = ni("ask_queue_threshold"),
            market_twse         = c["market_twse"].isChecked(),
            market_tpex         = c["market_tpex"].isChecked(),
            per_stock_amount    = ni("per_stock_amount"),
            f4_enabled          = t["f4_enabled"].value,
            f5_enabled          = t["f5_enabled"].value,
            volume_spike_sell_threshold   = ni("volume_spike_sell_threshold"),
            f6_enabled          = t["f6_enabled"].value,
            volume_spike_cancel_threshold = ni("volume_spike_cancel_threshold"),
            f7_enabled          = t["f7_enabled"].value,
            candle_limit        = ni("candle_limit"),
            f8_enabled          = t["f8_enabled"].value,
            daily_volume_min    = ni("daily_volume_min"),
            f9_enabled          = t["f9_enabled"].value,
            price_min           = nf("price_min"),
            price_max           = nf("price_max"),
            f10_enabled         = t["f10_enabled"].value,
            ask_price_ratio     = nf("ask_price_ratio"),
            entry_volume_confirm= ni("entry_volume_confirm"),
            f11_enabled         = t["f11_enabled"].value,
            f12_enabled         = t["f12_enabled"].value,
            f13_enabled         = t["f13_enabled"].value,
            daily_max_trades    = ni("daily_max_trades"),
        )

    def _save_settings(self):
        try:
            self.cfg = self._collect_config()
            self.cfg.save()
            self.save_status_lbl.setVisible(True)
            QTimer.singleShot(2000, lambda: self.save_status_lbl.setVisible(False))
        except ValueError as e:
            QMessageBox.critical(self, "格式錯誤", f"數字欄位格式有誤：{e}")

    def _reset_settings(self):
        reply = QMessageBox.question(self, "還原確認", "確定要還原為預設值？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._apply_config(TradingConfig())

    # ══════════════════════════════════════════
    #  即時監控頁
    # ══════════════════════════════════════════

    def _build_monitor(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 統計卡列
        stats_row = QWidget()
        stats_row.setStyleSheet(f"background-color: {C['base']};")
        stats_layout = QHBoxLayout(stats_row)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(10)

        self.stat_watching  = self._stat_card(stats_layout, "監控中股票", "0", C["blue"])
        self.stat_positions = self._stat_card(stats_layout, "持倉",       "0", C["green"])
        self.stat_pending   = self._stat_card(stats_layout, "委託中",     "0", C["yellow"])
        self.stat_trades    = self._stat_card(stats_layout, "今日成交",   "0", C["text"])
        layout.addWidget(stats_row)

        # 表格
        cols  = ["代號", "名稱", "漲停根數", "持倉(張)", "委託中", "1秒量(張)", "狀態"]
        self.monitor_table = QTableWidget(0, len(cols))
        self.monitor_table.setHorizontalHeaderLabels(cols)
        self.monitor_table.setStyleSheet(_table_style())
        self.monitor_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.monitor_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.monitor_table.verticalHeader().setVisible(False)
        self.monitor_table.setShowGrid(True)
        self.monitor_table.horizontalHeader().setStretchLastSection(True)

        widths = [70, 80, 80, 70, 70, 80, 80]
        for i, w in enumerate(widths):
            self.monitor_table.setColumnWidth(i, w)
        self.monitor_table.verticalHeader().setDefaultSectionSize(26)

        layout.addWidget(self.monitor_table, 1)

        # 用於差量更新的 code→row 映射
        self._monitor_rows: Dict[str, int] = {}

    def _stat_card(self, layout: QHBoxLayout, label_text: str,
                   init: str, color: str) -> QLabel:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {C['mantle']};
                border: 1px solid {C['surface0']};
                border-radius: 6px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 6, 10, 6)
        card_layout.setSpacing(2)

        top_lbl = _label(label_text, C["overlay0"], size=10)
        card_layout.addWidget(top_lbl)

        val_lbl = QLabel(init)
        val_lbl.setFont(_font(22, bold=True))
        val_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        card_layout.addWidget(val_lbl)

        layout.addWidget(card, 1)
        return val_lbl

    # ══════════════════════════════════════════
    #  系統日誌頁
    # ══════════════════════════════════════════

    def _build_log(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(14, 10, 14, 14)
        layout.setSpacing(4)

        toolbar = QWidget()
        toolbar.setStyleSheet(f"background-color: {C['base']};")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(0, 0, 0, 0)

        self.log_count_lbl = _label("共 0 行日誌", C["overlay0"])
        tb_layout.addWidget(self.log_count_lbl)
        tb_layout.addStretch()

        self.auto_scroll_cb = QCheckBox("自動捲動")
        self.auto_scroll_cb.setChecked(True)
        self.auto_scroll_cb.setFont(_font(10))
        self.auto_scroll_cb.setStyleSheet(f"""
            QCheckBox {{
                color: {C['overlay0']};
                background: transparent;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid {C['surface1']};
                border-radius: 3px;
                background-color: {C['surface0']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {C['blue']};
                border-color: {C['blue']};
            }}
        """)
        tb_layout.addWidget(self.auto_scroll_cb)

        clear_btn = QPushButton("清除日誌")
        clear_btn.setFont(_font(10))
        clear_btn.setFixedHeight(30)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['surface0']};
                color: {C['text']};
                border: none;
                border-radius: 4px;
                padding: 0 10px;
            }}
            QPushButton:hover {{ background-color: {C['surface1']}; }}
        """)
        clear_btn.clicked.connect(self._clear_log)
        tb_layout.addWidget(clear_btn)
        layout.addWidget(toolbar)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont(FONT_MONO, 10))
        self.log_box.setStyleSheet(f"""
            QTextEdit {{
                background-color: {C['crust']};
                color: {C['text']};
                border: none;
                padding: 4px;
            }}
            {_scroll_style()}
        """)
        layout.addWidget(self.log_box, 1)

        # 顏色對應
        self._log_colors = {
            "INFO":  C["blue"],
            "TRADE": C["green"],
            "WARN":  C["yellow"],
            "ERROR": C["red"],
            "DEBUG": C["overlay0"],
        }

    def _clear_log(self):
        self.log_box.clear()
        self._log_lines = 0
        self.log_count_lbl.setText("共 0 行日誌")

    # ══════════════════════════════════════════
    #  交易紀錄頁
    # ══════════════════════════════════════════

    def _build_trades(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(14, 10, 14, 14)
        layout.setSpacing(4)

        toolbar = QWidget()
        toolbar.setStyleSheet(f"background-color: {C['base']};")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(0, 0, 0, 0)

        self.trades_summary = _label("共 0 筆 ／ 買入 0 筆 ／ 賣出 0 筆", C["overlay0"])
        tb_layout.addWidget(self.trades_summary)
        tb_layout.addStretch()

        clear_btn = QPushButton("清除紀錄")
        clear_btn.setFont(_font(10))
        clear_btn.setFixedHeight(30)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['surface0']};
                color: {C['text']};
                border: none;
                border-radius: 4px;
                padding: 0 10px;
            }}
            QPushButton:hover {{ background-color: {C['surface1']}; }}
        """)
        clear_btn.clicked.connect(self._clear_trades)
        tb_layout.addWidget(clear_btn)
        layout.addWidget(toolbar)

        cols = ["時間", "代號", "名稱", "方向", "價格(元)", "張數", "備註"]
        self.trades_table = QTableWidget(0, len(cols))
        self.trades_table.setHorizontalHeaderLabels(cols)
        self.trades_table.setStyleSheet(_table_style())
        self.trades_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trades_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.trades_table.verticalHeader().setVisible(False)
        self.trades_table.horizontalHeader().setStretchLastSection(True)

        widths = [80, 65, 80, 65, 90, 60, 200]
        for i, w in enumerate(widths):
            self.trades_table.setColumnWidth(i, w)
        self.trades_table.verticalHeader().setDefaultSectionSize(26)

        layout.addWidget(self.trades_table, 1)

    def _clear_trades(self):
        self.trades_table.setRowCount(0)
        self._trade_count = 0
        self._buy_count = 0
        self._sell_count = 0
        self._update_trade_summary()

    # ══════════════════════════════════════════
    #  啟動 / 停止交易
    # ══════════════════════════════════════════

    def _start_trading(self):
        self.cfg = self._collect_config()
        if not self.cfg.get_markets():
            QMessageBox.warning(self, "市場未選擇", "請至少選擇上市或上櫃！")
            return

        self.engine = TradingEngine(
            config=self.cfg,
            on_log=lambda lvl, msg: LOG_Q.put((lvl, msg)),
            on_trade=self._on_trade,
            on_status=lambda s: None,
        )
        self.engine.start()
        self._running = True

        self.status_dot.setStyleSheet(f"color: {C['green']}; background: transparent;")
        self.status_text.setText("交易中")
        self.status_text.setStyleSheet(f"color: {C['green']}; background: transparent;")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._switch_tab("monitor")

    def _stop_trading(self):
        if self.engine:
            threading.Thread(target=self.engine.stop, daemon=True).start()
        self._running = False
        self.status_dot.setStyleSheet(f"color: {C['red']}; background: transparent;")
        self.status_text.setText("已停止")
        self.status_text.setStyleSheet(f"color: {C['overlay0']}; background: transparent;")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def _on_trade(self, d: dict):
        QTimer.singleShot(0, lambda: self._append_trade(d))

    # ══════════════════════════════════════════
    #  輪詢更新
    # ══════════════════════════════════════════

    def _start_polling(self):
        self._log_timer = QTimer()
        self._log_timer.timeout.connect(self._poll_log)
        self._log_timer.start(150)

        self._monitor_timer = QTimer()
        self._monitor_timer.timeout.connect(self._poll_monitor)
        self._monitor_timer.start(1200)

    def _poll_log(self):
        MAX_LINES = 600
        try:
            while True:
                lvl, msg = LOG_Q.get_nowait()
                self._append_log(lvl, msg)
        except queue.Empty:
            pass
        if self._log_lines > MAX_LINES:
            cursor = self.log_box.textCursor()
            from PyQt6.QtGui import QTextCursor
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(QTextCursor.MoveOperation.Down,
                                QTextCursor.MoveMode.KeepAnchor, 100)
            cursor.removeSelectedText()
            self._log_lines = max(0, self._log_lines - 100)

    def _poll_monitor(self):
        if self._running and self.engine:
            summary = self.engine.get_summary()
            self._render_monitor(summary)

    def _append_log(self, level: str, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"{ts} [{level}] {msg}"
        color = self._log_colors.get(level, C["text"])

        bold = level == "TRADE"
        tag_open = f'<b>' if bold else ''
        tag_close = f'</b>' if bold else ''
        html = f'{tag_open}<span style="color:{color};">{line}</span>{tag_close}'
        self.log_box.append(html)

        if self.auto_scroll_cb.isChecked():
            sb = self.log_box.verticalScrollBar()
            sb.setValue(sb.maximum())

        self._log_lines += 1
        self.log_count_lbl.setText(f"共 {self._log_lines} 行日誌")

    def _append_trade(self, d: dict):
        self._trade_count += 1
        action = d["action"]
        if action == "BUY":
            self._buy_count += 1
        else:
            self._sell_count += 1

        color = C["green"] if action == "BUY" else C["red"]
        label_txt = "↑ 買入" if action == "BUY" else "↓ 賣出"

        row = 0
        self.trades_table.insertRow(row)
        values = [
            d["time"], d["code"], d["name"],
            label_txt,
            f"{d['price']:,.0f}",
            str(d["qty"]), d["note"],
        ]
        for col, val in enumerate(values):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QColor(color))
            self.trades_table.setItem(row, col, item)

        self._update_trade_summary()
        self.stat_trades.setText(str(self._trade_count))

    def _update_trade_summary(self):
        self.trades_summary.setText(
            f"共 {self._trade_count} 筆 ／ 買入 {self._buy_count} 筆 ／ 賣出 {self._sell_count} 筆"
        )
        self.stat_trades.setText(str(self._trade_count))

    def _render_monitor(self, summary: list):
        pos_cnt  = sum(1 for s in summary if s["qty"] > 0)
        pend_cnt = sum(1 for s in summary if s["pending"])
        self.stat_watching.setText(str(len(summary)))
        self.stat_positions.setText(str(pos_cnt))
        self.stat_pending.setText(str(pend_cnt))

        threshold = self.cfg.volume_spike_sell_threshold

        STATUS_COLOR = {
            "已完成": C["overlay0"],
            "持倉中": C["green"],
            "委託中": C["yellow"],
            "監控中": C["blue"],
            "等待":   C["overlay0"],
        }

        for s in summary:
            if s["blocked"]:
                status = "已完成"
            elif s["qty"] > 0:
                status = "持倉中"
            elif s["pending"]:
                status = "委託中"
            elif s["candle"] > 0:
                status = "監控中"
            else:
                status = "等待"

            color = QColor(STATUS_COLOR[status])
            vol_color = QColor(C["red"]) if s["vol_1s"] > threshold else color
            candle_txt = f"第 {s['candle']} 根" if s["candle"] > 0 else "—"
            vol_txt = str(s["vol_1s"])
            vals = [s["code"], s["name"], candle_txt,
                    str(s["qty"]), "是" if s["pending"] else "—",
                    vol_txt, status]

            if s["code"] in self._monitor_rows:
                row = self._monitor_rows[s["code"]]
            else:
                row = self.monitor_table.rowCount()
                self.monitor_table.insertRow(row)
                self._monitor_rows[s["code"]] = row

            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                c_use = vol_color if col == 5 else color
                item.setForeground(c_use)
                self.monitor_table.setItem(row, col, item)


# ──────────────────────────────────────────────────────────────
#  Entry point (保留給直接執行測試用)
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    win = App()
    win.show()
    sys.exit(app.exec())
