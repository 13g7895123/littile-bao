"""
gui_renderers.py - GUI 表格同步與畫面渲染 helper。
"""
from __future__ import annotations

import math
from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableWidgetItem

from gui_theme import C
from limitup_detection import LIMIT_UP_DETECTION_MODES

STATUS_COLOR = {
    "準備進場": C["yellow_l"],
    "已進場": C["green"],
    "委賣過多": C["orange"],
    "條件不符": C["subtext"],
    "出場中": C["purple"],
    "已完成": C["subtext"],
    "已封鎖": C["subtext"],
    "資金不足": C["red_l"],
    "特殊排除": C["red_l"],
    "確認失敗": C["red_l"],
    "下單失敗": C["red_l"],
    "委託中": C["yellow_l"],
    "等待": C["subtext"],
    "收盤漲停": C["red_l"],
    "收盤觀察": C["blue_l"],
    "明日候選": C["blue_l"],
    "明日排除": C["red_l"],
}

STATUS_BG = {
    "準備進場": C["badge_ready"],
    "已進場": C["badge_in"],
    "委賣過多": "#3d1a00",
    "條件不符": C["badge_dim"],
    "出場中": C["badge_out"],
    "已完成": C["badge_dim"],
    "已封鎖": C["badge_dim"],
    "資金不足": C["badge_cancel"],
    "特殊排除": C["badge_cancel"],
    "確認失敗": C["badge_cancel"],
    "下單失敗": C["badge_cancel"],
    "委託中": C["badge_order"],
    "等待": C["badge_dim"],
    "收盤漲停": C["badge_cancel"],
    "收盤觀察": C["badge_ready"],
    "明日候選": C["badge_ready"],
    "明日排除": C["badge_cancel"],
}


def sync_orders_full_table(app) -> None:
    src = app.orders_table
    dst = app.orders_full_table
    if src is dst:
        return
    dst.setRowCount(0)
    for row in range(src.rowCount()):
        dst.insertRow(row)
        for col in range(src.columnCount()):
            item = src.item(row, col)
            if item:
                new_item = QTableWidgetItem(item.text())
                new_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                new_item.setForeground(item.foreground())
                if col == 0:
                    new_item.setData(Qt.ItemDataRole.UserRole, item.data(Qt.ItemDataRole.UserRole))
                dst.setItem(row, col, new_item)
    app.orders_full_summary_lbl.setText(f"委託總計 ({src.rowCount()})")


def sync_trades_full_table(app) -> None:
    src = app.trades_table
    dst = app.trades_full_table
    if src is dst:
        return
    dst.setRowCount(0)
    for row in range(src.rowCount()):
        dst.insertRow(row)
        for col in range(src.columnCount()):
            item = src.item(row, col)
            if item:
                new_item = QTableWidgetItem(item.text())
                new_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                new_item.setForeground(item.foreground())
                dst.setItem(row, col, new_item)
    app.trades_full_summary_lbl.setText(app.trd_summary_lbl.text())
    app.trades_full_pnl_lbl.setText(app.trd_pnl_lbl.text())
    app.trades_full_pnl_lbl.setStyleSheet(app.trd_pnl_lbl.styleSheet())


def sync_positions_full_table(app) -> None:
    src = app.positions_table
    dst = app.positions_full_table
    if src is dst:
        return
    dst.setRowCount(0)
    for row in range(src.rowCount()):
        dst.insertRow(row)
        for col in range(src.columnCount()):
            item = src.item(row, col)
            if item:
                new_item = QTableWidgetItem(item.text())
                new_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                new_item.setForeground(item.foreground())
                dst.setItem(row, col, new_item)
    app.pos_full_summary_lbl.setText(app.pos_summary_lbl.text())
    app.pos_full_pnl_lbl.setText(app.pos_pnl_lbl.text())
    app.pos_full_pnl_lbl.setStyleSheet(app.pos_pnl_lbl.styleSheet())


