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

    print("[StockTrader] Starting GUI...")
    win = gui.App()
    win.show()
    sys.exit(app.exec())


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
