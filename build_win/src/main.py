"""
main.py — 程式進入點
執行：python main.py
打包：pyinstaller build.spec
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app_logging import get_runtime_log_path
from bootstrap import (
    ensure_admin_or_exit,
    init_broker,
    init_runtime_logging,
    run_windows_time_startup_checks,
    runtime_log_dir,
    show_startup_message,
)


def main():
    ensure_admin_or_exit()
    file_logging_enabled, log_path = init_runtime_logging()
    print("[StockTrader] Python version:", sys.version)
    print("[StockTrader] sys.frozen:", getattr(sys, 'frozen', False))
    print("[StockTrader] exe path:", sys.executable if getattr(sys, 'frozen', False) else __file__)
    if file_logging_enabled and log_path:
        print("[StockTrader] File logging:", log_path)
    startup_notes, startup_warnings = run_windows_time_startup_checks()
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
    broker_adapter = init_broker(broker_settings)

    print("[StockTrader] Starting GUI...")
    win = gui.App()
    win.set_broker(broker_adapter)
    win.show()
    if startup_warnings:
        show_startup_message(
            "StockTrader 時間校正警告",
            "\n".join(["啟動時未能完整完成 Windows 校時：", *startup_warnings]),
            flags=0x30,
        )
    sys.exit(app.exec())


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
            crash_path = os.path.join(runtime_log_dir(), "startup_crash.log")
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
