---
name: fix-windows-time-sync
description: Repair Windows clock skew for this project when local time is ahead or behind NTP and latency metrics such as market_to_recv_ms are inflated by the host clock instead of real broker delay.
---

# Fix Windows Time Sync

## Overview

Use this skill after clock skew has been confirmed and you need to repair the local Windows clock before trusting latency metrics.

This skill focuses on fixing the host clock, not diagnosing whether skew exists. If skew has not been measured yet, run `diagnose-windows-time-skew` first.

## When To Use

- `w32tm /stripchart` shows stable seconds-level offset.
- `w32tm /query /status` shows `Source: Local CMOS Clock`.
- App logs keep reporting `[時鐘偏移]` around the same magnitude as the NTP offset.
- `market_to_recv_ms` looks stable at about the same value as the host clock skew.

## Repair Workflow

1. Measure the current offset and record it.
2. Check the Windows Time service status and source.
3. Run the sync commands from Administrator CMD or Administrator PowerShell.
4. Re-measure the offset after sync.
5. Re-run the latency path that previously looked delayed.
6. Report pre-sync and post-sync values separately.

## Pre-Check Commands

Run these first:

```bash
cmd.exe /c w32tm /stripchart /computer:time.windows.com /samples:5 /dataonly
cmd.exe /c w32tm /query /status
powershell.exe -NoProfile -Command "Get-Service W32Time | Format-List Name,Status,StartType"
```

Interpretation:

- Offset near `0.000s` means no repair is needed.
- Offset around `-01.6s` means local Windows time is about 1.6 seconds ahead of NTP.
- `Source: Local CMOS Clock` means Windows is not using a healthy time source for latency-sensitive analysis.

## Repair Commands

Run these from **Administrator** CMD or **Administrator** PowerShell:

```bat
w32tm /resync /force
w32tm /stripchart /computer:time.windows.com /samples:5 /dataonly
```

Project helper script:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_win\scripts\fix_windows_time_sync.ps1
```

If resync fails because the service or source is unhealthy, use the fallback sequence:

```bat
net start w32time
w32tm /config /manualpeerlist:time.windows.com /syncfromflags:manual /update
w32tm /resync /force
w32tm /query /status
w32tm /stripchart /computer:time.windows.com /samples:5 /dataonly
```

## Permission Failure

If `w32tm /resync /force` returns `0x80070005`, the current shell is not elevated enough to repair Windows time.

In that case:

1. Open Administrator CMD or Administrator PowerShell on Windows.
2. Run the repair commands there.
3. Return to this project and re-run the verification commands.

Do not interpret seconds-level `market_to_recv_ms` as real broker delay until the repair step succeeds.

## Verification

After sync, verify that the offset has dropped to milliseconds level:

```bash
cmd.exe /c w32tm /stripchart /computer:time.windows.com /samples:5 /dataonly
cmd.exe /c w32tm /query /status
```

Healthy result shape:

- Offset near `+00.000s` or `-00.000s`
- `Source` no longer stuck on `Local CMOS Clock`

Then re-check application latency:

```bash
python3 isolated_fubon_latency_probe/latency_probe.py --non-interactive --duration-sec 30
ls -t isolated_fubon_latency_probe/output/latency_summary_*.json | head -n 3
```

If app logs exist, confirm that `[時鐘偏移]` warnings disappear or drop sharply:

```bash
rg -n '時鐘偏移|第 1 筆有效|訂閱完成' /mnt/c/Jarvis/15_bonus/01_littile-bao/build_win/dist/log/program.log.YYYYMMDD | head -n 80
```

## Expected Outcome

After a successful repair:

- `w32tm /stripchart` should no longer show seconds-level skew.
- `market_to_recv_ms` should fall from clock-skew magnitude to actual transport latency magnitude.
- Healthy live latency is typically near `0ms` median with p95 in tens to low hundreds of milliseconds.

## Report Template

Include:

- Pre-sync offset
- Pre-sync `Source`
- Repair command result
- Post-sync offset
- Post-sync `Source`
- Before and after latency metric
- Conclusion: repaired, blocked by permission, or still unresolved
