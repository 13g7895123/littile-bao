"""
main.py — 程式進入點
執行：python main.py
打包：pyinstaller build.spec
"""
import sys
import os
import traceback

# 確保打包後的 exe 也能找到 src 下的模組
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _log_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def main():
    from gui import App
    app = App()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        log_path = os.path.join(_log_dir(), 'error.log')
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(tb)
        try:
            import tkinter as tk
            from tkinter import messagebox as mbox
            root = tk.Tk()
            root.withdraw()
            mbox.showerror('Startup Error', tb[:800])
            root.destroy()
        except Exception:
            pass
        sys.exit(1)
