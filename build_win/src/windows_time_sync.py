"""
Windows time synchronization helpers.

The trading latency metrics compare broker timestamps with local receive time,
so strategy startup should not proceed with a large host clock offset.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple


DEFAULT_NTP_SERVER = "time.windows.com"
DEFAULT_PEERS = ("time.windows.com", "time.google.com", "pool.ntp.org")
DEFAULT_THRESHOLD_SECONDS = 0.05
DEFAULT_CACHE_TTL_SECONDS = 300.0


_LAST_RESULT: Optional["TimeSyncResult"] = None
_LAST_RESULT_MONOTONIC: Optional[float] = None


@dataclass
class TimeSyncResult:
    checked: bool = False
    success: bool = True
    repaired: bool = False
    pre_offset_seconds: Optional[float] = None
    post_offset_seconds: Optional[float] = None
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def max_observed_offset_seconds(self) -> Optional[float]:
        values = [
            value
            for value in (self.pre_offset_seconds, self.post_offset_seconds)
            if value is not None
        ]
        if not values:
            return None
        return max(values, key=lambda value: abs(value))

    def clone(self) -> "TimeSyncResult":
        return TimeSyncResult(
            checked=self.checked,
            success=self.success,
            repaired=self.repaired,
            pre_offset_seconds=self.pre_offset_seconds,
            post_offset_seconds=self.post_offset_seconds,
            notes=list(self.notes),
            warnings=list(self.warnings),
        )


def is_windows() -> bool:
    return os.name == "nt"


def run_command(args: Sequence[str], timeout: int = 30) -> Tuple[int, str]:
    kwargs = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
    }
    if is_windows():
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(list(args), **kwargs)
    output = (proc.stdout or "").strip()
    error = (proc.stderr or "").strip()
    merged = "\n".join(part for part in (output, error) if part).strip()
    return proc.returncode, merged


def parse_stripchart_offsets(output: str) -> List[float]:
    return [float(match) for match in re.findall(r"([-+]\d+\.\d+)s", output or "")]


def median(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("median requires at least one value")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def measure_offset_seconds(server: str = DEFAULT_NTP_SERVER, samples: int = 5) -> Tuple[float, str]:
    code, output = run_command(
        ["w32tm", "/stripchart", f"/computer:{server}", f"/samples:{samples}", "/dataonly"],
        timeout=max(20, samples * 5),
    )
    if code != 0:
        raise RuntimeError(output or f"w32tm stripchart failed with exit code {code}")
    offsets = parse_stripchart_offsets(output)
    if not offsets:
        raise RuntimeError("無法解析 w32tm stripchart offset")
    return median(offsets), output


def ensure_w32time_running() -> None:
    command = (
        "$svc = Get-Service -Name 'W32Time' -ErrorAction Stop; "
        "if ($svc.Status -ne 'Running') { "
        "Start-Service -Name 'W32Time'; "
        "$svc.WaitForStatus('Running', '00:00:10') "
        "} "
        "(Get-Service -Name 'W32Time').Status"
    )
    code, output = run_command(["powershell.exe", "-NoProfile", "-Command", command], timeout=25)
    if code != 0 or "Running" not in output:
        raise RuntimeError(output or "W32Time 啟動失敗")


def configure_time_peers(peers: Sequence[str] = DEFAULT_PEERS) -> None:
    peer_list = " ".join(f"{peer},0x8" for peer in peers)
    code, output = run_command(
        [
            "w32tm",
            "/config",
            f"/manualpeerlist:{peer_list}",
            "/syncfromflags:manual",
            "/reliable:no",
            "/update",
        ],
        timeout=30,
    )
    if code != 0:
        raise RuntimeError(output or f"w32tm config failed with exit code {code}")


def restart_w32time() -> None:
    command = (
        "$svc = Get-Service -Name 'W32Time' -ErrorAction Stop; "
        "if ($svc.Status -eq 'Running') { "
        "Stop-Service -Name 'W32Time' -Force; "
        "$svc.WaitForStatus('Stopped', '00:00:15') "
        "} "
        "Start-Service -Name 'W32Time'; "
        "$svc.WaitForStatus('Running', '00:00:15')"
    )
    code, output = run_command(["powershell.exe", "-NoProfile", "-Command", command], timeout=40)
    if code != 0:
        raise RuntimeError(output or "W32Time 重啟失敗")


def resync_windows_time(attempts: int = 3) -> str:
    last_output = ""
    for attempt in range(1, max(1, attempts) + 1):
        code, output = run_command(["w32tm", "/resync", "/rediscover"], timeout=35)
        last_output = output
        if code == 0:
            return output
        if attempt >= attempts:
            raise RuntimeError(output or f"w32tm resync failed with exit code {code}")
    return last_output


def step_correct_time(offset_seconds: float) -> str:
    correction_seconds = -offset_seconds
    command = (
        "$ErrorActionPreference = 'Stop'; "
        "$now = Get-Date; "
        f"$target = $now.AddSeconds({correction_seconds:.9f}); "
        "Set-Date -Date $target | Out-Null; "
        "$target.ToString('o')"
    )
    code, output = run_command(["powershell.exe", "-NoProfile", "-Command", command], timeout=30)
    if code != 0:
        raise RuntimeError(output or "Set-Date 校正失敗")
    return output


def verify_and_repair(
    *,
    threshold_seconds: float = DEFAULT_THRESHOLD_SECONDS,
    server: str = DEFAULT_NTP_SERVER,
    samples: int = 5,
    force_step_correction: bool = True,
) -> TimeSyncResult:
    result = TimeSyncResult()
    if not is_windows():
        result.notes.append("非 Windows 環境，略過 Windows 校時檢查")
        return result

    result.checked = True
    try:
        pre_offset, _raw = measure_offset_seconds(server=server, samples=samples)
        result.pre_offset_seconds = pre_offset
        result.notes.append(f"Windows 時鐘偏移檢查：{pre_offset * 1000:.1f}ms")

        if abs(pre_offset) <= threshold_seconds:
            result.post_offset_seconds = pre_offset
            result.notes.append(f"偏移未超過 {threshold_seconds * 1000:.0f}ms，無需校正")
            return result

        result.notes.append(f"偏移超過 {threshold_seconds * 1000:.0f}ms，開始自動校正")
        ensure_w32time_running()
        configure_time_peers()
        restart_w32time()
        resync_windows_time()

        mid_offset, _raw = measure_offset_seconds(server=server, samples=samples)
        if force_step_correction and abs(mid_offset) > threshold_seconds:
            result.notes.append(f"resync 後仍偏移 {mid_offset * 1000:.1f}ms，執行直接校正")
            step_correct_time(mid_offset)
            result.repaired = True
            try:
                resync_windows_time()
            except Exception as exc:
                result.warnings.append(f"直接校正後 resync 未完成：{exc}")
        else:
            result.repaired = True

        post_offset, _raw = measure_offset_seconds(server=server, samples=samples)
        result.post_offset_seconds = post_offset
        result.notes.append(f"Windows 校時後偏移：{post_offset * 1000:.1f}ms")
        if abs(post_offset) > threshold_seconds:
            result.success = False
            result.warnings.append(
                f"Windows 校時後仍超過 {threshold_seconds * 1000:.0f}ms：{post_offset * 1000:.1f}ms"
            )
        return result
    except Exception as exc:
        result.success = False
        result.warnings.append(f"Windows 校時檢查/修復失敗：{exc}")
        return result


def _remember_result(result: TimeSyncResult) -> TimeSyncResult:
    global _LAST_RESULT, _LAST_RESULT_MONOTONIC
    _LAST_RESULT = result.clone()
    _LAST_RESULT_MONOTONIC = time.monotonic()
    return result


def get_cached_result(max_age_seconds: float = DEFAULT_CACHE_TTL_SECONDS) -> Optional[TimeSyncResult]:
    if _LAST_RESULT is None or _LAST_RESULT_MONOTONIC is None:
        return None
    age_seconds = time.monotonic() - _LAST_RESULT_MONOTONIC
    if age_seconds > max(0.0, float(max_age_seconds)):
        return None
    cached = _LAST_RESULT.clone()
    cached.notes.append(f"沿用 {age_seconds:.1f} 秒前的 Windows 校時結果")
    return cached


def verify_and_repair_cached(
    *,
    threshold_seconds: float = DEFAULT_THRESHOLD_SECONDS,
    server: str = DEFAULT_NTP_SERVER,
    samples: int = 5,
    force_step_correction: bool = True,
    cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
) -> TimeSyncResult:
    cached = get_cached_result(max_age_seconds=cache_ttl_seconds)
    if cached is not None:
        return cached
    result = verify_and_repair(
        threshold_seconds=threshold_seconds,
        server=server,
        samples=samples,
        force_step_correction=force_step_correction,
    )
    return _remember_result(result)