def append_log_html_to_views(app, html_text: str) -> None:
    app.event_log.append(html_text)
    scroll_bar = app.event_log.verticalScrollBar()
    scroll_bar.setValue(scroll_bar.maximum())
    if hasattr(app, "events_full_log") and app.events_full_log is not app.event_log:
        app.events_full_log.append(html_text)
        scroll_bar2 = app.events_full_log.verticalScrollBar()
        scroll_bar2.setValue(scroll_bar2.maximum())


def render_log_views(app) -> None:
    app.event_log.clear()
    if hasattr(app, "events_full_log") and app.events_full_log is not app.event_log:
        app.events_full_log.clear()
    for entry in app._log_entries:
        if app._log_entry_visible(entry):
            append_log_html_to_views(app, entry["html"])


def render_monitor(app, summary: list) -> None:
    app._latest_monitor_summary = list(summary or [])
    app._refresh_limitup_test_page(app._latest_monitor_summary)

    if summary:
        summary = [
            item for item in summary
            if (not item.get("out_of_range"))
            or item.get("next_day_excluded")
            or app._is_after_close_monitor_item(item)
        ]

    def _is_ready_to_enter(item: dict) -> bool:
        if item.get("next_day_excluded"):
            return False
        if app._is_after_close_monitor_item(item):
            return False
        if item.get("blocked"):
            return False
        if (item.get("qty") or 0) > 0:
            return False
        if item.get("pending"):
            return False
        return (item.get("candle") or 0) > 0

    def _sort_key(item: dict):
        code = str(item.get("code") or "")
        try:
            code_key = (0, int(code))
        except ValueError:
            code_key = (1, code)
        return (0 if _is_ready_to_enter(item) else 1, code_key)

    summary = sorted(summary, key=_sort_key)

    pos_cnt = 0
    next_excluded_cnt = sum(1 for item in summary if item.get("next_day_excluded"))
    after_close_cnt = sum(
        1 for item in summary
        if app._is_after_close_monitor_item(item) and not item.get("next_day_excluded")
    )
    if hasattr(app, "monitor_count_lbl"):
        if next_excluded_cnt:
            app.monitor_count_lbl.setText(
                f"收盤檢視 {len(summary) - next_excluded_cnt} / 明日排除 {next_excluded_cnt} 檔"
            )
        elif after_close_cnt:
            app.monitor_count_lbl.setText(f"收盤檢視 {after_close_cnt} 檔")
        else:
            app.monitor_count_lbl.setText(f"共 {len(summary)} 檔")

    order = {
        "準備進場": 0, "委託中": 1, "已進場": 2, "出場中": 3,
        "委賣過多": 4, "條件不符": 5,
        "資金不足": 6, "特殊排除": 7, "確認失敗": 8, "下單失敗": 9,
        "已封鎖": 10, "已完成": 11,
        "收盤漲停": 12, "收盤觀察": 13, "明日候選": 14, "明日排除": 15,
        "等待": 99,
    }
    app.monitor_table.setRowCount(0)
    app._monitor_rows.clear()
    summary = sorted(summary, key=lambda item: order.get(app._compute_monitor_status(item), 50))

    for item in summary:
        status = app._compute_monitor_status(item)
        if status == "已進場":
            pos_cnt += 1

        if item.get("next_day_excluded"):
            candle_txt = f"連{item.get('prior_limit_up_streak') or 0}根"
        elif app._is_after_close_monitor_item(item):
            candle_txt = "收盤"
        else:
            candle_txt = f"第{item['candle']}根" if item["candle"] > 0 else "—"
        fg = QColor(STATUS_COLOR.get(status, C["text"]))
        vol_fg = QColor(C["red"]) if is_volume_spike_highlighted(app, item) else fg

        price = item.get("price")
        change = item.get("change")
        change_pct = item.get("change_pct")
        ask_qty = item.get("ask_qty", 0)

        price_txt = f"{price:,.2f}" if price is not None else "—"
        if change is not None:
            change_txt = f"{'+' if change >= 0 else ''}{change:,.2f}"
            change_pct_txt = f"{'+' if change_pct >= 0 else ''}{change_pct:.2f}%"
            if change > 0:
                price_color = QColor(C["red"])
            elif change < 0:
                price_color = QColor(C["green"])
            else:
                price_color = QColor(C["text"])
        else:
            change_txt = "—"
            change_pct_txt = "—"
            price_color = QColor(C["subtext"])

        ask_qty_txt = str(ask_qty) if item.get("is_at_limit_up") else "—"
        ask_qty_color = QColor(C["orange"]) if ask_qty > 0 else QColor(C["subtext"])
        action_txt, action_color = app._monitor_action_text(item, status)

        values = [
            item["code"], item["name"], price_txt, change_txt, change_pct_txt,
            ask_qty_txt, str(item["vol_1s"]), candle_txt, status, action_txt,
        ]
        colors = [
            fg, fg, price_color, price_color, price_color,
            ask_qty_color, vol_fg, fg, fg, QColor(action_color),
        ]

        if item["code"] in app._monitor_rows:
            row = app._monitor_rows[item["code"]]
        else:
            row = app.monitor_table.rowCount()
            app.monitor_table.insertRow(row)
            app._monitor_rows[item["code"]] = row

        for col, (value, color) in enumerate(zip(values, colors)):
            table_item = QTableWidgetItem(value)
            table_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if col == 8:
                table_item.setForeground(QColor(STATUS_COLOR.get(status, C["text"])))
                table_item.setBackground(QColor(STATUS_BG.get(status, C["bg"])))
            else:
                table_item.setForeground(color)
            app.monitor_table.setItem(row, col, table_item)

    app.stat_positions.setText(str(pos_cnt))
    app._update_trade_count_stat()
    autosize_monitor_columns(app)


