"""
main.py — 程式進入點
執行：python main.py
打包：pyinstaller build.spec
"""
import sys
import os
import subprocess
import traceback
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app_logging import configure_runtime_logging, get_runtime_log_path, read_file_logging_flag
from windows_time_sync import verify_and_repair_cached


def _log_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _init_runtime_logging():
    config_path = os.path.join(_log_dir(), "config.json")
    enabled = read_file_logging_flag(config_path, default=True)
    log_path = configure_runtime_logging(enabled, base_dir=_log_dir())
    return enabled, log_path


def _is_windows() -> bool:
    return os.name == "nt"


def _show_startup_message(title: str, message: str, flags: int = 0x10) -> None:
    if not _is_windows():
        print(f"[{title}] {message}")
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, title, flags)
    except Exception:
        print(f"[{title}] {message}")


def _is_user_admin() -> bool:
    if not _is_windows():
        return True
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_as_admin() -> bool:
    if not _is_windows():
        return True
    try:
        import ctypes

        if getattr(sys, "frozen", False):
            executable = sys.executable
            params = sys.argv[1:]
        else:
            executable = sys.executable
            params = [os.path.abspath(__file__), *sys.argv[1:]]

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


def _ensure_admin_or_exit() -> None:
    if not _is_windows() or _is_user_admin():
        return
    if _relaunch_as_admin():
        sys.exit(0)
    _show_startup_message(
        "StockTrader",
        "此程式需要以 Administrator 啟動，才能檢查 Windows 時間服務並執行校時。",
    )
    sys.exit(1)


def _run_windows_command(args: List[str], timeout: int = 20) -> Tuple[int, str]:
    kwargs = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
    }
    if _is_windows():
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(args, **kwargs)
    output = (proc.stdout or "").strip()
    error = (proc.stderr or "").strip()
    merged = "\n".join(part for part in (output, error) if part).strip()
    return proc.returncode, merged


def _ensure_w32time_running(startup_notes: List[str]) -> bool:
    ps_check = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        "(Get-Service -Name 'W32Time' -ErrorAction Stop).Status",
    ]
    code, output = _run_windows_command(ps_check)
    if code != 0:
        startup_notes.append(f"W32Time 狀態查詢失敗：{output or 'unknown error'}")
        return False
    if "Running" in output:
        startup_notes.append("W32Time 狀態正常：Running")
        return True

    startup_notes.append(f"W32Time 目前狀態：{output or 'Unknown'}，嘗試啟動")
    ps_start = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        (
            "$svc = Get-Service -Name 'W32Time' -ErrorAction Stop; "
            "if ($svc.Status -ne 'Running') { "
            "Start-Service -Name 'W32Time'; "
            "$svc.WaitForStatus('Running', '00:00:10') "
            "} "
            "(Get-Service -Name 'W32Time').Status"
        ),
    ]
    code, output = _run_windows_command(ps_start, timeout=25)
    if code == 0 and "Running" in output:
        startup_notes.append("W32Time 啟動成功")
        return True
    startup_notes.append(f"W32Time 啟動失敗：{output or 'unknown error'}")
    return False


def _resync_windows_clock(startup_notes: List[str]) -> bool:
    code, output = _run_windows_command(["w32tm", "/resync", "/force"], timeout=30)
    if code == 0:
        startup_notes.append(f"Windows 校時完成：{output or 'success'}")
        return True
    startup_notes.append(f"Windows 校時失敗：{output or 'unknown error'}")
    return False


def _run_windows_time_startup_checks() -> Tuple[List[str], List[str]]:
    startup_notes: List[str] = []
    startup_warnings: List[str] = []
    if not _is_windows():
        return startup_notes, startup_warnings

    result = verify_and_repair_cached(threshold_seconds=0.05, force_step_correction=True)
    startup_notes.extend(result.notes)
    startup_warnings.extend(result.warnings)
    if not result.success and not startup_warnings:
        startup_warnings.append("Windows 校時未完成")
    return startup_notes, startup_warnings


def main():
    _ensure_admin_or_exit()
    file_logging_enabled, log_path = _init_runtime_logging()
    print("[StockTrader] Python version:", sys.version)
    print("[StockTrader] sys.frozen:", getattr(sys, 'frozen', False))
    print("[StockTrader] exe path:", sys.executable if getattr(sys, 'frozen', False) else __file__)
    if file_logging_enabled and log_path:
        print("[StockTrader] File logging:", log_path)
    startup_notes, startup_warnings = _run_windows_time_startup_checks()
    for note in startup_notes:
        print("[StockTrader] Startup time check:", note)
    print("[StockTrader] Importing modules...")

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt

    import config
    print("[StockTrader] config OK")
    import engine
    print("[StockTrader] engine OK")
    import gui
    print("[StockTrader] gui OK")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # ── Milestone 1：初始化 broker 適配器 ────────────────
    broker_settings = config.BrokerSettings.load()
    broker_adapter = _init_broker(broker_settings)

    print("[StockTrader] Starting GUI...")
    win = gui.App()
    win.set_broker(broker_adapter)
    win.show()
    if startup_warnings:
        _show_startup_message(
            "StockTrader 時間校正警告",
            "\n".join(["啟動時未能完整完成 Windows 校時：", *startup_warnings]),
            flags=0x30,
        )
    sys.exit(app.exec())


def _init_broker(settings):
    """依據設定建立 broker 適配器並嘗試登入。

    - MOCK_MODE=true 或 必要欄位不齊 → MockAdapter
    - 其餘情況 → FubonAdapter，登入失敗時降級為 MockAdapter
    """
    from broker import FubonAdapter, MockAdapter, BrokerError

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
            print(f"[StockTrader] Fubon 登入成功：{result.selected.display}"
                  f"（dry_run={settings.dry_run}）")
        return adapter
    except BrokerError as e:
        print(f"[StockTrader] Fubon 登入失敗：{e} → 改用 MockAdapter")
        adapter = MockAdapter()
        adapter.login()
        return adapter


if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        print("\n========== ERROR ==========")
        print(tb)
        print("===========================")
        # 即使 logging 沒初始化或 console=False，也把錯誤寫到固定檔案
        try:
            crash_path = os.path.join(_log_dir(), "startup_crash.log")
            with open(crash_path, "a", encoding="utf-8") as fp:
                fp.write("\n========== STARTUP CRASH ==========\n")
                fp.write(tb)
                fp.write("===================================\n")
        except Exception:
            pass
        log_path = get_runtime_log_path()
        if log_path:
            print("[StockTrader] Error log written to:", log_path)
        else:
            print("[StockTrader] File logging is disabled; no error log was written.")
        try:
            input("\nPress Enter to exit...")
        except Exception:
            pass
        sys.exit(1)
