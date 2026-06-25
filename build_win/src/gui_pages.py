"""
gui_pages.py - App 主要頁面的 UI 建構函式。
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QLineEdit,
)

from gui_theme import (
    C,
    FONT_MAIN,
    FONT_MONO,
    DEFAULT_UI_SCALE_PERCENT,
    ToggleButton,
    _checkbox,
    _combo,
    _divider,
    _entry,
    _font,
    _label,
    _panel_frame,
    _scroll_style,
    _scaled,
    _section_title,
    _table_style,
)


def create_strategy_settings_panel(app) -> QFrame:
    panel = QFrame()
    app._strategy_settings_panel = panel
    panel.setStyleSheet(f"background-color: {C['sidebar']}; border: none;")
    outer = QVBoxLayout(panel)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    hdr = QFrame()
    hdr.setFixedHeight(_scaled(40))
    hdr.setStyleSheet(
        f"background-color: {C['header']};"
        f"border-bottom: 1px solid {C['border']};"
    )
    app._strategy_settings_header = hdr
    hl = QHBoxLayout(hdr)
    hl.setContentsMargins(_scaled(14), 0, _scaled(14), 0)
    icon = QLabel("⚙")
    icon.setFont(QFont("Segoe UI Emoji", _scaled(11)))
    icon.setStyleSheet(f"color: {C['subtext']}; background: transparent;")
    hl.addWidget(icon)
    hl.addSpacing(_scaled(6))
    hl.addWidget(_label("策略設定", C["text"], 10, bold=True))
    hl.addStretch()
    outer.addWidget(hdr)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setStyleSheet(
        f"QScrollArea {{ border: none; background-color: {C['sidebar']}; }}"
        + _scroll_style()
    )
    app._strategy_settings_scroll = scroll
    content = QWidget()
    content.setStyleSheet(f"background-color: {C['sidebar']};")
    app._strategy_settings_content = content
    form = QVBoxLayout(content)
    form.setContentsMargins(_scaled(14), _scaled(10), _scaled(14), _scaled(10))
    form.setSpacing(0)

    row = QHBoxLayout()
    row.addWidget(_label("啟用策略", C["text"], 10))
    row.addStretch()
    tog = ToggleButton(initial=False)
    tog.toggled.connect(app._on_strategy_toggle)
    app._toggles["strategy_enabled"] = tog
    row.addWidget(tog)
    form.addLayout(row)
    form.addSpacing(_scaled(10))
    form.addWidget(_divider())

    form.addWidget(_section_title("市場選擇"))
    mkt_row = QHBoxLayout()
    app._checks["market_twse"] = _checkbox("上市")
    app._checks["market_tpex"] = _checkbox("上櫃")
    mkt_row.addWidget(app._checks["market_twse"])
    mkt_row.addSpacing(_scaled(14))
    mkt_row.addWidget(app._checks["market_tpex"])
    mkt_row.addStretch()
    form.addLayout(mkt_row)
    form.addSpacing(_scaled(8))
    form.addWidget(_divider())

    form.addWidget(_section_title("交易設定"))
    app._sf(form, "每檔金額", "per_stock_amount", suffix="元", w=90)
    app._sf(form, "每日最大交易檔數", "daily_max_trades", suffix="檔", w=45)
    app._checks["dry_run_mode"] = _checkbox("模擬下單（不送出真實委託）")
    app._checks["dry_run_mode"].toggled.connect(app._on_order_mode_toggled)
    form.addWidget(app._checks["dry_run_mode"])
    form.addSpacing(_scaled(6))
    app._checks["file_logging_enabled"] = _checkbox("寫入實體 log 檔（含完整錯誤訊息）")
    form.addWidget(app._checks["file_logging_enabled"])
    form.addSpacing(_scaled(6))
    app._checks["recording_enabled"] = _checkbox("盤中錄製即時行情（供事後分析 / 復盤）")
    form.addWidget(app._checks["recording_enabled"])
    app._checks["recording_record_raw"] = _checkbox("　└ 同時錄製原始 SDK 訊息（檔案較大）")
    form.addWidget(app._checks["recording_record_raw"])
    rec_row = QHBoxLayout()
    rec_row.addWidget(_label("保留天數", C["subtext"], 9))
    app._fields["recording_keep_days"] = QLineEdit()
    app._fields["recording_keep_days"].setFixedWidth(_scaled(50))
    rec_row.addWidget(app._fields["recording_keep_days"])
    rec_row.addWidget(_label("天", C["subtext"], 9))
    rec_row.addStretch()
    form.addLayout(rec_row)
    rec_dir_row = QHBoxLayout()
    rec_dir_row.addWidget(_label("存放路徑", C["subtext"], 9))
    app._fields["recording_dir"] = QLineEdit()
    app._fields["recording_dir"].setPlaceholderText("留空 = 預設 log/recordings")
    rec_dir_row.addWidget(app._fields["recording_dir"], 1)
    form.addLayout(rec_dir_row)
    form.addSpacing(6)
    form.addWidget(_divider())

    mock_row = QHBoxLayout()
    mock_row.addWidget(_label("使用模擬行情", C["subtext"], 9))
    mock_row.addStretch()
    mock_tog = ToggleButton(initial=True)
    mock_tog.toggled.connect(app._on_mock_mode_toggled)
    app._toggles["mock_mode"] = mock_tog
    mock_row.addWidget(mock_tog)
    form.addLayout(mock_row)
    app._mock_mode_lbl = _label("目前：Mock 模式（不連富邦）", C["yellow_l"], 8)
    form.addWidget(app._mock_mode_lbl)
    form.addSpacing(4)
    form.addWidget(_divider())

    form.addWidget(_section_title("買入策略"))
    form.addWidget(_section_title("時間設定"))
    app._sf(form, "開始時間", "start_time", w=72)
    app._sf(form, "結束時間", "entry_before_time", w=72)
    form.addSpacing(4)
    form.addWidget(_divider())

    form.addWidget(_section_title("進場條件"))

    ask_row = QHBoxLayout()
    ask_row.addWidget(_label("漲停委賣張數 <", C["subtext"], 9))
    ask_row.addStretch()
    app._fields["ask_queue_threshold"] = _entry(55)
    ask_row.addWidget(app._fields["ask_queue_threshold"])
    ask_row.addSpacing(4)
    ask_row.addWidget(_label("張", C["subtext"], 9))
    form.addLayout(ask_row)
    form.addSpacing(6)

    app._checks["prelock_ask_entry_enabled"] = _checkbox("鎖板前委賣低於門檻先買")
    form.addWidget(app._checks["prelock_ask_entry_enabled"])
    form.addSpacing(6)

    form.addWidget(_label("只做起漲K", C["subtext"], 9))
    k_row = QHBoxLayout()
    k_row.addSpacing(4)
    app._checks["candle_k1"] = _checkbox("第一根")
    app._checks["candle_k2"] = _checkbox("第二根")
    k_row.addWidget(app._checks["candle_k1"])
    k_row.addSpacing(10)
    k_row.addWidget(app._checks["candle_k2"])
    k_row.addStretch()
    form.addLayout(k_row)
    form.addSpacing(6)

    vol_row = QHBoxLayout()
    vol_row.addWidget(_label("昨日成交量 >", C["subtext"], 9))
    vol_row.addStretch()
    app._fields["daily_volume_min"] = _entry(65)
    vol_row.addWidget(app._fields["daily_volume_min"])
    vol_row.addSpacing(4)
    vol_row.addWidget(_label("張", C["subtext"], 9))
    form.addLayout(vol_row)
    form.addSpacing(6)

    form.addWidget(_label("股價區間", C["subtext"], 9))
    pr_row = QHBoxLayout()
    pr_row.addSpacing(4)
    app._fields["price_min"] = _entry(50)
    pr_row.addWidget(app._fields["price_min"])
    pr_row.addSpacing(4)
    pr_row.addWidget(_label("~", C["subtext"], 9))
    pr_row.addSpacing(4)
    app._fields["price_max"] = _entry(50)
    pr_row.addWidget(app._fields["price_max"])
    pr_row.addSpacing(4)
    pr_row.addWidget(_label("元", C["subtext"], 9))
    pr_row.addStretch()
    form.addLayout(pr_row)
    form.addSpacing(6)

    app._checks["consume_enabled"] = _checkbox("消化量進場")
    form.addWidget(app._checks["consume_enabled"])
    form.addSpacing(4)
    consume_row = QHBoxLayout()
    consume_row.addWidget(_label("漲停成交量 >=", C["subtext"], 9))
    consume_row.addStretch()
    app._fields["consume_qty_threshold"] = _entry(55)
    consume_row.addWidget(app._fields["consume_qty_threshold"])
    consume_row.addSpacing(4)
    consume_row.addWidget(_label("張", C["subtext"], 9))
    form.addLayout(consume_row)
    form.addSpacing(4)
    app._checks["consume_mutex_with_f1"] = _checkbox("啟用消化量時略過時間/委賣策略")
    form.addWidget(app._checks["consume_mutex_with_f1"])
    form.addSpacing(6)
    mode_row = QHBoxLayout()
    mode_row.addWidget(_label("鎖漲停判斷", C["subtext"], 9))
    mode_row.addStretch()
    app._combos["limit_up_detection_mode"] = _combo([], 160)
    app._populate_limit_up_mode_combo(app._combos["limit_up_detection_mode"])
    mode_row.addWidget(app._combos["limit_up_detection_mode"])
    form.addLayout(mode_row)
    form.addSpacing(6)
    form.addWidget(_divider())

    form.addWidget(_section_title("排除條件"))
    ex1 = QHBoxLayout()
    app._checks["excl_disposal"] = _checkbox("處置股")
    app._checks["excl_attention"] = _checkbox("注意股")
    app._checks["excl_daytrade"] = _checkbox("限當沖股")
    ex1.addWidget(app._checks["excl_disposal"])
    ex1.addSpacing(6)
    ex1.addWidget(app._checks["excl_attention"])
    ex1.addSpacing(6)
    ex1.addWidget(app._checks["excl_daytrade"])
    ex1.addStretch()
    form.addLayout(ex1)
    form.addSpacing(4)
    app._checks["excl_open_limit"] = _checkbox("開盤漲停股票不追")
    form.addWidget(app._checks["excl_open_limit"])
    form.addSpacing(4)
    app._checks["excl_sealed"] = _checkbox("開盤漲停且已賣過不再進場")
    form.addWidget(app._checks["excl_sealed"])
    form.addSpacing(6)
    form.addWidget(_divider())

    form.addWidget(_section_title("賣出策略"))

    ex_row1 = QHBoxLayout()
    ex_row1.addWidget(_label("漲停打開時", C["subtext"], 9))
    ex_row1.addStretch()
    app._combos["exit_method1"] = _combo(["市價賣出", "限價賣出"], 88)
    ex_row1.addWidget(app._combos["exit_method1"])
    form.addLayout(ex_row1)
    form.addSpacing(6)

    form.addWidget(_label("賣出時間", C["subtext"], 9))
    exit_time_row = QHBoxLayout()
    exit_time_row.addSpacing(4)
    app._fields["exit_start_time"] = _entry(50)
    exit_time_row.addWidget(app._fields["exit_start_time"])
    exit_time_row.addSpacing(4)
    exit_time_row.addWidget(_label("~", C["subtext"], 9))
    exit_time_row.addSpacing(4)
    app._fields["exit_before_time"] = _entry(50)
    exit_time_row.addWidget(app._fields["exit_before_time"])
    exit_time_row.addStretch()
    form.addLayout(exit_time_row)
    form.addSpacing(6)

    open_tick_row = QHBoxLayout()
    open_tick_row.addWidget(_label("打開檔位 >=", C["subtext"], 9))
    open_tick_row.addStretch()
    app._fields["f4_open_ticks_to_sell"] = _entry(45)
    open_tick_row.addWidget(app._fields["f4_open_ticks_to_sell"])
    open_tick_row.addSpacing(4)
    open_tick_row.addWidget(_label("檔", C["subtext"], 9))
    form.addLayout(open_tick_row)
    form.addSpacing(4)
    app._checks["f4_require_today_limitup"] = _checkbox("僅當日曾觸及漲停才賣")
    form.addWidget(app._checks["f4_require_today_limitup"])
    form.addSpacing(6)

    app._checks["prelock_stop_enabled"] = _checkbox("鎖板前委賣進場跌破買價自動賣")
    form.addWidget(app._checks["prelock_stop_enabled"])
    form.addSpacing(4)
    prelock_stop_row = QHBoxLayout()
    prelock_stop_row.addWidget(_label("跌破買價 >=", C["subtext"], 9))
    prelock_stop_row.addStretch()
    app._fields["prelock_stop_ticks"] = _entry(45)
    prelock_stop_row.addWidget(app._fields["prelock_stop_ticks"])
    prelock_stop_row.addSpacing(4)
    prelock_stop_row.addWidget(_label("檔", C["subtext"], 9))
    form.addLayout(prelock_stop_row)
    form.addSpacing(6)

    sp_mode_row = QHBoxLayout()
    app._checks["f5_enabled"] = _checkbox("啟用 1 秒爆量賣出")
    form.addWidget(app._checks["f5_enabled"])
    form.addSpacing(4)
    sp_mode_row.addWidget(_label("1秒爆量方式", C["subtext"], 9))
    sp_mode_row.addStretch()
    app._combos["volume_spike_sell_mode"] = _combo(["固定張數", "比例"], 88)
    app._combos["volume_spike_sell_mode"].currentIndexChanged.connect(
        app._sync_volume_spike_mode_fields
    )
    sp_mode_row.addWidget(app._combos["volume_spike_sell_mode"])
    form.addLayout(sp_mode_row)
    form.addSpacing(4)

    sp_row = QHBoxLayout()
    sp_row.addWidget(_label("1秒成交量 >=", C["subtext"], 9))
    sp_row.addStretch()
    app._fields["volume_spike_sell_threshold"] = _entry(55)
    sp_row.addWidget(app._fields["volume_spike_sell_threshold"])
    sp_row.addSpacing(4)
    sp_row.addWidget(_label("張", C["subtext"], 9))
    form.addLayout(sp_row)

    sp_ratio_row = QHBoxLayout()
    sp_ratio_row.addWidget(_label("占漲停買一 >=", C["subtext"], 9))
    sp_ratio_row.addStretch()
    app._fields["volume_spike_sell_ratio_percent"] = _entry(55)
    sp_ratio_row.addWidget(app._fields["volume_spike_sell_ratio_percent"])
    sp_ratio_row.addSpacing(4)
    sp_ratio_row.addWidget(_label("%", C["subtext"], 9))
    form.addLayout(sp_ratio_row)
    form.addSpacing(6)

    ex_row3 = QHBoxLayout()
    ex_row3.addWidget(_label("委託排隊中過爆量", C["subtext"], 9))
    ex_row3.addStretch()
    app._combos["exit_method3"] = _combo(["取消委託", "保留委託"], 88)
    ex_row3.addWidget(app._combos["exit_method3"])
    form.addLayout(ex_row3)
    form.addSpacing(8)

    app.sell_all_strategy_btn = QPushButton("全部策略持股賣出")
    app.sell_all_strategy_btn.setFont(_font(9, bold=True))
    app.sell_all_strategy_btn.setFixedHeight(_scaled(30))
    app.sell_all_strategy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    app.sell_all_strategy_btn.setStyleSheet(
        f"""
            QPushButton {{
                background-color: {C['red']};
                color: #ffffff;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{ background-color: {C['red_l']}; }}
        """
    )
    app.sell_all_strategy_btn.clicked.connect(app._sell_all_strategy_positions)
    form.addWidget(app.sell_all_strategy_btn)

    form.addStretch()
    scroll.setWidget(content)
    outer.addWidget(scroll, 1)

    btn_bar = QFrame()
    btn_bar.setFixedHeight(_scaled(92))
    btn_bar.setStyleSheet(
        f"background-color: {C['header']};"
        f"border-top: 1px solid {C['border']};"
    )
    app._strategy_settings_button_bar = btn_bar
    bl = QVBoxLayout(btn_bar)
    bl.setContentsMargins(12, 8, 12, 8)
    bl.setSpacing(8)

    def _secondary_button(text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFont(_font(9, bold=True))
        btn.setFixedHeight(_scaled(34))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"""
                QPushButton {{
                    background-color: {C['surface']};
                    color: {C['text']};
                    border: 1px solid {C['border']};
                    border-radius: 4px;
                }}
                QPushButton:hover {{ background-color: #2d333b; }}
            """
        )
        return btn

    row1 = QHBoxLayout()
    row1.setSpacing(8)
    import_btn = _secondary_button("匯入 JSON")
    import_btn.clicked.connect(app._import_settings_json)
    row1.addWidget(import_btn, 1)
    export_btn = _secondary_button("匯出 JSON")
    export_btn.clicked.connect(app._export_settings_json)
    row1.addWidget(export_btn, 1)
    bl.addLayout(row1)

    row2 = QHBoxLayout()
    row2.setSpacing(8)
    reset_btn = _secondary_button("重置設定")
    reset_btn.clicked.connect(app._reset_settings)
    row2.addWidget(reset_btn, 1)

    save_btn = QPushButton("儲存設定")
    save_btn.setFont(_font(9, bold=True))
    save_btn.setFixedHeight(_scaled(34))
    save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    save_btn.setStyleSheet(
        f"""
            QPushButton {{
                background-color: {C['blue']};
                color: #ffffff;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{ background-color: {C['blue_l']}; }}
        """
    )
    save_btn.clicked.connect(app._save_settings)
    row2.addWidget(save_btn, 1)
    bl.addLayout(row2)

    outer.addWidget(btn_bar)
    return panel


def build_dashboard(app, parent: QWidget) -> None:
    outer = QHBoxLayout(parent)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    app._dashboard_settings_host = QWidget()
    app._dashboard_settings_host.setStyleSheet(f"background-color: {C['sidebar']};")
    app._dashboard_settings_lay = QVBoxLayout(app._dashboard_settings_host)
    app._dashboard_settings_lay.setContentsMargins(0, 0, 0, 0)
    app._dashboard_settings_lay.setSpacing(0)
    app._dashboard_settings_lay.addWidget(app._create_strategy_settings_panel())
    outer.addWidget(app._dashboard_settings_host)

    sep = QFrame()
    sep.setFixedWidth(_scaled(1))
    sep.setStyleSheet(f"background-color: {C['border']};")
    outer.addWidget(sep)

    content = QWidget()
    content.setStyleSheet(f"background-color: {C['bg']};")
    lay = QVBoxLayout(content)
    lay.setContentsMargins(_scaled(10), _scaled(10), _scaled(10), _scaled(10))
    lay.setSpacing(_scaled(8))

    build_stats_row(app, lay)
    build_mid_row(app, lay)
    build_bot_row(app, lay)
    outer.addWidget(content, 1)


def build_stats_row(app, lay: QVBoxLayout) -> None:
    row = QWidget()
    row.setFixedHeight(_scaled(76))
    row.setStyleSheet("background: transparent;")
    rl = QHBoxLayout(row)
    rl.setContentsMargins(0, 0, 0, 0)
    rl.setSpacing(8)

    defs = [
        ("今日損益", "stat_pnl_today", "+0", C["green"]),
        ("今日報酬率", "stat_return", "+0.00%", C["green"]),
        ("已實現損益", "stat_realized", "+0", C["green"]),
        ("持倉檔數", "stat_positions", "0", C["text"]),
        ("今日交易檔數", "stat_trade_cnt", "0 / 0", C["text"]),
        ("可用額度", "stat_available", "0", C["text"]),
    ]
    for label_txt, attr, init, color in defs:
        frame = _panel_frame()
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(14, 6, 14, 6)
        fl.setSpacing(3)
        fl.addWidget(_label(label_txt, C["subtext"], 9))
        val_lbl = QLabel(init)
        val_lbl.setFont(QFont(FONT_MAIN, _scaled(18), QFont.Weight.Bold))
        val_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        fl.addWidget(val_lbl)
        setattr(app, attr, val_lbl)
        rl.addWidget(frame, 1)

    lay.addWidget(row)


def build_mid_row(app, lay: QVBoxLayout) -> None:
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    rl = QHBoxLayout(row)
    rl.setContentsMargins(0, 0, 0, 0)
    rl.setSpacing(8)

    mon = _panel_frame()
    ml = QVBoxLayout(mon)
    ml.setContentsMargins(10, 8, 10, 8)
    ml.setSpacing(6)

    mh = QHBoxLayout()
    mh.addWidget(_label("即時監控", C["text"], 10, bold=True))
    mh.addSpacing(8)
    app.monitor_count_lbl = _label("共 0 檔", C["subtext"], 9)
    mh.addWidget(app.monitor_count_lbl)
    mh.addStretch()
    ml.addLayout(mh)

    cols = ["代碼", "名稱", "價格", "漲跌", "漲跌幅", "委賣張數", "1秒成交量", "起漲K", "狀態", "動作"]
    app.monitor_table = QTableWidget(0, len(cols))
    app.monitor_table.setHorizontalHeaderLabels(cols)
    app.monitor_table.setStyleSheet(_table_style())
    app.monitor_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    app.monitor_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    app.monitor_table.verticalHeader().setVisible(False)
    app.monitor_table.setShowGrid(True)
    app.monitor_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    monitor_header = app.monitor_table.horizontalHeader()
    monitor_header.setStretchLastSection(False)
    monitor_header.setMinimumSectionSize(_scaled(44))
    monitor_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    app.monitor_table.verticalHeader().setDefaultSectionSize(_scaled(28))
    for i, width in enumerate([52, 70, 66, 62, 72, 78, 86, 70, 102, 86]):
        app.monitor_table.setColumnWidth(i, _scaled(width))
    ml.addWidget(app.monitor_table, 1)
    rl.addWidget(mon, 3)

    ev = _panel_frame()
    el = QVBoxLayout(ev)
    el.setContentsMargins(10, 8, 10, 8)
    el.setSpacing(6)

    eh = QHBoxLayout()
    eh.addWidget(_label("事件日誌", C["text"], 10, bold=True))
    eh.addStretch()
    app._add_log_filter_buttons(eh)
    eh.addSpacing(6)
    clr_btn = QPushButton("清除")
    clr_btn.setFont(_font(9))
    clr_btn.setFixedSize(_scaled(46), _scaled(22))
    clr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    clr_btn.setStyleSheet(
        f"""
            QPushButton {{
                background-color: {C['red']};
                color: #ffffff;
                border: none;
                border-radius: 3px;
            }}
            QPushButton:hover {{ background-color: {C['red_l']}; }}
        """
    )
    clr_btn.clicked.connect(app._clear_log)
    eh.addWidget(clr_btn)
    el.addLayout(eh)

    app.event_log = QTextEdit()
    app.event_log.setReadOnly(True)
    app.event_log.setFont(QFont(FONT_MAIN, _scaled(9)))
    app.event_log.setStyleSheet(
        f"""
            QTextEdit {{
                background-color: {C['bg']};
                color: {C['text']};
                border: none;
                border-radius: 4px;
                padding: 4px;
            }}
            {_scroll_style()}
        """
    )
    el.addWidget(app.event_log, 1)
    rl.addWidget(ev, 1)

    lay.addWidget(row, 3)


def build_bot_row(app, lay: QVBoxLayout) -> None:
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    rl = QHBoxLayout(row)
    rl.setContentsMargins(0, 0, 0, 0)
    rl.setSpacing(8)

    pos = _panel_frame()
    pl = QVBoxLayout(pos)
    pl.setContentsMargins(10, 8, 10, 8)
    pl.setSpacing(6)
    ph = QHBoxLayout()
    ph.addWidget(_label("持倉部位", C["text"], 10, bold=True))
    ph.addStretch()
    pl.addLayout(ph)
    pos_cols = ["代碼", "名稱", "持股數", "成本價", "現價", "損益", "損益率", "狀態"]
    app.positions_table = QTableWidget(0, len(pos_cols))
    app.positions_table.setHorizontalHeaderLabels(pos_cols)
    app.positions_table.setStyleSheet(_table_style())
    app.positions_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    app.positions_table.verticalHeader().setVisible(False)
    app.positions_table.setShowGrid(True)
    app.positions_table.horizontalHeader().setStretchLastSection(True)
    app.positions_table.verticalHeader().setDefaultSectionSize(_scaled(26))
    for i, width in enumerate([48, 55, 52, 52, 52, 58, 58, 52]):
        app.positions_table.setColumnWidth(i, _scaled(width))
    pl.addWidget(app.positions_table, 1)
    app.pos_summary_lbl = _label("小計 (0)", C["subtext"], 9)
    app.pos_pnl_lbl = _label("+0  +0.00%", C["green"], 9, bold=True)
    ps_row = QHBoxLayout()
    ps_row.addWidget(app.pos_summary_lbl)
    ps_row.addStretch()
    ps_row.addWidget(app.pos_pnl_lbl)
    pl.addLayout(ps_row)
    rl.addWidget(pos, 2)

    ord_f = _panel_frame()
    ol = QVBoxLayout(ord_f)
    ol.setContentsMargins(_scaled(10), _scaled(8), _scaled(10), _scaled(8))
    ol.setSpacing(_scaled(6))
    oh = QHBoxLayout()
    oh.addWidget(_label("委託狀態", C["text"], 10, bold=True))
    oh.addStretch()
    ol.addLayout(oh)
    ord_cols = ["代碼", "名稱", "委託類別", "價格", "數量", "掛單時間", "成交時間", "狀態", "來源"]
    app.orders_table = QTableWidget(0, len(ord_cols))
    app.orders_table.setHorizontalHeaderLabels(ord_cols)
    app.orders_table.setStyleSheet(_table_style())
    app.orders_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    app.orders_table.verticalHeader().setVisible(False)
    app.orders_table.setShowGrid(True)
    app.orders_table.horizontalHeader().setStretchLastSection(True)
    app.orders_table.verticalHeader().setDefaultSectionSize(_scaled(26))
    for i, width in enumerate([48, 55, 62, 58, 46, 70, 70, 48, 46]):
        app.orders_table.setColumnWidth(i, _scaled(width))
    ol.addWidget(app.orders_table, 1)
    rl.addWidget(ord_f, 2)

    trd_f = _panel_frame()
    tl = QVBoxLayout(trd_f)
    tl.setContentsMargins(_scaled(10), _scaled(8), _scaled(10), _scaled(8))
    tl.setSpacing(_scaled(6))
    th = QHBoxLayout()
    th.addWidget(_label("成交記錄", C["text"], 10, bold=True))
    th.addStretch()
    tl.addLayout(th)
    trd_cols = ["時間", "代碼", "名稱", "類別", "價格", "數量", "明細", "損益"]
    app.trades_table = QTableWidget(0, len(trd_cols))
    app.trades_table.setHorizontalHeaderLabels(trd_cols)
    app.trades_table.setStyleSheet(_table_style())
    app.trades_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    app.trades_table.verticalHeader().setVisible(False)
    app.trades_table.setShowGrid(True)
    app.trades_table.horizontalHeader().setStretchLastSection(True)
    app.trades_table.verticalHeader().setDefaultSectionSize(_scaled(26))
    for i, width in enumerate([60, 48, 55, 44, 55, 44, 180, 55]):
        app.trades_table.setColumnWidth(i, _scaled(width))
    tl.addWidget(app.trades_table, 1)
    app.trd_summary_lbl = _label("小計", C["subtext"], 9)
    app.trd_pnl_lbl = _label("+0", C["green"], 9, bold=True)
    ts_row = QHBoxLayout()
    ts_row.addWidget(app.trd_summary_lbl)
    ts_row.addStretch()
    ts_row.addWidget(app.trd_pnl_lbl)
    tl.addLayout(ts_row)
    rl.addWidget(trd_f, 2)

    lay.addWidget(row, 2)


def build_settings_page(app, parent: QWidget) -> None:
    lay = QVBoxLayout(parent)
    lay.setContentsMargins(_scaled(20), _scaled(16), _scaled(20), _scaled(16))
    lay.setSpacing(0)
    app._settings_page_settings_host = QWidget()
    app._settings_page_settings_host.setStyleSheet(f"background-color: {C['bg']};")
    app._settings_page_settings_lay = QVBoxLayout(app._settings_page_settings_host)
    app._settings_page_settings_lay.setContentsMargins(0, 0, 0, 0)
    app._settings_page_settings_lay.setSpacing(0)
    lay.addWidget(app._settings_page_settings_host, 1)


def build_system_settings_page(app, parent: QWidget) -> None:
    lay = QVBoxLayout(parent)
    lay.setContentsMargins(_scaled(20), _scaled(16), _scaled(20), _scaled(16))
    lay.setSpacing(_scaled(12))

    title = _label("系統設定", C["text"], 13, bold=True)
    lay.addWidget(title)

    panel = _panel_frame()
    pl = QVBoxLayout(panel)
    pl.setContentsMargins(_scaled(18), _scaled(16), _scaled(18), _scaled(16))
    pl.setSpacing(_scaled(12))

    pl.addWidget(_section_title("介面"))
    scale_row = QHBoxLayout()
    scale_row.addWidget(_label("介面縮放", C["subtext"], 9))
    scale_row.addStretch()
    app._combos["ui_scale_percent"] = _combo([], 140)
    for value in (100, 110, 120, 130, 140):
        app._combos["ui_scale_percent"].addItem(
            "100%（目前預設）" if value == DEFAULT_UI_SCALE_PERCENT else f"{value}%",
            value,
        )
    scale_row.addWidget(app._combos["ui_scale_percent"])
    pl.addLayout(scale_row)
    pl.addWidget(_label("最小值維持目前版面；放大後會在重新啟動時套用。", C["subtext"], 9))

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    app.system_settings_apply_btn = QPushButton("儲存並重新啟動")
    app.system_settings_apply_btn.setFont(_font(9, bold=True))
    app.system_settings_apply_btn.setFixedHeight(_scaled(34))
    app.system_settings_apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    app.system_settings_apply_btn.setStyleSheet(
        f"""
            QPushButton {{
                background-color: {C['blue']};
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 0 {_scaled(14)}px;
            }}
            QPushButton:hover {{ background-color: {C['blue_l']}; }}
        """
    )
    app.system_settings_apply_btn.clicked.connect(app._save_system_settings_and_restart)
    btn_row.addWidget(app.system_settings_apply_btn)
    pl.addLayout(btn_row)

    pl.addWidget(_divider())
    pl.addWidget(_section_title("更新"))
    update_row = QHBoxLayout()
    update_row.addWidget(_label("版本更新", C["subtext"], 9))
    update_row.addStretch()
    app.system_settings_update_btn = QPushButton("檢查更新")
    app.system_settings_update_btn.setFont(_font(9, bold=True))
    app.system_settings_update_btn.setFixedHeight(_scaled(34))
    app.system_settings_update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    app.system_settings_update_btn.setStyleSheet(
        f"""
            QPushButton {{
                background-color: {C['surface']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 4px;
                padding: 0 {_scaled(14)}px;
            }}
            QPushButton:hover {{ background-color: #2d333b; }}
        """
    )
    app.system_settings_update_btn.clicked.connect(app._show_update_feature_pending)
    update_row.addWidget(app.system_settings_update_btn)
    pl.addLayout(update_row)
    pl.addWidget(_label("版本更新功能開發中。", C["subtext"], 9))

    lay.addWidget(panel, 0)
    lay.addStretch()


def build_placeholder(_app, parent: QWidget, title: str) -> None:
    lay = QVBoxLayout(parent)
    lay.setContentsMargins(_scaled(24), _scaled(24), _scaled(24), _scaled(24))
    lbl = _label(title, C["subtext"], 12)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addStretch()
    lay.addWidget(lbl)
    lay.addStretch()


def build_orders_page(app, parent: QWidget) -> None:
    lay = QVBoxLayout(parent)
    lay.setContentsMargins(_scaled(10), _scaled(10), _scaled(10), _scaled(10))
    lay.setSpacing(_scaled(8))

    ord_f = _panel_frame()
    ol = QVBoxLayout(ord_f)
    ol.setContentsMargins(10, 8, 10, 8)
    ol.setSpacing(6)
    oh = QHBoxLayout()
    oh.addWidget(_label("委託狀態", C["text"], 10, bold=True))
    oh.addStretch()
    ol.addLayout(oh)
    ord_cols = ["代碼", "名稱", "委託類別", "價格", "數量", "掛單時間", "成交時間", "狀態", "來源"]
    app.orders_full_table = QTableWidget(0, len(ord_cols))
    app.orders_full_table.setHorizontalHeaderLabels(ord_cols)
    app.orders_full_table.setStyleSheet(_table_style())
    app.orders_full_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    app.orders_full_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    app.orders_full_table.verticalHeader().setVisible(False)
    app.orders_full_table.setShowGrid(True)
    app.orders_full_table.horizontalHeader().setStretchLastSection(True)
    app.orders_full_table.verticalHeader().setDefaultSectionSize(_scaled(28))
    for i, width in enumerate([60, 80, 80, 72, 55, 90, 90, 65, 65]):
        app.orders_full_table.setColumnWidth(i, _scaled(width))
    ol.addWidget(app.orders_full_table, 1)
    app.orders_full_summary_lbl = _label("委託總計 (0)", C["subtext"], 9)
    ol.addWidget(app.orders_full_summary_lbl)
    lay.addWidget(ord_f, 1)

    trd_f = _panel_frame()
    tl = QVBoxLayout(trd_f)
    tl.setContentsMargins(10, 8, 10, 8)
    tl.setSpacing(6)
    th = QHBoxLayout()
    th.addWidget(_label("成交記錄", C["text"], 10, bold=True))
    th.addStretch()
    tl.addLayout(th)
    trd_cols = ["時間", "代碼", "名稱", "類別", "價格", "數量", "明細", "損益"]
    app.trades_full_table = QTableWidget(0, len(trd_cols))
    app.trades_full_table.setHorizontalHeaderLabels(trd_cols)
    app.trades_full_table.setStyleSheet(_table_style())
    app.trades_full_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    app.trades_full_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    app.trades_full_table.verticalHeader().setVisible(False)
    app.trades_full_table.setShowGrid(True)
    app.trades_full_table.horizontalHeader().setStretchLastSection(True)
    app.trades_full_table.verticalHeader().setDefaultSectionSize(_scaled(28))
    for i, width in enumerate([72, 60, 80, 55, 72, 55, 220, 72]):
        app.trades_full_table.setColumnWidth(i, _scaled(width))
    tl.addWidget(app.trades_full_table, 1)
    app.trades_full_pnl_lbl = _label("+0", C["green"], 9, bold=True)
    app.trades_full_summary_lbl = _label("成交總計 (0)", C["subtext"], 9)
    ts_row = QHBoxLayout()
    ts_row.addWidget(app.trades_full_summary_lbl)
    ts_row.addStretch()
    ts_row.addWidget(app.trades_full_pnl_lbl)
    tl.addLayout(ts_row)
    lay.addWidget(trd_f, 1)


def build_positions_page(app, parent: QWidget) -> None:
    lay = QVBoxLayout(parent)
    lay.setContentsMargins(_scaled(10), _scaled(10), _scaled(10), _scaled(10))
    lay.setSpacing(_scaled(8))

    pos_f = _panel_frame()
    pl = QVBoxLayout(pos_f)
    pl.setContentsMargins(_scaled(10), _scaled(8), _scaled(10), _scaled(8))
    pl.setSpacing(_scaled(6))
    ph = QHBoxLayout()
    ph.addWidget(_label("持倉部位", C["text"], 10, bold=True))
    ph.addStretch()
    pl.addLayout(ph)
    pos_cols = ["代碼", "名稱", "持股數", "成本價", "現價", "損益", "損益率", "狀態"]
    app.positions_full_table = QTableWidget(0, len(pos_cols))
    app.positions_full_table.setHorizontalHeaderLabels(pos_cols)
    app.positions_full_table.setStyleSheet(_table_style())
    app.positions_full_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    app.positions_full_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    app.positions_full_table.verticalHeader().setVisible(False)
    app.positions_full_table.setShowGrid(True)
    app.positions_full_table.horizontalHeader().setStretchLastSection(True)
    app.positions_full_table.verticalHeader().setDefaultSectionSize(_scaled(28))
    for i, width in enumerate([60, 80, 60, 70, 70, 72, 72, 60]):
        app.positions_full_table.setColumnWidth(i, _scaled(width))
    pl.addWidget(app.positions_full_table, 1)
    app.pos_full_summary_lbl = _label("小計 (0)", C["subtext"], 9)
    app.pos_full_pnl_lbl = _label("+0  +0.00%", C["green"], 9, bold=True)
    ps_row = QHBoxLayout()
    ps_row.addWidget(app.pos_full_summary_lbl)
    ps_row.addStretch()
    ps_row.addWidget(app.pos_full_pnl_lbl)
    pl.addLayout(ps_row)
    lay.addWidget(pos_f, 1)


def build_events_page(app, parent: QWidget) -> None:
    lay = QVBoxLayout(parent)
    lay.setContentsMargins(_scaled(10), _scaled(10), _scaled(10), _scaled(10))
    lay.setSpacing(_scaled(8))

    trigger_f = _panel_frame()
    tl = QVBoxLayout(trigger_f)
    tl.setContentsMargins(_scaled(10), _scaled(8), _scaled(10), _scaled(8))
    tl.setSpacing(_scaled(6))
    th = QHBoxLayout()
    th.addWidget(_label("策略觸發紀錄", C["text"], 10, bold=True))
    th.addStretch()
    app.decision_tab_toggle_btn = QPushButton("顯示決策明細")
    app.decision_tab_toggle_btn.setFont(_font(9))
    app.decision_tab_toggle_btn.setFixedHeight(_scaled(24))
    app.decision_tab_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    app.decision_tab_toggle_btn.clicked.connect(app._toggle_decision_detail_tab)
    th.addWidget(app.decision_tab_toggle_btn)
    th.addSpacing(8)
    app.strategy_trigger_summary_lbl = _label("共 0 筆", C["subtext"], 9)
    th.addWidget(app.strategy_trigger_summary_lbl)
    tl.addLayout(th)
    trigger_cols = ["時間", "代碼", "名稱", "買/賣", "策略", "明細"]
    app.strategy_trigger_table = QTableWidget(0, len(trigger_cols))
    app.strategy_trigger_table.setHorizontalHeaderLabels(trigger_cols)
    app.strategy_trigger_table.setStyleSheet(_table_style())
    app.strategy_trigger_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    app.strategy_trigger_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    app.strategy_trigger_table.verticalHeader().setVisible(False)
    app.strategy_trigger_table.setShowGrid(True)
    app.strategy_trigger_table.horizontalHeader().setStretchLastSection(True)
    app.strategy_trigger_table.verticalHeader().setDefaultSectionSize(_scaled(28))
    for i, width in enumerate([72, 60, 80, 58, 110, 360]):
        app.strategy_trigger_table.setColumnWidth(i, _scaled(width))
    tl.addWidget(app.strategy_trigger_table, 1)
    lay.addWidget(trigger_f, 1)

    ev_f = _panel_frame()
    el = QVBoxLayout(ev_f)
    el.setContentsMargins(_scaled(10), _scaled(8), _scaled(10), _scaled(8))
    el.setSpacing(_scaled(6))
    eh = QHBoxLayout()
    eh.addWidget(_label("事件日誌", C["text"], 10, bold=True))
    eh.addStretch()
    app._add_log_filter_buttons(eh)
    eh.addSpacing(6)
    clr_btn = QPushButton("清除")
    clr_btn.setFont(_font(9))
    clr_btn.setFixedSize(_scaled(46), _scaled(22))
    clr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    clr_btn.setStyleSheet(
        f"""
            QPushButton {{
                background-color: {C['red']};
                color: #ffffff;
                border: none;
                border-radius: 3px;
            }}
            QPushButton:hover {{ background-color: {C['red_l']}; }}
        """
    )
    clr_btn.clicked.connect(app._clear_log)
    eh.addWidget(clr_btn)
    el.addLayout(eh)
    app.events_full_log = QTextEdit()
    app.events_full_log.setReadOnly(True)
    app.events_full_log.setFont(QFont(FONT_MAIN, _scaled(9)))
    app.events_full_log.setStyleSheet(
        f"""
            QTextEdit {{
                background-color: {C['bg']};
                color: {C['text']};
                border: none;
                border-radius: 4px;
                padding: 4px;
            }}
            {_scroll_style()}
        """
    )
    el.addWidget(app.events_full_log, 1)
    lay.addWidget(ev_f, 1)
    app._sync_decision_tab_toggle_text()


def build_limitup_test_page(app, parent: QWidget) -> None:
    lay = QVBoxLayout(parent)
    lay.setContentsMargins(_scaled(10), _scaled(10), _scaled(10), _scaled(10))
    lay.setSpacing(_scaled(8))

    top_f = _panel_frame()
    tl = QVBoxLayout(top_f)
    tl.setContentsMargins(_scaled(10), _scaled(8), _scaled(10), _scaled(8))
    tl.setSpacing(_scaled(6))
    head = QHBoxLayout()
    head.addWidget(_label("鎖板測試 / 判斷分析", C["text"], 10, bold=True))
    head.addStretch()
    app.limitup_test_selected_lbl = _label("尚未選擇股票", C["subtext"], 9)
    head.addWidget(app.limitup_test_selected_lbl)
    head.addSpacing(8)
    app.limitup_test_apply_btn = QPushButton("套用選取模式")
    app.limitup_test_apply_btn.setFont(_font(9))
    app.limitup_test_apply_btn.setFixedHeight(_scaled(24))
    app.limitup_test_apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    app.limitup_test_apply_btn.clicked.connect(app._apply_selected_limitup_test_mode)
    head.addWidget(app.limitup_test_apply_btn)
    tl.addLayout(head)

    app.limitup_test_hint_lbl = _label(
        "上表選股票，下表看各模式在當前節點的成立結果，選一列後可直接套用。",
        C["subtext"],
        9,
    )
    tl.addWidget(app.limitup_test_hint_lbl)

    stock_cols = ["代碼", "名稱", "成交", "漲停", "啟用模式", "目前結果", "成立模式", "委賣", "買一", "賣一"]
    app.limitup_test_stock_table = QTableWidget(0, len(stock_cols))
    app.limitup_test_stock_table.setHorizontalHeaderLabels(stock_cols)
    app.limitup_test_stock_table.setStyleSheet(_table_style())
    app.limitup_test_stock_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    app.limitup_test_stock_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    app.limitup_test_stock_table.verticalHeader().setVisible(False)
    app.limitup_test_stock_table.setShowGrid(True)
    app.limitup_test_stock_table.horizontalHeader().setStretchLastSection(True)
    app.limitup_test_stock_table.verticalHeader().setDefaultSectionSize(_scaled(28))
    for i, width in enumerate([66, 86, 66, 66, 130, 70, 260, 60, 70, 70]):
        app.limitup_test_stock_table.setColumnWidth(i, _scaled(width))
    app.limitup_test_stock_table.currentCellChanged.connect(app._on_limitup_test_stock_changed)
    tl.addWidget(app.limitup_test_stock_table, 1)
    lay.addWidget(top_f, 1)

    bottom_f = _panel_frame()
    bl = QVBoxLayout(bottom_f)
    bl.setContentsMargins(_scaled(10), _scaled(8), _scaled(10), _scaled(8))
    bl.setSpacing(_scaled(6))
    bl.addWidget(_label("模式明細", C["text"], 10, bold=True))
    detail_cols = ["模式", "條件說明", "結果", "符合項目"]
    app.limitup_test_mode_table = QTableWidget(0, len(detail_cols))
    app.limitup_test_mode_table.setHorizontalHeaderLabels(detail_cols)
    app.limitup_test_mode_table.setStyleSheet(_table_style())
    app.limitup_test_mode_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    app.limitup_test_mode_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    app.limitup_test_mode_table.verticalHeader().setVisible(False)
    app.limitup_test_mode_table.setShowGrid(True)
    app.limitup_test_mode_table.horizontalHeader().setStretchLastSection(True)
    app.limitup_test_mode_table.verticalHeader().setDefaultSectionSize(_scaled(28))
    for i, width in enumerate([150, 250, 72, 500]):
        app.limitup_test_mode_table.setColumnWidth(i, _scaled(width))
    app.limitup_test_mode_table.currentCellChanged.connect(app._on_limitup_test_mode_changed)
    bl.addWidget(app.limitup_test_mode_table, 1)

    bl.addWidget(_label("當前資料快照", C["text"], 10, bold=True))
    app.limitup_test_snapshot = QTextEdit()
    app.limitup_test_snapshot.setReadOnly(True)
    app.limitup_test_snapshot.setFont(QFont(FONT_MONO, _scaled(9)))
    app.limitup_test_snapshot.setFixedHeight(_scaled(130))
    app.limitup_test_snapshot.setStyleSheet(
        f"""
            QTextEdit {{
                background-color: {C['bg']};
                color: {C['text']};
                border: none;
                border-radius: 4px;
                padding: 4px;
            }}
            {_scroll_style()}
        """
    )
    bl.addWidget(app.limitup_test_snapshot)
    lay.addWidget(bottom_f, 1)


def build_decision_detail_page(app, parent: QWidget) -> None:
    lay = QVBoxLayout(parent)
    lay.setContentsMargins(10, 10, 10, 10)
    lay.setSpacing(8)

    detail_f = _panel_frame()
    dl = QVBoxLayout(detail_f)
    dl.setContentsMargins(_scaled(10), _scaled(8), _scaled(10), _scaled(8))
    dl.setSpacing(_scaled(6))
    dh = QHBoxLayout()
    dh.addWidget(_label("決策明細", C["text"], 10, bold=True))
    dh.addSpacing(_scaled(8))
    app.decision_detail_summary_lbl = _label("共 0 筆", C["subtext"], 9)
    dh.addWidget(app.decision_detail_summary_lbl)
    dh.addStretch()
    hide_btn = QPushButton("隱藏頁籤")
    hide_btn.setFont(_font(9))
    hide_btn.setFixedHeight(_scaled(24))
    hide_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    hide_btn.clicked.connect(app._hide_decision_detail_tab)
    dh.addWidget(hide_btn)
    clear_btn = QPushButton("清除")
    clear_btn.setFont(_font(9))
    clear_btn.setFixedHeight(_scaled(24))
    clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    clear_btn.clicked.connect(app._clear_decision_detail)
    dh.addWidget(clear_btn)
    dl.addLayout(dh)

    detail_cols = ["時間", "代碼", "名稱", "類型", "結果", "原因/策略", "條件快照"]
    app.decision_detail_table = QTableWidget(0, len(detail_cols))
    app.decision_detail_table.setHorizontalHeaderLabels(detail_cols)
    app.decision_detail_table.setStyleSheet(_table_style())
    app.decision_detail_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    app.decision_detail_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    app.decision_detail_table.verticalHeader().setVisible(False)
    app.decision_detail_table.setShowGrid(True)
    app.decision_detail_table.horizontalHeader().setStretchLastSection(True)
    app.decision_detail_table.verticalHeader().setDefaultSectionSize(_scaled(28))
    for i, width in enumerate([72, 60, 80, 88, 88, 150, 520]):
        app.decision_detail_table.setColumnWidth(i, _scaled(width))
    dl.addWidget(app.decision_detail_table, 1)
    lay.addWidget(detail_f, 1)


def build_broker_page(app, parent: QWidget) -> None:
    outer = QVBoxLayout(parent)
    outer.setContentsMargins(_scaled(20), _scaled(16), _scaled(20), _scaled(16))
    outer.setSpacing(_scaled(12))

    hdr = QHBoxLayout()
    hdr.addWidget(_label("券商設定", C["text"], 13, bold=True))
    hdr.addSpacing(_scaled(12))
    app._broker_conn_dot = QLabel("●")
    app._broker_conn_dot.setFont(_font(10))
    app._broker_conn_dot.setStyleSheet(f"color:{C['subtext']}; background:transparent;")
    hdr.addWidget(app._broker_conn_dot)
    app._broker_conn_lbl = _label("未連線", C["subtext"], 10)
    hdr.addWidget(app._broker_conn_lbl)
    hdr.addStretch()
    outer.addLayout(hdr)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setStyleSheet(
        f"QScrollArea {{ border: none; background-color: {C['bg']}; }}"
        + _scroll_style()
    )
    content = QWidget()
    content.setStyleSheet(f"background-color: {C['bg']};")
    cl = QVBoxLayout(content)
    cl.setContentsMargins(0, 0, _scaled(12), 0)
    cl.setSpacing(_scaled(14))

    def _group(title: str) -> tuple:
        grp = _panel_frame()
        gl = QGridLayout(grp)
        gl.setContentsMargins(_scaled(16), _scaled(10), _scaled(16), _scaled(14))
        gl.setHorizontalSpacing(_scaled(12))
        gl.setVerticalSpacing(_scaled(8))
        gl.setColumnStretch(1, 1)
        title_lbl = _label(title, C["subtext"], 9, bold=True)
        title_lbl.setContentsMargins(0, 0, 0, 4)
        gl.addWidget(title_lbl, 0, 0, 1, 3)
        return grp, gl

    def _row(gl, row: int, label: str, key: str, pw: bool = False, width: int = 260, placeholder: str = ""):
        gl.addWidget(_label(label, C["subtext"], 9), row, 0)
        entry = _entry(width, password=pw)
        if placeholder:
            entry.setPlaceholderText(placeholder)
        app._bfields[key] = entry
        gl.addWidget(entry, row, 1)

    grp1, gl1 = _group("帳號資訊")
    _row(gl1, 1, "身分證字號", "personal_id", placeholder="A123456789")
    _row(gl1, 2, "網路下單密碼", "password", pw=True, placeholder="登入密碼")
    _row(gl1, 3, "分行代號", "branch_no", placeholder="例：6460")
    _row(gl1, 4, "帳號（7碼）", "account_no", placeholder="1234567")
    cl.addWidget(grp1)

    grp2, gl2 = _group("憑證設定")
    gl2.addWidget(_label("憑證檔案", C["subtext"], 9), 1, 0)
    cert_row = QHBoxLayout()
    app._bfields["cert_path"] = _entry(190)
    app._bfields["cert_path"].setPlaceholderText("憑證路徑 (.pfx / .p12)")
    app._bfields["cert_path"].setReadOnly(False)
    cert_row.addWidget(app._bfields["cert_path"])
    cert_row.addSpacing(_scaled(6))
    browse_btn = QPushButton("瀏覽…")
    browse_btn.setFont(_font(9))
    browse_btn.setFixedSize(_scaled(64), _scaled(26))
    browse_btn.setStyleSheet(
        f"""
            QPushButton {{
                background-color: {C['surface']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 4px;
            }}
            QPushButton:hover {{ background-color: #2d333b; }}
        """
    )
    browse_btn.clicked.connect(app._browse_cert)
    cert_row.addWidget(browse_btn)
    cert_w = QWidget()
    cert_w.setLayout(cert_row)
    cert_w.setStyleSheet("background:transparent;")
    gl2.addWidget(cert_w, 1, 1)
    _row(gl2, 2, "憑證密碼", "cert_password", pw=True, placeholder="留空則同身分證字號")
    cl.addWidget(grp2)

    grp3, gl3 = _group("API Key（選填）")
    _row(gl3, 1, "API Key", "api_key", placeholder="選填，申請後填入")
    _row(gl3, 2, "API Secret", "api_secret", pw=True, placeholder="選填")
    cl.addWidget(grp3)

    grp4, gl4 = _group("連線選項")
    gl4.addWidget(_label("模擬下單", C["subtext"], 9), 1, 0)
    dry_tog = ToggleButton(initial=True)
    app._toggles["broker_dry_run"] = dry_tog
    gl4.addWidget(dry_tog, 1, 1, Qt.AlignmentFlag.AlignLeft)
    gl4.addWidget(_label("（開啟：不送出真實委託）", C["subtext"], 8), 1, 2)
    cl.addWidget(grp4)

    cl.addStretch()
    scroll.setWidget(content)
    outer.addWidget(scroll, 1)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(_scaled(10))

    load_btn = QPushButton("匯入 JSON")
    load_btn.setFont(_font(9, bold=True))
    load_btn.setFixedHeight(_scaled(34))
    load_btn.setStyleSheet(
        f"""
            QPushButton {{
                background-color: {C['surface']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 4px; padding: 0 14px;
            }}
            QPushButton:hover {{ background-color: #2d333b; }}
        """
    )
    load_btn.clicked.connect(app._broker_import_json)
    btn_row.addWidget(load_btn)

    save_env_btn = QPushButton("匯出 JSON")
    save_env_btn.setFont(_font(9, bold=True))
    save_env_btn.setFixedHeight(_scaled(34))
    save_env_btn.setStyleSheet(
        f"""
            QPushButton {{
                background-color: {C['surface']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 4px; padding: 0 14px;
            }}
            QPushButton:hover {{ background-color: #2d333b; }}
        """
    )
    save_env_btn.clicked.connect(app._broker_export_json)
    btn_row.addWidget(save_env_btn)

    btn_row.addStretch()

    test_btn = QPushButton("測試連線")
    test_btn.setFont(_font(9, bold=True))
    test_btn.setFixedHeight(_scaled(34))
    test_btn.setStyleSheet(
        f"""
            QPushButton {{
                background-color: {C['yellow']};
                color: #000000;
                border: none;
                border-radius: 4px; padding: 0 16px;
            }}
            QPushButton:hover {{ background-color: {C['yellow_l']}; }}
        """
    )
    test_btn.clicked.connect(app._broker_test_connection)
    btn_row.addWidget(test_btn)

    connect_btn = QPushButton("連線並套用")
    connect_btn.setFont(_font(9, bold=True))
    connect_btn.setFixedHeight(_scaled(34))
    connect_btn.setStyleSheet(
        f"""
            QPushButton {{
                background-color: {C['blue']};
                color: #ffffff;
                border: none;
                border-radius: 4px; padding: 0 16px;
            }}
            QPushButton:hover {{ background-color: {C['blue_l']}; }}
        """
    )
    connect_btn.clicked.connect(app._broker_connect)
    btn_row.addWidget(connect_btn)

    outer.addLayout(btn_row)
    app._broker_load_default_json()
