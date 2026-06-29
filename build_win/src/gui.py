"""
gui.py — 打板策略系統 主視窗
使用 PyQt6，介面對應 S__5456203.jpg 設計稿。
"""
from __future__ import annotations
import html
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from decimal import Decimal
from typing import Dict, Optional
from datetime import datetime, time as dtime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QLineEdit, QCheckBox, QMessageBox, QHBoxLayout, QVBoxLayout, QComboBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

from app_logging import compose_log_message, configure_runtime_logging, runtime_base_dir, write_log_event
from broker import SymbolMeta
from config import (
    BROKER_SETTINGS_FILE,
    CONFIG_FILE,
    LOCKED_LIMIT_UP_DETECTION_MODE,
    get_locked_trading_config_baseline_paths,
    AppState,
    BrokerSettings,
    TradingConfig,
)
from engine import TradingEngine
from gui_pages import (
    build_broker_page,
    build_decision_detail_page,
    build_bot_row,
    build_dashboard,
    build_events_page,
    build_limitup_test_page,
    build_mid_row,
    build_orders_page,
    build_placeholder,
    build_positions_page,
    build_settings_page,
    build_system_settings_page,
    build_stats_row,
    create_strategy_settings_panel,
)
from gui_renderers import (
    append_log_html_to_views,
    append_decision_detail,
    append_order,
    append_strategy_event,
    append_trade,
    autosize_monitor_columns,
    is_volume_spike_highlighted,
    mark_order_filled,
    refresh_broker_status,
    refresh_limitup_test_page,
    render_account,
    render_limitup_test_detail,
    render_limitup_test_snapshot,
    render_log_views,
    render_monitor,
    set_broker_status,
    sync_decision_tab_toggle_text,
    sync_orders_full_table,
    sync_positions_full_table,
    sync_trades_full_table,
)
from gui_theme import (
    C,
    FONT_MONO,
    LIMIT_UP_SIGNAL_LABELS,
    _scaled,
    ToggleButton,
    _entry,
    _font,
    _label,
    _scroll_style,
    _sep_bar,
    set_ui_scale_percent,
)
from limitup_detection import LIMIT_UP_DETECTION_MODES, resolve_limit_up_mode
import official_special_flags
from windows_time_sync import verify_and_repair_cached

LOG_Q: queue.Queue = queue.Queue()


def push_log(level: str, msg: object, *, include_traceback: Optional[bool] = None) -> None:
    text = compose_log_message(level, msg, include_traceback=include_traceback)
    LOG_Q.put((level, text))
    write_log_event(level, text)


def _jsonl_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonl_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonl_value(v) for v in value]
    return value


def _append_jsonl_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_jsonl_value(record), ensure_ascii=False) + "\n")


# ──────────────────────────────────────────────
#  主視窗
# ──────────────────────────────────────────────

