"""
engine.py — 模擬交易引擎
完全獨立運行，不依賴任何券商 API，透過模擬 tick 展示完整邏輯。
"""
from __future__ import annotations
import random
import threading
import time
from collections import deque
from datetime import datetime, time as dtime
from typing import Callable, Dict, List, Optional

from config import TradingConfig


# ─────────────────────────────────────────────────────────────
#  資料結構
# ─────────────────────────────────────────────────────────────

class StockInfo:
    def __init__(self, code: str, name: str, limit_up: float, market: str,
                 is_disposal: bool = False, is_attention: bool = False,
                 is_day_trade_restricted: bool = False,
                 open_limit_up: bool = False):
        self.code = code
        self.name = name
        self.limit_up = limit_up
        self.market = market
        self.is_disposal = is_disposal                       # 處置股
        self.is_attention = is_attention                     # 注意股
        self.is_day_trade_restricted = is_day_trade_restricted  # 限當沖股
        self.open_limit_up = open_limit_up                   # 開盤即漲停


class StockState:
    def __init__(self, info: StockInfo):
        self.info = info
        self.candle_index: int = 0
        self.position_qty: int = 0
        self.pending: bool = False
        self.entry_blocked: bool = False
        self.last_1s_vol: int = 0
        self.tick_vols: deque = deque()   # (timestamp, vol)
        self.limit_up_since: Optional[float] = None
        self.sold_today: bool = False     # 功能 12：當天已賣過


MOCK_STOCKS = [
    StockInfo("2330", "台積電",   1100.0, "TSE"),
    StockInfo("2317", "鴻海",      220.0, "TSE", is_attention=True),
    StockInfo("3008", "大立光",   2860.0, "TSE"),
    StockInfo("2454", "聯發科",   1430.0, "TSE", is_disposal=True),
    StockInfo("6505", "台塑化",    108.0, "TSE", is_day_trade_restricted=True),
    StockInfo("6669", "緯穎",     3135.0, "OTC"),
    StockInfo("4919", "新唐",      231.0, "OTC", open_limit_up=True),
    StockInfo("2382", "廣達",      335.0, "TSE"),
    StockInfo("3711", "日月光投",  150.0, "TSE"),
    StockInfo("2603", "長榮",      202.0, "TSE"),
]


# ─────────────────────────────────────────────────────────────
#  引擎
# ─────────────────────────────────────────────────────────────

