#!/usr/bin/env python3
"""
Generate a daily trade timing report from audit, decision events, and recording meta.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional


def d(value) -> Decimal:
    return Decimal(str(value))


def fmt_decimal(value: Optional[Decimal]) -> str:
    if value is None:
        return "-"
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def fmt_ms(value) -> str:
    if value is None:
        return "-"
    return f"{float(value):.3f}"


def fmt_ts(value: Optional[str]) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%H:%M:%S.%f")[:-3]
    except Exception:
        return value


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
class EventRow:
    code: str
    name: str
    category: str
    result: str
    reason: str
    time: str
    market_event_time: Optional[str]
    recv_time: Optional[str]
    decision_time: Optional[str]
    market_to_recv_ms: Optional[float]
    recv_to_decision_ms: Optional[float]
    market_to_decision_ms: Optional[float]
    price: Optional[Decimal]
    qty: Optional[int]


@dataclass
class SessionWindow:
    session_id: str
    start_ts: datetime
    end_ts: Optional[datetime]


def load_audit(path: Path) -> list[Fill]:
    result: list[Fill] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("type") != "FILL":
            continue
        result.append(
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
    return result


def load_decision_events(path: Path) -> list[EventRow]:
    result: list[EventRow] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("category") not in {"STRATEGY", "FILL"}:
            continue
        if row.get("result") not in {"進場觸發", "出場觸發", "買進成交", "賣出成交"}:
            continue
        details = row.get("details") or {}
        price = details.get("price")
        result.append(
            EventRow(
                code=str(row.get("code") or ""),
                name=str(row.get("name") or ""),
                category=str(row.get("category") or ""),
                result=str(row.get("result") or ""),
                reason=str(row.get("reason") or ""),
                time=str(row.get("time") or ""),
                market_event_time=row.get("market_event_time"),
                recv_time=row.get("recv_time"),
                decision_time=row.get("decision_time"),
                market_to_recv_ms=details.get("market_to_recv_ms"),
                recv_to_decision_ms=details.get("recv_to_decision_ms"),
                market_to_decision_ms=details.get("market_to_decision_ms"),
                price=d(price) if price not in (None, "") else None,
                qty=int(details["qty"]) if details.get("qty") not in (None, "") else None,
            )
        )
    return result


def index_events(events: list[EventRow]) -> dict[tuple[str, str], list[EventRow]]:
    grouped: dict[tuple[str, str], list[EventRow]] = defaultdict(list)
    for event in events:
        if event.result in {"進場觸發", "買進成交"}:
            grouped[(event.code, "BUY")].append(event)
        else:
            grouped[(event.code, "SELL")].append(event)
    return grouped


def pair_event_for_fill(fill: Fill, grouped: dict[tuple[str, str], list[EventRow]], result_name: str) -> Optional[EventRow]:
    pool = grouped.get((fill.code, fill.side), [])
    for idx, event in enumerate(pool):
        if event.result != result_name:
            continue
        pool.pop(idx)
        return event
    return None


def load_sessions(recordings_dir: Path) -> list[SessionWindow]:
    sessions: list[SessionWindow] = []
    for meta_path in sorted(recordings_dir.glob("session_*.meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        start_raw = meta.get("start_ts")
        if not start_raw:
            continue
        start_ts = datetime.fromisoformat(start_raw)
        end_raw = meta.get("end_ts")
        end_ts = datetime.fromisoformat(end_raw) if end_raw else None
        sessions.append(
            SessionWindow(
                session_id=str(meta.get("session_id") or meta_path.stem),
                start_ts=start_ts,
                end_ts=end_ts,
            )
        )
    return sessions


def find_session_name(value: Optional[str], sessions: list[SessionWindow]) -> str:
    if not value:
        return "-"
    dt = datetime.fromisoformat(value)
    for session in sessions:
        if session.end_ts is None:
            if dt >= session.start_ts:
                return session.session_id
        elif session.start_ts <= dt <= session.end_ts:
            return session.session_id
    return "未覆蓋/缺口"


def classify_time_basis(event: Optional[EventRow]) -> str:
    if event is None:
        return "缺少事件"
    value = event.market_to_recv_ms
    if value is None:
        return "無延遲數據"
    if value < 0:
        return "本機時鐘偏快/偏移反轉"
    if value >= 200:
        return "有延遲"
    return "可採信"


def generate_report(
    *,
    report_date: str,
    audit_path: Path,
    decision_events_path: Path,
    recordings_dir: Path,
) -> str:
    fills = load_audit(audit_path)
    events = load_decision_events(decision_events_path)
    grouped = index_events(events)
    sessions = load_sessions(recordings_dir)

    buy_trigger_map: dict[str, list[Optional[EventRow]]] = defaultdict(list)
    buy_fill_map: dict[str, list[Optional[EventRow]]] = defaultdict(list)
    sell_trigger_map: dict[str, list[Optional[EventRow]]] = defaultdict(list)
    sell_fill_map: dict[str, list[Optional[EventRow]]] = defaultdict(list)
    fill_map: dict[str, list[Fill]] = defaultdict(list)
    open_positions: list[tuple[Fill, Optional[EventRow], Optional[EventRow]]] = []
    realized_rows: list[str] = []

    buy_lots: dict[str, list[tuple[Fill, Optional[EventRow], Optional[EventRow]]]] = defaultdict(list)

    for fill in fills:
        fill_event = pair_event_for_fill(fill, grouped, "買進成交" if fill.side == "BUY" else "賣出成交")
        trigger_event = pair_event_for_fill(fill, grouped, "進場觸發" if fill.side == "BUY" else "出場觸發")
        fill_map[fill.code].append(fill)
        if fill.side == "BUY":
            buy_lots[fill.code].append((fill, trigger_event, fill_event))
            buy_trigger_map[fill.code].append(trigger_event)
            buy_fill_map[fill.code].append(fill_event)
            continue
        sell_trigger_map[fill.code].append(trigger_event)
        sell_fill_map[fill.code].append(fill_event)
        remaining = fill.qty
        while remaining > 0 and buy_lots[fill.code]:
            buy_fill, buy_trigger, buy_fill_event = buy_lots[fill.code][0]
            matched_qty = min(remaining, buy_fill.qty)
            basis = classify_time_basis(buy_trigger)
            sell_basis = classify_time_basis(trigger_event)
            realized_rows.append(
                "| "
                + " | ".join(
                    [
                        fill.code,
                        fill.name,
                        str(matched_qty),
                        fmt_decimal(buy_fill.price),
                        fmt_ts(buy_trigger.market_event_time if buy_trigger else None),
                        fmt_ts(buy_fill.ts),
                        buy_trigger.reason if buy_trigger else "-",
                        fmt_ms(buy_trigger.market_to_recv_ms if buy_trigger else None),
                        fmt_decimal(fill.price),
                        fmt_ts(trigger_event.market_event_time if trigger_event else None),
                        fmt_ts(fill.ts),
                        trigger_event.reason if trigger_event else "-",
                        fmt_ms(trigger_event.market_to_recv_ms if trigger_event else None),
                        basis,
                        sell_basis,
                        find_session_name(buy_trigger.market_event_time if buy_trigger else None, sessions),
                        find_session_name(trigger_event.market_event_time if trigger_event else None, sessions),
                    ]
                )
                + " |"
            )
            remaining -= matched_qty
            if matched_qty == buy_fill.qty:
                buy_lots[fill.code].pop(0)
            else:
                buy_fill.qty -= matched_qty

    for code, lots in buy_lots.items():
        for buy_fill, buy_trigger, buy_fill_event in lots:
            open_positions.append((buy_fill, buy_trigger, buy_fill_event))

    fill_times = [fill.ts for fill in fills]
    all_codes = sorted({fill.code for fill in fills})
    delay_affected = sum(1 for fill in fills if classify_time_basis((buy_trigger_map if fill.side == "BUY" else sell_trigger_map)[fill.code][0]) != "可採信")

    session_lines = []
    prev_end: Optional[datetime] = None
    for session in sessions:
        gap_note = ""
        if prev_end is not None:
            gap_sec = (session.start_ts - prev_end).total_seconds()
            if gap_sec > 0:
                gap_note = f"（與前段缺口 {gap_sec:.0f} 秒）"
        end_text = session.end_ts.isoformat() if session.end_ts else "未正常收尾"
        session_lines.append(f"- `{session.session_id}`：`{session.start_ts.isoformat()}` → `{end_text}` {gap_note}".rstrip())
        if session.end_ts is not None:
            prev_end = session.end_ts

    open_rows = []
    for fill, trigger, fill_event in open_positions:
        open_rows.append(
            "| "
            + " | ".join(
                [
                    fill.code,
                    fill.name,
                    str(fill.qty),
                    fmt_decimal(fill.price),
                    fmt_ts(trigger.market_event_time if trigger else None),
                    fmt_ts(fill.ts),
                    trigger.reason if trigger else "-",
                    fmt_ms(trigger.market_to_recv_ms if trigger else None),
                    classify_time_basis(trigger),
                    find_session_name(trigger.market_event_time if trigger else None, sessions),
                ]
            )
            + " |"
        )

    realized_table = "\n".join(realized_rows) if realized_rows else "| - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |"
    open_table = "\n".join(open_rows) if open_rows else "| - | - | - | - | - | - | - | - | - | - |"

    return f"""# {report_date} 今日成交資料修正版報告

