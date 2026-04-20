"""
main.py — 程式進入點
執行：python main.py
打包：pyinstaller build.spec
"""
import sys
import os
import logging

# 讓打包後的 exe 也能找到 src 下的模組
sys.path.insert(0, os.path.dirname(__file__))

from gui import App

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = App()
    app.mainloop()
