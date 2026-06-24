"""
bootstrap.py - 啟動前檢查與 broker 初始化。
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import List, Tuple

from app_logging import configure_runtime_logging, read_file_logging_flag
from windows_time_sync import verify_and_repair_cached


def runtime_log_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def init_runtime_logging() -> tuple[bool, str | None]:
    config_path = os.path.join(runtime_log_dir(), "config.json")
    enabled = read_file_logging_flag(config_path, default=True)
    log_path = configure_runtime_logging(enabled, base_dir=runtime_log_dir())
    return enabled, log_path


def is_windows() -> bool:
    return os.name == "nt"


def show_startup_message(title: str, message: str, flags: int = 0x10) -> None:
    if not is_windows():
        print(f"[{title}] {message}")
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, title, flags)
    except Exception:
        print(f"[{title}] {message}")


def is_user_admin() -> bool:
    if not is_windows():
        return True
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    if not is_windows():
        return True
    try:
        import ctypes

        if getattr(sys, "frozen", False):
            executable = sys.executable
            params = sys.argv[1:]
        else:
            executable = sys.executable
            params = [os.path.abspath(sys.argv[0]), *sys.argv[1:]]

        rc = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            subprocess.list2cmdline(params),
            os.getcwd(),
            1,
        )
        return rc > 32
    except Exception:
        return False


def ensure_admin_or_exit() -> None:
    if not is_windows() or is_user_admin():
        return
    if relaunch_as_admin():
        sys.exit(0)
    show_startup_message(
        "StockTrader",
        "此程式需要以 Administrator 啟動，才能檢查 Windows 時間服務並執行校時。",
    )
    sys.exit(1)


def run_windows_command(args: List[str], timeout: int = 20) -> Tuple[int, str]:
    kwargs = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
    }
    if is_windows():
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(args, **kwargs)
    output = (proc.stdout or "").strip()
    error = (proc.stderr or "").strip()
    merged = "\n".join(part for part in (output, error) if part).strip()
    return proc.returncode, merged


def run_windows_time_startup_checks() -> Tuple[List[str], List[str]]:
    startup_notes: List[str] = []
    startup_warnings: List[str] = []
    if not is_windows():
        return startup_notes, startup_warnings

    result = verify_and_repair_cached(threshold_seconds=0.05, force_step_correction=True)
    startup_notes.extend(result.notes)
    startup_warnings.extend(result.warnings)
    if not result.success and not startup_warnings:
        startup_warnings.append("Windows 校時未完成")
    return startup_notes, startup_warnings


def init_broker(settings):
    """依據設定建立 broker 適配器並嘗試登入。"""
    from broker import BrokerError, FubonAdapter, MockAdapter

    if settings.mock_mode or not settings.is_complete():
        if not settings.is_complete():
            print("[StockTrader] 未備齊富邦券商設定 → 啟用 MockAdapter")
        else:
            print("[StockTrader] MOCK_MODE=true → 啟用 MockAdapter")
        adapter = MockAdapter()
        adapter.login()
        return adapter

    try:
        adapter = FubonAdapter.from_config(settings)
        result = adapter.login()
        if result.success and result.selected:
            print(
                f"[StockTrader] Fubon 登入成功：{result.selected.display}"
                f"（dry_run={settings.dry_run}）"
            )
        return adapter
    except BrokerError as exc:
        print(f"[StockTrader] Fubon 登入失敗：{exc} → 改用 MockAdapter")
        adapter = MockAdapter()
        adapter.login()
        return adapter
