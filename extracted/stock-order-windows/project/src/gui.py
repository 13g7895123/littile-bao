"""
gui.py — tkinter 主視窗（分頁：設定 / 監控 / 交易紀錄）
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import queue
import logging
from datetime import datetime
from typing import Optional

from config import TradingConfig
from broker import ShioajiBroker
from engine import TradingEngine

LOG_QUEUE: queue.Queue = queue.Queue()


class QueueHandler(logging.Handler):
    def emit(self, record):
        LOG_QUEUE.put(self.format(record))


# ─────────────────────────────────────────────────────────────
#  主視窗
# ─────────────────────────────────────────────────────────────

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("台股漲停自動交易系統 v1.0")
        self.geometry("900x660")
        self.resizable(True, True)
        self.configure(bg="#1e1e2e")

        self.config_data = TradingConfig.load()
        self.broker: Optional[ShioajiBroker] = None
        self.engine: Optional[TradingEngine] = None
        self._running = False

        self._build_ui()
        self._start_log_poller()
        self._start_monitor_poller()

        # 設定 logging
        handler = QueueHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                               datefmt="%H:%M:%S"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    # ─────────────────────────────────────────
    #  UI 建立
    # ─────────────────────────────────────────

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook", background="#1e1e2e", borderwidth=0)
        style.configure("TNotebook.Tab",
                        background="#2a2a3e", foreground="#cdd6f4",
                        padding=[14, 6], font=("微軟正黑體", 10))
        style.map("TNotebook.Tab",
                  background=[("selected", "#89b4fa")],
                  foreground=[("selected", "#1e1e2e")])
        style.configure("TFrame", background="#1e1e2e")
        style.configure("TLabel", background="#1e1e2e", foreground="#cdd6f4",
                        font=("微軟正黑體", 10))
        style.configure("TCheckbutton", background="#1e1e2e", foreground="#cdd6f4",
                        font=("微軟正黑體", 10))
        style.configure("TEntry", fieldbackground="#313244", foreground="#cdd6f4",
                        insertcolor="#cdd6f4")
        style.configure("TLabelframe", background="#1e1e2e", foreground="#89b4fa",
                        font=("微軟正黑體", 10, "bold"))
        style.configure("TLabelframe.Label", background="#1e1e2e", foreground="#89b4fa",
                        font=("微軟正黑體", 10, "bold"))
        style.configure("Treeview", background="#313244", foreground="#cdd6f4",
                        fieldbackground="#313244", rowheight=24)
        style.configure("Treeview.Heading", background="#45475a", foreground="#cdd6f4",
                        font=("微軟正黑體", 9, "bold"))

        # 頂部狀態列
        top = tk.Frame(self, bg="#181825", height=46)
        top.pack(fill="x")
        top.pack_propagate(False)

        self.status_dot = tk.Label(top, text="●", fg="#f38ba8", bg="#181825",
                                   font=("Arial", 14))
        self.status_dot.pack(side="left", padx=(14, 4), pady=8)
        self.status_label = tk.Label(top, text="未連線", fg="#cdd6f4", bg="#181825",
                                     font=("微軟正黑體", 11, "bold"))
        self.status_label.pack(side="left")

        self.btn_start = tk.Button(
            top, text="▶ 啟動交易", bg="#a6e3a1", fg="#1e1e2e",
            font=("微軟正黑體", 10, "bold"), relief="flat",
            padx=14, pady=4, cursor="hand2", command=self._start_trading
        )
        self.btn_start.pack(side="right", padx=10, pady=8)

        self.btn_stop = tk.Button(
            top, text="■ 停止", bg="#f38ba8", fg="#1e1e2e",
            font=("微軟正黑體", 10, "bold"), relief="flat",
            padx=14, pady=4, cursor="hand2", command=self._stop_trading,
            state="disabled"
        )
        self.btn_stop.pack(side="right", padx=(0, 6), pady=8)

        # 分頁
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=(6, 8))

        self.tab_settings = ttk.Frame(notebook)
        self.tab_monitor = ttk.Frame(notebook)
        self.tab_log = ttk.Frame(notebook)
        self.tab_trades = ttk.Frame(notebook)

        notebook.add(self.tab_settings, text="⚙  設定")
        notebook.add(self.tab_monitor, text="📊  即時監控")
        notebook.add(self.tab_log, text="📋  系統日誌")
        notebook.add(self.tab_trades, text="💹  交易紀錄")

        self._build_settings(self.tab_settings)
        self._build_monitor(self.tab_monitor)
        self._build_log(self.tab_log)
        self._build_trades(self.tab_trades)

    # ─────────────────────────────────────────
    #  設定頁
    # ─────────────────────────────────────────

    def _build_settings(self, parent):
        canvas = tk.Canvas(parent, bg="#1e1e2e", highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _resize(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(win_id, width=e.width)
        inner.bind("<Configure>", _resize)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))

        cfg = self.config_data
        self._vars = {}

        # ── 帳號設定 ─────────────────────────────────────────
        f0 = self._section(inner, "🔐  券商帳號（永豐金 Shioaji）")
        self._row(f0, "API Key", "api_id", cfg.api_id, 0)
        self._row(f0, "Secret Key", "api_key", cfg.api_key, 1, show="*")
        self._row(f0, "憑證路徑 (選填)", "broker_cert_path", cfg.broker_cert_path, 2)

        # ── 功能 1 ───────────────────────────────────────────
        f1 = self._section(inner, "① 時間 + 委賣篩選（10點前漲停）")
        self._check(f1, "啟用此功能", "f1_enabled", cfg.f1_enabled, 0)
        self._row(f1, "進場截止時間 (HH:MM)", "entry_before_time", cfg.entry_before_time, 1)
        self._row(f1, "漲停委賣張數上限 (低於才進)", "ask_queue_threshold",
                  cfg.ask_queue_threshold, 2)

        # ── 功能 2 ───────────────────────────────────────────
        f2 = self._section(inner, "② 市場選擇")
        self._check(f2, "上市 (TSE)", "market_twse", cfg.market_twse, 0)
        self._check(f2, "上櫃 (OTC)", "market_tpex", cfg.market_tpex, 1)

        # ── 功能 3 ───────────────────────────────────────────
        f3 = self._section(inner, "③ 每隻股票投入金額")
        self._row(f3, "金額（元）", "per_stock_amount", cfg.per_stock_amount, 0)

        # ── 功能 4 ───────────────────────────────────────────
        f4 = self._section(inner, "④ 持倉出場：委買漲停 → 市價賣")
        self._check(f4, "啟用此功能", "f4_enabled", cfg.f4_enabled, 0)

        # ── 功能 5 ───────────────────────────────────────────
        f5 = self._section(inner, "⑤ 持倉出場：1秒成交量爆量")
        self._check(f5, "啟用此功能", "f5_enabled", cfg.f5_enabled, 0)
        self._row(f5, "1秒成交張數門檻（超過則賣）", "volume_spike_sell_threshold",
                  cfg.volume_spike_sell_threshold, 1)

        # ── 功能 6 ───────────────────────────────────────────
        f6 = self._section(inner, "⑥ 委託中取消：1秒成交量爆量")
        self._check(f6, "啟用此功能", "f6_enabled", cfg.f6_enabled, 0)
        self._row(f6, "1秒成交張數門檻（超過則取消）", "volume_spike_cancel_threshold",
                  cfg.volume_spike_cancel_threshold, 1)

        # ── 功能 7 ───────────────────────────────────────────
        f7 = self._section(inner, "⑦ 只買起漲第幾根K棒")
        self._check(f7, "啟用此功能", "f7_enabled", cfg.f7_enabled, 0)
        self._row(f7, "最多第幾根（1=只買第1根，2=買第1或第2根）",
                  "candle_limit", cfg.candle_limit, 1)

        # ── 功能 8 ───────────────────────────────────────────
        f8 = self._section(inner, "⑧ 當天成交量門檻（幾張以上才進場）")
        self._check(f8, "啟用此功能", "f8_enabled", cfg.f8_enabled, 0)
        self._row(f8, "當天最低成交量（張，低於不進場）",
                  "daily_volume_min", cfg.daily_volume_min, 1)

        # ── 功能 9 ───────────────────────────────────────────
        f9 = self._section(inner, "⑨ 股價區間篩選")
        self._check(f9, "啟用此功能", "f9_enabled", cfg.f9_enabled, 0)
        self._row(f9, "最低股價（元）", "price_min", cfg.price_min, 1)
        self._row(f9, "最高股價（元）", "price_max", cfg.price_max, 2)

        # ── 功能 10 ──────────────────────────────────────────
        f10 = self._section(inner, "⑩ 委賣價 + 即時量雙重確認進場")
        self._check(f10, "啟用此功能", "f10_enabled", cfg.f10_enabled, 0)
        self._row(f10, "委賣價倍率（≤漲停價×倍率，例：1.0）",
                  "ask_price_ratio", cfg.ask_price_ratio, 1)
        self._row(f10, "進場前1秒成交量須達（張）",
                  "entry_volume_confirm", cfg.entry_volume_confirm, 2)

        # 儲存按鈕
        btn = tk.Button(
            inner, text="💾  儲存設定", bg="#89b4fa", fg="#1e1e2e",
            font=("微軟正黑體", 11, "bold"), relief="flat",
            padx=20, pady=8, cursor="hand2", command=self._save_settings
        )
        btn.pack(pady=(10, 20))

    def _section(self, parent, title: str) -> ttk.LabelFrame:
        f = ttk.LabelFrame(parent, text=title, padding=(12, 8))
        f.pack(fill="x", padx=16, pady=(8, 4))
        return f

    def _row(self, parent, label: str, key: str, default, row: int, show: str = ""):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        var = tk.StringVar(value=str(default))
        self._vars[key] = var
        e = ttk.Entry(parent, textvariable=var, width=28, show=show)
        e.grid(row=row, column=1, sticky="w", padx=(12, 0), pady=3)

    def _check(self, parent, label: str, key: str, default: bool, row: int):
        var = tk.BooleanVar(value=default)
        self._vars[key] = var
        ttk.Checkbutton(parent, text=label, variable=var).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=3
        )

    def _save_settings(self):
        cfg = self.config_data
        v = self._vars
        try:
            cfg.api_id = v["api_id"].get()
            cfg.api_key = v["api_key"].get()
            cfg.broker_cert_path = v["broker_cert_path"].get()
            cfg.f1_enabled = v["f1_enabled"].get()
            cfg.entry_before_time = v["entry_before_time"].get()
            cfg.ask_queue_threshold = int(v["ask_queue_threshold"].get())
            cfg.market_twse = v["market_twse"].get()
            cfg.market_tpex = v["market_tpex"].get()
            cfg.per_stock_amount = int(v["per_stock_amount"].get())
            cfg.f4_enabled = v["f4_enabled"].get()
            cfg.f5_enabled = v["f5_enabled"].get()
            cfg.volume_spike_sell_threshold = int(v["volume_spike_sell_threshold"].get())
            cfg.f6_enabled = v["f6_enabled"].get()
            cfg.volume_spike_cancel_threshold = int(v["volume_spike_cancel_threshold"].get())
            cfg.f7_enabled = v["f7_enabled"].get()
            cfg.candle_limit = int(v["candle_limit"].get())
            cfg.f8_enabled = v["f8_enabled"].get()
            cfg.daily_volume_min = int(v["daily_volume_min"].get())
            cfg.f9_enabled = v["f9_enabled"].get()
            cfg.price_min = float(v["price_min"].get())
            cfg.price_max = float(v["price_max"].get())
            cfg.f10_enabled = v["f10_enabled"].get()
            cfg.ask_price_ratio = float(v["ask_price_ratio"].get())
            cfg.entry_volume_confirm = int(v["entry_volume_confirm"].get())
            cfg.save()
            messagebox.showinfo("儲存成功", "設定已儲存！")
        except ValueError as e:
            messagebox.showerror("格式錯誤", f"請確認數字欄位格式正確：{e}")

    # ─────────────────────────────────────────
    #  監控頁
    # ─────────────────────────────────────────

    def _build_monitor(self, parent):
        cols = ("symbol", "candle", "qty", "pending", "vol_1s", "status")
        labels = ("股票代號", "漲停根數", "持倉(張)", "委託中", "1秒量(張)", "狀態")
        self.tree_monitor = ttk.Treeview(parent, columns=cols, show="headings", height=20)
        for c, l in zip(cols, labels):
            self.tree_monitor.heading(c, text=l)
            self.tree_monitor.column(c, width=110, anchor="center")
        self.tree_monitor.pack(fill="both", expand=True, padx=8, pady=8)

    # ─────────────────────────────────────────
    #  日誌頁
    # ─────────────────────────────────────────

    def _build_log(self, parent):
        self.log_box = scrolledtext.ScrolledText(
            parent, bg="#11111b", fg="#a6e3a1",
            font=("Consolas", 9), state="disabled", wrap="word"
        )
        self.log_box.pack(fill="both", expand=True, padx=8, pady=8)

    # ─────────────────────────────────────────
    #  交易紀錄頁
    # ─────────────────────────────────────────

    def _build_trades(self, parent):
        cols = ("time", "symbol", "action", "price", "qty", "note")
        labels = ("時間", "股票", "方向", "價格", "張數", "備註")
        self.tree_trades = ttk.Treeview(parent, columns=cols, show="headings", height=20)
        for c, l in zip(cols, labels):
            self.tree_trades.heading(c, text=l)
            self.tree_trades.column(c, width=120, anchor="center")
        self.tree_trades.tag_configure("buy", foreground="#a6e3a1")
        self.tree_trades.tag_configure("sell", foreground="#f38ba8")
        self.tree_trades.pack(fill="both", expand=True, padx=8, pady=8)

    # ─────────────────────────────────────────
    #  啟動 / 停止交易
    # ─────────────────────────────────────────

    def _start_trading(self):
        self._save_settings()
        cfg = self.config_data
        if not cfg.api_id or not cfg.api_key:
            messagebox.showwarning("缺少帳號", "請先填寫 API Key 和 Secret Key！")
            return

        self.broker = ShioajiBroker()
        ok = self.broker.login(cfg.api_id, cfg.api_key, cfg.broker_cert_path)
        if not ok:
            messagebox.showerror("登入失敗", "無法連線券商，請確認帳號密碼和網路。")
            return

        self.engine = TradingEngine(
            config=cfg,
            broker=self.broker,
            on_log=self._append_log,
            on_trade=self._append_trade,
        )
        self.engine.start()
        self._running = True

        self.status_dot.config(fg="#a6e3a1")
        self.status_label.config(text="交易中")
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")

    def _stop_trading(self):
        if self.engine:
            threading.Thread(target=self.engine.stop, daemon=True).start()
        self._running = False
        self.status_dot.config(fg="#f38ba8")
        self.status_label.config(text="已停止")
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")

    # ─────────────────────────────────────────
    #  輪詢更新
    # ─────────────────────────────────────────

    def _start_log_poller(self):
        def poll():
            while True:
                try:
                    msg = LOG_QUEUE.get_nowait()
                    self._append_log(msg)
                except queue.Empty:
                    pass
                self.after(200, poll)
                break
        self.after(200, poll)

    def _start_monitor_poller(self):
        def poll():
            if self._running and self.engine:
                summary = self.engine.get_summary()
                self.tree_monitor.delete(*self.tree_monitor.get_children())
                for s in summary:
                    status = "持倉" if s["qty"] > 0 else ("委託中" if s["pending"] else "監控")
                    self.tree_monitor.insert("", "end", values=(
                        s["symbol"], s["candle"], s["qty"],
                        "是" if s["pending"] else "否",
                        s["vol_1s"], status,
                    ))
            self.after(1000, poll)
        self.after(1000, poll)

    def _append_log(self, msg: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _append_trade(self, d: dict):
        tag = "buy" if d["action"] == "BUY" else "sell"
        self.tree_trades.insert("", 0, values=(
            d["time"], d["symbol"], d["action"],
            d["price"], d["qty"], d["note"]
        ), tags=(tag,))
