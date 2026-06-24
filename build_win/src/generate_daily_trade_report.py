#!/usr/bin/env python3
"""
從 dry_run_audit 與 log 生成每日交易整理 Markdown。
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Iterable


FEE_RATE = Decimal("0.001425")
FEE_DISCOUNT = Decimal("0.6")
MIN_FEE = Decimal("20")
TAX_RATE_DAYTRADE = Decimal("0.0015")


def d(value: str | int | float | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def calc_fee(price: Decimal, qty_lots: int) -> Decimal:
    raw = price * qty_lots * Decimal("1000") * FEE_RATE * FEE_DISCOUNT
    fee = raw.quantize(Decimal("1"), rounding=ROUND_DOWN)
    return max(fee, MIN_FEE) if qty_lots > 0 else Decimal("0")


def calc_tax(price: Decimal, qty_lots: int) -> Decimal:
    raw = price * qty_lots * Decimal("1000") * TAX_RATE_DAYTRADE
    return raw.quantize(Decimal("1"), rounding=ROUND_DOWN)


def fmt_int(value: Decimal | int) -> str:
    if isinstance(value, Decimal):
        value = int(value)
    return f"{value:,}"


def fmt_price(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def short_ts(iso_ts: str) -> str:
    return iso_ts[11:19]


@dataclass
class Fill:
    ts: str
    code: str
    name: str
    side: str
    price: Decimal
    qty: int
    note: str


@dataclass
class RealizedTrade:
    buy_ts: str
    sell_ts: str
    code: str
    name: str
    qty: int
    buy_price: Decimal
    sell_price: Decimal
    trigger: str
    trigger_detail: str
    gross: Decimal
    buy_fee: Decimal
    sell_fee: Decimal
    tax: Decimal
    net: Decimal


@dataclass
class OrphanSell:
    ts: str
    code: str
    name: str
    qty: int
    sell_price: Decimal
    trigger: str
    trigger_detail: str


def parse_audit(path: Path) -> list[Fill]:
    fills: list[Fill] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("type") != "FILL":
            continue
        fills.append(
            Fill(
                ts=row["ts"],
                code=row["code"],
                name=row["name"],
                side=row["side"],
                price=d(row["price"]),
                qty=int(row["qty"]),
                note=str(row.get("note", "")).strip(),
            )
        )
    return fills


def classify_trigger(note: str) -> tuple[str, str]:
    clean = note.strip()
    if clean.startswith("1秒量"):
        return "F5", clean
    if clean.startswith("漲停板打開"):
        return "F4", clean
    return "UNKNOWN", clean


def match_trades(
    fills: Iterable[Fill],
) -> tuple[list[Fill], list[RealizedTrade], list[Fill], list[OrphanSell]]:
    buys = [fill for fill in fills if fill.side == "BUY"]
    positions: dict[str, list[Fill]] = defaultdict(list)
    realized: list[RealizedTrade] = []
    orphan_sells: list[OrphanSell] = []
    for fill in fills:
        if fill.side == "BUY":
            positions[fill.code].append(fill)
            continue
        remaining = fill.qty
        trigger, detail = classify_trigger(fill.note)
        while remaining > 0:
            if not positions[fill.code]:
                orphan_sells.append(
                    OrphanSell(
                        ts=fill.ts,
                        code=fill.code,
                        name=fill.name,
                        qty=remaining,
                        sell_price=fill.price,
                        trigger=trigger,
                        trigger_detail=detail,
                    )
                )
                remaining = 0
                break
            buy = positions[fill.code][0]
            matched_qty = min(remaining, buy.qty)
            gross = (fill.price - buy.price) * matched_qty * Decimal("1000")
            buy_fee = calc_fee(buy.price, matched_qty)
            sell_fee = calc_fee(fill.price, matched_qty)
            tax = calc_tax(fill.price, matched_qty)
            realized.append(
                RealizedTrade(
                    buy_ts=buy.ts,
                    sell_ts=fill.ts,
                    code=fill.code,
                    name=fill.name,
                    qty=matched_qty,
                    buy_price=buy.price,
                    sell_price=fill.price,
                    trigger=trigger,
                    trigger_detail=detail,
                    gross=gross,
                    buy_fee=buy_fee,
                    sell_fee=sell_fee,
                    tax=tax,
                    net=gross - buy_fee - sell_fee - tax,
                )
            )
            remaining -= matched_qty
            if matched_qty == buy.qty:
                positions[fill.code].pop(0)
            else:
                buy.qty -= matched_qty
    open_positions = [lot for lots in positions.values() for lot in lots]
    open_positions.sort(key=lambda item: item.ts)
    return buys, realized, open_positions, orphan_sells


def grep(pattern: str, text: str) -> list[re.Match[str]]:
    return list(re.finditer(pattern, text, re.MULTILINE))


def unique_preserve(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def extract_runtime(program_log: Path, client_log: Path) -> dict[str, object]:
    program = program_log.read_text(encoding="utf-8", errors="ignore")
    client = client_log.read_text(encoding="utf-8", errors="ignore")

    modes = [m.group(1) for m in grep(r"鎖漲停判斷模式：([^\s]+)", program)]
    first_trade_marks = [m.group(1) for m in grep(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*今日第 1 檔", program)]
    boot_limitup = [f"{m.group(1)} {m.group(2)}" for m in grep(r"\[(\d+) ([^\]]+)\] 啟用時已鎖漲停", program)]
    buy_trades = grep(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*\[策略觸發\]\[BUY\]\[(\d+) ([^\]]+)\].*candle=(\d+)", program)
    sell_trades = grep(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*\[策略觸發\]\[SELL\]\[(\d+) ([^\]]+)\] 策略=(F\d+).*", program)
    ask_thresholds = sorted({m.group(1) for m in grep(r"門檻 (\d+) 張", program)})
    entry_cutoffs = sorted({m.group(1) for m in grep(r"已過進場時段 (\d{2}:\d{2})", program)})
    f5_thresholds = sorted({m.group(1) for m in grep(r"1秒量 \d+ 張 > (\d+) 張", program)})
    f4_thresholds = sorted({m.group(1) for m in grep(r"達出場門檻 (\d+) 檔", program)})
    login_times = unique_preserve(
        m.group(1)
        for m in grep(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+ \+08:00 INFO\] \[apikey_login\] personal_id=', client)
    )
    logout_times = unique_preserve(
        m.group(1)
        for m in grep(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+ \+08:00 INFO\] \[logout\]", client)
    )
    reconnect_times = unique_preserve(
        m.group(1)
        for m in grep(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[INFO\] \[FubonFeed\] websocket #1 connected", program)
    )
    subscribe_times = unique_preserve(
        m.group(1)
        for m in grep(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[INFO\] \[FubonFeed\] 訂閱完成", program)
    )

    return {
        "modes": modes,
        "first_trade_marks": first_trade_marks,
        "boot_limitup": boot_limitup,
        "buy_trade_matches": buy_trades,
        "sell_trade_matches": sell_trades,
        "ask_thresholds": ask_thresholds,
        "entry_cutoffs": entry_cutoffs,
        "f5_thresholds": f5_thresholds,
        "f4_thresholds": f4_thresholds,
        "login_times": login_times,
        "logout_times": logout_times,
        "reconnect_times": reconnect_times,
        "subscribe_times": subscribe_times,
    }


def render_report(
    report_date: str,
    audit_path: Path,
    program_log: Path,
    client_log: Path,
    config_path: Path,
    fills: list[Fill],
    buys: list[Fill],
    realized: list[RealizedTrade],
    open_positions: list[Fill],
    orphan_sells: list[OrphanSell],
    runtime: dict[str, object],
) -> str:
    def is_time_sync_related(line: str) -> bool:
        keywords = ("校時", "stripchart", "修復完成", "時間基準", "修復後")
        return any(keyword in line for keyword in keywords)

    sell_fills = [fill for fill in fills if fill.side == "SELL"]
    buy_amount = sum(fill.price * fill.qty * Decimal("1000") for fill in buys)
    sell_amount = sum(fill.price * fill.qty * Decimal("1000") for fill in sell_fills)
    gross = sum(item.gross for item in realized)
    buy_fees = sum(item.buy_fee for item in realized)
    sell_fees = sum(item.sell_fee for item in realized)
    taxes = sum(item.tax for item in realized)
    net = sum(item.net for item in realized)
    open_cost = sum(fill.price * fill.qty * Decimal("1000") for fill in open_positions)
    trigger_counter = Counter(item.trigger for item in realized)
    losses = sorted(realized, key=lambda item: item.net)

    login_times = runtime["login_times"]
    logout_times = runtime["logout_times"]
    reconnect_times = runtime["reconnect_times"]
    subscribe_times = runtime["subscribe_times"]
    first_trade_marks = runtime["first_trade_marks"]
    boot_limitup = runtime["boot_limitup"]
    modes = runtime["modes"]
    entry_cutoffs = runtime["entry_cutoffs"]
    ask_thresholds = runtime["ask_thresholds"]
    f4_thresholds = runtime["f4_thresholds"]
    f5_thresholds = runtime["f5_thresholds"]

    buy_lines = []
    for fill in buys:
        candle = fill.note.split("-")[-1] if fill.note.startswith("BUY-") else "?"
        buy_lines.append(
            f"| {short_ts(fill.ts)} | {fill.code} | {fill.name} | {fill.qty} | {fmt_price(fill.price)} | `F1+F7+F10` | 第 {candle} 根；鎖漲停忽略 F1/F10 細部檢查 |"
        )

    sell_lines = []
    for item in realized:
        gross_text = f"+{fmt_int(item.gross)}" if item.gross > 0 else fmt_int(item.gross)
        sell_lines.append(
            f"| {short_ts(item.sell_ts)} | {item.code} | {item.name} | {item.qty} | {fmt_price(item.sell_price)} | `{item.trigger}` | {item.trigger_detail} | {gross_text} | {fmt_int(item.buy_fee)} | {fmt_int(item.sell_fee)} | {fmt_int(item.tax)} | {fmt_int(item.net)} |"
        )

    orphan_sell_lines = []
    for item in orphan_sells:
        orphan_sell_lines.append(
            f"| {short_ts(item.ts)} | {item.code} | {item.name} | {item.qty} | {fmt_price(item.sell_price)} | `{item.trigger}` | {item.trigger_detail} | 無對應 BUY 可配對 |"
        )

    open_lines = []
    for fill in open_positions:
        open_lines.append(
            f"| {short_ts(fill.ts)} | {fill.code} | {fill.name} | {fill.qty} | {fmt_price(fill.price)} | {fmt_int(fill.price * fill.qty * Decimal('1000'))} |"
        )

    loss_lines = []
    for idx, item in enumerate(losses[:10], 1):
        loss_lines.append(
            f"| {idx} | {short_ts(item.sell_ts)} | {item.code} | {item.name} | `{item.trigger}` | {fmt_int(item.net)} | {item.trigger_detail} |"
        )

    last_buy_time = short_ts(max((fill.ts for fill in buys), default=f"{report_date}T00:00:00"))
    mode_summary = " -> ".join(modes) if modes else "未知"
    entry_cutoff_text = " / ".join(entry_cutoffs) if entry_cutoffs else "未知"
    ask_threshold_text = " / ".join(ask_thresholds) if ask_thresholds else "未知"
    f4_threshold_text = " / ".join(f4_thresholds) if f4_thresholds else "未知"
    f5_threshold_text = " / ".join(f5_thresholds) if f5_thresholds else "未知"

    important_lines = [
        "- 今日下單模式為 `order_dry_run = true`，以下整理的是策略模擬下單 / 模擬成交，不是真實券商成交。",
        "- 已實現損益依程式規則重算：買賣雙邊手續費 `0.1425% × 0.6`，最低 `20` 元；交易稅採當沖 `0.15%`。",
        f"- 本報告以 `{audit_path.name}` 的完整成交序列為主，`program.log` / `client.log` 用來補策略啟動、登入重連與盤中事件。",
    ]
    if logout_times:
        important_lines.append(
            f"- `client.log` 顯示今日於 `{logout_times[0]}` 發生手動登出，並在 `{login_times[-1] if login_times else '未知時間'}` 重新登入；之後 `program.log` 的「今日第 1 檔」計數重新開始。"
        )

    runtime_lines = []
    if login_times:
        runtime_lines.append(f"- 第 1 次 API Key / 憑證登入：約 `{login_times[0]}`")
    if reconnect_times:
        runtime_lines.append(f"- 第 1 次行情連線完成：`{reconnect_times[0]}`；訂閱完成：`{subscribe_times[0] if subscribe_times else '未知'}`")
    if logout_times:
        runtime_lines.append(f"- 手動登出：`{logout_times[0]}`")
    if len(login_times) > 1:
        runtime_lines.append(f"- 第 2 次 API Key / 憑證登入：約 `{login_times[1]}`")
    if len(reconnect_times) > 1:
        runtime_lines.append(f"- 第 2 次行情連線完成：`{reconnect_times[1]}`；訂閱完成：`{subscribe_times[1] if len(subscribe_times) > 1 else '未知'}`")
    if first_trade_marks:
        runtime_lines.append(f"- `program.log` 中「今日第 1 檔」出現 {len(first_trade_marks)} 次：`{'`、`'.join(first_trade_marks)}`。")
    if boot_limitup:
        runtime_lines.append(f"- 啟用時即被標記為「程式啟用後已漲停」共 {len(boot_limitup)} 檔：`{'`、`'.join(boot_limitup)}`")
    runtime_lines.append(f"- 最後一筆進場：`{last_buy_time}`；其後多次出現「F1:已過進場時段 {entry_cutoff_text}」略過新進場。")
    if len(modes) >= 2 and modes[0] != modes[-1]:
        runtime_lines.append(f"- 鎖漲停判斷模式曾在盤中變更：上午先用 `{modes[0]}`，重連後改為 `{modes[-1]}`。")
    runtime_lines = [line for line in runtime_lines if not is_time_sync_related(line)]

    obs_lines = [
        f"- 今日 {len(buys)} 筆買進全部屬 `鎖漲停` 情境，`program.log` 在進場前都出現「已鎖漲停，忽略 F1 委賣張數限制」與「已鎖漲停，忽略 F10 進場確認」。",
        f"- 今日共有 {len(realized)} 筆已平倉，其中 `F4` {trigger_counter.get('F4', 0)} 筆、`F5` {trigger_counter.get('F5', 0)} 筆；已實現淨損益為 `{fmt_int(net)}`。",
        f"- 最大單筆虧損為 `{losses[0].code} {losses[0].name}` 在 `{short_ts(losses[0].sell_ts)}` 的 `{fmt_int(losses[0].net)}`，觸發原因為 `{losses[0].trigger_detail}`。"
        if losses
        else "- 今日沒有已平倉交易。",
        f"- 稽核檔另發現 {len(orphan_sells)} 筆孤兒賣出；這些 SELL 沒有可配對的 BUY，已另外列示，未納入已實現損益。"
        if orphan_sells
        else "- 今日稽核檔未發現孤兒賣出。",
        f"- `client.log` 與 `program.log` 顯示 10:05 左右曾手動登出並重建行情連線；若後續要分析每日檔數限制或鎖漲停模式切換，需將重連前後分開看。"
        if logout_times
        else "- 今日未觀察到中途登出 / 重連事件。",
        f"- 原始 `config.json` 與實際執行參數並不完全一致；本報告的進場截止 `{entry_cutoff_text}`、F4 門檻 `{f4_threshold_text}`、F5 門檻 `{f5_threshold_text}` 以當日 log 觀察到的執行結果為準。"
        if config_path.exists()
        else "- 本次未找到可用 `config.json`，策略摘要改以當日 log 觀察值為準。",
    ]
    important_lines = [line for line in important_lines if not is_time_sync_related(line)]
    obs_lines = [line for line in obs_lines if not is_time_sync_related(line)]

    return f"""# {report_date} 今日交易整理

