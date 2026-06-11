#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
BUILD_WIN_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$BUILD_WIN_DIR/.." && pwd)"

RAW_DATE="${ANALYZE_DATE:-}"
if [ "${1:-}" = "-d" ] || [ "${1:-}" = "--date" ]; then
  RAW_DATE="${2:-}"
elif [ -n "${1:-}" ] && [[ "${1:-}" != -* ]]; then
  RAW_DATE="${1:-}"
fi

if [ -z "$RAW_DATE" ]; then
  RAW_DATE="$(TZ=Asia/Taipei date +%Y%m%d)"
fi

STAMP="${RAW_DATE//-/}"
if ! [[ "$STAMP" =~ ^[0-9]{8}$ ]]; then
  echo "用法：$0 [YYYYMMDD|YYYY-MM-DD]" >&2
  echo "也可用環境變數 ANALYZE_DATE 指定日期。" >&2
  exit 2
fi

LOG_DIR=""
for candidate in \
  "$BUILD_WIN_DIR/dist/log" \
  "$BUILD_WIN_DIR/src/log" \
  "$REPO_ROOT/log"
do
  if [ -d "$candidate" ]; then
    LOG_DIR="$candidate"
    break
  fi
done

if [ -z "$LOG_DIR" ]; then
  echo "找不到 log 目錄。" >&2
  exit 1
fi

DECISION_EVENTS="$LOG_DIR/decision_events.$STAMP.jsonl"
LATENCY_SUMMARY="$LOG_DIR/latency_summary.$STAMP.jsonl"
PROGRAM_LOG="$LOG_DIR/program.log.$STAMP"

python3 - "$STAMP" "$LOG_DIR" "$DECISION_EVENTS" "$LATENCY_SUMMARY" "$PROGRAM_LOG" <<'PY'
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean

stamp = sys.argv[1]
log_dir = Path(sys.argv[2])
decision_events_path = Path(sys.argv[3])
latency_summary_path = Path(sys.argv[4])
program_log_path = Path(sys.argv[5])

warn_market_ms = float(os.environ.get("WARN_MARKET_MS", "1000"))
warn_recv_ms = float(os.environ.get("WARN_RECV_MS", "200"))
warn_order_ms = float(os.environ.get("WARN_ORDER_MS", "200"))

metric_specs = [
    ("market_to_recv_ms", warn_market_ms, "市場事件 -> 本機接收"),
    ("recv_to_decision_ms", warn_recv_ms, "本機接收 -> 策略決策"),
    ("decision_to_order_ms", warn_order_ms, "決策 -> 委託送出"),
]


def iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield lineno, payload


def to_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_time(value):
    if value in (None, ""):
        return "-"
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def extract_metric_row(row: dict):
    details = row.get("details") or {}
    if not isinstance(details, dict):
        details = {}
    values = {}
    for metric, _threshold, _label in metric_specs:
        value = details.get(metric)
        if value is None:
            value = row.get(metric)
        values[metric] = to_float(value)
    return values


def load_decision_events(path: Path):
    samples = {metric: [] for metric, _, _ in metric_specs}
    top_rows = []
    event_count = 0
    for lineno, row in iter_jsonl(path) or []:
        event_count += 1
        details = row.get("details") or {}
        if not isinstance(details, dict):
            details = {}
        values = extract_metric_row(row)
        code = str(row.get("code") or "").strip() or "-"
        name = str(row.get("name") or "").strip() or "-"
        category = str(row.get("category") or "").strip() or "-"
        result = str(row.get("result") or "").strip() or "-"
        reason = str(row.get("reason") or "").strip() or "-"
        market_event_time = normalize_time(row.get("market_event_time") or details.get("market_event_time"))
        recv_time = normalize_time(row.get("recv_time") or details.get("recv_time"))
        decision_time = normalize_time(row.get("decision_time") or details.get("decision_time"))

        max_value = None
        max_metric = None
        for metric, _threshold, _label in metric_specs:
            value = values.get(metric)
            if value is None:
                continue
            samples[metric].append((value, code, name, category, result, reason, market_event_time, recv_time, decision_time, lineno))
            if max_value is None or value > max_value:
                max_value = value
                max_metric = metric
        if max_value is not None:
            top_rows.append((max_value, max_metric, code, name, category, result, reason, market_event_time, recv_time, decision_time))
    return event_count, samples, top_rows


def load_latency_summary(path: Path):
    records = list(iter_jsonl(path) or [])
    if not records:
        return None
    lineno, latest = records[-1]
    metrics = latest.get("metrics") or {}
    top_codes = latest.get("top_codes") or []
    return {
        "lineno": lineno,
        "record": latest,
        "metrics": metrics,
        "top_codes": top_codes,
    }


