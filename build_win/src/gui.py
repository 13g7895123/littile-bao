"""
gui.py — 台股漲停自動交易系統 主視窗
使用純 tkinter，不依賴任何券商 API，可直接 PyInstaller 打包為 exe。
"""
from __future__ import annotations
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, font as tkfont
from typing import Dict, Optional, Tuple
from datetime import datetime

from config import TradingConfig
from engine import TradingEngine

# ──────────────────────────────────────────────
#  Catppuccin Mocha 調色盤
# ──────────────────────────────────────────────
C = {
    "base":    "#1e1e2e",
    "mantle":  "#181825",
    "crust":   "#11111b",
    "surface0":"#313244",
    "surface1":"#45475a",
    "surface2":"#585b70",
    "overlay0":"#6c7086",
    "overlay1":"#7f849c",
    "text":    "#cdd6f4",
    "subtext0":"#a6adc8",
    "blue":    "#89b4fa",
    "green":   "#a6e3a1",
    "red":     "#f38ba8",
    "yellow":  "#f9e2af",
    "peach":   "#fab387",
    "mauve":   "#cba6f7",
    "teal":    "#94e2d5",
}

LOG_Q: queue.Queue = queue.Queue()


# ──────────────────────────────────────────────────────────────
#  工具元件
# ──────────────────────────────────────────────────────────────

class ToggleButton(tk.Frame):
    """iOS 風格 toggle switch"""

    def __init__(self, master, initial=True, command=None, **kw):
        super().__init__(master, bg=kw.pop("bg", C["mantle"]), **kw)
        self._on = initial
        self._cmd = command
        self._canvas = tk.Canvas(self, width=42, height=22,
                                  bg=self["bg"], highlightthickness=0, cursor="hand2")
        self._canvas.pack()
        self._canvas.bind("<Button-1>", self._toggle)
        self._draw()

    def _draw(self):
        self._canvas.delete("all")
        fill = C["blue"] if self._on else C["surface0"]
        self._canvas.create_rounded_rect = lambda *a, **k: None  # placeholder
        # pill background
        self._canvas.create_oval(1, 1, 20, 21, fill=fill, outline="")
        self._canvas.create_oval(22, 1, 41, 21, fill=fill, outline="")
        self._canvas.create_rectangle(11, 1, 31, 21, fill=fill, outline="")
        # knob
        x = 30 if self._on else 12
        self._canvas.create_oval(x - 9, 3, x + 9, 19,
                                   fill=C["base"], outline="")

    def _toggle(self, _=None):
        self._on = not self._on
        self._draw()
        if self._cmd:
            self._cmd(self._on)

    @property
    def value(self) -> bool:
        return self._on

    def set(self, val: bool):
        if self._on != val:
            self._on = val
            self._draw()


def label(parent, text, fg=None, bg=None, **kw):
    return tk.Label(parent, text=text,
                    fg=fg or C["text"], bg=bg or C["base"],
                    font=("微軟正黑體", 10), **kw)


def entry(parent, var, width=22, show="", readonly=False):
    e = tk.Entry(parent, textvariable=var, width=width,
                 bg=C["surface0"], fg=C["text"],
                 insertbackground=C["text"],
                 relief="flat", bd=0, show=show,
                 font=("微軟正黑體", 10),
                 disabledbackground=C["surface0"],
                 disabledforeground=C["overlay0"],
                 highlightthickness=1,
                 highlightcolor=C["blue"],
                 highlightbackground=C["surface1"])
    if readonly:
        e.config(state="disabled")
    return e


def section_frame(parent, title):  # type: (...) -> Tuple[tk.LabelFrame, tk.Frame]
    lf = tk.LabelFrame(parent, text=f"  {title}  ",
                        fg=C["blue"], bg=C["base"],
                        font=("微軟正黑體", 10, "bold"),
                        relief="flat", bd=1,
                        highlightthickness=1,
                        highlightbackground=C["surface0"])
    lf.pack(fill="x", padx=16, pady=(0, 10))
    inner = tk.Frame(lf, bg=C["base"])
    inner.pack(fill="x", padx=10, pady=(4, 10))
    return lf, inner


