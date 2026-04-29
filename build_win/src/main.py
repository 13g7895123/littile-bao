"""
main.py — 程式進入點
執行：python main.py
打包：pyinstaller build.spec
"""
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _log_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _write_log(msg):
    log_path = os.path.join(_log_dir(), 'error.log')
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write(msg)


def main():
    print("[StockTrader] Python version:", sys.version)
    print("[StockTrader] sys.frozen:", getattr(sys, 'frozen', False))
    print("[StockTrader] exe path:", sys.executable if getattr(sys, 'frozen', False) else __file__)
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
    broker_settings = config.BrokerSettings.from_env()
    broker_adapter = _init_broker(broker_settings)

    print("[StockTrader] Starting GUI...")
    win = gui.App()
    win.set_broker(broker_adapter)
    win.show()
    sys.exit(app.exec())


def _init_broker(settings):
    """依據設定建立 broker 適配器並嘗試登入。

    - MOCK_MODE=true 或 必要欄位不齊 → MockAdapter
    - 其餘情況 → FubonAdapter，登入失敗時降級為 MockAdapter
    """
    from broker import FubonAdapter, MockAdapter, BrokerError

    if settings.mock_mode or not settings.is_complete():
        if not settings.is_complete():
            print("[StockTrader] 未備齊 FUBON_* 環境變數 → 啟用 MockAdapter")
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
        _write_log(tb)
        print("[StockTrader] Error log written to:", os.path.join(_log_dir(), 'error.log'))
        input("\nPress Enter to exit...")
        sys.exit(1)