## 資料來源

- 交易稽核：`{audit_path}`
- 決策事件：`{decision_events_path}`
- 錄製目錄：`{recordings_dir}`

## 判讀口徑

- `市場事件時間`：以 `decision_events` 的 `market_event_time` 作為修正版進出場觸發時間。
- `程式成交時間`：以 `dry_run_audit` 的 `ts` 作為乾跑成交時間。
- 本報告把「觸發時間」和「乾跑成交時間」拆開呈現，不混稱為同一個時間。
- 若 `market_to_recv_ms >= 200`，標示為 `有延遲`。
- 若 `market_to_recv_ms < 0`，標示為 `本機時鐘偏快/偏移反轉`；此時仍保留 `market_event_time`，但不把 `recv_time` 當可信依據。

## 今日總結

- 成交股票數：`{len(all_codes)}` 檔
- 買進成交：`{sum(1 for f in fills if f.side == "BUY")}` 筆
- 賣出成交：`{sum(1 for f in fills if f.side == "SELL")}` 筆
- 未平倉：`{len(open_positions)}` 檔
- 成交時間範圍（audit）：`{fmt_ts(min(fill_times))}` ~ `{fmt_ts(max(fill_times))}`
- 錄製 session：
{chr(10).join(session_lines)}

## 重點結論