# ──────────────────────────────────────────────────────────────
#  主視窗
# ──────────────────────────────────────────────────────────────

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("台股漲停自動交易系統 v1.0")
        self.geometry("980x700")
        self.minsize(860, 600)
        self.configure(bg=C["crust"])

        self.cfg = TradingConfig.load()
        self.engine: Optional[TradingEngine] = None
        self._running = False
        self._trade_count = 0
        self._buy_count = 0
        self._sell_count = 0

        self._vars = {}   # type: Dict[str, tk.Variable]
        self._toggles = {}  # type: Dict[str, ToggleButton]

        self._build_ui()
        self._apply_config(self.cfg)
        self._start_polling()

    # ══════════════════════════════════════════
    #  UI 建立
    # ══════════════════════════════════════════

    def _build_ui(self):
        self._build_titlebar()
        self._build_tabbar(defer_switch=True)
        self._build_pages()
        self._switch_tab("settings")

    # ── 標題列 ───────────────────────────────
    def _build_titlebar(self):
        bar = tk.Frame(self, bg=C["mantle"], height=50)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        tk.Label(bar, text="\u25B2", bg=C["mantle"],
                 font=("Segoe UI Emoji", 16)).pack(side="left", padx=(14, 4), pady=10)
        tk.Label(bar, text="台股漲停自動交易系統 v1.0",
                 fg=C["text"], bg=C["mantle"],
                 font=("微軟正黑體", 12, "bold")).pack(side="left", padx=(0, 20))

        # 右側按鈕
        self.btn_start = tk.Button(
            bar, text="▶  啟動交易",
            bg=C["green"], fg=C["base"],
            font=("微軟正黑體", 10, "bold"),
            relief="flat", padx=16, pady=6,
            cursor="hand2", command=self._start_trading,
            activebackground=C["teal"], activeforeground=C["base"])
        self.btn_start.pack(side="right", padx=14, pady=10)

        self.btn_stop = tk.Button(
            bar, text="■  停止",
            bg=C["red"], fg=C["base"],
            font=("微軟正黑體", 10, "bold"),
            relief="flat", padx=16, pady=6,
            cursor="hand2", command=self._stop_trading,
            state="disabled",
            activebackground="#ff9999", activeforeground=C["base"])
        self.btn_stop.pack(side="right", padx=(0, 6), pady=10)

        # 狀態燈
        status_box = tk.Frame(bar, bg=C["mantle"])
        status_box.pack(side="right", padx=20)
        self.status_dot = tk.Label(status_box, text="●",
                                    fg=C["red"], bg=C["mantle"],
                                    font=("Arial", 13))
        self.status_dot.pack(side="left")
        self.status_text = tk.Label(status_box, text="未連線",
                                     fg=C["overlay0"], bg=C["mantle"],
                                     font=("微軟正黑體", 10))
        self.status_text.pack(side="left", padx=(4, 0))

    # ── 分頁列 ───────────────────────────────
    def _build_tabbar(self, defer_switch=False):
        bar = tk.Frame(self, bg=C["mantle"], height=38)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        sep = tk.Frame(self, bg=C["surface0"], height=1)
        sep.pack(fill="x")

        self._tab_btns = {}  # type: Dict[str, tk.Label]
        self._current_tab = tk.StringVar(value="settings")

        tabs = [
            ("settings", "⚙  設定"),
            ("monitor",  "\u25CF  即時監控"),
            ("log",      "\u2261  系統日誌"),
            ("trades",   "\u2606  交易紀錄"),
        ]
        for key, text in tabs:
            btn = tk.Label(bar, text=text,
                           fg=C["overlay0"], bg=C["mantle"],
                           font=("微軟正黑體", 10, "bold"),
                           padx=18, pady=10, cursor="hand2")
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda e, k=key: self._switch_tab(k))
            self._tab_btns[key] = btn
        if not defer_switch:
            self._switch_tab("settings")

    def _switch_tab(self, key: str):
        self._current_tab.set(key)
        for k, btn in self._tab_btns.items():
            if k == key:
                btn.config(fg=C["blue"],
                           font=("微軟正黑體", 10, "bold"))
            else:
                btn.config(fg=C["overlay0"],
                           font=("微軟正黑體", 10, "bold"))
        for k, frame in self._pages.items():
            if k == key:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()

    # ── 分頁容器 ─────────────────────────────
    def _build_pages(self):
        container = tk.Frame(self, bg=C["crust"])
        container.pack(fill="both", expand=True)

        self._pages = {}  # type: Dict[str, tk.Frame]
        for key in ("settings", "monitor", "log", "trades"):
            f = tk.Frame(container, bg=C["base"])
            self._pages[key] = f

        self._build_settings(self._pages["settings"])
        self._build_monitor(self._pages["monitor"])
        self._build_log(self._pages["log"])
        self._build_trades(self._pages["trades"])

    # ══════════════════════════════════════════
    #  設定頁
    # ══════════════════════════════════════════

    def _build_settings(self, parent):
        # 外層帶 scrollbar
        canvas = tk.Canvas(parent, bg=C["base"], highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=C["base"])
        wid = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _resize(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def _resize_w(e):
            canvas.itemconfig(wid, width=e.width)
        inner.bind("<Configure>", _resize)
        canvas.bind("<Configure>", _resize_w)

        # 滑鼠滾輪
        def _on_wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_wheel)

        # ── 帳號設定 ──────────────────────────
        _, f = section_frame(inner, "\u25A0  券商帳號（永豐金 Shioaji）")
        self._srow(f, 0, "API Key",        "api_id")
        self._srow(f, 1, "Secret Key",     "api_key", show="*")
        self._srow(f, 2, "憑證路徑（選填）", "broker_cert_path", width=40)

        # ── 功能 1 ────────────────────────────
        lf1, f1 = section_frame(inner, "① 時間 + 委賣篩選（10點前漲停才進場）")
        self._add_toggle(lf1, "f1_enabled")
        self._srow(f1, 0, "進場截止時間（HH:MM）",             "entry_before_time")
        self._srow(f1, 1, "漲停委賣張數上限（低於此數才進場）", "ask_queue_threshold")

        # ── 功能 2 ────────────────────────────
        _, f2 = section_frame(inner, "② 市場選擇")
        self._check(f2, 0, "上市（TSE）", "market_twse")
        self._check(f2, 1, "上櫃（OTC）", "market_tpex")

        # ── 功能 3 ────────────────────────────
        _, f3 = section_frame(inner, "③ 每隻股票投入金額（元）")
        self._srow(f3, 0, "金額（元）",  "per_stock_amount")
        v = tk.StringVar(value="依漲停價自動計算張數")
        label(f3, "計算說明：").grid(row=1, column=0, sticky="w", pady=3)
        entry(f3, v, width=30, readonly=True).grid(row=1, column=1, sticky="w", padx=8, pady=3)

        # ── 功能 4 ────────────────────────────
        lf4, f4 = section_frame(inner, "④ 持倉出場：委買漲停 → 市價賣出")
        self._add_toggle(lf4, "f4_enabled")
        label(f4, "買進後，若委買價達到漲停（市場打開），立即市價賣出。",
              fg=C["overlay0"]).grid(row=0, column=0, columnspan=2, sticky="w", pady=3)

        # ── 功能 5 ────────────────────────────
        lf5, f5 = section_frame(inner, "⑤ 持倉出場：1秒成交量爆量賣出")
        self._add_toggle(lf5, "f5_enabled")
        self._srow(f5, 0, "1秒成交張數門檻（超過則市價賣出）", "volume_spike_sell_threshold")

        # ── 功能 6 ────────────────────────────
        lf6, f6 = section_frame(inner, "⑥ 委託中取消：1秒成交量爆量取消委託")
        self._add_toggle(lf6, "f6_enabled")
        self._srow(f6, 0, "1秒成交張數門檻（超過則取消委託）", "volume_spike_cancel_threshold")

        # ── 功能 7 ────────────────────────────
        lf7, f7 = section_frame(inner, "⑦ 只買起漲第幾根 K 棒")
        self._add_toggle(lf7, "f7_enabled")
        self._srow(f7, 0, "最多第幾根（1=只買第1根，2=第1或第2根）", "candle_limit")

        # ── 功能 8 ────────────────────────────
        lf8, f8 = section_frame(inner, "⑧ 當天成交量門檻（幾張以上才進場）")
        self._add_toggle(lf8, "f8_enabled")
        self._srow(f8, 0, "當天最低成交量（張，低於不進場）", "daily_volume_min")

        # ── 功能 9 ────────────────────────────
        lf9, f9 = section_frame(inner, "⑨ 股價區間篩選")
        self._add_toggle(lf9, "f9_enabled")
        self._srow(f9, 0, "最低股價（元）", "price_min")
        self._srow(f9, 1, "最高股價（元）", "price_max")

        # ── 功能 10 ───────────────────────────
        lf10, f10 = section_frame(inner, "⑩ 委賣價 + 即時成交量雙重確認進場")
        self._add_toggle(lf10, "f10_enabled")
        self._srow(f10, 0, "委賣價必須 ≤ 漲停價 × 倍率（1.0 = 恰好漲停）", "ask_price_ratio")
        self._srow(f10, 1, "該檔 1 秒內成交量必須達到（張）才進場",          "entry_volume_confirm")
        label(f10, "兩條件須同時成立才進場，可搭配功能①使用。",
              fg=C["overlay0"]).grid(row=2, column=0, columnspan=2, sticky="w", pady=2)

        # ── 底部按鈕 ──────────────────────────
        btn_bar = tk.Frame(inner, bg=C["base"])
        btn_bar.pack(fill="x", padx=16, pady=(0, 16))

        tk.Button(btn_bar, text="\u2714  儲存設定",
                  bg=C["blue"], fg=C["base"],
                  font=("微軟正黑體", 11, "bold"),
                  relief="flat", padx=20, pady=8,
                  cursor="hand2", command=self._save_settings,
                  activebackground=C["mauve"], activeforeground=C["base"]
                  ).pack(side="left", padx=(0, 10))

        tk.Button(btn_bar, text="↩  還原預設",
                  bg=C["surface0"], fg=C["text"],
                  font=("微軟正黑體", 10),
                  relief="flat", padx=14, pady=8,
                  cursor="hand2", command=self._reset_settings,
                  activebackground=C["surface1"], activeforeground=C["text"]
                  ).pack(side="left")

        self.save_status = tk.Label(btn_bar, text="✓ 設定已儲存",
                                     fg=C["green"], bg=C["base"],
                                     font=("微軟正黑體", 10))
        self.save_status.pack(side="left", padx=14)
        self.save_status.pack_forget()

    def _srow(self, parent, row, lbl_text, key, width=22, show=""):
        label(parent, lbl_text + " ：").grid(row=row, column=0, sticky="w", pady=4)
        var = tk.StringVar()
        self._vars[key] = var
        e = entry(parent, var, width=width, show=show)
        e.grid(row=row, column=1, sticky="w", padx=10, pady=4)

    def _check(self, parent, row, lbl_text, key):
        var = tk.BooleanVar()
        self._vars[key] = var
        cb = tk.Checkbutton(parent, text=lbl_text, variable=var,
                             fg=C["text"], bg=C["base"],
                             activeforeground=C["text"],
                             activebackground=C["base"],
                             selectcolor=C["surface0"],
                             font=("微軟正黑體", 10))
        cb.grid(row=row, column=0, columnspan=2, sticky="w", pady=3)

    def _add_toggle(self, labelframe: tk.LabelFrame, key: str):
        tog = ToggleButton(labelframe, bg=C["mantle"])
        tog.place(relx=1.0, x=-10, rely=0.5, anchor="e")
        self._toggles[key] = tog

    # ── 設定讀寫 ─────────────────────────────
    def _apply_config(self, cfg: TradingConfig):
        def sv(k, v): self._vars[k].set(str(v))
        def bv(k, v): self._vars[k].set(v)

        sv("api_id",              cfg.api_id)
        sv("api_key",             cfg.api_key)
        sv("broker_cert_path",    cfg.broker_cert_path)
        sv("entry_before_time",   cfg.entry_before_time)
        sv("ask_queue_threshold", cfg.ask_queue_threshold)
        bv("market_twse",         cfg.market_twse)
        bv("market_tpex",         cfg.market_tpex)
        sv("per_stock_amount",    cfg.per_stock_amount)
        sv("volume_spike_sell_threshold",   cfg.volume_spike_sell_threshold)
        sv("volume_spike_cancel_threshold", cfg.volume_spike_cancel_threshold)
        sv("candle_limit",        cfg.candle_limit)
        sv("daily_volume_min",    cfg.daily_volume_min)
        sv("price_min",           cfg.price_min)
        sv("price_max",           cfg.price_max)
        sv("ask_price_ratio",     cfg.ask_price_ratio)
        sv("entry_volume_confirm",cfg.entry_volume_confirm)

        self._toggles["f1_enabled"].set(cfg.f1_enabled)
        self._toggles["f4_enabled"].set(cfg.f4_enabled)
        self._toggles["f5_enabled"].set(cfg.f5_enabled)
        self._toggles["f6_enabled"].set(cfg.f6_enabled)
        self._toggles["f7_enabled"].set(cfg.f7_enabled)
        self._toggles["f8_enabled"].set(cfg.f8_enabled)
        self._toggles["f9_enabled"].set(cfg.f9_enabled)
        self._toggles["f10_enabled"].set(cfg.f10_enabled)

    def _collect_config(self) -> TradingConfig:
        v = self._vars
        t = self._toggles

        def g(k): return v[k].get()
        def ni(k):
            try: return int(float(g(k)))
            except: return 0
        def nf(k):
            try: return float(g(k))
            except: return 0.0

        return TradingConfig(
            api_id              = g("api_id"),
            api_key             = g("api_key"),
            broker_cert_path    = g("broker_cert_path"),
            f1_enabled          = t["f1_enabled"].value,
            entry_before_time   = g("entry_before_time"),
            ask_queue_threshold = ni("ask_queue_threshold"),
            market_twse         = bool(v["market_twse"].get()),
            market_tpex         = bool(v["market_tpex"].get()),
            per_stock_amount    = ni("per_stock_amount"),
            f4_enabled          = t["f4_enabled"].value,
            f5_enabled          = t["f5_enabled"].value,
            volume_spike_sell_threshold   = ni("volume_spike_sell_threshold"),
            f6_enabled          = t["f6_enabled"].value,
            volume_spike_cancel_threshold = ni("volume_spike_cancel_threshold"),
            f7_enabled          = t["f7_enabled"].value,
            candle_limit        = ni("candle_limit"),
            f8_enabled          = t["f8_enabled"].value,
            daily_volume_min    = ni("daily_volume_min"),
            f9_enabled          = t["f9_enabled"].value,
            price_min           = nf("price_min"),
            price_max           = nf("price_max"),
            f10_enabled         = t["f10_enabled"].value,
            ask_price_ratio     = nf("ask_price_ratio"),
            entry_volume_confirm= ni("entry_volume_confirm"),
        )

    def _save_settings(self):
        try:
            self.cfg = self._collect_config()
            self.cfg.save()
            self.save_status.pack(side="left", padx=14)
            self.after(2000, self.save_status.pack_forget)
        except ValueError as e:
            messagebox.showerror("格式錯誤", f"數字欄位格式有誤：{e}")

    def _reset_settings(self):
        if messagebox.askyesno("還原確認", "確定要還原為預設值？"):
            self._apply_config(TradingConfig())

    # ══════════════════════════════════════════
    #  即時監控頁
    # ══════════════════════════════════════════

    def _build_monitor(self, parent):
        top = tk.Frame(parent, bg=C["base"])
        top.pack(fill="x", padx=14, pady=14)

        # 統計卡
        stats_frame = tk.Frame(top, bg=C["base"])
        stats_frame.pack(fill="x")

        self.stat_watching  = self._stat_card(stats_frame, "監控中股票", "0", C["blue"])
        self.stat_positions = self._stat_card(stats_frame, "持倉",       "0", C["green"])
        self.stat_pending   = self._stat_card(stats_frame, "委託中",     "0", C["yellow"])
        self.stat_trades    = self._stat_card(stats_frame, "今日成交",   "0", C["text"])

        # 表格
        tbl_frame = tk.Frame(parent, bg=C["surface0"])
        tbl_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        cols = ("code", "name", "candle", "qty", "pending", "vol_1s", "status")
        heads = ("代號", "名稱", "漲停根數", "持倉(張)", "委託中", "1秒量(張)", "狀態")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Monitor.Treeview",
                         background=C["base"],
                         foreground=C["text"],
                         fieldbackground=C["base"],
                         rowheight=26,
                         font=("微軟正黑體", 9))
        style.configure("Monitor.Treeview.Heading",
                         background=C["mantle"],
                         foreground=C["overlay0"],
                         font=("微軟正黑體", 9, "bold"),
                         relief="flat")
        style.map("Monitor.Treeview",
                  background=[("selected", C["surface0"])],
                  foreground=[("selected", C["text"])])

        self.monitor_tree = ttk.Treeview(tbl_frame, columns=cols,
                                          show="headings",
                                          style="Monitor.Treeview")
        widths = [70, 80, 80, 70, 70, 80, 80]
        for c, h, w in zip(cols, heads, widths):
            self.monitor_tree.heading(c, text=h)
            self.monitor_tree.column(c, width=w, anchor="center", minwidth=60)

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical",
                             command=self.monitor_tree.yview)
        self.monitor_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.monitor_tree.pack(fill="both", expand=True)

        # 彩色列 tag
        self.monitor_tree.tag_configure("holding",  foreground=C["green"])
        self.monitor_tree.tag_configure("pending",  foreground=C["yellow"])
        self.monitor_tree.tag_configure("watching", foreground=C["blue"])
        self.monitor_tree.tag_configure("done",     foreground=C["overlay0"])
        self.monitor_tree.tag_configure("hot",      foreground=C["red"])

    def _stat_card(self, parent, label_text, init, color):
        card = tk.Frame(parent, bg=C["mantle"],
                        highlightthickness=1,
                        highlightbackground=C["surface0"])
        card.pack(side="left", expand=True, fill="both", padx=(0, 10), ipady=8, ipadx=12)
        tk.Label(card, text=label_text, fg=C["overlay0"],
                  bg=C["mantle"], font=("微軟正黑體", 10)).pack(anchor="w", padx=10, pady=(6, 2))
        val_lbl = tk.Label(card, text=init, fg=color,
                            bg=C["mantle"], font=("微軟正黑體", 22, "bold"))
        val_lbl.pack(anchor="w", padx=10, pady=(0, 6))
        return val_lbl

    # ══════════════════════════════════════════
    #  系統日誌頁
    # ══════════════════════════════════════════

    def _build_log(self, parent):
        toolbar = tk.Frame(parent, bg=C["base"])
        toolbar.pack(fill="x", padx=14, pady=(10, 4))

        self.log_count_lbl = tk.Label(toolbar, text="共 0 行日誌",
                                       fg=C["overlay0"], bg=C["base"],
                                       font=("微軟正黑體", 10))
        self.log_count_lbl.pack(side="left")

        self.auto_scroll_var = tk.BooleanVar(value=True)
        tk.Checkbutton(toolbar, text="自動捲動",
                        variable=self.auto_scroll_var,
                        fg=C["overlay0"], bg=C["base"],
                        activeforeground=C["text"],
                        activebackground=C["base"],
                        selectcolor=C["surface0"],
                        font=("微軟正黑體", 10)).pack(side="right", padx=(0, 10))

        tk.Button(toolbar, text="清除日誌",
                   bg=C["surface0"], fg=C["text"],
                   font=("微軟正黑體", 10),
                   relief="flat", padx=10, pady=4,
                   cursor="hand2", command=self._clear_log,
                   activebackground=C["surface1"]
                   ).pack(side="right", padx=(0, 8))

        self.log_box = scrolledtext.ScrolledText(
            parent,
            bg=C["crust"], fg=C["text"],
            font=("Consolas", 10),
            state="disabled", wrap="word",
            relief="flat", bd=0,
        )
        self.log_box.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        # 顏色 tag
        self.log_box.tag_config("INFO",  foreground=C["blue"])
        self.log_box.tag_config("TRADE", foreground=C["green"],
                                 font=("Consolas", 10, "bold"))
        self.log_box.tag_config("WARN",  foreground=C["yellow"])
        self.log_box.tag_config("ERROR", foreground=C["red"])
        self.log_box.tag_config("DEBUG", foreground=C["overlay0"])

        self._log_lines = 0

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self._log_lines = 0
        self.log_count_lbl.config(text="共 0 行日誌")

    # ══════════════════════════════════════════
    #  交易紀錄頁
    # ══════════════════════════════════════════

    def _build_trades(self, parent):
        toolbar = tk.Frame(parent, bg=C["base"])
        toolbar.pack(fill="x", padx=14, pady=(10, 4))

        self.trades_summary = tk.Label(toolbar,
            text="共 0 筆 ／ 買入 0 筆 ／ 賣出 0 筆",
            fg=C["overlay0"], bg=C["base"],
            font=("微軟正黑體", 10))
        self.trades_summary.pack(side="left")

        tk.Button(toolbar, text="清除紀錄",
                   bg=C["surface0"], fg=C["text"],
                   font=("微軟正黑體", 10),
                   relief="flat", padx=10, pady=4,
                   cursor="hand2", command=self._clear_trades,
                   activebackground=C["surface1"]
                   ).pack(side="right")

        tbl_frame = tk.Frame(parent, bg=C["surface0"])
        tbl_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        cols  = ("time", "code", "name", "action", "price", "qty", "note")
        heads = ("時間", "代號", "名稱", "方向", "價格(元)", "張數", "備註")

        style = ttk.Style()
        style.configure("Trades.Treeview",
                         background=C["base"],
                         foreground=C["text"],
                         fieldbackground=C["base"],
                         rowheight=26,
                         font=("微軟正黑體", 9))
        style.configure("Trades.Treeview.Heading",
                         background=C["mantle"],
                         foreground=C["overlay0"],
                         font=("微軟正黑體", 9, "bold"),
                         relief="flat")

        self.trades_tree = ttk.Treeview(tbl_frame, columns=cols,
                                         show="headings",
                                         style="Trades.Treeview")
        widths = [80, 65, 80, 65, 90, 60, 200]
        for c, h, w in zip(cols, heads, widths):
            self.trades_tree.heading(c, text=h)
            self.trades_tree.column(c, width=w, anchor="center", minwidth=50)

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical",
                             command=self.trades_tree.yview)
        self.trades_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.trades_tree.pack(fill="both", expand=True)

        self.trades_tree.tag_configure("buy",  foreground=C["green"])
        self.trades_tree.tag_configure("sell", foreground=C["red"])

    def _clear_trades(self):
        self.trades_tree.delete(*self.trades_tree.get_children())
        self._trade_count = 0
        self._buy_count = 0
        self._sell_count = 0
        self._update_trade_summary()

    # ══════════════════════════════════════════
    #  啟動 / 停止交易
    # ══════════════════════════════════════════

    def _start_trading(self):
        self.cfg = self._collect_config()
        if not self.cfg.get_markets():
            messagebox.showwarning("市場未選擇", "請至少選擇上市或上櫃！")
            return

        self.engine = TradingEngine(
            config=self.cfg,
            on_log=lambda lvl, msg: LOG_Q.put((lvl, msg)),
            on_trade=self._on_trade,
            on_status=lambda s: None,
        )
        self.engine.start()
        self._running = True

        self.status_dot.config(fg=C["green"])
        self.status_text.config(text="交易中", fg=C["green"])
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self._switch_tab("monitor")

    def _stop_trading(self):
        if self.engine:
            threading.Thread(target=self.engine.stop, daemon=True).start()
        self._running = False
        self.status_dot.config(fg=C["red"])
        self.status_text.config(text="已停止", fg=C["overlay0"])
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")

    def _on_trade(self, d: dict):
        """由引擎執行緒呼叫 → 丟到主執行緒處理"""
        self.after(0, self._append_trade, d)

    # ══════════════════════════════════════════
    #  輪詢更新
    # ══════════════════════════════════════════

    def _start_polling(self):
        self._poll_log()
        self._poll_monitor()

    def _poll_log(self):
        MAX_LINES = 600
        try:
            while True:
                lvl, msg = LOG_Q.get_nowait()
                self._append_log(lvl, msg)
        except queue.Empty:
            pass
        if self._log_lines > MAX_LINES:
            self.log_box.configure(state="normal")
            self.log_box.delete("1.0", "100.0")
            self.log_box.configure(state="disabled")
            self._log_lines = max(0, self._log_lines - 100)
        self.after(150, self._poll_log)

    def _poll_monitor(self):
        if self._running and self.engine:
            summary = self.engine.get_summary()
            self._render_monitor(summary)
        self.after(1200, self._poll_monitor)

    def _append_log(self, level: str, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"{ts} [{level}] {msg}\n"
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line, level)
        if self.auto_scroll_var.get():
            self.log_box.see("end")
        self.log_box.configure(state="disabled")
        self._log_lines += 1
        self.log_count_lbl.config(text=f"共 {self._log_lines} 行日誌")

    def _append_trade(self, d: dict):
        self._trade_count += 1
        action = d["action"]
        if action == "BUY":
            self._buy_count += 1
        else:
            self._sell_count += 1

        tag = "buy" if action == "BUY" else "sell"
        label_txt = "↑ 買入" if action == "BUY" else "↓ 賣出"
        self.trades_tree.insert("", 0,
            values=(
                d["time"], d["code"], d["name"],
                label_txt,
                f"{d['price']:,.0f}",
                d["qty"], d["note"],
            ),
            tags=(tag,))
        self._update_trade_summary()
        self.stat_trades.config(text=str(self._trade_count))

    def _update_trade_summary(self):
        self.trades_summary.config(
            text=f"共 {self._trade_count} 筆 ／ 買入 {self._buy_count} 筆 ／ 賣出 {self._sell_count} 筆"
        )
        self.stat_trades.config(text=str(self._trade_count))

    def _render_monitor(self, summary: list):
        pos_cnt  = sum(1 for s in summary if s["qty"] > 0)
        pend_cnt = sum(1 for s in summary if s["pending"])
        self.stat_watching.config(text=str(len(summary)))
        self.stat_positions.config(text=str(pos_cnt))
        self.stat_pending.config(text=str(pend_cnt))

        # 差量更新
        existing = {self.monitor_tree.item(iid)["values"][0]: iid
                    for iid in self.monitor_tree.get_children()}
        threshold = self.cfg.volume_spike_sell_threshold

        for s in summary:
            if s["blocked"]:
                status = "已完成"
                tag = "done"
            elif s["qty"] > 0:
                status = "持倉中"
                tag = "holding"
            elif s["pending"]:
                status = "委託中"
                tag = "pending"
            elif s["candle"] > 0:
                status = "監控中"
                tag = "watching"
            else:
                status = "等待"
                tag = "done"

            candle_txt = f"第 {s['candle']} 根" if s["candle"] > 0 else "—"
            vol_txt = str(s["vol_1s"])
            vol_tag = "hot" if s["vol_1s"] > threshold else tag

            vals = (s["code"], s["name"], candle_txt,
                    s["qty"], "是" if s["pending"] else "—",
                    vol_txt, status)

            if s["code"] in existing:
                iid = existing[s["code"]]
                self.monitor_tree.item(iid, values=vals, tags=(tag,))
            else:
                self.monitor_tree.insert("", "end", values=vals, tags=(tag,))
