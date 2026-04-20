"""
engine.py — 核心交易引擎
負責篩選漲停股、判斷進場條件、管理持倉與委託、觸發出場邏輯
"""
from __future__ import annotations
import logging
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, time as dtime
from typing import Callable, Dict, List, Optional

from config import TradingConfig
from broker import BrokerBase, Quote, Order

logger = logging.getLogger(__name__)


class StockState:
    """單一股票的狀態追蹤"""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.candle_index: int = 0          # 已出現的漲停K棒根數
        self.position_qty: int = 0          # 持倉張數
        self.pending_order: Optional[Order] = None  # 排隊中的委託
        self.filled_order: Optional[Order] = None   # 已成交的買單
        self.sell_order: Optional[Order] = None     # 賣出委託
        self.tick_volumes: deque = deque()  # (timestamp, volume) 近1秒tick
        self.last_1s_volume: int = 0        # 最近1秒成交量（張）
        self.entry_blocked: bool = False    # 已觸發過出場，不再進場
        self.limit_up_since: Optional[float] = None  # 首次漲停時間


class TradingEngine:

    def __init__(
        self,
        config: TradingConfig,
        broker: BrokerBase,
        on_log: Callable[[str], None] = None,
        on_trade: Callable[[dict], None] = None,
    ):
        self.config = config
        self.broker = broker
        self.on_log = on_log or (lambda msg: logger.info(msg))
        self.on_trade = on_trade or (lambda d: None)

        self._states: Dict[str, StockState] = {}
        self._lock = threading.Lock()
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None

    # ─────────────────────────────────────────
    #  啟動 / 停止
    # ─────────────────────────────────────────

    def start(self):
        self._running = True
        markets = self.config.get_markets()
        self.on_log(f"引擎啟動，監控市場：{', '.join(markets)}")
        self.broker.subscribe_limit_up_stocks(markets, self._on_quote)
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True
        )
        self._monitor_thread.start()

    def stop(self):
        self._running = False
        self.broker.logout()
        self.on_log("引擎已停止")

    # ─────────────────────────────────────────
    #  行情回調（每個 tick 呼叫）
    # ─────────────────────────────────────────

    def _on_quote(self, quote: Quote):
        with self._lock:
            sym = quote.symbol
            if sym not in self._states:
                self._states[sym] = StockState(sym)
            state = self._states[sym]

            # 更新1秒成交量
            now = time.time()
            state.tick_volumes.append((now, quote.volume_1s))
            while state.tick_volumes and now - state.tick_volumes[0][0] > 1.0:
                state.tick_volumes.popleft()
            state.last_1s_volume = sum(v for _, v in state.tick_volumes)

            # 判斷是否漲停
            is_limit_up = (quote.price >= quote.limit_up_price)

            # ── 更新 K 棒計數 ──────────────────────────────────────────────
            if is_limit_up and state.limit_up_since is None:
                state.limit_up_since = now
                state.candle_index += 1
                self.on_log(f"[{sym}] 漲停！第 {state.candle_index} 根")
            elif not is_limit_up and state.limit_up_since is not None:
                # 跌出漲停，準備計下一根
                state.limit_up_since = None

            # ── 出場邏輯（持倉）────────────────────────────────────────────
            if state.position_qty > 0:
                self._check_exit(state, quote)
                return

            # ── 取消委託邏輯（排隊中）──────────────────────────────────────
            if state.pending_order is not None:
                self._check_cancel(state, quote)
                return

            # ── 進場邏輯 ───────────────────────────────────────────────────
            if not state.entry_blocked:
                self._check_entry(state, quote)

    # ─────────────────────────────────────────
    #  進場條件檢查
    # ─────────────────────────────────────────

    def _check_entry(self, state: StockState, quote: Quote):
        cfg = self.config
        sym = quote.symbol

        # 功能 1：時間限制 + 委賣張數
        if cfg.f1_enabled:
            now_time = datetime.now().time()
            cutoff = dtime(*map(int, cfg.entry_before_time.split(":")))
            if now_time >= cutoff:
                return
            if quote.ask_price >= quote.limit_up_price:
                if quote.ask_qty >= cfg.ask_queue_threshold:
                    return

        # 功能 7：只買第 N 根以內
        if cfg.f7_enabled:
            if state.candle_index == 0 or state.candle_index > cfg.candle_limit:
                return

        # 功能 8：當天成交量門檻
        if cfg.f8_enabled:
            if quote.volume_1s < cfg.daily_volume_min:
                return

        # 功能 9：股價區間
        if cfg.f9_enabled:
            if not (cfg.price_min <= quote.price <= cfg.price_max):
                return

        # 功能 10：委賣價 + 即時量雙重確認
        if cfg.f10_enabled:
            ask_limit = quote.limit_up_price * cfg.ask_price_ratio
            if quote.ask_price > ask_limit:
                return
            if state.last_1s_volume < cfg.entry_volume_confirm:
                return

        # 必須是漲停狀態
        if quote.price < quote.limit_up_price:
            return

        # 計算買進張數
        if quote.limit_up_price <= 0:
            return
        qty = max(1, int(cfg.per_stock_amount / (quote.limit_up_price * 1000)))

        self.on_log(
            f"[{sym}] 進場！漲停價={quote.limit_up_price}，"
            f"委賣={quote.ask_qty}張，第{state.candle_index}根，買{qty}張"
        )
        try:
            order = self.broker.place_market_buy(sym, qty)
            state.pending_order = order
            self.on_trade({
                "time": datetime.now().strftime("%H:%M:%S"),
                "symbol": sym,
                "action": "BUY",
                "price": quote.limit_up_price,
                "qty": qty,
                "note": f"第{state.candle_index}根漲停",
            })
        except Exception as e:
            self.on_log(f"[{sym}] 下單失敗：{e}")

    # ─────────────────────────────────────────
    #  出場條件檢查（已持倉）
    # ─────────────────────────────────────────

    def _check_exit(self, state: StockState, quote: Quote):
        cfg = self.config
        sym = quote.symbol

        if state.sell_order:
            return  # 已有賣單

        reason = None

        # 功能 4：委買漲停 → 市價賣
        if cfg.f4_enabled:
            if quote.bid_price >= quote.limit_up_price:
                reason = "委買漲停，市價出場"

        # 功能 5：1秒成交超過門檻 → 賣
        if cfg.f5_enabled and reason is None:
            if state.last_1s_volume > cfg.volume_spike_sell_threshold:
                reason = f"1秒量{state.last_1s_volume}張>{cfg.volume_spike_sell_threshold}張，出場"

        if reason:
            self.on_log(f"[{sym}] 出場觸發：{reason}")
            try:
                order = self.broker.place_market_sell(sym, state.position_qty)
                state.sell_order = order
                state.entry_blocked = True
                self.on_trade({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "symbol": sym,
                    "action": "SELL",
                    "price": quote.price,
                    "qty": state.position_qty,
                    "note": reason,
                })
            except Exception as e:
                self.on_log(f"[{sym}] 賣出失敗：{e}")

    # ─────────────────────────────────────────
    #  取消委託（排隊中）
    # ─────────────────────────────────────────

    def _check_cancel(self, state: StockState, quote: Quote):
        cfg = self.config
        sym = quote.symbol

        if not cfg.f6_enabled:
            return

        if state.last_1s_volume > cfg.volume_spike_cancel_threshold:
            self.on_log(
                f"[{sym}] 取消委託！1秒量{state.last_1s_volume}張"
                f">{cfg.volume_spike_cancel_threshold}張"
            )
            try:
                self.broker.cancel_order(state.pending_order.order_id)
                state.pending_order = None
                state.entry_blocked = True
            except Exception as e:
                self.on_log(f"[{sym}] 取消委託失敗：{e}")

    # ─────────────────────────────────────────
    #  持倉同步（由成交回報更新 position_qty）
    # ─────────────────────────────────────────

    def on_order_filled(self, symbol: str, qty: int, price: float):
        with self._lock:
            if symbol not in self._states:
                self._states[symbol] = StockState(symbol)
            state = self._states[symbol]
            state.position_qty += qty
            state.pending_order = None
            self.on_log(f"[{symbol}] 成交 {qty} 張 @ {price}")

    def on_order_cancelled(self, symbol: str):
        with self._lock:
            if symbol in self._states:
                self._states[symbol].pending_order = None

    # ─────────────────────────────────────────
    #  監控執行緒（定期清理 + 狀態整理）
    # ─────────────────────────────────────────

    def _monitor_loop(self):
        while self._running:
            time.sleep(1)
            with self._lock:
                for sym, state in list(self._states.items()):
                    # 清理1秒外的 tick
                    now = time.time()
                    while state.tick_volumes and now - state.tick_volumes[0][0] > 1.0:
                        state.tick_volumes.popleft()

    def get_summary(self) -> List[dict]:
        """回傳目前所有股票狀態（供 UI 顯示）"""
        with self._lock:
            result = []
            for sym, s in self._states.items():
                result.append({
                    "symbol": sym,
                    "candle": s.candle_index,
                    "qty": s.position_qty,
                    "pending": s.pending_order is not None,
                    "vol_1s": s.last_1s_volume,
                    "blocked": s.entry_blocked,
                })
            return result