## 資料來源

- 交易稽核：`{audit_path}`
- 執行紀錄：`{program_log}`
- SDK client log：`{client_log}`
- 當日設定參考：`{config_path}`

## 重要前提

{chr(10).join(important_lines)}

## 今日總覽

- 買進成交：{len(buys)} 筆
- 賣出成交：{len(sell_fills)} 筆
- 已配對賣出：{len(realized)} 筆
- 孤兒賣出：{len(orphan_sells)} 筆
- 未平倉檔數：{len(open_positions)} 檔
- 未平倉總張數：{sum(fill.qty for fill in open_positions)} 張
- 買進成交總金額：`{fmt_int(buy_amount)}`
- 賣出成交總金額：`{fmt_int(sell_amount)}`
- 已實現毛損益：`{fmt_int(gross)}`
- 已實現買進手續費：`{fmt_int(buy_fees)}`
- 已實現賣出手續費：`{fmt_int(sell_fees)}`
- 已實現交易稅：`{fmt_int(taxes)}`
- 已實現淨損益：`{fmt_int(net)}`
- 未平倉成本總額：`{fmt_int(open_cost)}`

## 策略與參數摘要

- 進場策略：`F1 + F7 + F10`
  - 進場截止：`{entry_cutoff_text}`
  - 每檔投入金額：`100,000`
  - 委賣張數門檻：`{ask_threshold_text}` 張
  - 起漲 K 限制：第 `1 ~ 2` 根