def is_volume_spike_highlighted(app, item: dict) -> bool:
    vol_1s = int(item.get("vol_1s") or 0)
    mode = str(getattr(app.cfg, "volume_spike_sell_mode", "qty") or "qty").lower()
    if mode == "ratio":
        limit_up = item.get("limit_up")
        bid0_price = item.get("bid0_price")
        bid0_volume = int(item.get("bid0_volume") or 0)
        if limit_up is None or bid0_price is None or bid0_volume <= 0:
            return False
        try:
            if Decimal(str(bid0_price)) != Decimal(str(limit_up)):
                return False
        except Exception:
            return False
        ratio_percent = max(0.0, float(getattr(app.cfg, "volume_spike_sell_ratio_percent", 0.0) or 0.0))
        if ratio_percent <= 0:
            return False
        threshold = max(1, int(math.ceil(bid0_volume * ratio_percent / 100.0)))
        return vol_1s >= threshold
    threshold = int(getattr(app.cfg, "volume_spike_sell_threshold", 0) or 0)
    return vol_1s >= threshold


def autosize_monitor_columns(app) -> None:
    if not hasattr(app, "monitor_table"):
        return
    min_widths = [52, 70, 66, 62, 72, 78, 86, 70, 102, 86]
    app.monitor_table.resizeColumnsToContents()
    for col, min_width in enumerate(min_widths):
        width = max(app.monitor_table.columnWidth(col) + 10, min_width)
        app.monitor_table.setColumnWidth(col, width)


def render_limitup_test_snapshot(app, item) -> None:
    if not hasattr(app, "limitup_test_snapshot"):
        return
    if not item:
        app.limitup_test_snapshot.setPlainText("尚無即時資料")
        return
    lines = [
        f"code={item.get('code') or ''}",
        f"name={item.get('name') or ''}",
        f"price={app._fmt_limitup_price(item.get('price'))}",
        f"limit_up={app._fmt_limitup_price(item.get('limit_up'))}",
        f"ask0={app._fmt_limitup_price(item.get('ask0_price'))} / vol={item.get('ask0_volume', 0)}",
        f"bid0={app._fmt_limitup_price(item.get('bid0_price'))} / vol={item.get('bid0_volume', 0)}",
        f"trade_bid={app._fmt_limitup_price(item.get('trade_bid'))}",
        f"trade_ask={app._fmt_limitup_price(item.get('trade_ask'))}",
        f"has_ask_levels={bool(item.get('has_ask_levels'))}",
        f"has_bid_levels={bool(item.get('has_bid_levels'))}",
        f"ask_qty={int(item.get('ask_qty') or 0)}",
        f"signals={item.get('limit_up_signals') or {}}",
        f"candidates={item.get('limit_up_candidates') or {}}",
    ]
    app.limitup_test_snapshot.setPlainText("\n".join(lines))