class App(QMainWindow):
    _ui_dispatch = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("打板策略系統")
        self._app_state = AppState.load()
        self.cfg = self._load_startup_trading_config()
        set_ui_scale_percent(getattr(self.cfg, "ui_scale_percent", 100))
        self.resize(_scaled(1440), _scaled(860))
        self.setMinimumSize(_scaled(1200), _scaled(680))
        self.setStyleSheet(f"background-color: {C['bg']};")
        configure_runtime_logging(self.cfg.file_logging_enabled)
        self.engine: Optional[TradingEngine] = None
        self.broker = None  # type: ignore[assignment]  # broker.BrokerAdapter，由 main.py 注入
        self._recorder = None  # Phase 1：盤中行情錄製 writer（啟用時建立）
        self._reserve_pool: Dict[str, object] = {}   # 動態換股：500 外的備用池
        self._pool_swap_timer: Optional[QTimer] = None
        self._pool_swap_warmup_done = False          # 第一次換股前等 30s 暖機
        self._running = False
        self._strategy_starting = False
        self._strategy_start_token = 0
        self._trade_count = 0
        self._buy_count = 0
        self._sell_count = 0
        self._daily_trade_codes = set()
        self._realized_pnl = 0.0   # M4：今日已實現損益累計
        self._realized_cost_basis = 0.0
        self._unrealized_pnl = 0.0
        self._positions_cost = 0.0
        self._log_lines = 0
        self._log_entries = []
        self._log_filter = "strategy"
        self._log_filter_buttons = {"all": [], "strategy": []}
        self._strategy_trigger_count = 0
        self._decision_detail_count = 0
        self._latency_stats = self._new_latency_stats()
        self._syncing_order_mode_control = False
        self._socket_recovering = False
        self._last_socket_disconnect_at: Optional[datetime] = None
        self._last_socket_disconnect_reason = ""
        self._last_socket_restart_requested_at: Optional[datetime] = None
        self._last_socket_restart_result = "idle"
        self._last_socket_restart_token = 0
        self._broker_event_source = None
        self._current_tab = "dashboard"
        self._hidden_tabs = {"risk", "limitup_test"}
        self._latest_monitor_summary = []
        self._official_special_flags_meta: Optional[dict] = None
        self._limitup_test_selected_code = ""
        self._limitup_test_selected_mode = resolve_limit_up_mode(
            getattr(self.cfg, "limit_up_detection_mode", "")
        )

        self._fields: Dict[str, QLineEdit] = {}
        self._bfields: Dict[str, QLineEdit] = {}   # 券商設定欄位
        self._checks: Dict[str, QCheckBox] = {}
        self._toggles: Dict[str, ToggleButton] = {}
        self._combos: Dict[str, QComboBox] = {}
        self._monitor_rows: Dict[str, int] = {}
        self._dashboard_preview_summary = []
        self._dashboard_preview_loading = False
        self._dashboard_preview_broker_key = ""

        self._log_colors = {
            "INFO":  C["blue"],
            "TRADE": C["green"],
            "WARN":  C["yellow_l"],
            "ERROR": C["red"],
            "DEBUG": C["subtext"],
        }
        self._ui_dispatch.connect(self._run_ui_dispatch, Qt.ConnectionType.QueuedConnection)

        self._build_ui()
        self._apply_config(self.cfg)
        self._log_startup_import_sources()
        self._start_polling()

    def _dispatch_ui(self, callback) -> None:
        self._ui_dispatch.emit(callback)

    def _run_ui_dispatch(self, callback) -> None:
        if callable(callback):
            callback()

    def _on_feed_disconnect(self, reason: str) -> None:
        self._dispatch_ui(lambda reason=reason: self._handle_feed_disconnect_ui(reason))

    def _on_clock_skew(self, snap: dict) -> None:
        self._dispatch_ui(lambda s=snap: self._handle_clock_skew_ui(s))

    def _handle_clock_skew_ui(self, snap: dict) -> None:
        if not hasattr(self, "latency_lbl"):
            return
        median = float(snap.get("median_ms") or 0.0)
        median_abs = abs(median)
        if median_abs < 1000.0:
            text = f"行情延遲：{median:.0f}ms"
        else:
            text = f"行情延遲：{median / 1000.0:.2f}秒"
        if median_abs >= 3000.0:
            color = C["red"]
        elif median_abs >= 1000.0:
            color = C["yellow_l"]
        elif median_abs >= 200.0:
            color = C["yellow_l"]
        else:
            color = C["subtext"]
        self.latency_lbl.setText(text)
        self.latency_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        if median_abs >= 3000.0:
            self.latency_warn_lbl.setText("⚠ 嚴重偏移")
            self.latency_warn_lbl.setStyleSheet(
                f"color: {C['red']}; background: transparent; font-weight: bold;"
            )
            self.latency_warn_lbl.setVisible(True)
        else:
            self.latency_warn_lbl.setVisible(False)

    def _handle_feed_disconnect_ui(self, reason: str) -> None:
        if self._socket_recovering:
            push_log("INFO", f"已在處理 socket 斷線重啟，略過重複事件：{reason}", include_traceback=False)
            return
        if not self._running and not self._strategy_starting:
            push_log("INFO", f"收到 socket 斷線事件，但策略未運行，略過：{reason}", include_traceback=False)
            return

        self._last_socket_disconnect_at = datetime.now()
        self._last_socket_disconnect_reason = reason
        self._last_socket_restart_result = "received"
        self._socket_recovering = True
        push_log(
            "WARN",
            "偵測到 socket 中斷，將停止策略並自動重啟："
            f"time={self._last_socket_disconnect_at.strftime('%Y-%m-%d %H:%M:%S')} reason={reason}",
            include_traceback=False,
        )
        self._stop_trading()
        self._last_socket_restart_result = "scheduled"
        self._set_strategy_status("斷線重啟中…", C["yellow_l"])
        push_log(
            "INFO",
            f"socket 斷線已進入自動重連流程：reason={reason}",
            include_traceback=False,
        )
        QTimer.singleShot(1200, self._restart_strategy_after_disconnect)

    def _restart_strategy_after_disconnect(self) -> None:
        try:
            if not self._socket_recovering:
                return
            self._last_socket_restart_requested_at = datetime.now()
            self._last_socket_restart_result = "starting"
            if "strategy_enabled" in self._toggles:
                self._toggles["strategy_enabled"].set(True)
            self._start_trading()
            self._last_socket_restart_token = self._strategy_start_token
            push_log(
                "INFO",
                "socket 自動重啟已送出："
                f"time={self._last_socket_restart_requested_at.strftime('%Y-%m-%d %H:%M:%S')} "
                f"token={self._last_socket_restart_token}",
                include_traceback=False,
            )
        finally:
            self._socket_recovering = False

    def _save_app_state(self) -> None:
        try:
            self._app_state.save()
        except Exception as e:
            push_log("WARN", f"儲存 app_state 失敗：{e}")

    def _load_startup_trading_config(self) -> TradingConfig:
        for path in get_locked_trading_config_baseline_paths():
            if path and os.path.exists(path):
                try:
                    return TradingConfig.load_strict(path)
                except Exception:
                    pass
        path = (self._app_state.last_trading_config_path or "").strip()
        if path and os.path.exists(path):
            try:
                return TradingConfig.load_strict(path)
            except Exception:
                pass
        return TradingConfig.load()

    def _log_startup_import_sources(self) -> None:
        for path in get_locked_trading_config_baseline_paths():
            if path and os.path.exists(path):
                push_log("INFO", f"啟動時已優先套用固定交易設定 JSON：{path}", include_traceback=False)
                return
        cfg_path = (self._app_state.last_trading_config_path or "").strip()
        if cfg_path:
            if os.path.exists(cfg_path):
                push_log("INFO", f"啟動時已自動套用上次匯入設定 JSON：{cfg_path}", include_traceback=False)
            else:
                push_log("WARN", f"上次匯入設定 JSON 不存在，已改用預設設定檔：{cfg_path}", include_traceback=False)

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
        bar.setFixedHeight(_scaled(48))
        bar.setStyleSheet(
            f"background-color: {C['header']};"
            f"border-bottom: 1px solid {C['border']};"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(_scaled(16), 0, _scaled(16), 0)
        lay.setSpacing(0)

        title = _label("打板策略系統", C["text"], 13, bold=True)
        lay.addWidget(title)
        lay.addSpacing(_scaled(10))
        self.order_mode_badge = QLabel("模擬下單")
        self.order_mode_badge.setFont(_font(9, bold=True))
        self.order_mode_badge.setFixedHeight(_scaled(24))
        self.order_mode_badge.setContentsMargins(_scaled(10), 0, _scaled(10), 0)
        lay.addWidget(self.order_mode_badge)
        lay.addSpacing(_scaled(28))

        # 分頁按鈕
        self._tab_btns: Dict[str, QLabel] = {}
        tabs = [
            ("dashboard", "儀表板"),
            ("settings",  "策略設定"),
            ("system_settings", "系統設定"),
            ("broker",    "券商設定"),
            ("orders",    "委託/成交"),
            ("positions", "持倉部位"),
            ("events",    "事件日誌"),
            ("limitup_test", "鎖板測試"),
            ("decision_detail", "決策明細"),
            ("risk",      "風控設定"),
        ]
        for key, text in tabs:
            btn = QLabel(text)
            btn.setFont(_font(10))
            btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn.setFixedHeight(_scaled(48))
            btn.setContentsMargins(_scaled(14), 0, _scaled(14), 0)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.mousePressEvent = lambda _e, k=key: self._switch_tab(k)
            lay.addWidget(btn)
            self._tab_btns[key] = btn
            btn.setVisible(key not in self._hidden_tabs)

        lay.addStretch()

        # 策略狀態徽章
        self.strategy_badge = QPushButton("● 策略已啟用")
        self.strategy_badge.setFont(_font(9, bold=True))
        self.strategy_badge.setFixedHeight(_scaled(28))
        self.strategy_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_badge_active(True)
        lay.addWidget(self.strategy_badge)
        lay.addSpacing(_scaled(16))

        # 時鐘
        self.clock_lbl = QLabel("00:00:00")
        self.clock_lbl.setFont(QFont(FONT_MONO, _scaled(12), QFont.Weight.Bold))
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

    def _set_badge_loading(self):
        self.strategy_badge.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['badge_ready']};
                color: {C['yellow_l']};
                border: 1px solid {C['yellow']};
                border-radius: 4px;
                padding: 0 12px;
            }}
        """)
        self.strategy_badge.setText("● 策略載入中")

    def _set_strategy_status(self, state: str, color: str):
        if hasattr(self, "strategy_dot"):
            self.strategy_dot.setStyleSheet(
                f"color: {color}; background: transparent;")
        if hasattr(self, "strategy_status_lbl"):
            self.strategy_status_lbl.setText(f"策略狀態：{state}")
            self.strategy_status_lbl.setStyleSheet(
                f"color: {color}; background: transparent;")

    def _switch_tab(self, key: str):
        if key in self._hidden_tabs:
            return
        self._current_tab = key
        if hasattr(self, "_strategy_settings_panel"):
            self._place_strategy_settings_panel(full_page=(key == "settings"))
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
        if key == "dashboard":
            if self._running and self.engine:
                self._render_monitor(self.engine.get_summary())
            elif self._dashboard_preview_summary:
                self._render_monitor(self._dashboard_preview_summary)
            else:
                self._render_monitor([])
                self._preload_dashboard_preview_async()
        elif key == "orders":
            self._sync_orders_full_table()
            self._sync_trades_full_table()
        elif key == "positions":
            self._sync_positions_full_table()
        elif key == "limitup_test":
            self._refresh_limitup_test_page()

    # ── 主體 ─────────────────────────────────

    def _build_body(self, root: QVBoxLayout):
        body = QWidget()
        body.setStyleSheet(f"background-color: {C['bg']};")
        lay = QHBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 右側分頁容器
        pages_w = QWidget()
        pages_w.setStyleSheet(f"background-color: {C['bg']};")
        pages_lay = QVBoxLayout(pages_w)
        pages_lay.setContentsMargins(0, 0, 0, 0)
        pages_lay.setSpacing(0)

        self._pages: Dict[str, QWidget] = {}
        for key in (
            "dashboard",
            "settings",
            "system_settings",
            "broker",
            "orders",
            "positions",
            "events",
            "limitup_test",
            "decision_detail",
            "risk",
        ):
            page = QWidget()
            page.setStyleSheet(f"background-color: {C['bg']};")
            pages_lay.addWidget(page)
            self._pages[key] = page

        self._build_dashboard(self._pages["dashboard"])
        self._build_settings_page(self._pages["settings"])
        self._build_system_settings_page(self._pages["system_settings"])
        self._build_broker_page(self._pages["broker"])
        self._build_orders_page(self._pages["orders"])
        self._build_positions_page(self._pages["positions"])
        self._build_events_page(self._pages["events"])
        self._build_limitup_test_page(self._pages["limitup_test"])
        self._build_decision_detail_page(self._pages["decision_detail"])
        self._build_placeholder(self._pages["risk"],      "風控設定")

        lay.addWidget(pages_w, 1)
        root.addWidget(body, 1)
        self._switch_tab("dashboard")

    # ══════════════════════════════════════════
    #  策略設定頁
    # ══════════════════════════════════════════

    def _create_strategy_settings_panel(self) -> QFrame:
        return create_strategy_settings_panel(self)

    def _set_strategy_panel_mode(self, *, full_page: bool) -> None:
        panel = self._strategy_settings_panel
        if full_page:
            panel.setMinimumWidth(0)
            panel.setMaximumWidth(16777215)
            panel.setStyleSheet(f"background-color: {C['bg']}; border: none;")
            self._strategy_settings_scroll.setStyleSheet(
                f"QScrollArea {{ border: none; background-color: {C['bg']}; }}"
                + _scroll_style()
            )
            self._strategy_settings_content.setStyleSheet(f"background-color: {C['bg']};")
        else:
            panel.setMinimumWidth(_scaled(300))
            panel.setMaximumWidth(_scaled(300))
            panel.setStyleSheet(f"background-color: {C['sidebar']}; border: none;")
            self._strategy_settings_scroll.setStyleSheet(
                f"QScrollArea {{ border: none; background-color: {C['sidebar']}; }}"
                + _scroll_style()
            )
            self._strategy_settings_content.setStyleSheet(f"background-color: {C['sidebar']};")

    def _place_strategy_settings_panel(self, *, full_page: bool) -> None:
        target_lay = (
            self._settings_page_settings_lay
            if full_page else self._dashboard_settings_lay
        )
        self._set_strategy_panel_mode(full_page=full_page)
        target_lay.addWidget(self._strategy_settings_panel)

    def _populate_limit_up_mode_combo(self, combo: QComboBox) -> None:
        combo.clear()
        for mode, desc in LIMIT_UP_DETECTION_MODES.items():
            combo.addItem(f"{mode} | {desc}", mode)
        locked_index = combo.findData(LOCKED_LIMIT_UP_DETECTION_MODE)
        if locked_index >= 0:
            combo.setCurrentIndex(locked_index)
        combo.setEnabled(False)
        combo.setToolTip("鎖漲停判斷模式目前固定，不提供變更。")

    def _set_limit_up_mode_selection(self, mode: str) -> str:
        resolved = resolve_limit_up_mode(LOCKED_LIMIT_UP_DETECTION_MODE)
        combo = self._combos.get("limit_up_detection_mode")
        if combo is None:
            return resolved
        idx = combo.findData(resolved)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        return resolved

    def _get_selected_limit_up_mode(self) -> str:
        return resolve_limit_up_mode(LOCKED_LIMIT_UP_DETECTION_MODE)

    def _apply_limit_up_mode(self, mode: str, *, log_change: bool = True) -> str:
        resolved = self._set_limit_up_mode_selection(mode)
        self.cfg.limit_up_detection_mode = resolved
        self._limitup_test_selected_mode = resolved
        if self._running and self.engine is not None:
            try:
                resolved = self.engine.update_limit_up_mode(resolved)
            except Exception as e:
                push_log("WARN", f"熱套用鎖漲停判斷模式失敗：{e}")
        if log_change:
            push_log(
                "INFO",
                f"鎖漲停判斷模式已套用：{resolved} "
                f"（{LIMIT_UP_DETECTION_MODES.get(resolved, '')}）",
                include_traceback=False,
            )
        self._refresh_limitup_test_page()
        return resolved

    def _sf(self, form: QVBoxLayout, lbl: str, key: str,
            suffix: str = "", w: int = 90):
        """設定頁單行欄位"""
        row = QHBoxLayout()
        row.addWidget(_label(lbl, C["subtext"], 9))
        row.addStretch()
        self._fields[key] = _entry(w)
        row.addWidget(self._fields[key])
        if suffix:
            row.addSpacing(_scaled(4))
            row.addWidget(_label(suffix, C["subtext"], 9))
        form.addLayout(row)
        form.addSpacing(_scaled(4))

    # ══════════════════════════════════════════
    #  儀表板頁
    # ══════════════════════════════════════════

    def _build_dashboard(self, parent: QWidget):
        build_dashboard(self, parent)

    # ── 統計卡列 ─────────────────────────────

    def _build_stats_row(self, lay: QVBoxLayout):
        build_stats_row(self, lay)

    # ── 中段：即時監控 + 事件日誌 ────────────

    def _build_mid_row(self, lay: QVBoxLayout):
        build_mid_row(self, lay)

    # ── 下段：持倉 + 委託 + 成交 ─────────────

    def _build_bot_row(self, lay: QVBoxLayout):
        build_bot_row(self, lay)

    # ── 其他分頁（佔位）───────────────────────

    def _build_settings_page(self, parent: QWidget):
        build_settings_page(self, parent)

    def _build_system_settings_page(self, parent: QWidget):
        build_system_settings_page(self, parent)

    def _build_placeholder(self, parent: QWidget, title: str):
        build_placeholder(self, parent, title)

    # ── 委託/成交 全頁面 ──────────────────────

    def _build_orders_page(self, parent: QWidget):
        build_orders_page(self, parent)

    # ── 持倉部位 全頁面 ──────────────────────

    def _build_positions_page(self, parent: QWidget):
        build_positions_page(self, parent)

    # ── 事件日誌 全頁面 ──────────────────────

    def _build_events_page(self, parent: QWidget):
        build_events_page(self, parent)

    def _build_limitup_test_page(self, parent: QWidget):
        build_limitup_test_page(self, parent)

    def _build_decision_detail_page(self, parent: QWidget):
        build_decision_detail_page(self, parent)

    @staticmethod
    def _fmt_limitup_price(value) -> str:
        if value is None or value == "":
            return "—"
        try:
            return f"{float(value):,.2f}"
        except Exception:
            return str(value)

    @staticmethod
    def _fmt_limitup_mode_hits(candidates: dict) -> str:
        hits = [mode for mode, ok in (candidates or {}).items() if ok]
        return ", ".join(hits) if hits else "—"

    @staticmethod
    def _fmt_limitup_signal_hits(signals: dict) -> str:
        hits = [
            LIMIT_UP_SIGNAL_LABELS.get(key, key)
            for key, ok in (signals or {}).items()
            if ok
        ]
        return ", ".join(hits) if hits else "無"

    def _render_limitup_test_snapshot(self, item: Optional[dict]) -> None:
        render_limitup_test_snapshot(self, item)

    def _render_limitup_test_detail(self, item: Optional[dict]) -> None:
        render_limitup_test_detail(self, item)

    def _current_limitup_test_item(self) -> Optional[dict]:
        for item in self._latest_monitor_summary:
            if str(item.get("code") or "") == self._limitup_test_selected_code:
                return item
        return None

    def _refresh_limitup_test_page(self, summary=None) -> None:
        refresh_limitup_test_page(self, summary)

    def _on_limitup_test_stock_changed(self, current_row: int, _current_col: int, _prev_row: int, _prev_col: int) -> None:
        if current_row < 0 or not hasattr(self, "limitup_test_stock_table"):
            return
        code_item = self.limitup_test_stock_table.item(current_row, 0)
        if code_item is None:
            return
        self._limitup_test_selected_code = code_item.text()
        current = self._current_limitup_test_item()
        if hasattr(self, "limitup_test_selected_lbl"):
            if current:
                self.limitup_test_selected_lbl.setText(
                    f"目前選擇：{current.get('code')} {current.get('name')} / 啟用={current.get('limit_up_mode')}"
                )
            else:
                self.limitup_test_selected_lbl.setText(f"目前選擇：{self._limitup_test_selected_code}")
        self._render_limitup_test_detail(current)

    def _on_limitup_test_mode_changed(self, current_row: int, _current_col: int, _prev_row: int, _prev_col: int) -> None:
        if current_row < 0 or not hasattr(self, "limitup_test_mode_table"):
            return
        mode_item = self.limitup_test_mode_table.item(current_row, 0)
        if mode_item is None:
            return
        self._limitup_test_selected_mode = mode_item.text()

    def _apply_selected_limitup_test_mode(self) -> None:
        mode = resolve_limit_up_mode(self._limitup_test_selected_mode)
        if not mode:
            QMessageBox.warning(self, "未選擇模式", "請先在模式明細表選擇一個判斷模式。")
            return
        self._apply_limit_up_mode(mode)

    # ── 頁面資料同步輔助 ──────────────────────

    def _sync_decision_tab_toggle_text(self) -> None:
        sync_decision_tab_toggle_text(self)

    def _set_tab_visible(self, key: str, visible: bool) -> None:
        if visible:
            self._hidden_tabs.discard(key)
        else:
            self._hidden_tabs.add(key)
        btn = self._tab_btns.get(key)
        if btn is not None:
            btn.setVisible(visible)
        if not visible and self._current_tab == key:
            self._switch_tab("events")
        self._sync_decision_tab_toggle_text()

    def _toggle_decision_detail_tab(self) -> None:
        self._set_tab_visible("decision_detail", "decision_detail" in self._hidden_tabs)
        if "decision_detail" not in self._hidden_tabs:
            self._switch_tab("decision_detail")

    def _hide_decision_detail_tab(self) -> None:
        self._set_tab_visible("decision_detail", False)

    def _clear_decision_detail(self) -> None:
        self._decision_detail_count = 0
        if hasattr(self, "decision_detail_table"):
            self.decision_detail_table.setRowCount(0)
        if hasattr(self, "decision_detail_summary_lbl"):
            self.decision_detail_summary_lbl.setText("共 0 筆")

    def _sync_orders_full_table(self) -> None:
        sync_orders_full_table(self)

    def _sync_trades_full_table(self) -> None:
        sync_trades_full_table(self)

    def _sync_positions_full_table(self) -> None:
        sync_positions_full_table(self)

    def _build_broker_page(self, parent: QWidget):
        build_broker_page(self, parent)

    # ── 券商設定輔助方法 ────────────────────────

    def _browse_cert(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇憑證檔案", "",
            "憑證檔案 (*.pfx *.p12 *.cer *.crt);;所有檔案 (*)"
        )
        if path:
            self._bfields["cert_path"].setText(path)

    def _broker_apply_settings(self, settings: BrokerSettings) -> None:
        self._bfields["personal_id"].setText(settings.personal_id)
        self._bfields["password"].setText(settings.password)
        self._bfields["branch_no"].setText(settings.branch_no)
        self._bfields["account_no"].setText(settings.account_no)
        self._bfields["cert_path"].setText(settings.cert_path)
        self._bfields["cert_password"].setText(settings.cert_password)
        self._bfields["api_key"].setText(settings.api_key)
        self._bfields["api_secret"].setText(settings.api_secret)
        self._toggles["broker_dry_run"].set(settings.dry_run)

    def _broker_load_default_json(self):
        last_path = (self._app_state.last_broker_settings_path or "").strip()
        if last_path and os.path.exists(last_path):
            try:
                settings = BrokerSettings.load_strict(last_path)
                self._broker_apply_settings(settings)
                push_log("INFO", f"券商設定已自動套用上次匯入 JSON：{last_path}", include_traceback=False)
                return
            except Exception as e:
                push_log("WARN", f"載入上次匯入券商設定 JSON 失敗，改用預設檔：{e}")
        elif last_path:
            push_log("WARN", f"上次匯入券商設定 JSON 不存在，改用預設檔：{last_path}", include_traceback=False)

        if not os.path.exists(BROKER_SETTINGS_FILE):
            return
        try:
            settings = BrokerSettings.load_strict(BROKER_SETTINGS_FILE)
            self._broker_apply_settings(settings)
            push_log("INFO", f"券商設定已從預設 JSON 載入：{BROKER_SETTINGS_FILE}", include_traceback=False)
        except Exception as e:
            push_log("ERROR", f"載入預設券商設定 JSON 失敗：{e}")

    def _broker_import_json(self):
        from PyQt6.QtWidgets import QFileDialog

        base_dir = os.path.dirname(BROKER_SETTINGS_FILE)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "匯入券商設定 JSON",
            base_dir,
            "JSON 檔案 (*.json);;所有檔案 (*)",
        )
        if not path:
            return

        try:
            settings = BrokerSettings.load_strict(path)
            self._broker_apply_settings(settings)
            self._app_state.last_broker_settings_path = path
            self._save_app_state()
            push_log("INFO", f"券商設定已自 JSON 匯入：{path}", include_traceback=False)
            QMessageBox.information(
                self,
                "匯入成功",
                f"已載入券商設定：\n{path}\n\n目前已套用到畫面。",
            )
        except Exception as e:
            push_log("ERROR", f"匯入券商設定 JSON 失敗：{e}")
            QMessageBox.critical(self, "匯入失敗", str(e))

    def _broker_export_json(self):
        from PyQt6.QtWidgets import QFileDialog

        base_dir = os.path.dirname(BROKER_SETTINGS_FILE)
        default_path = BROKER_SETTINGS_FILE
        path, _ = QFileDialog.getSaveFileName(
            self,
            "匯出券商設定 JSON",
            default_path,
            "JSON 檔案 (*.json);;所有檔案 (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"

        try:
            settings = self._broker_fields_to_settings()
            settings.save(path)
            push_log("INFO", f"券商設定已匯出至 JSON：{path}", include_traceback=False)
            QMessageBox.information(self, "匯出成功", f"券商設定已匯出：\n{path}")
        except Exception as e:
            push_log("ERROR", f"匯出券商設定 JSON 失敗：{e}")
            QMessageBox.critical(self, "匯出失敗", str(e))

    def _broker_fields_to_settings(self):
        """將欄位值轉為 BrokerSettings。"""
        f = self._bfields
        return BrokerSettings(
            personal_id=f["personal_id"].text().strip(),
            password=f["password"].text(),
            cert_path=f["cert_path"].text().strip(),
            cert_password=f["cert_password"].text(),
            branch_no=f["branch_no"].text().strip(),
            account_no=f["account_no"].text().strip(),
            api_key=f["api_key"].text().strip(),
            api_secret=f["api_secret"].text(),
            dry_run=self._toggles["broker_dry_run"].value,
        )

    def _persist_broker_settings(self, settings: BrokerSettings) -> str:
        settings.save(BROKER_SETTINGS_FILE)
        self._app_state.last_broker_settings_path = BROKER_SETTINGS_FILE
        self._save_app_state()
        return BROKER_SETTINGS_FILE

    def _load_dashboard_preview_summary(self, broker, cfg: TradingConfig) -> list:
        if broker is None:
            return []

        from broker import FUBON_REALTIME_SYMBOL_LIMIT, ScanCriteria
        from broker.universe import (
            FubonSymbolInfoLoader,
            MarketSnapshotCache,
            PreviousTradingDaysApiClient,
            is_limit_up_close,
            resolve_preview_price,
            scan_daily,
            scan_preview_candidates,
        )

        # 若市場選項全未勾選，則預設兩個市場都納入（避免回傳 0 支）
        markets = tuple(cfg.get_markets()) or ("TSE", "OTC")

        crit = ScanCriteria(
            price_min=Decimal(str(cfg.price_min)) if cfg.f9_enabled else Decimal("0"),
            price_max=Decimal(str(cfg.price_max)) if cfg.f9_enabled else Decimal("999999"),
            exclude_disposal=cfg.f11_enabled,
            exclude_attention=cfg.f11_enabled,
            exclude_day_trade_restricted=cfg.f11_enabled,
            markets=markets,
            min_prev_volume=(cfg.daily_volume_min if cfg.f8_enabled else 0),
            max_candidates=FUBON_REALTIME_SYMBOL_LIMIT,
            max_prior_limit_up_streak=(cfg.candle_limit - 1)
                if cfg.f7_enabled and cfg.candle_limit > 0 else None,
        )

        is_fubon = hasattr(broker, "_sdk") or type(broker).__name__ == "FubonAdapter"
        after_close_preview = self._is_after_market_close()
        next_day_exclusions = []
        if is_fubon:
            loader = FubonSymbolInfoLoader(broker)
            snapshot_cache = MarketSnapshotCache()
            symbol_infos = {}
            all_infos = {}
            api_loaded = False

            # 收盤後使用零波動的快照條件（不限昨量），盤中沿用原始 crit
            preview_crit = crit
            if after_close_preview:
                preview_crit = ScanCriteria(
                    price_min=crit.price_min,
                    price_max=crit.price_max,
                    exclude_disposal=crit.exclude_disposal,
                    exclude_attention=crit.exclude_attention,
                    exclude_day_trade_restricted=crit.exclude_day_trade_restricted,
                    markets=crit.markets,
                    min_prev_volume=0,
                    max_candidates=crit.max_candidates,
                    max_prior_limit_up_streak=crit.max_prior_limit_up_streak,
                )

            try:
                price_client = PreviousTradingDaysApiClient()
                all_infos = price_client.load_symbol_infos(markets=markets)
                api_loaded = True
                source = "快取" if price_client.last_from_cache else "API"
                push_log("INFO",
                    f"前兩個交易日價量已由{source}載入 {len(all_infos)} 支"
                    f"（as_of={price_client.last_as_of}）",
                    include_traceback=False)
            except Exception as e:
                push_log("WARN",
                    f"前兩個交易日價量 API 不可用，退回富邦 snapshot：{e}",
                    include_traceback=False)

            if api_loaded:
                candidates = scan_preview_candidates(all_infos.values(), preview_crit)
                if after_close_preview:
                    next_day_exclusions = self._build_next_day_exclusion_rows(
                        all_infos.values(), crit, already_next_session=True)
                    excluded_codes = {item["code"] for item in next_day_exclusions}
                    if excluded_codes:
                        candidates = [
                            si for si in candidates
                            if si.code not in excluded_codes
                        ]
                symbol_infos = {si.code: si for si in candidates}
            else:
                # API 連線失敗時才退回富邦 snapshot；snapshot 失敗再用舊逐支 ticker 流程。
                all_infos = loader.load_market_snapshots(
                    markets=markets,
                    quote_type="COMMONSTOCK",
                    snapshot_cache=snapshot_cache,
                    cache_snapshots=after_close_preview,
                )

                if all_infos:
                    if cfg.f7_enabled and cfg.candle_limit > 0:
                        snapshot_cache.apply_prior_limit_up_streaks(
                            all_infos.values(), max_days=cfg.candle_limit)
                    candidates = scan_preview_candidates(all_infos.values(), preview_crit)
                    if after_close_preview:
                        next_day_exclusions = self._build_next_day_exclusion_rows(
                            all_infos.values(), crit)
                        excluded_codes = {item["code"] for item in next_day_exclusions}
                        if excluded_codes:
                            candidates = [
                                si for si in candidates
                                if si.code not in excluded_codes
                            ]
                    symbol_infos = {si.code: si for si in candidates}
                else:
                    all_codes = loader.fetch_all_codes(markets=markets)
                    if not all_codes:
                        return []
                    all_infos = loader.load(all_codes)
                    candidates = scan_preview_candidates(all_infos.values(), crit)
                    symbol_infos = {si.code: si for si in candidates}
        else:
            from broker import DEFAULT_MOCK_INFOS
            mock_crit = ScanCriteria(
                price_min=crit.price_min,
                price_max=crit.price_max,
                exclude_disposal=crit.exclude_disposal,
                exclude_attention=crit.exclude_attention,
                exclude_day_trade_restricted=crit.exclude_day_trade_restricted,
                markets=crit.markets,
                min_prev_volume=0,
                max_candidates=crit.max_candidates,
            )
            candidates = scan_preview_candidates(DEFAULT_MOCK_INFOS, mock_crit)
            default_codes = [i.code for i in candidates]
            symbol_infos = broker.load_symbol_info(default_codes)

        summary = []
        for code, info in symbol_infos.items():
            preview_price_dec = resolve_preview_price(info)
            display_prev_close_dec = getattr(info, "display_prev_close", None)
            change_base_dec = (
                display_prev_close_dec
                if after_close_preview and display_prev_close_dec is not None
                else info.prev_close
            )
            prev_close = float(change_base_dec)
            preview_price = float(preview_price_dec)
            change = preview_price - prev_close
            change_pct = (change / prev_close * 100.0) if prev_close > 0 else 0.0
            closed_at_limit_up = bool(getattr(info, "closed_at_limit_up", False))
            if after_close_preview and not closed_at_limit_up:
                closed_at_limit_up = is_limit_up_close(preview_price_dec, change_base_dec)
            summary.append({
                "code": code,
                "name": info.name,
                "market": info.market,
                "candle": 0,
                "qty": 0,
                "pending": False,
                "vol_1s": 0,
                "blocked": False,
                "price": preview_price,
                "limit_up": float(info.limit_up_price),
                "prev_close": prev_close,
                "change": change,
                "change_pct": change_pct,
                "ask_qty": 0,
                "is_at_limit_up": False,
                "after_close_preview": after_close_preview,
                "closed_at_limit_up": closed_at_limit_up,
            })
        summary.sort(key=lambda item: item["code"])
        if next_day_exclusions:
            summary.extend(next_day_exclusions)
            self._log_next_day_exclusions(next_day_exclusions)
        return summary

    def _build_next_day_exclusion_rows(self, infos, crit, *, already_next_session: bool = False) -> list:
        if crit.max_prior_limit_up_streak is None:
            return []

        from broker import ScanCriteria, scan_daily

        next_infos = []
        if already_next_session:
            next_infos = list(infos)
        else:
            from broker.universe import build_next_session_symbol_info
            for info in infos:
                next_info = build_next_session_symbol_info(info)
                if next_info is not None:
                    next_infos.append(next_info)

        base_crit = ScanCriteria(
            price_min=crit.price_min,
            price_max=crit.price_max,
            min_prev_volume=crit.min_prev_volume,
            exclude_disposal=crit.exclude_disposal,
            exclude_attention=crit.exclude_attention,
            exclude_day_trade_restricted=crit.exclude_day_trade_restricted,
            markets=crit.markets,
            max_candidates=10000,
            max_prior_limit_up_streak=None,
        )
        potential = scan_daily(next_infos, base_crit)
        excluded = [
            info for info in potential
            if info.prior_limit_up_streak is not None
            and info.prior_limit_up_streak > crit.max_prior_limit_up_streak
        ]

        rows = []
        for info in excluded:
            price = float(info.prev_close)
            rows.append({
                "code": info.code,
                "name": info.name,
                "market": info.market,
                "candle": 0,
                "qty": 0,
                "pending": False,
                "vol_1s": 0,
                "blocked": True,
                "price": price,
                "limit_up": float(info.limit_up_price),
                "prev_close": price,
                "change": 0.0,
                "change_pct": 0.0,
                "ask_qty": 0,
                "is_at_limit_up": False,
                "after_close_preview": True,
                "next_day_excluded": True,
                "closed_at_limit_up": True,
                "prior_limit_up_streak": info.prior_limit_up_streak,
            })
        rows.sort(key=lambda item: (item.get("prior_limit_up_streak") or 0, item["code"]), reverse=True)
        return rows

    def _log_next_day_exclusions(self, rows: list) -> None:
        if not rows:
            return
        preview = []
        for item in rows[:50]:
            streak = item.get("prior_limit_up_streak") or 0
            preview.append(f"{item['code']} {item['name']}（連{streak}根）")
        more = "" if len(rows) <= 50 else f"，另 {len(rows) - 50} 支"
        push_log(
            "INFO",
            f"明日 F7 排除預覽 {len(rows)} 支：" + "、".join(preview) + more,
            include_traceback=False,
        )

    def _is_after_market_close(self, now: Optional[datetime] = None) -> bool:
        current = now or datetime.now()
        if current.weekday() >= 5:
            return True
        return current.time() >= dtime(13, 30)

    def _dashboard_broker_key(self, broker) -> str:
        if broker is None:
            return ""
        account = getattr(broker, "account", None)
        account_text = getattr(account, "display", "") if account else ""
        return f"{type(broker).__name__}:{id(broker)}:{account_text}"

    def _apply_dashboard_preview_summary(self, summary: list, broker=None) -> None:
        self._dashboard_preview_summary = summary
        self._dashboard_preview_broker_key = self._dashboard_broker_key(broker or self.broker)
        if not self._running:
            self._render_monitor(summary)

    def _preload_dashboard_preview_async(self, broker=None) -> None:
        if self._dashboard_preview_loading:
            return
        broker = broker or self.broker
        if broker is None:
            return

        cfg = self._collect_config()
        self.cfg = cfg
        self._dashboard_preview_loading = True

        def _worker():
            try:
                summary = self._load_dashboard_preview_summary(broker, cfg)
                push_log("INFO",
                    f"儀錶板即時監控預覽已更新 {len(summary)} 支"
                    f"（價格 {cfg.price_min:g}~{cfg.price_max:g} 元）",
                    include_traceback=False)
                self._dispatch_ui(lambda summary=summary, broker=broker: self._apply_dashboard_preview_summary(summary, broker))
            except Exception as e:
                push_log("WARN", f"載入儀錶板即時監控預覽失敗：{e}")
            finally:
                self._dashboard_preview_loading = False

        threading.Thread(target=_worker, daemon=True).start()

    def _broker_test_connection(self):
        """測試連線（登入後立即登出，只驗證憑證）。"""
        self._set_broker_page_status("連線測試中…", C["yellow_l"])
        settings = self._broker_fields_to_settings()

        if not settings.is_complete():
            missing = settings.missing_fields()
            self._set_broker_page_status(f"欄位不完整：{', '.join(missing)}", C["red"])
            return

        def _do_test():
            try:
                from broker import FubonAdapter, BrokerError
                adapter = FubonAdapter.from_config(settings)
                result = adapter.login()
                if result.success:
                    acc = result.selected
                    msg = f"連線成功：{acc.display}" if acc else "連線成功"
                    acc_display = acc.display if acc else "—"
                    cfg = self._collect_config()
                    self.cfg = cfg
                    preview_summary = self._load_dashboard_preview_summary(adapter, cfg)
                    try:
                        adapter.logout()
                    except Exception:
                        pass
                    push_log("INFO", f"富邦連線測試成功：{acc_display}", include_traceback=False)
                    self._dispatch_ui(lambda preview_summary=preview_summary, adapter=adapter: self._apply_dashboard_preview_summary(preview_summary, adapter))
                    self._dispatch_ui(lambda msg=msg: self._set_broker_page_status(msg, C["green"]))
                    self._dispatch_ui(lambda acc_display=acc_display: QMessageBox.information(
                        self, "測試成功", f"富邦連線測試成功！\n帳號：{acc_display}"))
                else:
                    err = result.message or "登入失敗"
                    push_log("ERROR", f"富邦連線測試失敗：{err}")
                    status_text = f"失敗：{err}"
                    self._dispatch_ui(lambda status_text=status_text: self._set_broker_page_status(status_text, C["red"]))
            except Exception as e:
                error_text = str(e)
                status_text = f"錯誤：{error_text}"
                push_log("ERROR", f"富邦連線測試失敗：{error_text}")
                self._dispatch_ui(lambda status_text=status_text: self._set_broker_page_status(status_text, C["red"]))
                self._dispatch_ui(lambda error_text=error_text: QMessageBox.critical(self, "連線失敗", error_text))

        import threading
        threading.Thread(target=_do_test, daemon=True).start()

    def _broker_connect(self):
        """用目前欄位登入，並套用為系統 broker（替換現有連線）。"""
        if self._running:
            QMessageBox.warning(self, "策略運行中", "請先停止策略再切換券商連線。")
            return

        settings = self._broker_fields_to_settings()
        if not settings.is_complete():
            missing = settings.missing_fields()
            QMessageBox.warning(self, "欄位不完整",
                "請填寫以下欄位：\n" + "\n".join(f"• {m}" for m in missing))
            return

        try:
            saved_path = self._persist_broker_settings(settings)
            push_log("INFO", f"券商設定已儲存至：{saved_path}", include_traceback=False)
        except Exception as e:
            error_text = str(e)
            self._set_broker_page_status(f"設定儲存失敗：{error_text}", C["red"])
            push_log("ERROR", f"券商設定儲存失敗：{error_text}")
            QMessageBox.critical(
                self,
                "設定儲存失敗",
                f"券商設定未能寫入 broker_settings.json：\n{error_text}",
            )
            return

        self._set_broker_page_status("登入中…", C["yellow_l"])

        def _do_connect():
            try:
                from broker import FubonAdapter, BrokerError
                if self.broker is not None:
                    try:
                        self.broker.logout()
                    except Exception:
                        pass
                adapter = FubonAdapter.from_config(settings)
                result = adapter.login()
                if result.success:
                    acc = result.selected
                    msg = f"已連線：{acc.display}" if acc else "已連線"
                    acc_display = acc.display if acc else "—"
                    cfg = self._collect_config()
                    self.cfg = cfg
                    preview_summary = self._load_dashboard_preview_summary(adapter, cfg)
                    self._dispatch_ui(lambda preview_summary=preview_summary, adapter=adapter: self._apply_dashboard_preview_summary(preview_summary, adapter))
                    self._dispatch_ui(lambda adapter=adapter: self.set_broker(adapter))
                    self._dispatch_ui(lambda msg=msg: self._set_broker_page_status(msg, C["green"]))
                    self._dispatch_ui(lambda: self._toggles["mock_mode"].set(False))
                    self._dispatch_ui(lambda: self._update_mock_mode_label(False))
                    self._dispatch_ui(lambda acc_display=acc_display: push_log("INFO", f"富邦券商已連線：{acc_display}", include_traceback=False))
                    self._dispatch_ui(lambda acc_display=acc_display, saved_path=saved_path: QMessageBox.information(
                        self, "連線成功", f"已成功連線富邦券商！\n帳號：{acc_display}\n\n設定已儲存至：\n{saved_path}"))
                else:
                    err = result.message or "登入失敗"
                    push_log("ERROR", f"富邦券商登入失敗：{err}")
                    status_text = f"失敗：{err}"
                    self._dispatch_ui(lambda status_text=status_text: self._set_broker_page_status(status_text, C["red"]))
                    self._dispatch_ui(lambda err=err: QMessageBox.critical(self, "登入失敗", err))
            except Exception as e:
                error_text = str(e)
                status_text = f"錯誤：{error_text}"
                push_log("ERROR", f"富邦券商連線失敗：{error_text}")
                self._dispatch_ui(lambda status_text=status_text: self._set_broker_page_status(status_text, C["red"]))
                self._dispatch_ui(lambda error_text=error_text: QMessageBox.critical(self, "連線失敗", error_text))

        import threading
        threading.Thread(target=_do_connect, daemon=True).start()

    def _set_broker_page_status(self, text: str, color: str):
        if hasattr(self, "_broker_conn_dot"):
            self._broker_conn_dot.setStyleSheet(f"color:{color}; background:transparent;")
        if hasattr(self, "_broker_conn_lbl"):
            self._broker_conn_lbl.setText(text)
            self._broker_conn_lbl.setStyleSheet(f"color:{color}; background:transparent;")

    # ── 狀態列 ───────────────────────────────

    def _build_statusbar(self, root: QVBoxLayout):
        bar = QFrame()
        bar.setFixedHeight(_scaled(28))
        bar.setStyleSheet(
            f"background-color: {C['header']};"
            f"border-top: 1px solid {C['border']};"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(_scaled(16), 0, _scaled(16), 0)
        lay.setSpacing(0)

        self.broker_dot = QLabel("●")
        self.broker_dot.setFont(_font(8))
        self.broker_dot.setStyleSheet(f"color: {C['subtext']}; background: transparent;")
        lay.addWidget(self.broker_dot)
        lay.addSpacing(_scaled(4))
        self.broker_status_lbl = _label("券商狀態：未連線", C["subtext"], 9)
        lay.addWidget(self.broker_status_lbl)
        lay.addSpacing(_scaled(20))
        lay.addWidget(_sep_bar())
        lay.addSpacing(_scaled(20))
        self.latency_lbl = _label("行情延遲：—", C["subtext"], 9)
        lay.addWidget(self.latency_lbl)
        lay.addSpacing(_scaled(8))
        self.latency_warn_lbl = _label("", C["red"], 9, bold=True)
        self.latency_warn_lbl.setVisible(False)
        lay.addWidget(self.latency_warn_lbl)
        lay.addSpacing(_scaled(20))
        lay.addWidget(_sep_bar())
        lay.addSpacing(_scaled(20))

        self.strategy_dot = QLabel("●")
        self.strategy_dot.setFont(_font(8))
        self.strategy_dot.setStyleSheet(f"color: {C['red']}; background: transparent;")
        lay.addWidget(self.strategy_dot)
        lay.addSpacing(_scaled(4))
        self.strategy_status_lbl = _label("策略狀態：已停止", C["subtext"], 9)
        lay.addWidget(self.strategy_status_lbl)

        lay.addStretch()
        lay.addWidget(_label("版本：1.0.0", C["subtext"], 9))
        root.addWidget(bar)

    # ══════════════════════════════════════════
    #  設定讀寫
    # ══════════════════════════════════════════

    def _sync_volume_spike_mode_fields(self):
        if "volume_spike_sell_mode" in self._combos:
            ratio_mode = self._combos["volume_spike_sell_mode"].currentIndex() == 1
            if "volume_spike_sell_threshold" in self._fields:
                self._fields["volume_spike_sell_threshold"].setEnabled(not ratio_mode)
            if "volume_spike_sell_ratio_percent" in self._fields:
                self._fields["volume_spike_sell_ratio_percent"].setEnabled(ratio_mode)

    def _apply_config(self, cfg: TradingConfig):
        f = self._fields
        f["per_stock_amount"].setText(str(cfg.per_stock_amount))
        f["daily_max_trades"].setText(str(cfg.daily_max_trades))
        f["start_time"].setText(cfg.start_time)
        f["entry_before_time"].setText(cfg.entry_before_time)
        f["ask_queue_threshold"].setText(str(cfg.ask_queue_threshold))
        f["daily_volume_min"].setText(str(cfg.daily_volume_min))
        f["price_min"].setText(str(int(cfg.price_min)))
        f["price_max"].setText(str(int(cfg.price_max)))
        f["consume_qty_threshold"].setText(str(cfg.consume_qty_threshold))
        f["f4_open_ticks_to_sell"].setText(str(cfg.f4_open_ticks_to_sell))
        f["exit_start_time"].setText(getattr(cfg, "exit_start_time", "09:00"))
        f["exit_before_time"].setText(getattr(cfg, "exit_before_time", "13:25"))
        f["prelock_stop_ticks"].setText(str(cfg.prelock_stop_ticks))
        f["volume_spike_sell_threshold"].setText(str(cfg.volume_spike_sell_threshold))
        f["volume_spike_sell_ratio_percent"].setText(str(cfg.volume_spike_sell_ratio_percent))
        self._combos["volume_spike_sell_mode"].setCurrentIndex(
            1 if getattr(cfg, "volume_spike_sell_mode", "qty") == "ratio" else 0
        )
        if "exit_method3" in self._combos:
            self._combos["exit_method3"].setCurrentIndex(
                0 if getattr(cfg, "f6_cancel_order_when_spike", True) else 1
            )
        self._sync_volume_spike_mode_fields()

        c = self._checks
        c["market_twse"].setChecked(cfg.market_twse)
        c["market_tpex"].setChecked(cfg.market_tpex)
        c["candle_k1"].setChecked(cfg.candle_limit >= 1)
        c["candle_k2"].setChecked(cfg.candle_limit >= 2)
        c["excl_disposal"].setChecked(cfg.f11_enabled)
        c["excl_attention"].setChecked(cfg.f11_enabled)
        c["excl_daytrade"].setChecked(cfg.f11_enabled)
        c["consume_enabled"].setChecked(cfg.f_consume_enabled)
        c["consume_mutex_with_f1"].setChecked(cfg.consume_mutex_with_f1)
        c["prelock_ask_entry_enabled"].setChecked(cfg.f_prelock_ask_entry_enabled)
        c["excl_open_limit"].setChecked(not cfg.f_open_limitup_entry_enabled)
        c["excl_sealed"].setChecked(cfg.f12_enabled)
        c["f4_require_today_limitup"].setChecked(cfg.f4_require_today_limitup)
        c["f5_enabled"].setChecked(cfg.f5_enabled)
        c["prelock_stop_enabled"].setChecked(cfg.f_prelock_stop_enabled)
        if "dry_run_mode" in c:
            self._syncing_order_mode_control = True
            c["dry_run_mode"].setChecked(cfg.order_dry_run)
            self._syncing_order_mode_control = False
        c["file_logging_enabled"].setChecked(cfg.file_logging_enabled)
        # 錄製設定
        if "recording_enabled" in c:
            c["recording_enabled"].setChecked(cfg.recording_enabled)
        if "recording_record_raw" in c:
            c["recording_record_raw"].setChecked(cfg.recording_record_raw)
        if "recording_keep_days" in f:
            f["recording_keep_days"].setText(str(cfg.recording_keep_days))
        if "recording_dir" in f:
            f["recording_dir"].setText(cfg.recording_dir or "")
        self._set_limit_up_mode_selection(cfg.limit_up_detection_mode)
        self._limitup_test_selected_mode = resolve_limit_up_mode(cfg.limit_up_detection_mode)
        if "ui_scale_percent" in self._combos:
            combo = self._combos["ui_scale_percent"]
            idx = combo.findData(int(getattr(cfg, "ui_scale_percent", 100) or 100))
            if idx >= 0:
                combo.setCurrentIndex(idx)
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
        volume_spike_sell_mode = (
            "ratio" if self._combos["volume_spike_sell_mode"].currentIndex() == 1 else "qty"
        )

        return TradingConfig(
            api_id                        = self.cfg.api_id,
            api_key                       = self.cfg.api_key,
            broker_cert_path              = self.cfg.broker_cert_path,
            f1_enabled                    = True,
            start_time                    = f["start_time"].text(),
            entry_before_time             = f["entry_before_time"].text(),
            ask_queue_threshold           = ni("ask_queue_threshold"),
            market_twse                   = c["market_twse"].isChecked(),
            market_tpex                   = c["market_tpex"].isChecked(),
            per_stock_amount              = ni("per_stock_amount"),
            f4_enabled                    = True,
            f4_open_ticks_to_sell         = max(1, ni("f4_open_ticks_to_sell")),
            f4_require_today_limitup      = c["f4_require_today_limitup"].isChecked(),
            exit_start_time               = f["exit_start_time"].text(),
            exit_before_time              = f["exit_before_time"].text(),
            f5_enabled                    = c["f5_enabled"].isChecked(),
            volume_spike_sell_mode        = volume_spike_sell_mode,
            volume_spike_sell_threshold   = ni("volume_spike_sell_threshold"),
            volume_spike_sell_ratio_percent = max(0.0, nf("volume_spike_sell_ratio_percent")),
            f6_enabled                    = True,
            volume_spike_cancel_threshold = ni("volume_spike_sell_threshold"),
            f6_cancel_order_when_spike    = self._combos["exit_method3"].currentIndex() == 0,
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
            f11_allow_previous_day_official_cache = getattr(
                self.cfg, "f11_allow_previous_day_official_cache", True
            ),
            f12_enabled                   = c["excl_sealed"].isChecked(),
            f_open_limitup_entry_enabled  = not c["excl_open_limit"].isChecked(),
            f13_enabled                   = True,
            daily_max_trades              = ni("daily_max_trades"),
            f_consume_enabled             = c["consume_enabled"].isChecked(),
            consume_qty_threshold         = max(0, ni("consume_qty_threshold")),
            consume_mutex_with_f1         = c["consume_mutex_with_f1"].isChecked(),
            f_prelock_ask_entry_enabled   = c["prelock_ask_entry_enabled"].isChecked(),
            f_prelock_stop_enabled        = c["prelock_stop_enabled"].isChecked(),
            prelock_stop_ticks            = max(1, ni("prelock_stop_ticks")),
            order_dry_run                 = c["dry_run_mode"].isChecked(),
            file_logging_enabled          = c["file_logging_enabled"].isChecked(),
            ui_scale_percent              = int(
                self._combos["ui_scale_percent"].currentData()
                if "ui_scale_percent" in self._combos
                and self._combos["ui_scale_percent"].currentData() is not None
                else getattr(self.cfg, "ui_scale_percent", 100)
            ),
            recording_enabled             = (c["recording_enabled"].isChecked()
                                              if "recording_enabled" in c
                                              else self.cfg.recording_enabled),
            recording_record_raw          = (c["recording_record_raw"].isChecked()
                                              if "recording_record_raw" in c
                                              else self.cfg.recording_record_raw),
            recording_keep_days           = (max(0, ni("recording_keep_days"))
                                              if "recording_keep_days" in self._fields
                                              else self.cfg.recording_keep_days),
            recording_dir                 = (self._fields["recording_dir"].text().strip()
                                              if "recording_dir" in self._fields
                                              else self.cfg.recording_dir),
            limit_up_detection_mode      = self._get_selected_limit_up_mode(),
        )

    def _save_settings(self):
        try:
            new_cfg = self._collect_config()
            was_file_logging_enabled = self.cfg.file_logging_enabled
            limit_up_mode_changed = (
                resolve_limit_up_mode(getattr(self.cfg, "limit_up_detection_mode", ""))
                != resolve_limit_up_mode(getattr(new_cfg, "limit_up_detection_mode", ""))
            )
            # 偵測：價格區間是否被變動（影響的是「訂閱清單」，需重啟才會生效）
            price_range_changed = (
                self._running and self.engine is not None and (
                    float(getattr(self.cfg, "price_min", 0) or 0) != float(getattr(new_cfg, "price_min", 0) or 0)
                    or float(getattr(self.cfg, "price_max", 0) or 0) != float(getattr(new_cfg, "price_max", 0) or 0)
                )
            )
            self._persist_trading_config(new_cfg)
            self.cfg = new_cfg
            if self.cfg.file_logging_enabled:
                log_path = configure_runtime_logging(True)
                if not was_file_logging_enabled and log_path:
                    push_log("INFO", f"實體 log 檔記錄已啟用：{log_path}", include_traceback=False)
            else:
                if was_file_logging_enabled:
                    push_log("INFO", "實體 log 檔記錄已停用", include_traceback=False)
                configure_runtime_logging(False)
                log_path = None
            # ── 熱套用：策略執行中時，直接更新 engine 內部設定（不需停用再啟用）──
            applied_live = False
            if self._running and self.engine is not None:
                try:
                    self.engine.config = new_cfg
                    if limit_up_mode_changed:
                        self.engine.update_limit_up_mode(new_cfg.limit_up_detection_mode)
                    applied_live = True
                    push_log("INFO",
                        "設定已熱套用至執行中的策略（價格區間 / 各功能開關 / 數值閾值即時生效；"
                        "訂閱範圍仍以本次啟動時的清單為準）",
                        include_traceback=False)
                except Exception as e:
                    push_log("WARN", f"設定熱套用失敗：{e}")
            if self.broker is not None and not self._running:
                self._dashboard_preview_summary = []
                self._dashboard_preview_broker_key = ""
                self._render_monitor([])
                self._preload_dashboard_preview_async()
            message = "設定已儲存！"
            if applied_live:
                message += "\n（已即時套用至執行中的策略）"
            if price_range_changed:
                message += (
                    "\n\n股價區間有變動，即將背景重新掃描訂閱範圍…"
                    "\n（會顯示進度視窗，請稍候完成後再操作。）"
                )
            if log_path:
                message += f"\nlog 檔案：{log_path}"
            QMessageBox.information(self, "儲存成功", message)

            # ── 價格區間有變動且策略執行中 → 背景重跑掃描 + 熱替換訂閱 ──
            if price_range_changed and self._running and self.engine is not None:
                self._rescan_universe_with_progress()
        except ValueError as e:
            QMessageBox.critical(self, "格式錯誤", f"數字欄位格式有誤：{e}")
        except Exception as e:
            push_log("ERROR", f"儲存設定失敗：{e}")
            QMessageBox.critical(self, "儲存失敗", str(e))

    def _trading_config_save_path(self) -> str:
        path = (self._app_state.last_trading_config_path or "").strip()
        return path or CONFIG_FILE

    def _persist_trading_config(self, cfg: TradingConfig) -> str:
        path = self._trading_config_save_path()
        cfg.save(path)
        if path != CONFIG_FILE:
            cfg.save(CONFIG_FILE)
        return path

    def _show_update_feature_pending(self) -> None:
        QMessageBox.information(self, "版本更新", "版本更新功能開發中。")

    def _save_system_settings_and_restart(self) -> None:
        try:
            new_cfg = self._collect_config()
            save_path = self._persist_trading_config(new_cfg)
            self.cfg = new_cfg
            reply = QMessageBox.question(
                self,
                "重新啟動確認",
                f"介面縮放已儲存至：\n{save_path}\n\n需要重新啟動程式後套用，是否立即重新啟動？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            if self._running:
                self._stop_trading()
            self._restart_application()
        except Exception as e:
            push_log("ERROR", f"儲存系統設定失敗：{e}")
            QMessageBox.critical(self, "儲存失敗", str(e))

    def _restart_application(self) -> None:
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, *sys.argv[1:]]
        else:
            cmd = [sys.executable, os.path.abspath(sys.argv[0]), *sys.argv[1:]]
        kwargs = {"cwd": os.getcwd()}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(cmd, **kwargs)
        QApplication.instance().quit()

    # ────────────────────────────────────────────────────────
    #  盤中熱換訂閱（價格區間變動時呼叫）
    # ────────────────────────────────────────────────────────

    def _rescan_universe_with_progress(self) -> None:
        """
        顯示「重新掃描中…」的 modal 進度對話框，背景執行緒：
          1. 重跑 _load_trading_runtime → 取得新 symbol_infos
          2. 停掉現有 engine.feed
          3. engine.replace_universe(new_infos)（保留有持倉/委託的股票）
          4. engine.resubscribe_feed()
          5. 完成後關閉對話框並顯示結果摘要
        """
        from PyQt6.QtWidgets import QProgressDialog
        from PyQt6.QtCore import Qt

        if self.engine is None or not self._running:
            return

        dlg = QProgressDialog("正在重新掃描股票範圍，請稍候…", "", 0, 0, self)
        dlg.setWindowTitle("更新訂閱範圍")
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setCancelButton(None)  # 不允許取消
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.show()
        QApplication.processEvents()

        engine = self.engine
        broker = self.broker
        cfg = self.cfg
        recording_was_enabled = bool(getattr(cfg, "recording_enabled", False))

        def _worker():
            error = None
            result = None
            try:
                push_log("INFO",
                    "[Rescan] 開始重跑訂閱掃描（價格區間已變動）…",
                    include_traceback=False)
                new_infos, _new_feed, _new_reserve = self._load_trading_runtime(broker, cfg)
                if new_infos is None:
                    new_infos = {}
                push_log("INFO",
                    f"[Rescan] 新掃描候選 {len(new_infos)} 支，準備熱替換…",
                    include_traceback=False)

                # 停掉舊 feed（feed 物件本身保留，stop 後再用 start 重新連）
                if engine.feed is not None:
                    try:
                        engine.feed.stop()
                    except Exception as e:
                        push_log("WARN", f"[Rescan] 停止舊 feed 時警告：{e}")

                diff = engine.replace_universe(new_infos)

                try:
                    engine.resubscribe_feed()
                except Exception as e:
                    push_log("ERROR", f"[Rescan] 重新訂閱失敗：{e}")
                    raise

                result = diff
                push_log("INFO",
                    "[Rescan] 完成："
                    f"新增 {len(diff['added'])} 支、"
                    f"移除 {len(diff['removed'])} 支、"
                    f"保留（仍在新範圍）{len(diff['kept_in_new'])} 支、"
                    f"保留（有持倉/委託）{len(diff['kept_protected'])} 支",
                    include_traceback=False)
            except Exception as e:  # noqa: BLE001
                error = e
                push_log("ERROR", f"[Rescan] 重跑掃描失敗：{e}")

            self._dispatch_ui(lambda: _on_done(error, result))

        def _on_done(error, result):
            try:
                dlg.close()
            except Exception:
                pass
            if error is not None:
                QMessageBox.critical(
                    self, "重跑掃描失敗",
                    f"重新掃描訂閱範圍失敗：\n{error}\n\n"
                    f"建議：請停止策略後重新啟動。",
                )
                return
            diff = result or {}
            added = diff.get("added", [])
            removed = diff.get("removed", [])
            kept_protected = diff.get("kept_protected", [])
            kept_in_new = diff.get("kept_in_new", [])

            def _preview(codes, n=8):
                if not codes:
                    return "（無）"
                head = "、".join(codes[:n])
                if len(codes) > n:
                    head += f" 等共 {len(codes)} 支"
                return head

            msg = (
                f"訂閱範圍已更新！\n\n"
                f"• 新增訂閱：{len(added)} 支\n  {_preview(added)}\n\n"
                f"• 移除訂閱：{len(removed)} 支\n  {_preview(removed)}\n\n"
                f"• 保留（仍在新範圍）：{len(kept_in_new)} 支\n"
                f"• 保留（有持倉/委託，強制保留）：{len(kept_protected)} 支\n"
                f"  {_preview(kept_protected)}\n\n"
                f"監控表將以新的訂閱清單顯示。"
            )
            QMessageBox.information(self, "重跑掃描完成", msg)
            if recording_was_enabled:
                push_log("INFO",
                    "[Rescan] 提示：feed 已重新連線，本次重訂閱沿用原 recorder；"
                    "若需建立新錄製檔，請停止後重新啟動策略。",
                    include_traceback=False)

        threading.Thread(target=_worker, daemon=True, name="Rescan-Universe").start()

    # ────────────────────────────────────────────────────────
    #  動態換股池（每 60 秒掃描一次，漲幅 8~10% 優先留池）
    # ────────────────────────────────────────────────────────

    _POOL_SWAP_PCT_LO = 8.0    # 目標漲幅下限（含）
    _POOL_SWAP_PCT_HI = 10.0   # 目標漲幅上限（含）
    _POOL_SWAP_INTERVAL_MS = 60_000   # 正常掃描間隔
    _POOL_SWAP_WARMUP_MS   = 30_000   # 啟動後第一次掃描延遲

    def _start_pool_swap_timer(self) -> None:
        self._stop_pool_swap_timer()
        if not getattr(self.cfg, "dynamic_pool_swap_enabled", False):
            push_log(
                "INFO",
                "[PoolSwap] 動態換股已停用，不啟動每分鐘換股與重訂閱",
                include_traceback=False,
            )
            return
        if not self._reserve_pool:
            return
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(self._pool_swap_tick)
        t.start(self._POOL_SWAP_WARMUP_MS)
        self._pool_swap_timer = t
        push_log("INFO",
            f"[PoolSwap] 動態換股已啟用，備用池 {len(self._reserve_pool)} 支，"
            f"首次掃描在 {self._POOL_SWAP_WARMUP_MS // 1000} 秒後",
            include_traceback=False)

    def _stop_pool_swap_timer(self) -> None:
        if self._pool_swap_timer is not None:
            try:
                self._pool_swap_timer.stop()
            except Exception:
                pass
            self._pool_swap_timer = None

    def _pool_swap_tick(self) -> None:
        """在主執行緒（QTimer callback）執行，將換股工作丟到背景 thread。"""
        if not self._running or self.engine is None:
            return
        engine = self.engine
        reserve_pool = dict(self._reserve_pool)
        threading.Thread(
            target=self._pool_swap_worker,
            args=(engine, reserve_pool),
            daemon=True,
            name="PoolSwap",
        ).start()
        # 重排下一次定時
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(self._pool_swap_tick)
        t.start(self._POOL_SWAP_INTERVAL_MS)
        self._pool_swap_timer = t

    @staticmethod
    def _pool_swap_snapshot_value(value):
        return _jsonl_value(value)

    def _pool_swap_snapshot_path(self, now: Optional[datetime] = None) -> Path:
        stamp = (now or datetime.now()).strftime("%Y%m%d")
        return Path(runtime_base_dir()) / "log" / f"pool_swap.{stamp}.jsonl"

    def _write_pool_swap_snapshot(self, stage: str, payload: dict) -> None:
        now = datetime.now()
        path = self._pool_swap_snapshot_path(now)
        record = {
            "ts": now.isoformat(timespec="microseconds"),
            "stage": stage,
        }
        record.update(self._pool_swap_snapshot_value(payload))
        try:
            _append_jsonl_record(path, record)
        except Exception as e:
            push_log("WARN", f"[PoolSwap] 寫入快照失敗：{e}", include_traceback=False)

    def _decision_event_log_path(self, now: Optional[datetime] = None) -> Path:
        stamp = (now or datetime.now()).strftime("%Y%m%d")
        return Path(runtime_base_dir()) / "log" / f"decision_events.{stamp}.jsonl"

    def _latency_summary_log_path(self, now: Optional[datetime] = None) -> Path:
        stamp = (now or datetime.now()).strftime("%Y%m%d")
        return Path(runtime_base_dir()) / "log" / f"latency_summary.{stamp}.jsonl"

    def _write_decision_event_record(self, ev: dict) -> None:
        now = datetime.now()
        record = {
            "logged_at": now.isoformat(timespec="microseconds"),
            **(ev or {}),
        }
        _append_jsonl_record(self._decision_event_log_path(now), record)

    @staticmethod
    def _new_latency_bucket() -> dict:
        return {
            "count": 0,
            "sum": 0.0,
            "min": None,
            "max": None,
        }

    def _new_latency_stats(self) -> dict:
        return {
            "started_at": datetime.now().isoformat(timespec="microseconds"),
            "event_count": 0,
            "metrics": {
                "market_to_recv_ms": self._new_latency_bucket(),
                "recv_to_decision_ms": self._new_latency_bucket(),
                "decision_to_order_ms": self._new_latency_bucket(),
            },
            "codes": {},
        }

    def _reset_latency_stats(self) -> None:
        self._latency_stats = self._new_latency_stats()

    @staticmethod
    def _update_latency_bucket(bucket: dict, value) -> bool:
        try:
            sample = float(value)
        except (TypeError, ValueError):
            return False
        if sample < 0:
            return False
        bucket["count"] += 1
        bucket["sum"] += sample
        bucket["min"] = sample if bucket["min"] is None else min(bucket["min"], sample)
        bucket["max"] = sample if bucket["max"] is None else max(bucket["max"], sample)
        return True

    def _record_latency_stats(self, ev: dict) -> None:
        details = ev.get("details") or {}
        if not isinstance(details, dict):
            return
        code = str(ev.get("code") or "")
        name = str(ev.get("name") or "")
        category = str(ev.get("category") or "")
        result = str(ev.get("result") or "")
        reason = str(ev.get("reason") or "")
        self._latency_stats["event_count"] += 1

        code_stats = self._latency_stats["codes"].setdefault(code, {
            "name": name,
            "metrics": {
                "market_to_recv_ms": self._new_latency_bucket(),
                "recv_to_decision_ms": self._new_latency_bucket(),
                "decision_to_order_ms": self._new_latency_bucket(),
            },
            "last_category": "",
            "last_result": "",
            "last_reason": "",
        })
        code_stats["name"] = name or code_stats.get("name", "")
        code_stats["last_category"] = category
        code_stats["last_result"] = result
        code_stats["last_reason"] = reason

        metrics = {
            "market_to_recv_ms": details.get("market_to_recv_ms"),
            "recv_to_decision_ms": details.get("recv_to_decision_ms"),
        }
        if category == "ORDER" and result == "委託PENDING":
            metrics["decision_to_order_ms"] = details.get("decision_to_order_ms")

        wrote_sample = False
        for key, value in metrics.items():
            if self._update_latency_bucket(self._latency_stats["metrics"][key], value):
                self._update_latency_bucket(code_stats["metrics"][key], value)
                wrote_sample = True

        if wrote_sample and (
            self._latency_stats["event_count"] % 100 == 0
            or (category == "ORDER" and result == "委託PENDING")
        ):
            self._write_latency_summary_snapshot(
                reason="order_pending" if category == "ORDER" and result == "委託PENDING" else "periodic",
            )

    @staticmethod
    def _latency_bucket_snapshot(bucket: dict) -> dict:
        count = int(bucket.get("count") or 0)
        total = float(bucket.get("sum") or 0.0)
        avg = round(total / count, 3) if count > 0 else None
        min_value = bucket.get("min")
        max_value = bucket.get("max")
        return {
            "count": count,
            "avg": avg,
            "min": round(float(min_value), 3) if min_value is not None else None,
            "max": round(float(max_value), 3) if max_value is not None else None,
        }

    def _write_latency_summary_snapshot(self, *, reason: str) -> None:
        stats = self._latency_stats or {}
        code_rows = []
        for code, payload in (stats.get("codes") or {}).items():
            metrics = payload.get("metrics") or {}
            market_snapshot = self._latency_bucket_snapshot(metrics.get("market_to_recv_ms") or {})
            decision_snapshot = self._latency_bucket_snapshot(metrics.get("decision_to_order_ms") or {})
            code_rows.append({
                "code": code,
                "name": payload.get("name", ""),
                "market_to_recv_ms": market_snapshot,
                "decision_to_order_ms": decision_snapshot,
                "last_category": payload.get("last_category", ""),
                "last_result": payload.get("last_result", ""),
                "last_reason": payload.get("last_reason", ""),
            })

        code_rows.sort(
            key=lambda row: (
                row["market_to_recv_ms"].get("max") or 0.0,
                row["decision_to_order_ms"].get("max") or 0.0,
            ),
            reverse=True,
        )
        record = {
            "logged_at": datetime.now().isoformat(timespec="microseconds"),
            "reason": reason,
            "started_at": stats.get("started_at"),
            "event_count": int(stats.get("event_count") or 0),
            "metrics": {
                key: self._latency_bucket_snapshot(bucket)
                for key, bucket in (stats.get("metrics") or {}).items()
            },
            "top_codes": code_rows[:20],
        }
        _append_jsonl_record(self._latency_summary_log_path(), record)

    def _pool_swap_worker(self, engine: TradingEngine, reserve_pool: dict) -> None:
        """背景執行緒：計算要換掉誰、補進誰，然後呼叫 replace_universe + resubscribe。

        兩階段邏輯：
          第一階段（本輪）— 主池篩出不在 8~10% 的股票、從備用池用昨量排序補入候選。
          第二階段（下輪，60 秒後）— 補入的股票已有行情，再次以真實漲幅排除。
        備用池股票無行情，無法即時確認漲幅，因此先用靜態指標（昨量）排序補入，
        等有行情後由下一輪掃描決定去留。
        """
        try:
            lo, hi = self._POOL_SWAP_PCT_LO, self._POOL_SWAP_PCT_HI
            summary = engine.get_summary()

            # ── 目前訂閱池的漲幅狀況 ──
            # 分三類：在範圍 / 不在範圍（可替換）/ 無行情（暫不動）
            in_range:  list[dict] = []
            out_range: list[dict] = []   # 有行情且不在 8~10%，且無持倉/委託/進場紀錄
            no_price:  list[dict] = []   # 尚未收到行情，本輪跳過
            protected_outside_range: list[dict] = []

            for row in summary:
                pct = row.get("change_pct")
                protected = (row.get("qty", 0) > 0
                             or row.get("pending", False)
                             or row.get("candle", 0) > 0)
                if pct is None:
                    no_price.append(row)
                elif lo <= pct <= hi:
                    in_range.append(row)
                elif not protected:
                    out_range.append(row)
                else:
                    protected_outside_range.append(row)

            push_log("INFO",
                f"[PoolSwap] 掃描：池內 {len(summary)} 支，"
                f"在範圍({lo}~{hi}%) {len(in_range)} 支，"
                f"待替換 {len(out_range)} 支，無行情 {len(no_price)} 支",
                include_traceback=False)
            self._write_pool_swap_snapshot(
                "scan",
                {
                    "range_pct": {"lo": lo, "hi": hi},
                    "pool_size": len(summary),
                    "reserve_pool_size": len(reserve_pool),
                    "active_codes": [row["code"] for row in summary],
                    "in_range_codes": [row["code"] for row in in_range],
                    "out_range_codes": [row["code"] for row in out_range],
                    "protected_outside_range_codes": [row["code"] for row in protected_outside_range],
                    "no_price_codes": [row["code"] for row in no_price],
                },
            )

            if not out_range:
                self._write_pool_swap_snapshot(
                    "skip",
                    {
                        "reason": "no_out_of_range_candidates",
                        "pool_size": len(summary),
                        "reserve_pool_size": len(reserve_pool),
                    },
                )
                return

            # ── 備用池候選：尚未訂閱，無即時行情 ──
            # 用昨量（prev_volume）降序排列，量大的流動性好，較容易出現漲幅機會
            subscribed = {row["code"] for row in summary}
            reserve_candidates: list[tuple[int, str]] = [
                (getattr(si, "prev_volume", 0) or 0, code)
                for code, si in reserve_pool.items()
                if code not in subscribed
            ]
            reserve_candidates.sort(reverse=True)   # 昨量大的優先

            if not reserve_candidates:
                push_log("INFO",
                    "[PoolSwap] 備用池已空，無法補入新股票",
                    include_traceback=False)
                self._write_pool_swap_snapshot(
                    "skip",
                    {
                        "reason": "reserve_pool_empty",
                        "pool_size": len(summary),
                        "reserve_pool_size": len(reserve_pool),
                        "out_range_codes": [row["code"] for row in out_range],
                    },
                )
                return

            # ── 決定換掉誰 ──
            # out_range 按「與 8~10% 中心的偏離度」降序排（最偏離的先換）
            mid = (lo + hi) / 2

            def _deviation(row):
                pct = row.get("change_pct") or 0.0
                return abs(pct - mid)

            out_range.sort(key=_deviation, reverse=True)
            swap_count = min(len(out_range), len(reserve_candidates))
            to_remove  = [row["code"] for row in out_range[:swap_count]]
            to_add     = [code for _, code in reserve_candidates[:swap_count]]

            def _fmt(codes, n=5):
                head = "、".join(codes[:n])
                return head + (f" 等 {len(codes)} 支" if len(codes) > n else "")

            push_log("INFO",
                f"[PoolSwap] 準備換股：移除 {_fmt(to_remove)} → 補入 {_fmt(to_add)}",
                include_traceback=False)
            self._write_pool_swap_snapshot(
                "plan",
                {
                    "pool_size": len(summary),
                    "reserve_pool_size": len(reserve_pool),
                    "swap_count": swap_count,
                    "planned_remove_codes": to_remove,
                    "planned_add_codes": to_add,
                    "reserve_candidate_codes": [code for _, code in reserve_candidates[:swap_count]],
                },
            )

            # ── 建立新的 symbol_infos（目前池 - 移除 + 加入）──
            remove_set = set(to_remove)
            with engine._lock:
                new_infos = {
                    code: st.info
                    for code, st in engine._states.items()
                    if code not in remove_set
                }
            for code in to_add:
                if code in reserve_pool:
                    new_infos[code] = reserve_pool[code]

            # replace_universe 會刪掉 _states 裡被移除的 code，先備份它們的 si
            with engine._lock:
                evicted_infos = {
                    code: engine._states[code].info
                    for code in remove_set
                    if code in engine._states
                }

            diff = engine.replace_universe(new_infos)

            feed_swapped = False
            if engine.feed is not None and hasattr(engine.feed, "swap_symbols"):
                try:
                    meta = {
                        code: SymbolMeta(
                            code=code,
                            limit_up=Decimal(str(new_infos[code].limit_up)),
                            prev_close=Decimal(str(new_infos[code].prev_close)),
                            open_limit_up=new_infos[code].open_limit_up,
                        )
                        for code in to_add
                        if code in new_infos
                    }
                    feed_swapped = bool(engine.feed.swap_symbols(to_remove, to_add, meta))
                except Exception as e:
                    push_log("WARN", f"[PoolSwap] 局部換股失敗，改走全量重訂閱：{e}")
                    feed_swapped = False

            if not feed_swapped:
                if engine.feed is not None:
                    try:
                        engine.feed.stop()
                    except Exception as e:
                        push_log("WARN", f"[PoolSwap] 停止 feed 時警告：{e}")

                try:
                    engine.resubscribe_feed()
                except Exception as e:
                    push_log("ERROR", f"[PoolSwap] 重新訂閱失敗：{e}")
                    return

            # 更新備用池：換進來的從備用池移除；換出去的（evicted）加回備用池
            actual_removed = set(diff["removed"])
            actual_added   = set(diff["added"])
            self._dispatch_ui(lambda r=actual_removed, a=actual_added, ev=evicted_infos:
                self._update_reserve_pool(r, a, ev))

            push_log("INFO",
                f"[PoolSwap] 換股完成：新增 {len(diff['added'])} 支、"
                f"移除 {len(diff['removed'])} 支、"
                f"保留（在新範圍）{len(diff['kept_in_new'])} 支、"
                f"保留（有持倉/委託）{len(diff['kept_protected'])} 支",
                include_traceback=False)
            post_summary = engine.get_summary()
            self._write_pool_swap_snapshot(
                "complete",
                {
                    "pool_size": len(post_summary),
                    "reserve_pool_size": len(self._reserve_pool),
                    "active_codes": [row["code"] for row in post_summary],
                    "added_codes": diff["added"],
                    "removed_codes": diff["removed"],
                    "kept_in_new_codes": diff["kept_in_new"],
                    "kept_protected_codes": diff["kept_protected"],
                    "planned_remove_codes": to_remove,
                    "planned_add_codes": to_add,
                },
            )

        except Exception as e:
            push_log("ERROR", f"[PoolSwap] 換股掃描發生例外：{e}")

    def _update_reserve_pool(self, removed_from_main: set, added_to_main: set,
                             evicted_infos: "Dict[str, object] | None" = None) -> None:
        """在主執行緒更新 _reserve_pool（避免 thread race）。"""
        # 換進主池的從備用池移除
        for code in added_to_main:
            self._reserve_pool.pop(code, None)
        # 換出主池的加回備用池（用 evicted_infos 裡 replace 前備份的 si）
        if evicted_infos:
            for code in removed_from_main:
                si = evicted_infos.get(code)
                if si is not None:
                    self._reserve_pool[code] = si

    def _sell_all_strategy_positions(self):
        if self.engine is None or not self._running:
            QMessageBox.information(self, "策略未啟動", "目前沒有執行中的策略持倉可賣出。")
            return
        summary = [s for s in self.engine.get_summary() if int(s.get("qty") or 0) > 0]
        if not summary:
            QMessageBox.information(self, "沒有持倉", "目前沒有策略持倉。")
            return

        preview = "、".join(f"{s['code']}({s['qty']}張)" for s in summary[:8])
        if len(summary) > 8:
            preview += f" 等 {len(summary)} 檔"
        answer = QMessageBox.question(
            self,
            "確認全部賣出",
            f"將賣出所有策略持倉：{preview}\n是否繼續？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        sold = self.engine.sell_all_strategy_positions("GUI 手動全部賣出")
        push_log("WARN", f"GUI 手動全部策略持股賣出：已送出 {sold} 檔")

    def _export_settings_json(self):
        from PyQt6.QtWidgets import QFileDialog

        base_dir = os.path.dirname(CONFIG_FILE)
        default_name = f"trading_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        default_path = os.path.join(base_dir, default_name)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "匯出設定 JSON",
            default_path,
            "JSON 檔案 (*.json);;所有檔案 (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"

        try:
            cfg = self._collect_config()
            cfg.save(path)
            push_log("INFO", f"設定已匯出至 JSON：{path}", include_traceback=False)
            QMessageBox.information(self, "匯出成功", f"設定已匯出：\n{path}")
        except ValueError as e:
            QMessageBox.critical(self, "格式錯誤", f"數字欄位格式有誤：{e}")
        except Exception as e:
            push_log("ERROR", f"匯出設定 JSON 失敗：{e}")
            QMessageBox.critical(self, "匯出失敗", str(e))

    def _import_settings_json(self):
        from PyQt6.QtWidgets import QFileDialog

        base_dir = os.path.dirname(CONFIG_FILE)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "匯入設定 JSON",
            base_dir,
            "JSON 檔案 (*.json);;所有檔案 (*)",
        )
        if not path:
            return

        try:
            cfg = TradingConfig.load_strict(path)
            self.cfg = cfg
            self._apply_config(cfg)
            self._app_state.last_trading_config_path = path
            self._save_app_state()
            push_log("INFO", f"設定已自 JSON 匯入：{path}", include_traceback=False)
            QMessageBox.information(
                self,
                "匯入成功",
                f"已載入設定：\n{path}\n\n目前已套用到畫面，按「儲存設定」可覆寫預設設定檔。",
            )
        except Exception as e:
            push_log("ERROR", f"匯入設定 JSON 失敗：{e}")
            QMessageBox.critical(self, "匯入失敗", str(e))

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

    def _on_mock_mode_toggled(self, use_mock: bool) -> None:
        """切換 Mock ↔ 真實富邦模式（即時替換 broker 實例）。"""
        if self._running:
            QMessageBox.warning(self, "策略運行中",
                "請先停止策略再切換行情模式。")
            # 恢復 toggle 狀態
            self._toggles["mock_mode"].set(not use_mock)
            return

        if use_mock:
            # 切回 Mock
            reply = QMessageBox.question(
                self, "切換 Mock 模式",
                "切換為 Mock 模擬行情模式，不連線富邦。確定？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._toggles["mock_mode"].set(False)
                return
            self._switch_to_mock_broker()
        else:
            # 切換為真實富邦
            reply = QMessageBox.question(
                self, "切換真實行情",
                "切換為富邦真實行情模式，系統將嘗試重新登入。\n"
                "請確認券商設定欄位或 JSON 設定檔內容正確。確定？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._toggles["mock_mode"].set(True)
                return
            self._switch_to_fubon_broker()

    def _switch_to_mock_broker(self) -> None:
        """切換為 MockAdapter。"""
        from broker import MockAdapter
        if self.broker is not None:
            try:
                self.broker.logout()
            except Exception:
                pass
        adapter = MockAdapter()
        adapter.login()
        self.set_broker(adapter)
        self._update_mock_mode_label(True)
        push_log("INFO", "已切換為 Mock 模擬行情模式", include_traceback=False)

    def _switch_to_fubon_broker(self) -> None:
        """切換為 FubonAdapter，登入失敗時自動退回 Mock。"""
        try:
            from broker import FubonAdapter, MockAdapter, BrokerError
            settings = self._broker_fields_to_settings()
            if not settings.is_complete():
                QMessageBox.critical(
                    self, "設定不完整",
                    "未設定富邦帳號資訊，請先填寫券商設定欄位，或先匯入 JSON 設定檔。"
                )
                self._toggles["mock_mode"].set(True)
                return

            if self.broker is not None:
                try:
                    self.broker.logout()
                except Exception:
                    pass

            push_log("INFO", "正在登入富邦券商…", include_traceback=False)
            adapter = FubonAdapter.from_config(settings)
            result = adapter.login()
            if result.success and result.selected:
                self.set_broker(adapter)
                self._update_mock_mode_label(False)
                push_log("INFO", f"富邦登入成功：{result.selected.display}", include_traceback=False)
            else:
                raise Exception(result.message or "登入失敗")

        except Exception as e:
            push_log("ERROR", f"富邦登入失敗：{e}，退回 Mock 模式")
            QMessageBox.critical(self, "登入失敗",
                f"無法連線富邦券商：\n{e}\n\n系統已退回 Mock 模式。")
            self._toggles["mock_mode"].set(True)
            self._switch_to_mock_broker()

    def _update_mock_mode_label(self, is_mock: bool) -> None:
        if not hasattr(self, "_mock_mode_lbl"):
            return
        if is_mock:
            self._mock_mode_lbl.setText("目前：Mock 模式（不連富邦）")
            self._mock_mode_lbl.setStyleSheet(f"color: {C['yellow_l']}; background: transparent;")
        else:
            acc = getattr(self.broker, "account", None)
            acc_txt = f" {acc.display}" if acc else ""
            self._mock_mode_lbl.setText(f"目前：富邦真實行情{acc_txt}")
            self._mock_mode_lbl.setStyleSheet(f"color: {C['green_l']}; background: transparent;")

    # ══════════════════════════════════════════
    #  策略開關
    # ══════════════════════════════════════════

    def _on_strategy_toggle(self, enabled: bool):
        if enabled:
            self._start_trading()
        else:
            self._stop_trading()

    def _start_trading(self):
        if self._running:
            return
        if self._strategy_starting:
            push_log("INFO", "策略資料仍在載入中，請稍候…", include_traceback=False)
            return

        cfg = self._collect_config()
        self.cfg = cfg
        broker = self.broker
        if not cfg.get_markets():
            QMessageBox.warning(self, "市場未選擇", "請至少選擇上市或上櫃！")
            self._toggles["strategy_enabled"].set(False)
            self._set_badge_active(False)
            self._set_strategy_status("已停止", C["subtext"])
            return

        if self._is_after_market_close():
            self._toggles["strategy_enabled"].set(False)
            self._set_badge_active(False)
            self._set_strategy_status("收盤預覽", C["blue_l"])
            push_log(
                "INFO",
                    "目前已收盤，不啟動策略引擎與即時行情訂閱；改為更新收盤檢視 / 明日排除預覽。",
                include_traceback=False,
            )
            if broker is not None:
                self._dashboard_preview_summary = []
                self._dashboard_preview_broker_key = ""
                self._render_monitor([])
                self._preload_dashboard_preview_async(broker)
            return

        self._strategy_starting = True
        self._strategy_start_token += 1
        token = self._strategy_start_token

        self._realized_pnl = 0.0
        self._realized_cost_basis = 0.0
        self._unrealized_pnl = 0.0
        self._positions_cost = 0.0
        self._trade_count = 0
        self._buy_count = 0
        self._sell_count = 0
        self._daily_trade_codes = set()
        self._reset_latency_stats()
        self._clear_decision_detail()
        self._set_badge_loading()
        self._set_strategy_status("載入中…", C["yellow_l"])
        push_log("INFO", "策略啟動準備中，正在背景載入市場資料…", include_traceback=False)

        threading.Thread(
            target=self._start_trading_worker,
            args=(token, cfg, broker),
            daemon=True,
        ).start()

    def _start_trading_worker(self, token: int, cfg: TradingConfig, broker) -> None:
        try:
            self._verify_time_before_strategy_start()
            if not self._is_start_token_current(token):
                return

            symbol_infos, feed, reserve_pool = self._load_trading_runtime(broker, cfg)
            if not self._is_start_token_current(token):
                return

            # ── Phase 1：盤中行情錄製（僅富邦真實 feed 有效） ──
            self._maybe_attach_recorder(cfg, feed, symbol_infos)

            engine = TradingEngine(
                config=cfg,
                on_log=push_log,
                on_trade=self._on_trade,
                on_status=lambda _s: None,
                on_strategy_event=self._on_strategy_event,
                on_decision_event=self._on_decision_event,
                on_clock_skew=self._on_clock_skew,
                feed=feed,
                symbol_infos=symbol_infos,
                broker=broker,
            )
            engine.start()

            if not self._is_start_token_current(token):
                try:
                    engine.stop()
                except Exception:
                    pass
                # 取消時也要把 recorder 收掉
                self._stop_recorder()
                return

            self._dispatch_ui(
                lambda token=token, engine=engine, rp=reserve_pool:
                    self._finish_start_trading(token, engine, rp))
        except Exception as e:
            # 啟動過程中失敗 → 同步收掉 recorder，避免殘留
            self._stop_recorder()
            self._dispatch_ui(
                lambda token=token, e=e: self._fail_start_trading(token, e))

    def _verify_time_before_strategy_start(self) -> None:
        result = verify_and_repair_cached(
            threshold_seconds=0.05,
            force_step_correction=True,
            cache_ttl_seconds=300.0,
        )
        for note in result.notes:
            push_log("INFO", f"[WindowsTime] {note}", include_traceback=False)
        for warning in result.warnings:
            push_log("WARN", f"[WindowsTime] {warning}", include_traceback=False)
        if not result.success:
            raise RuntimeError("Windows 時間偏移超過 50ms，且自動校正未成功，策略啟動已停止。")

    def _is_start_token_current(self, token: int) -> bool:
        return self._strategy_starting and self._strategy_start_token == token

    def _maybe_attach_recorder(self, cfg, feed, symbol_infos) -> None:
        """
        Phase 1：依設定建立 RecordingWriter 並掛到 feed 上。
        - 僅當 cfg.recording_enabled=True 且 feed 支援 attach_recorder 時生效
        - 失敗一律不影響策略啟動（只 log warning）
        """
        # 先收掉舊的（保險）
        if self._recorder is not None:
            try:
                self._recorder.close()
            except Exception:
                pass
            self._recorder = None

        if not getattr(cfg, "recording_enabled", False):
            return
        if feed is None or not hasattr(feed, "attach_recorder"):
            push_log("INFO",
                "[Recording] 目前 feed 不支援錄製（例如 Mock 模式），略過。",
                include_traceback=False)
            return
        try:
            from broker import (
                RecordingWriter, cleanup_old_recordings, default_recording_root,
            )
            from pathlib import Path
            from dataclasses import asdict as _asdict

            root = (Path(cfg.recording_dir).expanduser()
                    if cfg.recording_dir else default_recording_root())
            # 先清掉過期錄製
            try:
                removed = cleanup_old_recordings(root, cfg.recording_keep_days, log_cb=push_log)
                if removed:
                    push_log("INFO",
                        f"[Recording] 已清除 {removed} 個過期錄製目錄",
                        include_traceback=False)
            except Exception as e:
                push_log("WARN", f"[Recording] 清理舊錄製失敗：{e}")

            writer = RecordingWriter(out_root=root, log_cb=push_log)
            # 準備 meta：含 config snapshot 與訂閱清單
            symbol_universe = []
            try:
                for code, si in (symbol_infos or {}).items():
                    symbol_universe.append({
                        "code": code,
                        "name": getattr(si, "name", ""),
                        "market": getattr(si, "market", ""),
                        "prev_close": str(getattr(si, "prev_close", "")),
                        "limit_up": str(getattr(si, "limit_up_price", "")),
                    })
            except Exception:
                pass
            try:
                cfg_snapshot = _asdict(cfg)
            except Exception:
                cfg_snapshot = {}
            writer.start(meta={
                "config_snapshot": cfg_snapshot,
                "symbol_universe": symbol_universe,
                "symbol_count": len(symbol_universe),
            })
            feed.attach_recorder(writer, record_raw=bool(cfg.recording_record_raw))
            self._recorder = writer
            push_log("INFO",
                f"[Recording] 已啟用錄製 → {writer.session_dir}"
                f"（含原始訊息={cfg.recording_record_raw}，訂閱 {len(symbol_universe)} 檔）",
                include_traceback=False)
        except Exception as e:
            push_log("WARN", f"[Recording] 啟用失敗：{e}")
            self._recorder = None

    def _stop_recorder(self) -> None:
        """停止錄製並關檔（在背景執行緒呼叫 close 避免阻塞 UI）。"""
        rec = self._recorder
        if rec is None:
            return
        self._recorder = None
        def _do_close():
            try:
                rec.close()
            except Exception as e:
                push_log("WARN", f"[Recording] close 失敗：{e}")
        threading.Thread(target=_do_close, daemon=True, name="Recording-Close").start()

    def _load_trading_runtime(self, broker, cfg: TradingConfig):
        """回傳 (symbol_infos, feed, reserve_pool)。
        reserve_pool 是通過靜態篩選但超出訂閱上限的備用股，供動態換股使用。
        """
        # ── 載入 SymbolInfo（昨收 / 漲停 / 特殊股）──────────────
        symbol_infos = None
        feed = None
        reserve_pool: Dict[str, object] = {}
        if broker:
            try:
                from broker import FUBON_REALTIME_SYMBOL_LIMIT, ScanCriteria, scan_daily
                from broker.universe import (
                    FubonSymbolInfoLoader,
                    MarketSnapshotCache,
                    PreviousTradingDaysApiClient,
                )

                max_prior_streak = (
                    cfg.candle_limit - 1
                    if cfg.f7_enabled and cfg.candle_limit > 0 else None
                )

                crit = ScanCriteria(
                    price_min=Decimal(str(cfg.price_min)) if cfg.f9_enabled else Decimal("0"),
                    price_max=Decimal(str(cfg.price_max)) if cfg.f9_enabled else Decimal("999999"),
                    exclude_disposal=False,
                    exclude_attention=False,
                    exclude_day_trade_restricted=False,
                    markets=tuple(cfg.get_markets()),
                    min_prev_volume=(cfg.daily_volume_min if cfg.f8_enabled else 0),
                    # 先保留完整靜態候選，之後再切成主池 500 + 備用池 overflow。
                    max_candidates=10_000,
                    max_prior_limit_up_streak=max_prior_streak,
                )

                # 判斷是否為真實券商（FubonAdapter）
                is_fubon = hasattr(broker, "_sdk") or type(broker).__name__ == "FubonAdapter"

                if is_fubon:
                    loader = FubonSymbolInfoLoader(broker)
                    snapshot_cache = MarketSnapshotCache()
                    all_infos = {}
                    api_loaded = False

                    push_log("INFO",
                        f"正在透過前兩個交易日價量 API 取得市場 {list(crit.markets)} 全市場資料…",
                        include_traceback=False)
                    try:
                        price_client = PreviousTradingDaysApiClient()
                        all_infos = price_client.load_symbol_infos(markets=crit.markets)
                        api_loaded = True
                        source = "本地快取" if price_client.last_from_cache else "API"
                        push_log("INFO",
                            f"前兩個交易日價量已由{source}載入 {len(all_infos)} 支"
                            f"（as_of={price_client.last_as_of}）",
                            include_traceback=False)
                    except Exception as e:
                        push_log("WARN",
                            f"前兩個交易日價量 API 不可用，退回富邦 snapshot：{e}",
                            include_traceback=False)

                    if not api_loaded:
                        push_log("INFO",
                            f"正在透過 snapshot 取得市場 {list(crit.markets)} 全市場個股快照…",
                            include_traceback=False)
                        all_infos = loader.load_market_snapshots(
                            markets=crit.markets,
                            quote_type="COMMONSTOCK",
                            snapshot_cache=snapshot_cache,
                            cache_snapshots=self._is_after_market_close(),
                        )
                        if all_infos:
                            push_log("INFO",
                                f"snapshot 載入 {len(all_infos)} 支個股資料",
                                include_traceback=False)
                            if cfg.f7_enabled and cfg.candle_limit > 0:
                                updated = snapshot_cache.apply_prior_limit_up_streaks(
                                    all_infos.values(), max_days=cfg.candle_limit)
                                if updated:
                                    push_log("INFO",
                                        f"已用本地收盤快照標註 {updated} 支連續漲停天數",
                                        include_traceback=False)
                        else:
                            # 備援：snapshot 失敗時才退回舊路徑（會打 1900+ 次 ticker）
                            push_log("WARN",
                                "snapshot 未取得資料，退回逐支 ticker 模式（較慢）…",
                                include_traceback=False)
                            all_codes = loader.fetch_all_codes(markets=list(cfg.get_markets()))
                            push_log("INFO", f"全市場取得 {len(all_codes)} 支股票代碼", include_traceback=False)

                            if all_codes:
                                push_log("INFO", "正在批次取得個股基本資料（昨收/漲停/特殊股）…", include_traceback=False)
                                all_infos = loader.load(all_codes)
                                push_log("INFO", f"成功載入 {len(all_infos)} 支個股資料", include_traceback=False)
                            else:
                                push_log("WARN", "無法取得全市場代碼，請確認已登入且行情權限正常", include_traceback=False)

                    if all_infos:
                        # 步驟 2：依設定條件篩選候選股
                        candidates = scan_daily(all_infos.values(), crit)
                        if not api_loaded and cfg.f7_enabled and cfg.candle_limit > 0:
                            missing = [
                                si for si in candidates
                                if si.prior_limit_up_streak is None
                            ]
                            if missing:
                                updated = loader.enrich_prior_limit_up_streaks_from_history(
                                    missing, max_days=cfg.candle_limit, max_symbols=50)
                                if updated:
                                    push_log("INFO",
                                        f"快取不足，已補查 {updated} 支候選股日 K 漲停序列",
                                        include_traceback=False)
                                    candidates = scan_daily(all_infos.values(), crit)
                                elif len(missing) > 0:
                                    push_log("WARN",
                                        "部分候選股缺少昨日起漲停序列資料，已保守保留；"
                                        "建議收盤後更新一次全市場快照快取",
                                        include_traceback=False)
                        if cfg.f11_enabled:
                            if api_loaded:
                                candidates = self._confirm_embedded_special_candidates(
                                    candidates,
                                    source="前兩個交易日價量 API",
                                )
                            else:
                                candidates = self._confirm_fubon_special_candidates(
                                    loader, candidates, cfg)
                        subscribed_candidates = candidates[:FUBON_REALTIME_SYMBOL_LIMIT]
                        reserve_candidates = candidates[FUBON_REALTIME_SYMBOL_LIMIT:]
                        symbol_infos = {si.code: si for si in subscribed_candidates}
                        # ── 備用池：僅保留「通過靜態篩選但超出 500 上限」的股票 ──
                        reserve_pool = {si.code: si for si in reserve_candidates}
                        push_log("INFO",
                            f"篩選後候選 {len(symbol_infos)} 支"
                            f"（價格 {crit.price_min}~{crit.price_max} 元"
                            f"，昨量 ≥ {crit.min_prev_volume} 張"
                            f"，日漲停序列 ≤ {max_prior_streak + 1 if max_prior_streak is not None else '不限'} 根）"
                            f"，備用池 {len(reserve_pool)} 支",
                            include_traceback=False)
                    elif api_loaded:
                        symbol_infos = {}
                        push_log("WARN", "前兩個交易日價量 API 未回傳可用個股資料", include_traceback=False)

                else:
                    # MockAdapter：使用 DEFAULT_MOCK_INFOS
                    from broker import DEFAULT_MOCK_INFOS
                    mock_crit = ScanCriteria(
                        price_min=crit.price_min,
                        price_max=crit.price_max,
                        exclude_disposal=cfg.f11_enabled,
                        exclude_attention=cfg.f11_enabled,
                        exclude_day_trade_restricted=cfg.f11_enabled,
                        markets=crit.markets,
                        min_prev_volume=0,
                        max_candidates=crit.max_candidates,
                        max_prior_limit_up_streak=crit.max_prior_limit_up_streak,
                    )
                    candidates = scan_daily(DEFAULT_MOCK_INFOS, mock_crit)
                    default_codes = [i.code for i in candidates]
                    symbol_infos = broker.load_symbol_info(default_codes)
                    push_log("INFO", f"Mock 模式，載入 {len(symbol_infos)} 支模擬股票", include_traceback=False)

                feed = broker.create_realtime_feed()
                if hasattr(feed, "set_disconnect_callback"):
                    feed.set_disconnect_callback(self._on_feed_disconnect)

            except Exception as e:
                push_log("WARN", f"載入個股基本資料失敗：{e}")
        return symbol_infos, feed, reserve_pool

    def _confirm_embedded_special_candidates(self, candidates: list, *, source: str) -> list:
        """Use special-stock flags already embedded in the upstream candidate data."""
        kept = []
        excluded = []
        for si in candidates:
            reasons = self._special_flag_reasons(si)
            if reasons:
                excluded.append(f"{si.code} {si.name}（{'/'.join(reasons)}）")
            else:
                kept.append(si)

        if excluded:
            preview = "、".join(excluded[:20])
            more = "" if len(excluded) <= 20 else f"，另 {len(excluded) - 20} 支"
            push_log(
                "INFO",
                f"F11 {source} 排除 {len(excluded)} 支特殊股：{preview}{more}",
                include_traceback=False,
            )
        push_log(
            "INFO",
            f"F11 {source} 已確認 {len(candidates)} 支候選股，保留 {len(kept)} 支；"
            "不使用富邦 API 特殊股 fallback",
            include_traceback=False,
        )
        return kept

    def _confirm_fubon_special_candidates(self, loader, candidates: list, cfg: TradingConfig) -> list:
        if not cfg.f11_enabled or not candidates:
            return candidates
        payload, source = official_special_flags.resolve_today_payload(
            base_dir=runtime_base_dir(),
            markets=cfg.get_markets(),
            allow_previous_cache=bool(getattr(cfg, "f11_allow_previous_day_official_cache", True)),
        )
        if payload is not None:
            return self._confirm_candidates_with_official_special_flags(
                candidates,
                payload,
                source=source,
            )

        push_log(
            "WARN",
            "F11 官方清單未取得當日更新資料，退回富邦 API 最後確認",
            include_traceback=False,
        )
        codes = [si.code for si in candidates]
        try:
            refreshed = loader.load(codes) or {}
        except Exception as exc:  # noqa: BLE001
            push_log(
                "ERROR",
                f"富邦 API 特殊股最後確認失敗，候選股暫不納入：{exc}",
                include_traceback=False,
            )
            return []

        kept = []
        excluded = []
        missing = []
        for si in candidates:
            fresh = refreshed.get(si.code)
            if fresh is None:
                missing.append(f"{si.code} {si.name}")
                continue
            si.is_disposal = bool(getattr(fresh, "is_disposal", False))
            si.is_attention = bool(getattr(fresh, "is_attention", False))
            si.is_day_trade_restricted = bool(getattr(fresh, "is_day_trade_restricted", False))
            reasons = self._special_flag_reasons(si)
            if reasons:
                excluded.append(f"{si.code} {si.name}（{'/'.join(reasons)}）")
            else:
                kept.append(si)

        if missing:
            preview = "、".join(missing[:20])
            more = "" if len(missing) <= 20 else f"，另 {len(missing) - 20} 支"
            push_log(
                "WARN",
                f"富邦 API 未回傳特殊股旗標，保守排除 {len(missing)} 支：{preview}{more}",
                include_traceback=False,
            )
        if excluded:
            preview = "、".join(excluded[:20])
            more = "" if len(excluded) <= 20 else f"，另 {len(excluded) - 20} 支"
            push_log(
                "INFO",
                f"F11 富邦 API 最後排除 {len(excluded)} 支特殊股：{preview}{more}",
                include_traceback=False,
            )
        push_log(
            "INFO",
            f"F11 富邦 API 已最後確認 {len(codes)} 支候選股，保留 {len(kept)} 支",
            include_traceback=False,
        )
        return kept

    def _confirm_candidates_with_official_special_flags(
        self,
        candidates: list,
        payload: dict,
        *,
        source: str,
    ) -> list:
        flags_map = payload.get("flags") if isinstance(payload, dict) else {}
        flags_map = flags_map if isinstance(flags_map, dict) else {}
        trade_date = str(payload.get("trade_date_roc") or "")
        generated_date = str(payload.get("generated_date") or "")
        try:
            payload_day = datetime.strptime(generated_date, "%Y-%m-%d").date()
        except Exception:
            payload_day = datetime.now().date()
        path = official_special_flags.cache_path(
            runtime_base_dir(),
            payload_day,
        )
        source_text = {
            "cache": "本地快取",
            "api": "官方 API",
            "previous_cache": "前一交易日快取",
        }.get(source, source)
        self._official_special_flags_meta = {
            "source": source,
            "trade_date_roc": trade_date,
            "flagged_count": len(flags_map),
            "cache_path": str(path),
        }
        push_log(
            "INFO",
            f"F11 官方清單已由{source_text}載入 {len(flags_map)} 筆"
            f"（trade_date={trade_date}，cache={path}）",
            include_traceback=False,
        )
        if source == "previous_cache":
            push_log(
                "WARN",
                f"F11 今日官方清單尚未更新，先使用前一交易日官方快取 trade_date={trade_date}",
                include_traceback=False,
            )

        kept = []
        excluded = []
        for si in candidates:
            raw = flags_map.get(si.code)
            info = raw if isinstance(raw, dict) else {}
            si.is_disposal = bool(info.get("is_disposal", False))
            si.is_attention = bool(info.get("is_attention", False))
            si.is_day_trade_restricted = bool(info.get("is_day_trade_restricted", False))
            reasons = self._special_flag_reasons(si)
            if reasons:
                excluded.append(f"{si.code} {si.name}（{'/'.join(reasons)}）")
            else:
                kept.append(si)

        if excluded:
            preview = "、".join(excluded[:20])
            more = "" if len(excluded) <= 20 else f"，另 {len(excluded) - 20} 支"
            push_log(
                "INFO",
                f"F11 官方清單排除 {len(excluded)} 支特殊股：{preview}{more}",
                include_traceback=False,
            )
        push_log(
            "INFO",
            f"F11 官方清單已最後確認 {len(candidates)} 支候選股，保留 {len(kept)} 支",
            include_traceback=False,
        )
        return kept

    @staticmethod
    def _special_flag_reasons(info) -> list:
        reasons = []
        if getattr(info, "is_disposal", False):
            reasons.append("處置")
        if getattr(info, "is_attention", False):
            reasons.append("注意")
        if getattr(info, "is_day_trade_restricted", False):
            reasons.append("禁當沖")
        return reasons

    def _finish_start_trading(self, token: int, engine: TradingEngine,
                              reserve_pool: "Dict[str, object] | None" = None) -> None:
        if not self._is_start_token_current(token):
            try:
                engine.stop()
            except Exception:
                pass
            return
        self.engine = engine
        self._reserve_pool = reserve_pool or {}
        self._pool_swap_warmup_done = False
        self._strategy_starting = False
        self._running = True
        self._set_badge_active(True)
        started_at = getattr(engine, "_started_at", None)
        started_txt = started_at.strftime("%H:%M:%S") if started_at else datetime.now().strftime("%H:%M:%S")
        self._set_strategy_status(f"運行中（{started_txt} 啟用）", C["green"])
        if token == self._last_socket_restart_token:
            self._last_socket_restart_result = "success"
            push_log(
                "INFO",
                "socket 自動重啟成功："
                f"token={token} last_disconnect={self._last_socket_disconnect_reason}",
                include_traceback=False,
            )
        self._start_pool_swap_timer()

    def _fail_start_trading(self, token: int, error: Exception) -> None:
        if not self._is_start_token_current(token):
            return
        self._strategy_starting = False
        self._running = False
        self._toggles["strategy_enabled"].set(False)
        self._set_badge_active(False)
        self._set_strategy_status("啟動失敗", C["red"])
        if token == self._last_socket_restart_token:
            self._last_socket_restart_result = "failed"
            push_log("ERROR", f"socket 自動重啟失敗：token={token} error={error}")
        push_log("ERROR", f"策略啟動失敗：{error}")

    def _stop_trading(self):
        was_starting = self._strategy_starting
        self._strategy_start_token += 1
        self._strategy_starting = False
        if int(self._latency_stats.get("event_count") or 0) > 0:
            try:
                self._write_latency_summary_snapshot(reason="stop")
            except Exception as e:
                push_log("WARN", f"[Latency] 寫入統計摘要失敗：{e}", include_traceback=False)
        if self.engine:
            threading.Thread(target=self.engine.stop, daemon=True).start()
        # Phase 1：停止盤中錄製並 flush 檔案
        self._stop_recorder()
        self._stop_pool_swap_timer()
        self._reserve_pool = {}
        self._running = False
        self._set_badge_active(False)
        self._set_strategy_status("已停止", C["subtext"])
        if was_starting:
            push_log("INFO", "策略啟動載入已取消", include_traceback=False)

    def _on_trade(self, d: dict):
        self._dispatch_ui(lambda: self._append_trade(d))

    # ══════════════════════════════════════════
    #  券商狀態（Milestone 1）
    # ══════════════════════════════════════════

    def set_broker(self, broker) -> None:
        """由 main.py 注入 broker 適配器，並更新狀態列。"""
        self._detach_gui_broker_callbacks()
        self.broker = broker
        if broker is not None and hasattr(broker, "set_dry_run"):
            try:
                broker.set_dry_run(self.cfg.order_dry_run)
            except Exception:  # noqa: BLE001
                pass
        self._sync_order_mode_control()

        # 同步 mock_mode toggle 狀態
        is_mock = broker is None or type(broker).__name__ == "MockAdapter"
        if "mock_mode" in self._toggles:
            self._toggles["mock_mode"].set(is_mock)
        self._update_mock_mode_label(is_mock)

        self._attach_gui_broker_callbacks(broker)
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

        broker_key = self._dashboard_broker_key(broker)
        if broker is None:
            self._dashboard_preview_summary = []
            self._dashboard_preview_broker_key = ""
            if not self._running:
                self._render_monitor([])
            return
        if not self._running and self._dashboard_preview_broker_key != broker_key:
            self._dashboard_preview_summary = []
            self._dashboard_preview_broker_key = ""
            self._render_monitor([])
            self._preload_dashboard_preview_async(broker)

    def _attach_gui_broker_callbacks(self, broker) -> None:
        if broker is None:
            return
        if hasattr(broker, "on_order"):
            try:
                broker.on_order(self._on_order_event)
            except Exception:  # noqa: BLE001
                pass
        if hasattr(broker, "on_filled"):
            try:
                broker.on_filled(self._on_fill_event)
            except Exception:  # noqa: BLE001
                pass
        self._broker_event_source = broker

    def _detach_gui_broker_callbacks(self) -> None:
        broker = self._broker_event_source
        if broker is None:
            return
        if hasattr(broker, "off_order"):
            try:
                broker.off_order(self._on_order_event)
            except Exception:  # noqa: BLE001
                pass
        if hasattr(broker, "off_filled"):
            try:
                broker.off_filled(self._on_fill_event)
            except Exception:  # noqa: BLE001
                pass
        self._broker_event_source = None

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
        self._dispatch_ui(lambda: self._render_account(snap))

    def _render_account(self, snap) -> None:
        render_account(self, snap)

    def _update_pnl_stats(self) -> None:
        realized = float(self._realized_pnl)
        unrealized = float(self._unrealized_pnl)
        total = realized + unrealized
        invested = float(self._positions_cost) + float(self._realized_cost_basis)
        total_rate = (total / invested * 100) if invested > 0 else 0.0

        realized_sign = "+" if realized >= 0 else ""
        realized_text = f"{realized_sign}{realized:,.0f}"
        realized_color = C["red"] if realized >= 0 else C["green"]
        self.stat_realized.setText(realized_text)
        self.stat_realized.setStyleSheet(f"color:{realized_color};")

        total_sign = "+" if total >= 0 else ""
        total_rate_sign = "+" if total_rate >= 0 else ""
        total_text = f"{total_sign}{total:,.0f}"
        total_color = C["red"] if total >= 0 else C["green"]
        self.stat_pnl_today.setText(total_text)
        self.stat_pnl_today.setStyleSheet(f"color:{total_color};")
        self.stat_return.setText(f"{total_rate_sign}{total_rate:.2f}%")
        self.stat_return.setStyleSheet(f"color:{total_color};")

    def _on_order_event(self, ev) -> None:
        """從 broker 執行緒接收 OrderEvent，丟回 GUI 主執行緒繪製。"""
        self._dispatch_ui(lambda: self._append_order(ev))

    def _on_fill_event(self, ev) -> None:
        """從 broker 執行緒接收 FillEvent，丟回 GUI 主執行緒更新成交時間。"""
        self._dispatch_ui(lambda: self._mark_order_filled(ev))
        svc = getattr(self, "_account_svc", None)
        if svc is not None:
            try:
                snap = svc.snapshot()
                self._on_account_snapshot(snap)
            except Exception:  # noqa: BLE001
                pass

    def _on_strategy_event(self, ev: dict) -> None:
        """從策略引擎接收結構化觸發紀錄，丟回 GUI 主執行緒繪製。"""
        self._dispatch_ui(lambda ev=ev: self._append_strategy_event(ev))

    def _on_decision_event(self, ev: dict) -> None:
        """從策略引擎接收決策明細事件，丟回 GUI 主執行緒繪製。"""
        try:
            self._write_decision_event_record(ev)
            self._record_latency_stats(ev)
        except Exception as e:
            push_log("WARN", f"[DecisionEvent] 寫入事件檔失敗：{e}", include_traceback=False)
        self._dispatch_ui(lambda ev=ev: self._append_decision_detail(ev))

    def _append_strategy_event(self, ev: dict) -> None:
        append_strategy_event(self, ev)

    def _append_decision_detail(self, ev: dict) -> None:
        append_decision_detail(self, ev)

    def _append_order(self, ev) -> None:
        append_order(self, ev)

    def _mark_order_filled(self, ev) -> None:
        mark_order_filled(self, ev)

    def _refresh_broker_status(self) -> None:
        refresh_broker_status(self)

    def _set_broker_status(self, text: str, dot_color: str, text_color: str, *, raw: bool = False) -> None:
        set_broker_status(self, text, dot_color, text_color, raw=raw)


    # ══════════════════════════════════════════
    #  輪詢更新
    # ══════════════════════════════════════════

    def _add_log_filter_buttons(self, layout: QHBoxLayout) -> None:
        for mode, text in (("all", "全部"), ("strategy", "策略")):
            btn = QPushButton(text)
            btn.setFont(_font(9))
            btn.setFixedSize(44, 22)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, m=mode: self._set_log_filter(m))
            self._log_filter_buttons.setdefault(mode, []).append(btn)
            layout.addWidget(btn)
        self._sync_log_filter_buttons()

    def _set_log_filter(self, mode: str) -> None:
        if mode not in ("all", "strategy"):
            return
        if self._log_filter == mode:
            return
        self._log_filter = mode
        self._sync_log_filter_buttons()
        self._render_log_views()

    def _sync_log_filter_buttons(self) -> None:
        for mode, buttons in self._log_filter_buttons.items():
            active = mode == self._log_filter
            for btn in buttons:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {C['blue'] if active else C['surface']};
                        color: {'#ffffff' if active else C['subtext']};
                        border: 1px solid {C['blue'] if active else C['border']};
                        border-radius: 3px;
                    }}
                    QPushButton:hover {{
                        background-color: {C['blue_l'] if active else C['border']};
                        color: #ffffff;
                    }}
                """)

    @staticmethod
    def _is_strategy_log(level: str, msg: str) -> bool:
        if level == "TRADE":
            return True
        text = str(msg)
        keywords = (
            "策略", "候選", "篩選", "進場", "出場", "漲停",
            "封板", "委賣", "下單", "成交", "資金不足",
            "可用額度", "處置", "注意", "禁當沖", "限當沖",
        )
        return any(keyword in text for keyword in keywords)

    def _log_entry_visible(self, entry: dict) -> bool:
        return self._log_filter == "all" or bool(entry.get("strategy"))

    def _append_log_html_to_views(self, html_text: str) -> None:
        append_log_html_to_views(self, html_text)

    def _render_log_views(self) -> None:
        render_log_views(self)

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
        if len(self._log_entries) > MAX_LINES:
            self._log_entries = self._log_entries[-MAX_LINES:]
            self._log_lines = len(self._log_entries)
            self._render_log_views()

    def _poll_monitor(self):
        if self._running and self.engine:
            summary = self.engine.get_summary()
            self._render_monitor(summary)

    def _clear_log(self):
        self._log_entries.clear()
        self.event_log.clear()
        if (hasattr(self, "events_full_log")
                and self.events_full_log is not self.event_log):
            self.events_full_log.clear()
        self._log_lines = 0

    def _append_log(self, level: str, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        color = self._log_colors.get(level, C["text"])
        bold = level == "TRADE"
        tag_o = "<b>" if bold else ""
        tag_c = "</b>" if bold else ""
        raw_lines = str(msg).splitlines() or [""]
        safe_lines = [html.escape(raw_lines[0])]
        safe_lines.extend(
            f"&nbsp;&nbsp;→ {html.escape(line.strip())}"
            for line in raw_lines[1:]
        )
        safe_msg = "<br>".join(safe_lines)
        html_text = (
            f'{tag_o}<span style="color:{color}; line-height:1.35;">'
            f'{ts} {safe_msg}</span>{tag_c}'
        )
        entry = {
            "html": html_text,
            "strategy": self._is_strategy_log(level, msg),
        }
        self._log_entries.append(entry)
        self._log_lines = len(self._log_entries)
        if self._log_entry_visible(entry):
            self._append_log_html_to_views(html_text)

    def _append_trade(self, d: dict):
        append_trade(self, d)

    def _update_trade_count_stat(self) -> None:
        self.stat_trade_cnt.setText(
            f"{len(self._daily_trade_codes)} / {self.cfg.daily_max_trades}"
        )

    def _render_monitor(self, summary: list):
        render_monitor(self, summary)

    def _is_volume_spike_highlighted(self, item: dict) -> bool:
        return is_volume_spike_highlighted(self, item)

    def _monitor_action_text(self, summary_item: dict, status: str) -> tuple[str, str]:
        if status == "啟用後已漲停":
            started = (summary_item.get("engine_started_at") or "").strip()
            if started:
                return f"{started} 已鎖", C["orange"]
            return "等撬開重鎖", C["orange"]
        if status == "明日排除":
            return "隔日不追", C["red_l"]
        if status == "收盤漲停":
            return "明日觀察", C["red_l"]
        if status in ("收盤觀察", "明日候選"):
            return "明日觀察", C["blue_l"]
        if status == "已完成":
            return "已封鎖", C["subtext"]
        if status == "已封鎖":
            return "已封鎖", C["subtext"]
        if status == "資金不足":
            return "不購買", C["red_l"]
        if status == "特殊排除":
            return "不購買", C["red_l"]
        if status == "確認失敗":
            return "查看日誌", C["red_l"]
        if status == "下單失敗":
            return "查看日誌", C["red_l"]
        if status == "出場中":
            return "等待賣出", C["purple"]
        if status == "已進場":
            return "監控出場", C["green_l"]
        if status == "委託中":
            return "等待成交", C["yellow_l"]
        if status == "委賣過多":
            return "等委賣降", C["orange"]
        if status == "條件不符":
            return "等待封板", C["subtext"]
        if summary_item.get("is_at_limit_up"):
            ask_qty = int(summary_item.get("ask_qty") or 0)
            if ask_qty >= self.cfg.ask_queue_threshold:
                return "等委賣降", C["orange"]
            # 引擎若有「最近一次略過」訊息，優先顯示，讓使用者知道目前卡在哪一條
            skip = (summary_item.get("last_skip_reason") or "").strip()
            if skip:
                # 取冒號前的關鍵字，例如 "F1:委賣 600 ≥ 500 張" → "略過:F1"
                head = skip.split(":", 1)[0] if ":" in skip else skip
                return f"略過:{head}", C["orange"]
            return "檢查進場", C["blue_l"]
        if summary_item.get("candle", 0) > 0:
            return "等待封板", C["yellow_l"]
        return "等待漲停", C["subtext"]

    def _compute_monitor_status(self, s: dict) -> str:
        if s.get("next_day_excluded"):
            return "明日排除"
        if self._is_after_close_monitor_item(s):
            return "收盤漲停" if s.get("closed_at_limit_up") else "收盤觀察"
        if s.get("startup_limitup_blocked") and s.get("is_at_limit_up"):
            return "啟用後已漲停"
        if s["blocked"]:
            reason = s.get("blocked_reason") or ""
            if reason == "資金不足":
                return "資金不足"
            if reason == "特殊股排除":
                return "特殊排除"
            if reason in ("特殊股確認失敗", "額度確認失敗"):
                return "確認失敗"
            if reason == "下單失敗":
                return "下單失敗"
            if reason:
                return "已封鎖"
            return "已完成"
        if s["pending"] and s["qty"] > 0:
            return "出場中"
        if s["pending"]:
            return "委託中"
        if s["qty"] > 0:
            return "已進場"
        if s.get("is_at_limit_up") and int(s.get("ask_qty") or 0) >= self.cfg.ask_queue_threshold:
            return "委賣過多"
        if s["candle"] > 0:
            return "準備進場" if s.get("is_at_limit_up") else "條件不符"
        return "等待"

    def _is_after_close_monitor_item(self, summary_item: dict) -> bool:
        return bool(summary_item.get("after_close_preview"))

    def _autosize_monitor_columns(self) -> None:
        autosize_monitor_columns(self)


# ──────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    win = App()
    win.show()
    sys.exit(app.exec())
