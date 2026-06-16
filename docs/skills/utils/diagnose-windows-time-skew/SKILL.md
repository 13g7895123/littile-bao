---
name: diagnose-windows-time-skew
description: Diagnose and verify Windows clock offset in this project. Use when timestamps, GUI logs, CLI probes, websocket events, latency_summary, decision_events, or broker/API data appear delayed or early and local Windows time synchronization may affect recv_time minus api_time calculations.
---

# Diagnose Windows Time Skew

## Overview

Use this skill to prove or rule out local Windows clock offset before investigating application latency. The key question is whether local `recv_time` is trustworthy when compared with API, websocket, or broker event timestamps.

## Workflow

1. Measure Windows time offset against an NTP server.
2. Check Windows Time service source and status.
3. If offset is seconds-level, sync Windows time with administrator privileges.
4. Re-measure NTP offset after sync.
5. Re-run the same latency probe or log check and report before/after values separately.

## Measure Clock Offset

Run from WSL or Windows shell:

```bash
cmd.exe /c w32tm /stripchart /computer:time.windows.com /samples:5 /dataonly
cmd.exe /c w32tm /query /status
powershell.exe -NoProfile -Command "Get-Service W32Time | Format-List Name,Status,StartType"
```

Interpretation:

- Offset near `0.000s` means Windows clock is aligned enough for latency diagnosis.
- Offset like `-03.358s` means local Windows time is about 3.358 seconds ahead of the NTP server. This makes `recv_time - api_time` look about 3.358 seconds too large.
- Offset like `+03.358s` means local Windows time is behind the NTP server. This can make latency look too small or negative.
- `Source: Local CMOS Clock` is suspicious. Prefer an NTP source such as `time.windows.com`.

## Sync Windows Time

If `w32tm /resync /force` returns `0x80070005`, run the sync commands from Administrator CMD or Administrator PowerShell.

Preferred commands:

```bat
w32tm /resync /force
w32tm /stripchart /computer:time.windows.com /samples:5 /dataonly
```

Fallback commands:

```bat
net start w32time
w32tm /config /manualpeerlist:time.windows.com /syncfromflags:manual /update
w32tm /resync /force
w32tm /stripchart /computer:time.windows.com /samples:5 /dataonly
```

Expected post-sync result:

```text
+00.0005s
```

Small millisecond-level offsets are acceptable. Seconds-level offsets are not acceptable for market-data latency analysis.

## Check App Logs For Clock Symptoms

When app logs exist, use them only to confirm the effect of time skew:

```bash
rg -n '時鐘偏移|websocket #|訂閱完成|第 1 筆有效' /mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/dist/log/program.log.YYYYMMDD | head -n 80
```

Useful signal:

- Repeated `[時鐘偏移] 中位數 3000ms` while `w32tm stripchart` also shows about 3 seconds of offset indicates local clock skew is the primary cause.
- First valid tick/book arriving tens of milliseconds after subscribe means the app did not wait seconds before seeing data.

If `latency_summary.YYYYMMDD.jsonl` exists, compare first and last snapshots:

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path('/mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/dist/log/latency_summary.YYYYMMDD.jsonl')
rows = [json.loads(x) for x in p.open(encoding='utf-8') if x.strip()]
for row in (rows[0], rows[-1]):
    print(row['logged_at'], row['event_count'], row['metrics'].get('market_to_recv_ms'), row['metrics'].get('recv_to_decision_ms'))
PY
```

Do not treat `market_to_recv_ms` as broker delay until Windows clock offset is known.

## Verify After Sync

After syncing time, rerun the same measurement path that showed the problem. For the standalone probe:

```bash
python3 isolated_fubon_latency_probe/latency_probe.py --non-interactive --duration-sec 30
```

Report the newest summary path and the post-sync `live_latency_ms` values:

```bash
ls -t isolated_fubon_latency_probe/output/latency_summary_*.json | head -n 3
```

Expected healthy shape after clock sync:

- `live all` median near `0ms`
- `live all` p95 around tens to low hundreds of milliseconds
- No stable seconds-level `market_to_recv_ms`

If the process exits with SDK disconnect errors after writing the summary, mention the exit code but still use the summary if it is complete.

## Final Report Shape

Include:

- Pre-sync `w32tm stripchart` offset and `w32tm /query /status` source.
- Sync command result or permission error.
- Post-sync `w32tm stripchart` offset and source.
- Before/after latency metric that depended on local time.
- Conclusion: local clock skew confirmed, ruled out, or still unresolved.