def render_limitup_test_detail(app, item) -> None:
    if not hasattr(app, "limitup_test_mode_table"):
        return
    table = app.limitup_test_mode_table
    table.setRowCount(0)
    if not item:
        if hasattr(app, "limitup_test_selected_lbl"):
            app.limitup_test_selected_lbl.setText("尚未選擇股票")
        render_limitup_test_snapshot(app, None)
        return
    if hasattr(app, "limitup_test_selected_lbl"):
        app.limitup_test_selected_lbl.setText(
            f"目前選擇：{item.get('code')} {item.get('name')} / 啟用={item.get('limit_up_mode')}"
        )
    candidates = dict(item.get("limit_up_candidates") or {})
    signals = dict(item.get("limit_up_signals") or {})
    selected_mode = app._limitup_test_selected_mode or item.get("limit_up_mode") or app._get_selected_limit_up_mode()
    selected_row = -1
    for row, (mode, desc) in enumerate(LIMIT_UP_DETECTION_MODES.items()):
        table.insertRow(row)
        result_text = "成立" if candidates.get(mode) else "未成立"
        color = QColor(C["green_l"] if candidates.get(mode) else C["subtext"])
        vals = [mode, desc, result_text, app._fmt_limitup_signal_hits(signals)]
        for col, val in enumerate(vals):
            item_widget = QTableWidgetItem(val)
            if col == 2:
                item_widget.setForeground(color)
            else:
                item_widget.setForeground(QColor(C["text"]))
            if mode == item.get("limit_up_mode"):
                item_widget.setBackground(QColor(C["badge_order"]))
            item_widget.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter
                if col != 3 else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(row, col, item_widget)
        if mode == selected_mode:
            selected_row = row
    if selected_row < 0:
        selected_row = 0 if table.rowCount() else -1
    if selected_row >= 0:
        table.setCurrentCell(selected_row, 0)
        app._limitup_test_selected_mode = str(table.item(selected_row, 0).text())
    render_limitup_test_snapshot(app, item)


