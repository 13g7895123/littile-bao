"""
gui.py — 打板策略系統 主視窗
使用 PyQt6，介面對應 S__5456203.jpg 設計稿。
"""
from __future__ import annotations
import queue
import threading
from decimal import Decimal
from typing import Dict, Optional
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QLineEdit, QCheckBox, QScrollArea, QTextEdit,
    QTableWidget, QTableWidgetItem,
    QMessageBox, QHBoxLayout, QVBoxLayout, QComboBox,
)
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QFont, QBrush

from config import TradingConfig
from engine import TradingEngine

# ──────────────────────────────────────────────
#  配色（暗色交易終端風格）
# ──────────────────────────────────────────────
C = {
    "bg":       "#0d1117",
    "panel":    "#161b22",
    "header":   "#161b22",
    "sidebar":  "#0d1117",
    "surface":  "#21262d",
    "border":   "#30363d",
    "text":     "#e6edf3",
    "subtext":  "#8b949e",
    "green":    "#3fb950",
    "green_l":  "#56d364",
    "red":      "#f85149",
    "red_l":    "#ff7b72",
    "blue":     "#58a6ff",
    "blue_l":   "#79c0ff",
    "yellow":   "#d29922",
    "yellow_l": "#e3b341",
    "orange":   "#f0883e",
    "purple":   "#bc8cff",
    # status badge backgrounds
    "badge_ready":  "#4d3800",
    "badge_in":     "#033a16",
    "badge_out":    "#3d1a78",
    "badge_cancel": "#4a0900",
    "badge_dim":    "#1c2128",
    "badge_order":  "#1a3a5c",
}

LOG_Q: queue.Queue = queue.Queue()
FONT_MAIN = "微軟正黑體"
FONT_MONO = "Consolas"


# ──────────────────────────────────────────────
#  基礎工具
# ──────────────────────────────────────────────

def _font(size: int = 10, bold: bool = False) -> QFont:
    f = QFont(FONT_MAIN, size)
    if bold:
        f.setBold(True)
    return f


def _label(text: str, color: str = None, size: int = 10, bold: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(_font(size, bold))
    lbl.setStyleSheet(f"color: {color or C['text']}; background: transparent;")
    return lbl


def _entry(width: int = 90, password: bool = False) -> QLineEdit:
    e = QLineEdit()
    e.setFixedWidth(width)
    e.setFixedHeight(26)
    e.setFont(_font(9))
    if password:
        e.setEchoMode(QLineEdit.EchoMode.Password)
    e.setStyleSheet(f"""
        QLineEdit {{
            background-color: {C['surface']};
            color: {C['text']};
            border: 1px solid {C['border']};
            border-radius: 4px;
            padding: 2px 6px;
        }}
        QLineEdit:focus {{ border: 1px solid {C['blue']}; }}
    """)
    return e


def _combo(items: list, width: int = 90) -> QComboBox:
    cb = QComboBox()
    cb.setFixedWidth(width)
    cb.setFixedHeight(26)
    cb.setFont(_font(9))
    cb.addItems(items)
    cb.setStyleSheet(f"""
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
    """)
    return cb


def _checkbox(text: str, size: int = 9) -> QCheckBox:
    cb = QCheckBox(text)
    cb.setFont(_font(size))
    cb.setStyleSheet(f"""
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
    """)
    return cb


def _divider() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background-color: {C['border']};")
    return f


def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(_font(9, bold=True))
    lbl.setStyleSheet(
        f"color: {C['subtext']}; background: transparent; padding: 8px 0 3px 0;"
    )
    return lbl


def _sep_bar() -> QLabel:
    lbl = QLabel("|")
    lbl.setStyleSheet(f"color: {C['border']}; background: transparent;")
    lbl.setFont(_font(9))
    return lbl


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
    f = QFrame()
    f.setStyleSheet(f"""
        QFrame {{
            background-color: {C['panel']};
            border: 1px solid {C['border']};
            border-radius: 6px;
        }}
    """)
    return f


# ──────────────────────────────────────────────
#  ToggleButton — iOS 風格
# ──────────────────────────────────────────────

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
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill = QColor(C["green"] if self._on else C["surface"])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(fill))
        p.drawRoundedRect(0, 0, 46, 24, 12, 12)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QPoint(30 if self._on else 16, 12), 9, 9)

    @property
    def value(self) -> bool:
        return self._on

    def set(self, val: bool):
        if self._on != val:
            self._on = val
            self.update()


# ──────────────────────────────────────────────
#  主視窗
# ──────────────────────────────────────────────