class TradingEngine:

    def __init__(
        self,
        config: TradingConfig,
        on_log: Callable[[str, str], None],   # (level, msg)
        on_trade: Callable[[dict], None],
        on_status: Callable[[List[dict]], None],
    ):
        self.config = config
        self.on_log = on_log
        self.on_trade = on_trade
        self.on_status = on_status

        self._states: Dict[str, StockState] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._daily_trade_count: int = 0   # 功能 13：當天已成交檔數

        # 篩選市場
        markets = config.get_markets()
        for s in MOCK_STOCKS:
            if s.market in markets:
                self._states[s.code] = StockState(s)

    # ─────────────────────────────────────────
    #  啟動 / 停止
    # ─────────────────────────────────────────

    def start(self):
        self._running = True
        self.on_log("INFO", f"引擎啟動，監控市場：{', '.join(self.config.get_markets())}")
        self.on_log("INFO", f"監控 {len(self._states)} 支股票")
        active = self._active_features()
        self.on_log("INFO", f"已啟用篩選功能：{active}")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self.on_log("INFO", "引擎已停止，登出完成")

    def _active_features(self) -> str:
        cfg = self.config
        flags = {
            "①": cfg.f1_enabled,  "④": cfg.f4_enabled,  "⑤": cfg.f5_enabled,
            "⑥": cfg.f6_enabled,  "⑦": cfg.f7_enabled,  "⑧": cfg.f8_enabled,
            "⑨": cfg.f9_enabled,  "⑩": cfg.f10_enabled,
            "⑪": cfg.f11_enabled, "⑫": cfg.f12_enabled, "⑬": cfg.f13_enabled,
        }
        return " ".join(k for k, v in flags.items() if v) or "（無）"

    # ─────────────────────────────────────────
    #  模擬主迴圈
    # ─────────────────────────────────────────

    def _loop(self):
        while self._running:
            now = time.time()
            with self._lock:
                for code, state in self._states.items():
                    self._tick(state, now)
            self.on_status(self.get_summary())
            time.sleep(1.5)

    def _tick(self, state: StockState, now: float):
        cfg = self.config
        info = state.info

        # ── 模擬 1 秒成交量 ──────────────────────────────────────
        vol = random.randint(10, 850)
        state.tick_vols.append((now, vol))
        while state.tick_vols and now - state.tick_vols[0][0] > 1.0:
            state.tick_vols.popleft()
        state.last_1s_vol = sum(v for _, v in state.tick_vols)

        # ── 功能 8：當天總成交量篩選 ─────────────────────────────
        if cfg.f8_enabled and vol < cfg.daily_volume_min:
            return

        # ── 功能 9：股價區間 ──────────────────────────────────────
        if cfg.f9_enabled:
            if not (cfg.price_min <= info.limit_up <= cfg.price_max):
                return

        # ── 功能 11：排除處置股、注意股、限當沖股 ────────────────
        if cfg.f11_enabled:
            if info.is_disposal:
                return
            if info.is_attention:
                return
            if info.is_day_trade_restricted:
                return

        # ── 模擬漲停觸發 ──────────────────────────────────────────
        if not state.entry_blocked and state.candle_index < (cfg.candle_limit if cfg.f7_enabled else 99):
            if random.random() > 0.75:
                if state.limit_up_since is None:
                    state.limit_up_since = now
                    state.candle_index += 1
                    ask_qty = random.randint(5, 130)
                    self.on_log("INFO",
                        f"[{info.code} {info.name}] 漲停！"
                        f"第 {state.candle_index} 根，委賣 {ask_qty} 張")

        elif state.limit_up_since and random.random() > 0.85:
            state.limit_up_since = None  # 暫時跌出漲停

        # ── 取消委託邏輯（功能 6）────────────────────────────────
        if state.pending and cfg.f6_enabled:
            if state.last_1s_vol > cfg.volume_spike_cancel_threshold:
                self.on_log("WARN",
                    f"[{info.code}] 委託中！1秒量 {state.last_1s_vol} 張"
                    f" > {cfg.volume_spike_cancel_threshold} 張，取消委託")
                state.pending = False
                state.entry_blocked = True
                return

        # ── 出場邏輯（功能 4、5）────────────────────────────────
        if state.position_qty > 0:
            reason = None

            # 功能 4：模擬委買打開
            if cfg.f4_enabled and random.random() > 0.88:
                reason = "委買漲停，市場打開，市價出場"

            # 功能 5：1秒爆量
            if cfg.f5_enabled and reason is None:
                if state.last_1s_vol > cfg.volume_spike_sell_threshold:
                    reason = f"1秒量 {state.last_1s_vol} 張 > {cfg.volume_spike_sell_threshold} 張，爆量出場"

            if reason:
                self.on_log("WARN", f"[{info.code}] 出場觸發：{reason}")
                self._do_sell(state, info, reason)
            return

        # ── 進場邏輯 ──────────────────────────────────────────────
        if state.pending or state.entry_blocked or state.candle_index == 0:
            return
        if state.limit_up_since is None:
            return

        # 功能 12：開盤即漲停 且 當天已賣過 → 封鎖
        if cfg.f12_enabled and info.open_limit_up and state.sold_today:
            return

        # 功能 13：當天成交檔數上限
        if cfg.f13_enabled and self._daily_trade_count >= cfg.daily_max_trades:
            return

        # 功能 1：時間 + 委賣篩選
        if cfg.f1_enabled:
            now_time = datetime.now().time()
            cutoff = dtime(*map(int, cfg.entry_before_time.split(":")))
            if now_time >= cutoff:
                return
            ask_qty = random.randint(0, 180)
            if ask_qty >= cfg.ask_queue_threshold:
                return
        else:
            ask_qty = random.randint(0, 180)

        # 功能 7：只買第N根以內
        if cfg.f7_enabled and state.candle_index > cfg.candle_limit:
            return

        # 功能 10：委賣價 + 即時量
        if cfg.f10_enabled:
            if state.last_1s_vol < cfg.entry_volume_confirm:
                return

        # 機率觸發（模擬真實訊號稀缺性）
        if random.random() > 0.40:
            return

        qty = max(1, int(cfg.per_stock_amount / (info.limit_up * 1000)))
        state.pending = True
        self.on_log("TRADE",
            f"[{info.code}] 進場委託 {qty} 張 @ "
            f"{info.limit_up:,.0f}（委賣 {ask_qty} 張 < {cfg.ask_queue_threshold} 張，"
            f"第 {state.candle_index} 根）")

        # 模擬延遲成交
        code = info.code
        def fill():
            time.sleep(0.6 + random.random() * 1.2)
            with self._lock:
                if not self._running:
                    return
                st = self._states.get(code)
                if st and st.pending:
                    st.pending = False
                    st.position_qty = qty
                    self._daily_trade_count += 1   # 功能 13：累計成交檔數
                    self.on_log("INFO", f"[{code}] 成交 {qty} 張 @ {info.limit_up:,.0f}，"
                                        f"今日第 {self._daily_trade_count} 檔")
                    self.on_trade({
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "code": code,
                        "name": info.name,
                        "action": "BUY",
                        "price": info.limit_up,
                        "qty": qty,
                        "note": f"第 {st.candle_index} 根漲停",
                    })
        threading.Thread(target=fill, daemon=True).start()

    def _do_sell(self, state: StockState, info: StockInfo, note: str):
        qty = state.position_qty
        state.position_qty = 0
        state.entry_blocked = True
        state.sold_today = True   # 功能 12：標記當天已賣過
        self.on_trade({
            "time": datetime.now().strftime("%H:%M:%S"),
            "code": info.code,
            "name": info.name,
            "action": "SELL",
            "price": info.limit_up,
            "qty": qty,
            "note": note,
        })

    # ─────────────────────────────────────────
    #  狀態彙整（供 UI 輪詢）
    # ─────────────────────────────────────────

    def get_summary(self) -> List[dict]:
        with self._lock:
            result = []
            for code, s in self._states.items():
                result.append({
                    "code":    code,
                    "name":    s.info.name,
                    "market":  s.info.market,
                    "candle":  s.candle_index,
                    "qty":     s.position_qty,
                    "pending": s.pending,
                    "vol_1s":  s.last_1s_vol,
                    "blocked": s.entry_blocked,
                })
            return result