def render_account(app, snap) -> None:
    mirror_positions = (
        hasattr(app, "positions_full_table")
        and app.positions_full_table is not app.positions_table
    )
    app.positions_table.setRowCount(0)
    if mirror_positions:
        app.positions_full_table.setRowCount(0)
    total_unr = 0.0
    total_cost = 0.0
    for position in snap.positions:
        row = app.positions_table.rowCount()
        app.positions_table.insertRow(row)
        unr = float(position.unrealized_pnl)
        unr_pct = float(position.unrealized_pnl_pct)
        total_unr += unr
        total_cost += float(position.avg_cost) * position.qty * 1000
        color = C["red"] if unr >= 0 else C["green"]
        cells = [
            (position.code, C["text"]),
            (position.name, C["text"]),
            (str(position.qty * 1000), C["text"]),
            (f"{float(position.avg_cost):,.2f}", C["text"]),
            (f"{float(position.last_price):,.2f}", C["text"]),
            (f"{'+' if unr >= 0 else ''}{unr:,.0f}", color),
            (f"{'+' if unr_pct >= 0 else ''}{unr_pct:.2f}%", color),
            ("持有", C["green"]),
        ]
        for col, (val, fg) in enumerate(cells):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QColor(fg))
            app.positions_table.setItem(row, col, item)
        if mirror_positions:
            app.positions_full_table.insertRow(row)
            for col, (val, fg) in enumerate(cells):
                item2 = QTableWidgetItem(val)
                item2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item2.setForeground(QColor(fg))
                app.positions_full_table.setItem(row, col, item2)
    app.stat_positions.setText(str(len(snap.positions)))
    app.stat_available.setText(f"{float(snap.buying_power):,.0f}")
    rate = (total_unr / total_cost * 100) if total_cost > 0 else 0.0
    summary_txt = f"小計 ({len(snap.positions)})"
    sign = "+" if total_unr >= 0 else ""
    rate_sign = "+" if rate >= 0 else ""
    pnl_txt = f"{sign}{total_unr:,.0f}  {rate_sign}{rate:.2f}%"
    pnl_color = C["red"] if total_unr >= 0 else C["green"]
    app.pos_summary_lbl.setText(summary_txt)
    app.pos_pnl_lbl.setText(pnl_txt)
    app.pos_pnl_lbl.setStyleSheet(f"color:{pnl_color};")
    if hasattr(app, "pos_full_summary_lbl"):
        app.pos_full_summary_lbl.setText(summary_txt)
        app.pos_full_pnl_lbl.setText(pnl_txt)
        app.pos_full_pnl_lbl.setStyleSheet(f"color:{pnl_color};")
    app._unrealized_pnl = total_unr
    app._positions_cost = total_cost
    app._update_pnl_stats()


def append_trade(app, trade: dict) -> None:
    app._trade_count += 1
    code = str(trade.get("code") or "").strip()
    if code:
        app._daily_trade_codes.add(code)
    mirror_trades = (
        hasattr(app, "trades_full_table")
        and app.trades_full_table is not app.trades_table
    )
    if trade["action"] == "BUY":
        app._buy_count += 1
    else:
        app._sell_count += 1
        app._realized_pnl += float(trade.get("pnl", 0.0))
        app._realized_cost_basis += float(trade.get("cost_basis", 0.0))

    action_color = C["green"] if trade["action"] == "BUY" else C["red"]
    label_txt = "買進" if trade["action"] == "BUY" else "賣出"
    pnl_val = float(trade.get("pnl", 0.0))
    if trade["action"] == "SELL":
        pnl_text = f"{'+' if pnl_val >= 0 else ''}{pnl_val:,.0f}"
        pnl_color = C["red"] if pnl_val >= 0 else C["green"]
    else:
        pnl_text = "—"
        pnl_color = C["subtext"]

    detail_time = str(trade.get("detail_time") or trade.get("time") or "")
    detail_txt = f"時間={detail_time}；數量={trade['qty']}"
    row = 0
    app.trades_table.insertRow(row)
    cells = [
        (trade["time"], action_color),
        (trade["code"], action_color),
        (trade["name"], action_color),
        (label_txt, action_color),
        (f"{trade['price']:,.2f}", action_color),
        (str(trade["qty"]), action_color),
        (detail_txt, C["subtext"]),
        (pnl_text, pnl_color),
    ]
    for col, (val, color) in enumerate(cells):
        item = QTableWidgetItem(val)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor(color))
        app.trades_table.setItem(row, col, item)
    if mirror_trades:
        app.trades_full_table.insertRow(0)
        for col, (val, color) in enumerate(cells):
            item2 = QTableWidgetItem(val)
            item2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item2.setForeground(QColor(color))
            app.trades_full_table.setItem(0, col, item2)

    app.trd_summary_lbl.setText(f"小計 ({app._trade_count})")
    sign = "+" if app._realized_pnl >= 0 else ""
    rp_text = f"{sign}{app._realized_pnl:,.0f}"
    rp_color = C["red"] if app._realized_pnl >= 0 else C["green"]
    app.trd_pnl_lbl.setText(rp_text)
    app.trd_pnl_lbl.setStyleSheet(f"color:{rp_color};")
    if hasattr(app, "trades_full_summary_lbl"):
        app.trades_full_summary_lbl.setText(f"成交總計 ({app._trade_count})")
        app.trades_full_pnl_lbl.setText(rp_text)
        app.trades_full_pnl_lbl.setStyleSheet(f"color:{rp_color};")
    app._update_pnl_stats()
    app._update_trade_count_stat()