class App(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("打板策略系統")
        self.resize(1340, 860)
        self.setMinimumSize(1100, 680)
        self.setStyleSheet(f"background-color: {C['bg']};")

        self.cfg = TradingConfig.load()
        self.engine: Optional[TradingEngine] = None
        self.broker = None  # type: ignore[assignment]  # broker.BrokerAdapter，由 main.py 注入
        self._running = False
        self._trade_count = 0
        self._buy_count = 0
        self._sell_count = 0
        self._realized_pnl = 0.0   # M4：今日已實現損益累計
        self._log_lines = 0
        self._syncing_order_mode_control = False

        self._fields: Dict[str, QLineEdit] = {}
        self._checks: Dict[str, QCheckBox] = {}
        self._toggles: Dict[str, ToggleButton] = {}
        self._combos: Dict[str, QComboBox] = {}
        self._monitor_rows: Dict[str, int] = {}

        self._log_colors = {
            "INFO":  C["blue"],
            "TRADE": C["green"],
            "WARN":  C["yellow_l"],
            "ERROR": C["red"],
            "DEBUG": C["subtext"],
        }

        self._build_ui()
        self._apply_config(self.cfg)
        self._start_polling()

    # ══════════════════════════════════════════
    #  建立 UI
    # ══════════════════════════════════════════

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._build_header(root)
        self._build_body(root)
        self._build_statusbar(root)

    # ── 標題列 ───────────────────────────────

    def _build_header(self, root: QVBoxLayout):
        bar = QFrame()
        bar.setFixedHeight(48)
        bar.setStyleSheet(
            f"background-color: {C['header']};"
            f"border-bottom: 1px solid {C['border']};"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(0)

        title = _label("打板策略系統", C["text"], 13, bold=True)
        lay.addWidget(title)
        lay.addSpacing(10)
        self.order_mode_badge = QLabel("模擬下單")
        self.order_mode_badge.setFont(_font(9, bold=True))
        self.order_mode_badge.setFixedHeight(24)
        self.order_mode_badge.setContentsMargins(10, 0, 10, 0)
        lay.addWidget(self.order_mode_badge)
        lay.addSpacing(28)

        # 分頁按鈕
        self._tab_btns: Dict[str, QLabel] = {}
        tabs = [
            ("dashboard", "儀表板"),
            ("settings",  "策略設定"),
            ("orders",    "委託/成交"),
            ("positions", "持倉部位"),
            ("events",    "事件日誌"),
            ("risk",      "風控設定"),
        ]
        for key, text in tabs:
            btn = QLabel(text)
            btn.setFont(_font(10))
            btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn.setFixedHeight(48)
            btn.setContentsMargins(14, 0, 14, 0)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.mousePressEvent = lambda _e, k=key: self._switch_tab(k)
            lay.addWidget(btn)
            self._tab_btns[key] = btn

        lay.addStretch()

        # 策略狀態徽章
        self.strategy_badge = QPushButton("● 策略已啟用")
        self.strategy_badge.setFont(_font(9, bold=True))
        self.strategy_badge.setFixedHeight(28)
        self.strategy_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_badge_active(True)
        lay.addWidget(self.strategy_badge)
        lay.addSpacing(16)

        # 時鐘
        self.clock_lbl = QLabel("00:00:00")
        self.clock_lbl.setFont(QFont(FONT_MONO, 12, QFont.Weight.Bold))
        self.clock_lbl.setStyleSheet(f"color: {C['text']}; background: transparent;")
        lay.addWidget(self.clock_lbl)

        timer = QTimer(self)
        timer.timeout.connect(self._tick_clock)
        timer.start(1000)
        self._tick_clock()

        root.addWidget(bar)

    def _tick_clock(self):
        self.clock_lbl.setText(datetime.now().strftime("%H:%M:%S"))

    def _set_badge_active(self, active: bool):
        if active:
            self.strategy_badge.setStyleSheet(f"""
                QPushButton {{
                    background-color: {C['badge_in']};
                    color: {C['green_l']};
                    border: 1px solid {C['green']};
                    border-radius: 4px;
                    padding: 0 12px;
                }}
            """)
            self.strategy_badge.setText("● 策略已啟用")
        else:
            self.strategy_badge.setStyleSheet(f"""
                QPushButton {{
                    background-color: {C['surface']};
                    color: {C['subtext']};
                    border: 1px solid {C['border']};
                    border-radius: 4px;
                    padding: 0 12px;
                }}
            """)
            self.strategy_badge.setText("● 策略已停用")

    def _switch_tab(self, key: str):
        for k, btn in self._tab_btns.items():
            if k == key:
                btn.setStyleSheet(f"""
                    color: {C['blue_l']};
                    background: transparent;
                    border-bottom: 2px solid {C['blue_l']};
                    padding-left: 14px; padding-right: 14px;
                """)
            else:
                btn.setStyleSheet(f"""
                    color: {C['subtext']};
                    background: transparent;
                    border-bottom: 2px solid transparent;
                    padding-left: 14px; padding-right: 14px;
                """)
        for k, w in self._pages.items():
            w.setVisible(k == key)

    # ── 主體 ─────────────────────────────────

    def _build_body(self, root: QVBoxLayout):
        body = QWidget()
        body.setStyleSheet(f"background-color: {C['bg']};")
        lay = QHBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._build_sidebar(lay)

        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background-color: {C['border']};")
        lay.addWidget(sep)

        # 右側分頁容器
        pages_w = QWidget()
        pages_w.setStyleSheet(f"background-color: {C['bg']};")
        pages_lay = QVBoxLayout(pages_w)
        pages_lay.setContentsMargins(0, 0, 0, 0)
        pages_lay.setSpacing(0)

        self._pages: Dict[str, QWidget] = {}
        for key in ("dashboard", "settings", "orders", "positions", "events", "risk"):
            page = QWidget()
            page.setStyleSheet(f"background-color: {C['bg']};")
            pages_lay.addWidget(page)
            self._pages[key] = page

        self._build_dashboard(self._pages["dashboard"])
        self._build_settings_page(self._pages["settings"])
        self._build_placeholder(self._pages["orders"],    "委託/成交")
        self._build_placeholder(self._pages["positions"], "持倉部位")
        self._build_placeholder(self._pages["events"],    "事件日誌")
        self._build_placeholder(self._pages["risk"],      "風控設定")

        lay.addWidget(pages_w, 1)
        root.addWidget(body, 1)
        self._switch_tab("dashboard")

    # ══════════════════════════════════════════
    #  左側邊欄（策略設定）
    # ══════════════════════════════════════════

    def _build_sidebar(self, body_lay: QHBoxLayout):
        sidebar = QFrame()
        sidebar.setFixedWidth(270)
        sidebar.setStyleSheet(f"background-color: {C['sidebar']}; border: none;")
        outer = QVBoxLayout(sidebar)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 邊欄標題
        hdr = QFrame()
        hdr.setFixedHeight(40)
        hdr.setStyleSheet(
            f"background-color: {C['header']};"
            f"border-bottom: 1px solid {C['border']};"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(14, 0, 14, 0)
        icon = QLabel("⚙")
        icon.setFont(QFont("Segoe UI Emoji", 11))
        icon.setStyleSheet(f"color: {C['subtext']}; background: transparent;")
        hl.addWidget(icon)
        hl.addSpacing(6)
        hl.addWidget(_label("策略設定", C["text"], 10, bold=True))
        hl.addStretch()
        outer.addWidget(hdr)

        # 可捲動設定區
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background-color: {C['sidebar']}; }}"
            + _scroll_style()
        )
        content = QWidget()
        content.setStyleSheet(f"background-color: {C['sidebar']};")
        form = QVBoxLayout(content)
        form.setContentsMargins(14, 10, 14, 10)
        form.setSpacing(0)

        # ── 啟用策略
        row = QHBoxLayout()
        row.addWidget(_label("啟用策略", C["text"], 10))
        row.addStretch()
        tog = ToggleButton(initial=True)
        tog.toggled.connect(self._on_strategy_toggle)
        self._toggles["strategy_enabled"] = tog
        row.addWidget(tog)
        form.addLayout(row)
        form.addSpacing(10)
        form.addWidget(_divider())

        # ── 市場選擇
        form.addWidget(_section_title("市場選擇"))
        mkt_row = QHBoxLayout()
        self._checks["market_twse"] = _checkbox("上市")
        self._checks["market_tpex"] = _checkbox("上櫃")
        mkt_row.addWidget(self._checks["market_twse"])
        mkt_row.addSpacing(14)
        mkt_row.addWidget(self._checks["market_tpex"])
        mkt_row.addStretch()
        form.addLayout(mkt_row)
        form.addSpacing(8)
        form.addWidget(_divider())

        # ── 交易設定
        form.addWidget(_section_title("交易設定"))
        self._sf(form, "每檔金額", "per_stock_amount", suffix="元", w=90)
        self._sf(form, "每日最大交易檔數", "daily_max_trades", suffix="檔", w=45)
        self._checks["dry_run_mode"] = _checkbox("模擬下單（不送出真實委託）")
        self._checks["dry_run_mode"].toggled.connect(self._on_order_mode_toggled)
        form.addWidget(self._checks["dry_run_mode"])
        form.addSpacing(4)
        form.addWidget(_divider())

        # ── 時間設定
        form.addWidget(_section_title("時間設定"))
        self._sf(form, "開始時間", "start_time", w=72)
        self._sf(form, "結束時間", "entry_before_time", w=72)
        form.addSpacing(4)
        form.addWidget(_divider())

        # ── 進場條件
        form.addWidget(_section_title("進場條件"))

        ask_row = QHBoxLayout()
        ask_row.addWidget(_label("漲停委賣張數 <", C["subtext"], 9))
        ask_row.addStretch()
        self._fields["ask_queue_threshold"] = _entry(55)
        ask_row.addWidget(self._fields["ask_queue_threshold"])
        ask_row.addSpacing(4)
        ask_row.addWidget(_label("張", C["subtext"], 9))
        form.addLayout(ask_row)
        form.addSpacing(6)

        form.addWidget(_label("只做起漲K", C["subtext"], 9))
        k_row = QHBoxLayout()
        k_row.addSpacing(4)
        self._checks["candle_k1"] = _checkbox("第一根")
        self._checks["candle_k2"] = _checkbox("第二根")
        k_row.addWidget(self._checks["candle_k1"])
        k_row.addSpacing(10)
        k_row.addWidget(self._checks["candle_k2"])
        k_row.addStretch()
        form.addLayout(k_row)
        form.addSpacing(6)

        vol_row = QHBoxLayout()
        vol_row.addWidget(_label("昨日成交量 >", C["subtext"], 9))
        vol_row.addStretch()
        self._fields["daily_volume_min"] = _entry(65)
        vol_row.addWidget(self._fields["daily_volume_min"])
        vol_row.addSpacing(4)
        vol_row.addWidget(_label("張", C["subtext"], 9))
        form.addLayout(vol_row)
        form.addSpacing(6)

        form.addWidget(_label("股價區間", C["subtext"], 9))
        pr_row = QHBoxLayout()
        pr_row.addSpacing(4)
        self._fields["price_min"] = _entry(50)
        pr_row.addWidget(self._fields["price_min"])
        pr_row.addSpacing(4)
        pr_row.addWidget(_label("~", C["subtext"], 9))
        pr_row.addSpacing(4)
        self._fields["price_max"] = _entry(50)
        pr_row.addWidget(self._fields["price_max"])
        pr_row.addSpacing(4)
        pr_row.addWidget(_label("元", C["subtext"], 9))
        pr_row.addStretch()
        form.addLayout(pr_row)
        form.addSpacing(6)
        form.addWidget(_divider())

        # ── 排除條件
        form.addWidget(_section_title("排除條件"))
        ex1 = QHBoxLayout()
        self._checks["excl_disposal"]  = _checkbox("處置股")
        self._checks["excl_attention"] = _checkbox("注意股")
        self._checks["excl_daytrade"]  = _checkbox("限當沖股")
        ex1.addWidget(self._checks["excl_disposal"])
        ex1.addSpacing(6)
        ex1.addWidget(self._checks["excl_attention"])
        ex1.addSpacing(6)
        ex1.addWidget(self._checks["excl_daytrade"])
        ex1.addStretch()
        form.addLayout(ex1)
        form.addSpacing(4)
        self._checks["excl_open_limit"] = _checkbox("開盤漲停股票不追")
        form.addWidget(self._checks["excl_open_limit"])
        form.addSpacing(4)
        self._checks["excl_sealed"] = _checkbox("當天封板後不再進場")
        form.addWidget(self._checks["excl_sealed"])
        form.addSpacing(6)
        form.addWidget(_divider())

        # ── 出場條件
        form.addWidget(_section_title("出場條件"))

        ex_row1 = QHBoxLayout()
        ex_row1.addWidget(_label("委賣價變漲停價", C["subtext"], 9))
        ex_row1.addStretch()
        self._combos["exit_method1"] = _combo(["市價賣出", "限價賣出"], 88)
        ex_row1.addWidget(self._combos["exit_method1"])
        form.addLayout(ex_row1)
        form.addSpacing(6)

        sp_row = QHBoxLayout()
        sp_row.addWidget(_label("1秒成交量 >", C["subtext"], 9))
        sp_row.addStretch()
        self._fields["volume_spike_sell_threshold"] = _entry(55)
        sp_row.addWidget(self._fields["volume_spike_sell_threshold"])
        sp_row.addSpacing(4)
        sp_row.addWidget(_label("張", C["subtext"], 9))
        form.addLayout(sp_row)
        form.addSpacing(6)

        ex_row3 = QHBoxLayout()
        ex_row3.addWidget(_label("委託排隊中過爆量", C["subtext"], 9))
        ex_row3.addStretch()
        self._combos["exit_method3"] = _combo(["取消委託", "保留委託"], 88)
        ex_row3.addWidget(self._combos["exit_method3"])
        form.addLayout(ex_row3)

        form.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # 底部按鈕列
        btn_bar = QFrame()
        btn_bar.setFixedHeight(52)
        btn_bar.setStyleSheet(
            f"background-color: {C['header']};"
            f"border-top: 1px solid {C['border']};"
        )
        bl = QHBoxLayout(btn_bar)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(8)

        reset_btn = QPushButton("重置設定")
        reset_btn.setFont(_font(9, bold=True))
        reset_btn.setFixedHeight(34)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['surface']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 4px;
            }}
            QPushButton:hover {{ background-color: #2d333b; }}
        """)
        reset_btn.clicked.connect(self._reset_settings)
        bl.addWidget(reset_btn, 1)

        save_btn = QPushButton("儲存設定")
        save_btn.setFont(_font(9, bold=True))
        save_btn.setFixedHeight(34)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['blue']};
                color: #ffffff;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{ background-color: {C['blue_l']}; }}
        """)
        save_btn.clicked.connect(self._save_settings)
        bl.addWidget(save_btn, 1)

        outer.addWidget(btn_bar)
        body_lay.addWidget(sidebar)

    def _sf(self, form: QVBoxLayout, lbl: str, key: str,
            suffix: str = "", w: int = 90):
        """sidebar 單行欄位"""
        row = QHBoxLayout()
        row.addWidget(_label(lbl, C["subtext"], 9))
        row.addStretch()
        self._fields[key] = _entry(w)
        row.addWidget(self._fields[key])
        if suffix:
            row.addSpacing(4)
            row.addWidget(_label(suffix, C["subtext"], 9))
        form.addLayout(row)
        form.addSpacing(4)

    # ══════════════════════════════════════════
    #  儀表板頁
    # ══════════════════════════════════════════

    def _build_dashboard(self, parent: QWidget):
        lay = QVBoxLayout(parent)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        self._build_stats_row(lay)
        self._build_mid_row(lay)
        self._build_bot_row(lay)

    # ── 統計卡列 ─────────────────────────────

    def _build_stats_row(self, lay: QVBoxLayout):
        row = QWidget()
        row.setFixedHeight(76)
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        defs = [
            ("今日損益",    "stat_pnl_today",  "+0",     C["green"]),
            ("今日報酬率",  "stat_return",     "+0.00%", C["green"]),
            ("已實現損益",  "stat_realized",   "+0",     C["green"]),
            ("持倉檔數",    "stat_positions",  "0",      C["text"]),
            ("今日交易檔數","stat_trade_cnt",  "0 / 0",  C["text"]),
            ("可用額度",    "stat_available",  "0",      C["text"]),
        ]
        for label_txt, attr, init, color in defs:
            frame = _panel_frame()
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(14, 6, 14, 6)
            fl.setSpacing(3)
            fl.addWidget(_label(label_txt, C["subtext"], 9))
            val_lbl = QLabel(init)
            val_lbl.setFont(QFont(FONT_MAIN, 18, QFont.Weight.Bold))
            val_lbl.setStyleSheet(f"color: {color}; background: transparent;")
            fl.addWidget(val_lbl)
            setattr(self, attr, val_lbl)
            rl.addWidget(frame, 1)

        lay.addWidget(row)

    # ── 中段：即時監控 + 事件日誌 ────────────

    def _build_mid_row(self, lay: QVBoxLayout):
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        # 即時監控
        mon = _panel_frame()
        ml = QVBoxLayout(mon)
        ml.setContentsMargins(10, 8, 10, 8)
        ml.setSpacing(6)

        mh = QHBoxLayout()
        mh.addWidget(_label("即時監控", C["text"], 10, bold=True))
        mh.addStretch()
        ml.addLayout(mh)

        cols = ["代碼", "名稱", "價格", "漲跌", "漲跌幅",
                "委賣張數", "1秒成交量", "起漲K", "狀態", "動作"]
        self.monitor_table = QTableWidget(0, len(cols))
        self.monitor_table.setHorizontalHeaderLabels(cols)
        self.monitor_table.setStyleSheet(_table_style())
        self.monitor_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.monitor_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.monitor_table.verticalHeader().setVisible(False)
        self.monitor_table.setShowGrid(True)
        self.monitor_table.horizontalHeader().setStretchLastSection(False)
        self.monitor_table.verticalHeader().setDefaultSectionSize(28)
        for i, w in enumerate([52, 60, 58, 52, 62, 68, 72, 60, 72, 52]):
            self.monitor_table.setColumnWidth(i, w)
        ml.addWidget(self.monitor_table, 1)
        rl.addWidget(mon, 3)

        # 事件日誌
        ev = _panel_frame()
        el = QVBoxLayout(ev)
        el.setContentsMargins(10, 8, 10, 8)
        el.setSpacing(6)

        eh = QHBoxLayout()
        eh.addWidget(_label("事件日誌", C["text"], 10, bold=True))
        eh.addStretch()
        clr_btn = QPushButton("清除")
        clr_btn.setFont(_font(9))
        clr_btn.setFixedSize(46, 22)
        clr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clr_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['red']};
                color: #ffffff;
                border: none;
                border-radius: 3px;
            }}
            QPushButton:hover {{ background-color: {C['red_l']}; }}
        """)
        clr_btn.clicked.connect(self._clear_log)
        eh.addWidget(clr_btn)
        el.addLayout(eh)

        self.event_log = QTextEdit()
        self.event_log.setReadOnly(True)
        self.event_log.setFont(QFont(FONT_MAIN, 9))
        self.event_log.setStyleSheet(f"""
            QTextEdit {{
                background-color: {C['bg']};
                color: {C['text']};
                border: none;
                border-radius: 4px;
                padding: 4px;
            }}
            {_scroll_style()}
        """)
        el.addWidget(self.event_log, 1)
        rl.addWidget(ev, 1)

        lay.addWidget(row, 3)

    # ── 下段：持倉 + 委託 + 成交 ─────────────

    def _build_bot_row(self, lay: QVBoxLayout):
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        # 持倉部位
        pos = _panel_frame()
        pl = QVBoxLayout(pos)
        pl.setContentsMargins(10, 8, 10, 8)
        pl.setSpacing(6)
        ph = QHBoxLayout()
        ph.addWidget(_label("持倉部位", C["text"], 10, bold=True))
        ph.addStretch()
        pl.addLayout(ph)
        pos_cols = ["代碼", "名稱", "持股數", "成本價", "現價", "損益", "損益率", "狀態"]
        self.positions_table = QTableWidget(0, len(pos_cols))
        self.positions_table.setHorizontalHeaderLabels(pos_cols)
        self.positions_table.setStyleSheet(_table_style())
        self.positions_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.positions_table.verticalHeader().setVisible(False)
        self.positions_table.setShowGrid(True)
        self.positions_table.horizontalHeader().setStretchLastSection(True)
        self.positions_table.verticalHeader().setDefaultSectionSize(26)
        for i, w in enumerate([48, 55, 52, 52, 52, 58, 58, 52]):
            self.positions_table.setColumnWidth(i, w)
        pl.addWidget(self.positions_table, 1)
        self.pos_summary_lbl = _label("小計 (0)", C["subtext"], 9)
        self.pos_pnl_lbl = _label("+0  +0.00%", C["green"], 9, bold=True)
        ps_row = QHBoxLayout()
        ps_row.addWidget(self.pos_summary_lbl)
        ps_row.addStretch()
        ps_row.addWidget(self.pos_pnl_lbl)
        pl.addLayout(ps_row)
        rl.addWidget(pos, 2)

        # 委託狀態
        ord_f = _panel_frame()
        ol = QVBoxLayout(ord_f)
        ol.setContentsMargins(10, 8, 10, 8)
        ol.setSpacing(6)
        oh = QHBoxLayout()
        oh.addWidget(_label("委託狀態", C["text"], 10, bold=True))
        oh.addStretch()
        ol.addLayout(oh)
        ord_cols = ["代碼", "名稱", "委託類別", "價格", "數量", "狀態", "來源"]
        self.orders_table = QTableWidget(0, len(ord_cols))
        self.orders_table.setHorizontalHeaderLabels(ord_cols)
        self.orders_table.setStyleSheet(_table_style())
        self.orders_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.orders_table.verticalHeader().setVisible(False)
        self.orders_table.setShowGrid(True)
        self.orders_table.horizontalHeader().setStretchLastSection(True)
        self.orders_table.verticalHeader().setDefaultSectionSize(26)
        for i, w in enumerate([48, 55, 62, 58, 46, 48, 46]):
            self.orders_table.setColumnWidth(i, w)
        ol.addWidget(self.orders_table, 1)
        rl.addWidget(ord_f, 2)

        # 成交記錄
        trd_f = _panel_frame()
        tl = QVBoxLayout(trd_f)
        tl.setContentsMargins(10, 8, 10, 8)
        tl.setSpacing(6)
        th = QHBoxLayout()
        th.addWidget(_label("成交記錄", C["text"], 10, bold=True))
        th.addStretch()
        tl.addLayout(th)
        trd_cols = ["時間", "代碼", "名稱", "類別", "價格", "數量", "損益"]
        self.trades_table = QTableWidget(0, len(trd_cols))
        self.trades_table.setHorizontalHeaderLabels(trd_cols)
        self.trades_table.setStyleSheet(_table_style())
        self.trades_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trades_table.verticalHeader().setVisible(False)
        self.trades_table.setShowGrid(True)
        self.trades_table.horizontalHeader().setStretchLastSection(True)
        self.trades_table.verticalHeader().setDefaultSectionSize(26)
        for i, w in enumerate([60, 48, 55, 44, 55, 44, 55]):
            self.trades_table.setColumnWidth(i, w)
        tl.addWidget(self.trades_table, 1)
        self.trd_summary_lbl = _label("小計", C["subtext"], 9)
        self.trd_pnl_lbl = _label("+0", C["green"], 9, bold=True)
        ts_row = QHBoxLayout()
        ts_row.addWidget(self.trd_summary_lbl)
        ts_row.addStretch()
        ts_row.addWidget(self.trd_pnl_lbl)
        tl.addLayout(ts_row)
        rl.addWidget(trd_f, 2)

        lay.addWidget(row, 2)

    # ── 其他分頁（佔位）───────────────────────

    def _build_settings_page(self, parent: QWidget):
        lay = QVBoxLayout(parent)
        lay.setContentsMargins(24, 24, 24, 24)
        lbl = _label("策略設定 — 請使用左側面板調整", C["subtext"], 12)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addStretch()
        lay.addWidget(lbl)
        lay.addStretch()

    def _build_placeholder(self, parent: QWidget, title: str):
        lay = QVBoxLayout(parent)
        lay.setContentsMargins(24, 24, 24, 24)
        lbl = _label(title, C["subtext"], 12)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addStretch()
        lay.addWidget(lbl)
        lay.addStretch()

    # ── 狀態列 ───────────────────────────────

    def _build_statusbar(self, root: QVBoxLayout):
        bar = QFrame()
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            f"background-color: {C['header']};"
            f"border-top: 1px solid {C['border']};"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(0)

        self.broker_dot = QLabel("●")
        self.broker_dot.setFont(_font(8))
        self.broker_dot.setStyleSheet(f"color: {C['subtext']}; background: transparent;")
        lay.addWidget(self.broker_dot)
        lay.addSpacing(4)
        self.broker_status_lbl = _label("券商狀態：未連線", C["subtext"], 9)
        lay.addWidget(self.broker_status_lbl)
        lay.addSpacing(20)
        lay.addWidget(_sep_bar())
        lay.addSpacing(20)
        lay.addWidget(_label("行情延遲：0.15秒", C["subtext"], 9))
        lay.addSpacing(20)
        lay.addWidget(_sep_bar())
        lay.addSpacing(20)

        self.strategy_dot = QLabel("●")
        self.strategy_dot.setFont(_font(8))
        self.strategy_dot.setStyleSheet(f"color: {C['red']}; background: transparent;")
        lay.addWidget(self.strategy_dot)
        lay.addSpacing(4)
        self.strategy_status_lbl = _label("策略狀態：已停止", C["subtext"], 9)
        lay.addWidget(self.strategy_status_lbl)

        lay.addStretch()
        lay.addWidget(_label("版本：1.0.0", C["subtext"], 9))
        root.addWidget(bar)

    # ══════════════════════════════════════════
    #  設定讀寫
    # ══════════════════════════════════════════

    def _apply_config(self, cfg: TradingConfig):
        f = self._fields
        f["per_stock_amount"].setText(str(cfg.per_stock_amount))
        f["daily_max_trades"].setText(str(cfg.daily_max_trades))
        f["start_time"].setText("09:00")
        f["entry_before_time"].setText(cfg.entry_before_time)
        f["ask_queue_threshold"].setText(str(cfg.ask_queue_threshold))
        f["daily_volume_min"].setText(str(cfg.daily_volume_min))
        f["price_min"].setText(str(int(cfg.price_min)))
        f["price_max"].setText(str(int(cfg.price_max)))
        f["volume_spike_sell_threshold"].setText(str(cfg.volume_spike_sell_threshold))

        c = self._checks
        c["market_twse"].setChecked(cfg.market_twse)
        c["market_tpex"].setChecked(cfg.market_tpex)
        c["candle_k1"].setChecked(cfg.candle_limit >= 1)
        c["candle_k2"].setChecked(cfg.candle_limit >= 2)
        c["excl_disposal"].setChecked(cfg.f11_enabled)
        c["excl_attention"].setChecked(cfg.f11_enabled)
        c["excl_daytrade"].setChecked(cfg.f11_enabled)
        c["excl_open_limit"].setChecked(cfg.f12_enabled)
        c["excl_sealed"].setChecked(True)
        if "dry_run_mode" in c:
            self._syncing_order_mode_control = True
            c["dry_run_mode"].setChecked(cfg.order_dry_run)
            self._syncing_order_mode_control = False
        self._update_order_mode_badge()

    def _collect_config(self) -> TradingConfig:
        f = self._fields
        c = self._checks

        def ni(k):
            try:
                return int(float(f[k].text()))
            except Exception:
                return 0

        def nf(k):
            try:
                return float(f[k].text())
            except Exception:
                return 0.0

        candle_limit = 0
        if c["candle_k1"].isChecked():
            candle_limit = 1
        if c["candle_k2"].isChecked():
            candle_limit = 2

        f11 = (c["excl_disposal"].isChecked() or
               c["excl_attention"].isChecked() or
               c["excl_daytrade"].isChecked())

        return TradingConfig(
            api_id                        = self.cfg.api_id,
            api_key                       = self.cfg.api_key,
            broker_cert_path              = self.cfg.broker_cert_path,
            f1_enabled                    = True,
            entry_before_time             = f["entry_before_time"].text(),
            ask_queue_threshold           = ni("ask_queue_threshold"),
            market_twse                   = c["market_twse"].isChecked(),
            market_tpex                   = c["market_tpex"].isChecked(),
            per_stock_amount              = ni("per_stock_amount"),
            f4_enabled                    = True,
            f5_enabled                    = True,
            volume_spike_sell_threshold   = ni("volume_spike_sell_threshold"),
            f6_enabled                    = True,
            volume_spike_cancel_threshold = ni("volume_spike_sell_threshold"),
            f7_enabled                    = candle_limit > 0,
            candle_limit                  = candle_limit,
            f8_enabled                    = True,
            daily_volume_min              = ni("daily_volume_min"),
            f9_enabled                    = True,
            price_min                     = nf("price_min"),
            price_max                     = nf("price_max"),
            f10_enabled                   = True,
            ask_price_ratio               = self.cfg.ask_price_ratio,
            entry_volume_confirm          = self.cfg.entry_volume_confirm,
            f11_enabled                   = f11,
            f12_enabled                   = c["excl_open_limit"].isChecked(),
            f13_enabled                   = True,
            daily_max_trades              = ni("daily_max_trades"),
            order_dry_run                 = c["dry_run_mode"].isChecked(),
        )

    def _save_settings(self):
        try:
            self.cfg = self._collect_config()
            self.cfg.save()
            QMessageBox.information(self, "儲存成功", "設定已儲存！")
        except ValueError as e:
            QMessageBox.critical(self, "格式錯誤", f"數字欄位格式有誤：{e}")

    def _reset_settings(self):
        reply = QMessageBox.question(
            self, "還原確認", "確定要還原為預設值？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._apply_config(TradingConfig())

    def _on_order_mode_toggled(self, dry_run: bool) -> None:
        if self._syncing_order_mode_control:
            return
        if self.broker is None or not hasattr(self.broker, "set_dry_run"):
            self._update_order_mode_badge()
            return
        if not dry_run:
            reply = QMessageBox.question(
                self,
                "切換實單確認",
                "切換為實單模式後，策略觸發時會送出真實委託。確定要切換？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._syncing_order_mode_control = True
                self._checks["dry_run_mode"].setChecked(True)
                self._syncing_order_mode_control = False
                self._update_order_mode_badge()
                return
        self.broker.set_dry_run(dry_run)
        self.cfg.order_dry_run = dry_run
        self._update_order_mode_badge()
        self._refresh_broker_status()

    # ══════════════════════════════════════════
    #  策略開關
    # ══════════════════════════════════════════

    def _on_strategy_toggle(self, enabled: bool):
        self._set_badge_active(enabled)
        if enabled:
            self._start_trading()
        else:
            self._stop_trading()

    def _start_trading(self):
        self.cfg = self._collect_config()
        if not self.cfg.get_markets():
            QMessageBox.warning(self, "市場未選擇", "請至少選擇上市或上櫃！")
            self._toggles["strategy_enabled"].set(False)
            self._set_badge_active(False)
            return

        # ── Milestone 3：先載入 SymbolInfo（昨收 / 漲停 / 特殊股）──
        symbol_infos = None
        feed = None
        if self.broker:
            try:
                from broker import DEFAULT_MOCK_INFOS, ScanCriteria, scan_daily
                # M6：依設定的價格區間動態篩選候選股
                crit = ScanCriteria(
                    price_min=Decimal(str(self.cfg.price_min)) if self.cfg.f9_enabled else Decimal("0"),
                    price_max=Decimal(str(self.cfg.price_max)) if self.cfg.f9_enabled else Decimal("999999"),
                    exclude_disposal=self.cfg.f11_enabled,
                    exclude_attention=self.cfg.f11_enabled,
                    exclude_day_trade_restricted=self.cfg.f11_enabled,
                    markets=tuple(self.cfg.get_markets()),
                    min_prev_volume=(self.cfg.daily_volume_min if self.cfg.f8_enabled else 0),
                )
                candidates = scan_daily(DEFAULT_MOCK_INFOS, crit) or DEFAULT_MOCK_INFOS
                default_codes = [i.code for i in candidates]
                symbol_infos = self.broker.load_symbol_info(default_codes)
                feed = self.broker.create_realtime_feed()
                LOG_Q.put(("INFO", f"動態選股完成，候選 {len(default_codes)} 檔"))
            except Exception as e:  # noqa: BLE001
                LOG_Q.put(("WARN", f"載入個股基本資料失敗：{e}"))

        self.engine = TradingEngine(
            config=self.cfg,
            on_log=lambda lvl, msg: LOG_Q.put((lvl, msg)),
            on_trade=self._on_trade,
            on_status=lambda _s: None,
            feed=feed,
            symbol_infos=symbol_infos,
            broker=self.broker,
        )
        # M4：重置今日損益
        self._realized_pnl = 0.0
        self._trade_count = 0
        self._buy_count = 0
        self._sell_count = 0
        self.engine.start()
        self._running = True
        self.strategy_dot.setStyleSheet(f"color: {C['green']}; background: transparent;")
        self.strategy_status_lbl.setText("策略狀態：運行中")
        self.strategy_status_lbl.setStyleSheet(f"color: {C['green']}; background: transparent;")

    def _stop_trading(self):
        if self.engine:
            threading.Thread(target=self.engine.stop, daemon=True).start()
        self._running = False
        self.strategy_dot.setStyleSheet(f"color: {C['red']}; background: transparent;")
        self.strategy_status_lbl.setText("策略狀態：已停止")
        self.strategy_status_lbl.setStyleSheet(
            f"color: {C['subtext']}; background: transparent;"
        )

    def _on_trade(self, d: dict):
        QTimer.singleShot(0, lambda: self._append_trade(d))

    # ══════════════════════════════════════════
    #  券商狀態（Milestone 1）
    # ══════════════════════════════════════════

    def set_broker(self, broker) -> None:
        """由 main.py 注入 broker 適配器，並更新狀態列。"""
        self.broker = broker
        if broker is not None and hasattr(broker, "set_dry_run"):
            try:
                broker.set_dry_run(self.cfg.order_dry_run)
            except Exception:  # noqa: BLE001
                pass
        self._sync_order_mode_control()
        # M5：訂閱委託回報，更新「委託狀態」表
        if broker is not None and hasattr(broker, "on_order"):
            try:
                broker.on_order(self._on_order_event)
            except Exception:  # noqa: BLE001
                pass
        # M6：啟動帳戶輪詢（10 秒一次）
        self._stop_account_polling()
        if broker is not None and hasattr(broker, "account_service"):
            try:
                svc = broker.account_service()
                self._account_svc = svc
                svc.start_polling(self._on_account_snapshot, interval=10.0)
            except Exception:  # noqa: BLE001
                pass
        self._refresh_broker_status()

    def _sync_order_mode_control(self) -> None:
        chk = self._checks.get("dry_run_mode")
        if chk is None:
            return
        self._syncing_order_mode_control = True
        if self.broker is None or not hasattr(self.broker, "dry_run"):
            chk.setChecked(True)
            chk.setEnabled(False)
            chk.setText("模擬下單（Mock 模式）")
        else:
            chk.setEnabled(True)
            chk.setText("模擬下單（不送出真實委託）")
            chk.setChecked(bool(getattr(self.broker, "dry_run", True)))
            self.cfg.order_dry_run = chk.isChecked()
        self._syncing_order_mode_control = False
        self._update_order_mode_badge()

    def _update_order_mode_badge(self) -> None:
        dry_run = True
        if self.broker is not None and hasattr(self.broker, "dry_run"):
            dry_run = bool(getattr(self.broker, "dry_run", True))
        elif "dry_run_mode" in self._checks:
            dry_run = self._checks["dry_run_mode"].isChecked()

        if not hasattr(self, "order_mode_badge"):
            return
        if dry_run:
            self.order_mode_badge.setText("模擬下單")
            self.order_mode_badge.setStyleSheet(f"""
                QLabel {{
                    color: {C['yellow_l']};
                    background-color: {C['badge_ready']};
                    border: 1px solid {C['yellow']};
                    border-radius: 4px;
                    padding: 0 8px;
                }}
            """)
            self.setWindowTitle("打板策略系統 [模擬下單]")
        else:
            self.order_mode_badge.setText("實單模式")
            self.order_mode_badge.setStyleSheet(f"""
                QLabel {{
                    color: #ffffff;
                    background-color: {C['red']};
                    border: 1px solid {C['red_l']};
                    border-radius: 4px;
                    padding: 0 8px;
                }}
            """)
            self.setWindowTitle("打板策略系統 [實單模式]")

    def _stop_account_polling(self) -> None:
        svc = getattr(self, "_account_svc", None)
        if svc is not None:
            try:
                svc.stop()
            except Exception:  # noqa: BLE001
                pass
            self._account_svc = None

    def _on_account_snapshot(self, snap) -> None:
        """從 polling thread 接收 AccountSnapshot，丟回主執行緒繪製。"""
        QTimer.singleShot(0, lambda: self._render_account(snap))

    def _render_account(self, snap) -> None:
        # 持倉表
        self.positions_table.setRowCount(0)
        total_unr = 0.0
        total_cost = 0.0
        for p in snap.positions:
            row = self.positions_table.rowCount()
            self.positions_table.insertRow(row)
            unr = float(p.unrealized_pnl)
            unr_pct = float(p.unrealized_pnl_pct)
            total_unr += unr
            total_cost += float(p.avg_cost) * p.qty * 1000
            color = C["red"] if unr >= 0 else C["green"]
            cells = [
                (p.code, C["text"]),
                (p.name, C["text"]),
                (str(p.qty * 1000), C["text"]),
                (f"{float(p.avg_cost):,.2f}", C["text"]),
                (f"{float(p.last_price):,.2f}", C["text"]),
                (f"{'+' if unr >= 0 else ''}{unr:,.0f}", color),
                (f"{'+' if unr_pct >= 0 else ''}{unr_pct:.2f}%", color),
                ("持有", C["green"]),
            ]
            for col, (val, c) in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(QColor(c))
                self.positions_table.setItem(row, col, item)
        # 統計卡：持倉檔數、可用額度、未實現損益小計
        self.stat_positions.setText(str(len(snap.positions)))
        bp = float(snap.buying_power)
        self.stat_available.setText(f"{bp:,.0f}")
        sign = "+" if total_unr >= 0 else ""
        rate = (total_unr / total_cost * 100) if total_cost > 0 else 0.0
        self.pos_summary_lbl.setText(f"小計 ({len(snap.positions)})")
        self.pos_pnl_lbl.setText(f"{sign}{total_unr:,.0f}  {sign}{rate:.2f}%")
        color = C["red"] if total_unr >= 0 else C["green"]
        self.pos_pnl_lbl.setStyleSheet(f"color:{color};")

    def _on_order_event(self, ev) -> None:
        """從 broker 執行緒接收 OrderEvent，丟回 GUI 主執行緒繪製。"""
        QTimer.singleShot(0, lambda: self._append_order(ev))

    def _append_order(self, ev) -> None:
        # 依 order_id 找既有列；若有則更新狀態欄，否則插入新列
        oid = getattr(ev, "order_id", "")
        row_idx = -1
        for r in range(self.orders_table.rowCount()):
            it = self.orders_table.item(r, 0)
            if it and it.data(Qt.ItemDataRole.UserRole) == oid:
                row_idx = r
                break

        side_txt = "買進" if ev.side.value == "BUY" else "賣出"
        status_map = {
            "PENDING":   ("委託中", C["yellow_l"]),
            "PARTIAL":   ("部分成交", C["orange"]),
            "FILLED":    ("已成交",  C["green"]),
            "CANCELLED": ("已取消",  C["subtext"]),
            "REJECTED":  ("已拒絕",  C["red"]),
        }
        st_txt, st_color = status_map.get(ev.status.value, (ev.status.value, C["text"]))
        side_color = C["green"] if ev.side.value == "BUY" else C["red"]

        if row_idx < 0:
            row_idx = 0
            self.orders_table.insertRow(row_idx)
            source = getattr(ev, "source", "") or ("DRY" if str(oid).startswith("DRY") else "REAL")
            cells = [
                (ev.code, side_color),
                (getattr(ev, "name", "") or "", side_color),
                (side_txt, side_color),
                (f"{float(ev.price):,.2f}", side_color),
                (str(ev.qty), side_color),
                (st_txt, st_color),
                (source, C["yellow_l"] if source == "DRY" else C["red_l"]),
            ]
            for col, (val, color) in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(QColor(color))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, oid)
                self.orders_table.setItem(row_idx, col, item)
        else:
            cell = self.orders_table.item(row_idx, 5)
            if cell:
                cell.setText(st_txt)
                cell.setForeground(QColor(st_color))

    def _refresh_broker_status(self) -> None:
        if self.broker is None:
            self._set_broker_status("未連線", C["subtext"], C["subtext"])
            return
        try:
            from broker import ConnectionState
        except ImportError:
            return
        st = getattr(self.broker, "state", None)
        acc = getattr(self.broker, "account", None)
        if st == ConnectionState.CONNECTED:
            dry_run = bool(getattr(self.broker, "dry_run", True))
            mode = "模擬下單" if dry_run else "實單模式"
            label = f"券商狀態：已登入 {acc.display}（{mode}）" if acc else f"券商狀態：已連線（{mode}）"
            self._set_broker_status(label, C["green"], C["text"], raw=True)
        elif st == ConnectionState.CONNECTING:
            self._set_broker_status("連線中…", C["yellow_l"], C["subtext"])
        elif st == ConnectionState.LOGIN_FAILED:
            self._set_broker_status("登入失敗", C["red"], C["red"])
        elif st == ConnectionState.ERROR:
            self._set_broker_status("連線錯誤", C["red"], C["red"])
        else:
            self._set_broker_status("未連線", C["subtext"], C["subtext"])

    def _set_broker_status(self, text: str, dot_color: str, text_color: str, *, raw: bool = False) -> None:
        if hasattr(self, "broker_dot"):
            self.broker_dot.setStyleSheet(f"color: {dot_color}; background: transparent;")
        if hasattr(self, "broker_status_lbl"):
            self.broker_status_lbl.setText(text if raw else f"券商狀態：{text}")
            self.broker_status_lbl.setStyleSheet(f"color: {text_color}; background: transparent;")


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
            from PyQt6.QtGui import QTextCursor
            cursor = self.event_log.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(QTextCursor.MoveOperation.Down,
                                QTextCursor.MoveMode.KeepAnchor, 100)
            cursor.removeSelectedText()
            self._log_lines = max(0, self._log_lines - 100)

    def _poll_monitor(self):
        if self._running and self.engine:
            summary = self.engine.get_summary()
            self._render_monitor(summary)

    def _clear_log(self):
        self.event_log.clear()
        self._log_lines = 0

    def _append_log(self, level: str, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        color = self._log_colors.get(level, C["text"])
        bold = level == "TRADE"
        tag_o = "<b>" if bold else ""
        tag_c = "</b>" if bold else ""
        html = f'{tag_o}<span style="color:{color};">{ts} {msg}</span>{tag_c}'
        self.event_log.append(html)
        sb = self.event_log.verticalScrollBar()
        sb.setValue(sb.maximum())
        self._log_lines += 1

    def _append_trade(self, d: dict):
        self._trade_count += 1
        if d["action"] == "BUY":
            self._buy_count += 1
        else:
            self._sell_count += 1
            self._realized_pnl += float(d.get("pnl", 0.0))

        action_color = C["green"] if d["action"] == "BUY" else C["red"]
        label_txt = "買進" if d["action"] == "BUY" else "賣出"

        # 損益欄：買進顯示 —，賣出顯示 +/- 幣別金額
        pnl_val = float(d.get("pnl", 0.0))
        if d["action"] == "SELL":
            pnl_text = f"{'+' if pnl_val >= 0 else ''}{pnl_val:,.0f}"
            pnl_color = C["red"] if pnl_val >= 0 else C["green"]
        else:
            pnl_text = "—"
            pnl_color = C["subtext"]

        row = 0
        self.trades_table.insertRow(row)
        cells = [
            (d["time"], action_color),
            (d["code"], action_color),
            (d["name"], action_color),
            (label_txt, action_color),
            (f"{d['price']:,.2f}", action_color),
            (str(d["qty"]), action_color),
            (pnl_text, pnl_color),
        ]
        for col, (val, color) in enumerate(cells):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QColor(color))
            self.trades_table.setItem(row, col, item)

        self.trd_summary_lbl.setText(f"小計 ({self._trade_count})")
        # 已實現損益 / 今日損益 卡片同步更新
        sign = "+" if self._realized_pnl >= 0 else ""
        rp_text = f"{sign}{self._realized_pnl:,.0f}"
        rp_color = C["red"] if self._realized_pnl >= 0 else C["green"]
        self.trd_pnl_lbl.setText(rp_text)
        self.trd_pnl_lbl.setStyleSheet(f"color:{rp_color};")
        self.stat_realized.setText(rp_text)
        self.stat_realized.setStyleSheet(f"color:{rp_color};")
        self.stat_pnl_today.setText(rp_text)
        self.stat_pnl_today.setStyleSheet(f"color:{rp_color};")
        self.stat_trade_cnt.setText(
            f"{self._trade_count} / {self.cfg.daily_max_trades}"
        )

    def _render_monitor(self, summary: list):
        STATUS_COLOR = {
            "準備進場": C["yellow_l"],
            "已進場":   C["green"],
            "委賣過多": C["orange"],
            "條件不符": C["subtext"],
            "出場中":   C["purple"],
            "已完成":   C["subtext"],
            "委託中":   C["yellow_l"],
            "等待":     C["subtext"],
        }
        STATUS_BG = {
            "準備進場": C["badge_ready"],
            "已進場":   C["badge_in"],
            "委賣過多": "#3d1a00",
            "條件不符": C["badge_dim"],
            "出場中":   C["badge_out"],
            "已完成":   C["badge_dim"],
            "委託中":   C["badge_order"],
            "等待":     C["badge_dim"],
        }

        threshold = self.cfg.volume_spike_sell_threshold
        pos_cnt = 0

        for s in summary:
            if s["blocked"]:
                status = "已完成"
            elif s["qty"] > 0:
                status = "已進場"
                pos_cnt += 1
            elif s["pending"]:
                status = "委託中"
            elif s["candle"] > 0:
                status = "準備進場"
            else:
                status = "等待"

            candle_txt = f"第{s['candle']}根" if s["candle"] > 0 else "—"
            fg = QColor(STATUS_COLOR.get(status, C["text"]))
            vol_fg = QColor(C["red"]) if s["vol_1s"] > threshold else fg

            vals = [
                s["code"], s["name"], "—", "—", "—",
                "—", str(s["vol_1s"]), candle_txt, status, "查看",
            ]

            if s["code"] in self._monitor_rows:
                row = self._monitor_rows[s["code"]]
            else:
                row = self.monitor_table.rowCount()
                self.monitor_table.insertRow(row)
                self._monitor_rows[s["code"]] = row

            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 8:  # 狀態徽章
                    item.setForeground(QColor(STATUS_COLOR.get(status, C["text"])))
                    item.setBackground(QColor(STATUS_BG.get(status, C["bg"])))
                elif col == 9:  # 查看
                    item.setForeground(QColor(C["blue_l"]))
                elif col == 6:
                    item.setForeground(vol_fg)
                else:
                    item.setForeground(fg)
                self.monitor_table.setItem(row, col, item)

        self.stat_positions.setText(str(pos_cnt))
        self.stat_trade_cnt.setText(
            f"{self._trade_count} / {self.cfg.daily_max_trades}"
        )


# ──────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    win = App()
    win.show()
    sys.exit(app.exec())