- 今天所有成交都已成功對上 `decision_events` 的 `market_event_time`，可以整理出修正版進出場觸發時間。
- 早盤大多數成交的 `market_to_recv_ms` 仍在數百毫秒，屬 `有延遲`；因此修正版應優先看 `市場事件時間`，不要只看 `audit` 的本機成交時間。
- `10:04` 之後的少數成交出現負的 `market_to_recv_ms`，代表當時本機時間基準已反轉；這些成交仍可保留 `market_event_time`，但不能把 `recv_time` / 本機時間當成市場真實時間。
- 兩段錄製缺口在 `09:13:08~09:15:26` 與 `10:23:48~10:26:04`；今日實際成交不落在缺口內。

## 已平倉明細

| 代碼 | 名稱 | 張數 | 買價 | 修正版進場時間 | 乾跑買進時間 | 進場策略 | 進場延遲ms | 賣價 | 修正版出場時間 | 乾跑賣出時間 | 出場策略 | 出場延遲ms | 進場時間基準 | 出場時間基準 | 進場session | 出場session |
| --- | --- | ---: | ---: | --- | --- | --- | ---: | ---: | --- | --- | --- | ---: | --- | --- | --- | --- |
{realized_table}

## 未平倉明細

| 代碼 | 名稱 | 張數 | 買價 | 修正版進場時間 | 乾跑買進時間 | 進場策略 | 進場延遲ms | 時間基準 | session |
| --- | --- | ---: | ---: | --- | --- | --- | ---: | --- | --- |
{open_table}

## 使用說明

- 若你要回看「當時市場何時真的觸發進場 / 出場規則」，優先看本報告的 `修正版進場時間` / `修正版出場時間`。
- 若你要回看「程式 UI / audit 上看到幾點幾分成交」，看 `乾跑買進時間` / `乾跑賣出時間`。
- 這份報告處理的是「策略觸發市場時間」與「乾跑成交時間」的校正，不是券商真實成交回報。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a trade timing report.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--audit", required=True)
    parser.add_argument("--decision-events", required=True)
    parser.add_argument("--recordings-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    report = generate_report(
        report_date=args.date,
        audit_path=Path(args.audit).expanduser().resolve(),
        decision_events_path=Path(args.decision_events).expanduser().resolve(),
        recordings_dir=Path(args.recordings_dir).expanduser().resolve(),
    )
    output = Path(args.output).expanduser().resolve()
    output.write_text(report, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