def refresh_limitup_test_page(app, summary=None) -> None:
    if not hasattr(app, "limitup_test_stock_table"):
        return
    if summary is None:
        summary = app._latest_monitor_summary
    app._latest_monitor_summary = list(summary or [])
    table = app.limitup_test_stock_table
    table.blockSignals(True)
    table.setRowCount(0)
    rows = sorted(app._latest_monitor_summary, key=lambda item: str(item.get("code") or ""))
    for row, item in enumerate(rows):
        table.insertRow(row)
        candidates = dict(item.get("limit_up_candidates") or {})
        buy1_txt = f"{app._fmt_limitup_price(item.get('bid0_price'))}/{int(item.get('bid0_volume') or 0)}"
        sell1_txt = f"{app._fmt_limitup_price(item.get('ask0_price'))}/{int(item.get('ask0_volume') or 0)}"
        vals = [
            str(item.get("code") or ""),
            str(item.get("name") or ""),
            app._fmt_limitup_price(item.get("price")),
            app._fmt_limitup_price(item.get("limit_up")),
            str(item.get("limit_up_mode") or ""),
            "鎖板中" if item.get("is_at_limit_up") else "未鎖板",
            app._fmt_limitup_mode_hits(candidates),
            str(item.get("ask_qty") or 0),
            buy1_txt,
            sell1_txt,
        ]
        for col, val in enumerate(vals):
            cell = QTableWidgetItem(val)
            cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if col == 5:
                cell.setForeground(QColor(C["green_l"] if item.get("is_at_limit_up") else C["subtext"]))
            else:
                cell.setForeground(QColor(C["text"]))
            table.setItem(row, col, cell)
    if rows:
        codes = {str(item.get("code") or "") for item in rows}
        if app._limitup_test_selected_code not in codes:
            app._limitup_test_selected_code = str(rows[0].get("code") or "")
        for row in range(table.rowCount()):
            code_item = table.item(row, 0)
            if code_item and code_item.text() == app._limitup_test_selected_code:
                table.setCurrentCell(row, 0)
                break
    else:
        app._limitup_test_selected_code = ""
    table.blockSignals(False)
    render_limitup_test_detail(app, app._current_limitup_test_item())


def sync_decision_tab_toggle_text(app) -> None:
    btn = getattr(app, "decision_tab_toggle_btn", None)
    if btn is None:
        return
    visible = "decision_detail" not in app._hidden_tabs
    btn.setText("隱藏決策明細" if visible else "顯示決策明細")


def append_strategy_event(app, ev: dict) -> None:
    if not hasattr(app, "strategy_trigger_table"):
        return
    app._strategy_trigger_count += 1
    side = str(ev.get("side") or "")
    side_text = {"BUY": "買入", "SELL": "賣出", "CANCEL": "取消"}.get(side, side or "—")
    color = {"BUY": C["green"], "SELL": C["red"], "CANCEL": C["yellow_l"]}.get(side, C["text"])
    details = ev.get("details") or {}
    detail_txt = "；".join(f"{k}={v}" for k, v in details.items()) if isinstance(details, dict) else str(details)
    cells = [
        (str(ev.get("time") or ""), color),
        (str(ev.get("code") or ""), color),
        (str(ev.get("name") or ""), color),
        (side_text, color),
        (str(ev.get("strategy") or ""), color),
        (detail_txt, C["subtext"]),
    ]
    app.strategy_trigger_table.insertRow(0)
    for col, (val, fg) in enumerate(cells):
        item = QTableWidgetItem(val)
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignCenter if col < 5 else Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        item.setForeground(QColor(fg))
        app.strategy_trigger_table.setItem(0, col, item)
    if app.strategy_trigger_table.rowCount() > 300:
        app.strategy_trigger_table.removeRow(app.strategy_trigger_table.rowCount() - 1)
    app.strategy_trigger_summary_lbl.setText(f"共 {app._strategy_trigger_count} 筆")