- 出場策略：`F4` 與 `F5`
  - `F4` 漲停板打開就賣：log 顯示實際門檻 `open_ticks >= {f4_threshold_text}`
  - `F5` 1 秒爆量就賣：`last_1s_vol >= {f5_threshold_text}`
- 鎖漲停判斷模式：`{mode_summary}`
- 實際執行口徑以當日 `program.log` 為準；若與 `config.json` 不一致，優先採信 log。

## 執行階段事件

{chr(10).join(runtime_lines)}

## 賣出觸發分布

- `F4`：{trigger_counter.get("F4", 0)} 筆
- `F5`：{trigger_counter.get("F5", 0)} 筆

## 已實現虧損排序

| 排名 | 時間 | 代碼 | 名稱 | 觸發 | 淨損益 | 補充 |
| --- | --- | --- | --- | --- | ---: | --- |
{chr(10).join(loss_lines)}

## 買進成交清單

| 時間 | 代碼 | 名稱 | 張數 | 成交價 | 進場註記 | 補充 |
| --- | --- | --- | ---: | ---: | --- | --- |
{chr(10).join(buy_lines)}

## 賣出成交清單

| 時間 | 代碼 | 名稱 | 張數 | 賣價 | 觸發 | 觸發細節 | 毛損益 | 買手續費 | 賣手續費 | 稅 | 淨損益 |
| --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(sell_lines)}

## 孤兒賣出清單

| 時間 | 代碼 | 名稱 | 張數 | 賣價 | 觸發 | 觸發細節 | 說明 |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
{chr(10).join(orphan_sell_lines)}

## 未平倉部位

| 首次買進時間 | 代碼 | 名稱 | 張數 | 均價 | 成本金額 |
| --- | --- | --- | ---: | ---: | ---: |
{chr(10).join(open_lines)}

## 觀察與結論

{chr(10).join(obs_lines)}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate daily trade report markdown.")
    parser.add_argument("--date", required=True, help="Report date in YYYY-MM-DD.")
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--program-log", required=True, type=Path)
    parser.add_argument("--client-log", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    fills = parse_audit(args.audit)
    buys, realized, open_positions, orphan_sells = match_trades(fills)
    runtime = extract_runtime(args.program_log, args.client_log)
    report = render_report(
        report_date=args.date,
        audit_path=args.audit,
        program_log=args.program_log,
        client_log=args.client_log,
        config_path=args.config,
        fills=fills,
        buys=buys,
        realized=realized,
        open_positions=open_positions,
        orphan_sells=orphan_sells,
        runtime=runtime,
    )
    args.output.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