def print_program_log_context(path: Path):
    if not path.exists():
        return
    interesting = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if "[FubonFeed][計時]" in line or "[Latency]" in line or "延遲" in line:
                interesting.append(line.rstrip())
    if not interesting:
        return
    print("\nprogram.log 相關片段：")
    for line in interesting[:20]:
        print(f"  {line}")


def fmt_value(value):
    if value is None:
        return "-"
    return f"{value:.3f} ms"


def print_sample_block(title: str, samples: list[tuple], threshold: float, limit: int = 5):
    if not samples:
        print(f"- {title}: 無樣本")
        return
    samples = sorted(samples, key=lambda item: item[0], reverse=True)
    over = [item for item in samples if item[0] >= threshold]
    avg = mean(item[0] for item in samples)
    worst = samples[0]
    print(
        f"- {title}: samples={len(samples)} avg={avg:.3f} ms "
        f"max={worst[0]:.3f} ms over>={threshold:g}ms={len(over)}"
    )
    for value, code, name, category, result, reason, market_event_time, recv_time, decision_time, lineno in samples[:limit]:
        flag = "超標" if value >= threshold else "正常"
        print(
            f"  - {flag} {value:.3f} ms | {code} {name} | {category}/{result} | "
            f"market={market_event_time} recv={recv_time} decision={decision_time} | {reason}"
        )


print(f"日期：{stamp}")
print(f"log 目錄：{log_dir}")
print(f"decision_events：{decision_events_path if decision_events_path.exists() else '(不存在)'}")
print(f"latency_summary：{latency_summary_path if latency_summary_path.exists() else '(不存在)'}")
print(f"program.log：{program_log_path if program_log_path.exists() else '(不存在)'}")

found_source = False

if decision_events_path.exists():
    event_count, samples, top_rows = load_decision_events(decision_events_path)
    found_source = True
    print(f"\ndecision_events 筆數：{event_count}")
    any_over = False
    for metric, threshold, label in metric_specs:
        metric_samples = samples.get(metric, [])
        if any(value >= threshold for value, *_rest in metric_samples):
            any_over = True
        print_sample_block(label, metric_samples, threshold)
    print(
        "\n判定："
        + ("今天有延遲跡象。" if any_over else "今天未看到明顯延遲樣本。")
    )
    if top_rows:
        print("\n最慢樣本（依三個延遲指標取最大者排序）：")
        for value, metric, code, name, category, result, reason, market_event_time, recv_time, decision_time in sorted(top_rows, key=lambda item: item[0], reverse=True)[:5]:
            print(
                f"  - {metric}={value:.3f} ms | {code} {name} | {category}/{result} | "
                f"market={market_event_time} recv={recv_time} decision={decision_time} | {reason}"
            )
elif latency_summary_path.exists():
    summary = load_latency_summary(latency_summary_path)
    if summary is not None:
        found_source = True
        record = summary["record"]
        metrics = summary["metrics"]
        top_codes = summary["top_codes"]
        print(f"\nlatency_summary 最新紀錄行號：{summary['lineno']}")
        print(f"reason：{record.get('reason', '-')}")
        print(f"started_at：{record.get('started_at', '-')}")
        print(f"event_count：{record.get('event_count', 0)}")
        any_over = False
        for metric, threshold, label in metric_specs:
            bucket = metrics.get(metric) or {}
            count = int(bucket.get("count") or 0)
            avg = bucket.get("avg")
            min_value = bucket.get("min")
            max_value = bucket.get("max")
            over = bool(max_value is not None and float(max_value) >= threshold)
            any_over = any_over or over
            print(
                f"- {label}: count={count} avg={avg if avg is not None else '-'} ms "
                f"min={min_value if min_value is not None else '-'} ms "
                f"max={max_value if max_value is not None else '-'} ms "
                f"over>={threshold:g}ms={'是' if over else '否'}"
            )
        print(
            "\n判定："
            + ("今天有延遲跡象。" if any_over else "今天未看到明顯延遲樣本。")
        )
        if top_codes:
            print("\ntop_codes：")
            for item in top_codes[:5]:
                code = item.get("code", "-")
                name = item.get("name", "-")
                market_bucket = item.get("market_to_recv_ms") or {}
                order_bucket = item.get("decision_to_order_ms") or {}
                print(
                    f"  - {code} {name} | market_max={market_bucket.get('max', '-')}"
                    f" decision_max={order_bucket.get('max', '-')} | {item.get('last_reason', '-')}"
                )
else:
    print("\n今天沒有可分析的結構化 latency 紀錄（decision_events / latency_summary 都不存在）。")
    print("只能補看 program.log 是否有 [FubonFeed][計時] 或 [Latency] 片段。")
    print("判定：無法從現有 log 直接證明是否有延遲。")

print_program_log_context(program_log_path)

if not found_source and program_log_path.exists():
    print("\nprogram.log 內容存在，但沒有結構化延遲紀錄可用。")
PY