def append_decision_detail(app, ev: dict) -> None:
    if not hasattr(app, "decision_detail_table"):
        return
    app._decision_detail_count += 1
    details = ev.get("details") or {}
    detail_txt = "；".join(f"{k}={v}" for k, v in details.items()) if isinstance(details, dict) else str(details)
    result = str(ev.get("result") or "")
    fg = {
        "未進場": C["yellow_l"],
        "封鎖進場": C["red"],
        "進場觸發": C["green"],
        "出場觸發": C["red"],
        "取消觸發": C["yellow_l"],
        "買進成交": C["green"],
        "賣出成交": C["red"],
        "鎖板中": C["red_l"],
        "未鎖板": C["subtext"],
    }.get(result, C["text"])
    app.decision_detail_table.insertRow(0)
    cells = [
        (str(ev.get("time") or ""), fg),
        (str(ev.get("code") or ""), fg),
        (str(ev.get("name") or ""), fg),
        (str(ev.get("category") or ""), fg),
        (result, fg),
        (str(ev.get("reason") or ""), C["text"]),
        (detail_txt, C["subtext"]),
    ]
    for col, (val, color) in enumerate(cells):
        item = QTableWidgetItem(val)
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignCenter if col < 6 else Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        item.setForeground(QColor(color))
        app.decision_detail_table.setItem(0, col, item)
    if app.decision_detail_table.rowCount() > 3000:
        app.decision_detail_table.removeRow(app.decision_detail_table.rowCount() - 1)
    app.decision_detail_summary_lbl.setText(f"共 {app._decision_detail_count} 筆")


def append_order(app, ev) -> None:
    oid = getattr(ev, "order_id", "")
    mirror_orders = hasattr(app, "orders_full_table") and app.orders_full_table is not app.orders_table
    row_idx = -1
    for row in range(app.orders_table.rowCount()):
        item = app.orders_table.item(row, 0)
        if item and item.data(Qt.ItemDataRole.UserRole) == oid:
            row_idx = row
            break

    side_txt = "買進" if ev.side.value == "BUY" else "賣出"
    status_map = {
        "PENDING": ("委託中", C["yellow_l"]),
        "PARTIAL": ("部分成交", C["orange"]),
        "FILLED": ("已成交", C["green"]),
        "CANCELLED": ("已取消", C["subtext"]),
        "REJECTED": ("已拒絕", C["red"]),
    }
    st_txt, st_color = status_map.get(ev.status.value, (ev.status.value, C["text"]))
    side_color = C["green"] if ev.side.value == "BUY" else C["red"]
    order_time_txt = getattr(getattr(ev, "time", None), "strftime", lambda _fmt: "")("%H:%M:%S")
    fill_time_txt = order_time_txt if ev.status.value == "FILLED" else ""

    if row_idx < 0:
        row_idx = 0
        app.orders_table.insertRow(row_idx)
        source = getattr(ev, "source", "") or ("DRY" if str(oid).startswith("DRY") else "REAL")
        cells = [
            (ev.code, side_color),
            (getattr(ev, "name", "") or "", side_color),
            (side_txt, side_color),
            (f"{float(ev.price):,.2f}", side_color),
            (str(ev.qty), side_color),
            (order_time_txt, C["subtext"]),
            (fill_time_txt, C["subtext"]),
            (st_txt, st_color),
            (source, C["yellow_l"] if source == "DRY" else C["red_l"]),
        ]
        for col, (val, color) in enumerate(cells):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QColor(color))
            if col == 0:
                item.setData(Qt.ItemDataRole.UserRole, oid)
            app.orders_table.setItem(row_idx, col, item)
        if mirror_orders:
            app.orders_full_table.insertRow(0)
            for col, (val, color) in enumerate(cells):
                item2 = QTableWidgetItem(val)
                item2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item2.setForeground(QColor(color))
                if col == 0:
                    item2.setData(Qt.ItemDataRole.UserRole, oid)
                app.orders_full_table.setItem(0, col, item2)
        if hasattr(app, "orders_full_summary_lbl"):
            app.orders_full_summary_lbl.setText(f"委託總計 ({app.orders_table.rowCount()})")
        return

    cell = app.orders_table.item(row_idx, 7)
    if cell:
        cell.setText(st_txt)
        cell.setForeground(QColor(st_color))
    if order_time_txt:
        order_time_cell = app.orders_table.item(row_idx, 5)
        if order_time_cell and not order_time_cell.text():
            order_time_cell.setText(order_time_txt)
    if fill_time_txt:
        fill_time_cell = app.orders_table.item(row_idx, 6)
        if fill_time_cell:
            fill_time_cell.setText(fill_time_txt)
            fill_time_cell.setForeground(QColor(C["subtext"]))
    if mirror_orders:
        for row in range(app.orders_full_table.rowCount()):
            item = app.orders_full_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == oid:
                cell2 = app.orders_full_table.item(row, 7)
                if cell2:
                    cell2.setText(st_txt)
                    cell2.setForeground(QColor(st_color))
                if order_time_txt:
                    order_time_cell2 = app.orders_full_table.item(row, 5)
                    if order_time_cell2 and not order_time_cell2.text():
                        order_time_cell2.setText(order_time_txt)
                if fill_time_txt:
                    fill_time_cell2 = app.orders_full_table.item(row, 6)
                    if fill_time_cell2:
                        fill_time_cell2.setText(fill_time_txt)
                        fill_time_cell2.setForeground(QColor(C["subtext"]))
                break


def mark_order_filled(app, ev) -> None:
    oid = getattr(ev, "order_id", "")
    if not oid:
        return
    fill_time_txt = getattr(getattr(ev, "time", None), "strftime", lambda _fmt: "")("%H:%M:%S")
    if not fill_time_txt:
        return
    for table in (app.orders_table, getattr(app, "orders_full_table", None)):
        if table is None:
            continue
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == oid:
                fill_item = table.item(row, 6)
                if fill_item is not None:
                    fill_item.setText(fill_time_txt)
                    fill_item.setForeground(QColor(C["subtext"]))
                break


def set_broker_status(app, text: str, dot_color: str, text_color: str, *, raw: bool = False) -> None:
    if hasattr(app, "broker_dot"):
        app.broker_dot.setStyleSheet(f"color: {dot_color}; background: transparent;")
    if hasattr(app, "broker_status_lbl"):
        app.broker_status_lbl.setText(text if raw else f"券商狀態：{text}")
        app.broker_status_lbl.setStyleSheet(f"color: {text_color}; background: transparent;")


def refresh_broker_status(app) -> None:
    if app.broker is None:
        set_broker_status(app, "未連線", C["subtext"], C["subtext"])
        return
    try:
        from broker import ConnectionState
    except ImportError:
        return
    state = getattr(app.broker, "state", None)
    account = getattr(app.broker, "account", None)
    if state == ConnectionState.CONNECTED:
        dry_run = bool(getattr(app.broker, "dry_run", True))
        mode = "模擬下單" if dry_run else "實單模式"
        label = f"券商狀態：已登入 {account.display}（{mode}）" if account else f"券商狀態：已連線（{mode}）"
        set_broker_status(app, label, C["green"], C["text"], raw=True)
    elif state == ConnectionState.CONNECTING:
        set_broker_status(app, "連線中…", C["yellow_l"], C["subtext"])
    elif state == ConnectionState.LOGIN_FAILED:
        set_broker_status(app, "登入失敗", C["red"], C["red"])
    elif state == ConnectionState.ERROR:
        set_broker_status(app, "連線錯誤", C["red"], C["red"])
    else:
        set_broker_status(app, "未連線", C["subtext"], C["subtext"])
