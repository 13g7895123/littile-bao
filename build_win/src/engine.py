"""
engine.py — 打板策略引擎

Milestone 2 起：1 秒成交量、漲停判斷、委賣張數均改由 RealtimeFeed 推播驅動，
不再使用 random.* 模擬市場資料。

對於進場 / 出場下單仍維持模擬延遲填單（待 Milestone 4/5 改為真實券商回報）。
"""
from __future__ import annotations
import random
import threading
import time
from collections import deque
from datetime import date, datetime, time as dtime
from decimal import Decimal
from typing import Callable, Dict, List, Optional

from config import (
    LOCKED_LIMIT_UP_DETECTION_MODE,
    LOCKED_STARTUP_LIMIT_UP_DETECTION_MODE,
    TradingConfig,
)
from limitup_detection import (
    DEFAULT_LIMIT_UP_DETECTION_MODE,
    LIMIT_UP_DETECTION_MODES,
    evaluate_limit_up_state,
    resolve_limit_up_mode,
)

try:
    from broker import (
        BookEvent, FillEvent, OrderEvent, OrderSide, RealtimeFeed, SymbolMeta, TickEvent,
        realized_pnl, tick_size,
    )
    from broker.orders import OrderRequest
except ImportError:  # 套件初始化失敗時退回為 None，避免阻擋既有測試
    BookEvent = SymbolMeta = TickEvent = RealtimeFeed = FillEvent = None  # type: ignore
    OrderEvent = OrderSide = OrderRequest = None  # type: ignore
    realized_pnl = tick_size = None  # type: ignore


# ─────────────────────────────────────────────────────────────
#  資料結構
# ─────────────────────────────────────────────────────────────

class StockInfo:
    def __init__(self, code: str, name: str, limit_up: float, market: str,
                 is_disposal: bool = False, is_attention: bool = False,
                 is_day_trade_restricted: bool = False,
                 open_limit_up: bool = False,
                 prev_close: float = 0.0,
                 prior_limit_up_streak: Optional[int] = 0):
        self.code = code
        self.name = name
        self.limit_up = limit_up
        self.market = market
        self.is_disposal = is_disposal                       # 處置股
        self.is_attention = is_attention                     # 注意股
        self.is_day_trade_restricted = is_day_trade_restricted  # 限當沖股
        self.open_limit_up = open_limit_up                   # 開盤即漲停
        # 昨收價：未提供時以 limit_up / 1.1 推估，方便 Mock 行情運作
        self.prev_close = prev_close or round(limit_up / 1.1, 2)
        # 昨日起往前連續收漲停天數；今天首次觸及漲停後 candle_index = 此值 + 1
        self.prior_limit_up_streak = (
            None if prior_limit_up_streak is None
            else max(0, int(prior_limit_up_streak))
        )


class StockState:
    def __init__(self, info: StockInfo):
        self.info = info
        self.candle_index: int = 0
        self.position_qty: int = 0
        self.pending: bool = False
        self.pending_side: str = ""
        self.pending_order_id: str = ""
        self.entry_blocked: bool = False
        self.entry_blocked_reason: str = ""
        # 進場「最近一次被略過」的原因（軟性過濾；不會像 entry_blocked 那樣永久封鎖）
        # 由 _skip_entry() 寫入，於 GUI 動作欄顯示，協助使用者了解為何尚未進場
        self.last_skip_reason: str = ""
        self.last_1s_vol: int = 0
        self.tick_vols: deque = deque()   # (timestamp, vol)
        self.limit_up_since: Optional[float] = None
        self.limit_up_candidate_since: Optional[float] = None
        self.today_limit_up_counted: bool = False
        self.sold_today: bool = False     # 功能 12：當天已賣過
        # ── Milestone 2：行情驅動欄位 ───────────────────────
        self.last_price: Optional[Decimal] = None
        self.ask0_price: Optional[Decimal] = None
        self.ask0_volume: int = 0
        self.bid0_price: Optional[Decimal] = None
        self.bid0_volume: int = 0
        self.effective_bid0_price: Optional[Decimal] = None
        self.effective_bid0_volume: int = 0
        self.ask_qty_at_limit: int = 0    # 漲停價委賣張數（不為漲停時 = 0）
        self.is_at_limit_up: bool = False
        self.touched_limit_up_today: bool = False
        self.limit_up_consumed_qty: int = 0
        self.trade_bid: Optional[Decimal] = None
        self.trade_ask: Optional[Decimal] = None
        self.trade_is_limit_up_price: Optional[bool] = None
        self.trade_is_limit_up_bid: Optional[bool] = None
        self.trade_is_limit_up_ask: Optional[bool] = None
        self.last_market_event_time: Optional[datetime] = None
        self.last_recv_time: Optional[datetime] = None
        self.first_limit_up_candidate_event_time: Optional[datetime] = None
        self.first_limit_up_confirmed_event_time: Optional[datetime] = None
        self.has_ask_levels: bool = False
        self.has_bid_levels: bool = False
        self.limit_up_signal_states: Dict[str, bool] = {}
        self.limit_up_candidate_states: Dict[str, bool] = {}
        self.effective_lock_segment_active: bool = False
        self.effective_lock_segment_tick_confirmed: bool = False
        self.active_limit_up_mode: str = DEFAULT_LIMIT_UP_DETECTION_MODE
        self.special_check_completed: bool = False
        self.initial_limit_up_checked: bool = False
        self.startup_limitup_blocked: bool = False
        self.f4_first_trigger_at: Optional[float] = None
        self.f5_first_trigger_at: Optional[float] = None
        self.f4_trigger_snapshot: Optional[dict] = None
        self.f5_trigger_snapshot: Optional[dict] = None
        self.last_strategy_decision_times: Dict[str, datetime] = {}
        self.last_order_submit_times: Dict[str, datetime] = {}
        # ── Milestone 4：損益追蹤 ────────────────────
        self.entry_price: Optional[Decimal] = None  # 進場成交均價


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
#  時鐘偏移監測
# ─────────────────────────────────────────────────────────────


class ClockSkewMonitor:
    """累計 (api_time, recv_time) 樣本，提供中位數/最大值統計。

    視窗為「最近 60 秒」的滑動視窗。skew = recv_time - api_time，
    代表「本地收到時間 - 市場時間戳」，含網路與本地時鐘偏移成分。
    持續性高偏移代表本地時鐘可能異常。
    """

    WINDOW_SEC = 60.0
    MAX_SAMPLES = 600

    def __init__(self) -> None:
        self._samples: deque = deque(maxlen=self.MAX_SAMPLES)
        self._lock = threading.Lock()

    def add_sample(self, api_time: Optional[datetime], recv_time: Optional[datetime]) -> None:
        if api_time is None or recv_time is None:
            return
        try:
            skew_ms = (recv_time - api_time).total_seconds() * 1000.0
        except Exception:
            return
        recv_ts = recv_time.timestamp()
        with self._lock:
            self._samples.append((recv_ts, skew_ms))

    def snapshot(self) -> Optional[dict]:
        cutoff = time.time() - self.WINDOW_SEC
        with self._lock:
            while self._samples and self._samples[0][0] < cutoff:
                self._samples.popleft()
            if not self._samples:
                return None
            values = sorted(s for _, s in self._samples)
            count = len(values)
            median = values[count // 2] if count % 2 == 1 else (values[count // 2 - 1] + values[count // 2]) / 2.0
            return {
                "median_ms": median,
                "max_ms": max(values),
                "min_ms": min(values),
                "sample_count": count,
                "window_sec": self.WINDOW_SEC,
            }


# ─────────────────────────────────────────────────────────────
#  引擎
# ─────────────────────────────────────────────────────────────

class TradingEngine:
    AUTO_TRADE_CUTOFF_TIME = dtime(13, 25)
    CLOCK_SKEW_REPORT_INTERVAL_SEC = 10.0
    CLOCK_SKEW_WARN_MS = 1000.0
    CLOCK_SKEW_ERROR_MS = 3000.0
    CLOCK_SKEW_INFO_MS = 200.0
    CLOCK_SKEW_INFO_LOG_INTERVAL_SEC = 60.0

    def __init__(
        self,
        config: TradingConfig,
        on_log: Callable[[str, str], None],   # (level, msg)
        on_trade: Callable[[dict], None],
        on_status: Callable[[List[dict]], None],
        on_strategy_event: Optional[Callable[[dict], None]] = None,
        on_decision_event: Optional[Callable[[dict], None]] = None,
        on_clock_skew: Optional[Callable[[dict], None]] = None,
        feed: Optional["RealtimeFeed"] = None,
        symbol_infos: Optional[Dict[str, "object"]] = None,
        broker: Optional[object] = None,
    ):
        self.config = config
        self.on_log = on_log
        self.on_trade = on_trade
        self.on_status = on_status
        self.on_strategy_event = on_strategy_event
        self.on_decision_event = on_decision_event
        self.on_clock_skew = on_clock_skew
        self.feed = feed
        self.broker = broker

        # ── 時鐘偏移監測 ───────────────────────────────────
        self._clock_skew_monitor = ClockSkewMonitor()
        self._clock_skew_last_report_ts: float = 0.0
        self._clock_skew_last_info_log_ts: float = 0.0
        self._clock_skew_last_level: str = ""

        self._states: Dict[str, StockState] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._started_at: Optional[datetime] = None
        self._daily_trade_count: int = 0   # 功能 13：當天已成交檔數
        self._daily_trade_codes: set = set()  # 已成交過的股票代號集合（同股票只算一檔）
        self._today_realized_pnl: Decimal = Decimal("0")  # M4：當日已實現損益
        self._trading_date: date = date.today()  # 跨日重置使用
        self._processed_fill_keys: set = set()   # 避免同一筆成交被重複處理
        self._broker_callbacks_registered = False
        self._limit_up_mode: str = resolve_limit_up_mode(
            getattr(config, "limit_up_detection_mode", DEFAULT_LIMIT_UP_DETECTION_MODE)
        )
        self._startup_limit_up_mode: str = resolve_limit_up_mode(
            getattr(
                config,
                "startup_limit_up_detection_mode",
                LOCKED_STARTUP_LIMIT_UP_DETECTION_MODE,
            )
        )
        # ── 診斷計數器 ─────────────────────────────────────
        self._tick_recv_count: int = 0   # engine 收到的 tick 總數
        self._book_recv_count: int = 0   # engine 收到的 book 總數
        self._tick_miss_count: int = 0   # tick.code 不在 _states 的次數

        # ── 篩選市場 ─────────────────────────────────────────
        markets = config.get_markets()

        if symbol_infos is not None:
            # Milestone 3：使用 broker.load_symbol_info() 提供的真實基本資料
            for code, si in symbol_infos.items():
                if si.market not in markets:
                    continue
                state = StockState(self._stock_info_from_symbol_info(si))
                # SymbolInfo is loaded and, for Fubon runtime, batch-confirmed before
                # subscription. Avoid a per-stock synchronous broker lookup on the
                # first hot-path entry trigger.
                state.special_check_completed = True
                state.active_limit_up_mode = self._limit_up_mode
                self._states[code] = state
        else:
            # 退回 MOCK_STOCKS 預設清單
            for s in MOCK_STOCKS:
                if s.market in markets:
                    self._states[s.code] = StockState(s)
                    self._states[s.code].active_limit_up_mode = self._limit_up_mode

    @staticmethod
    def _stock_info_from_symbol_info(si: object) -> StockInfo:
        # limit_up_price（SymbolInfo）或 limit_up（StockInfo）都接受
        limit_up = getattr(si, "limit_up_price", None) or getattr(si, "limit_up", None)
        return StockInfo(
            code=si.code,
            name=si.name,
            limit_up=float(limit_up),
            market=si.market,
            is_disposal=getattr(si, "is_disposal", False),
            is_attention=getattr(si, "is_attention", False),
            is_day_trade_restricted=getattr(si, "is_day_trade_restricted", False),
            open_limit_up=getattr(si, "open_limit_up", False),
            prev_close=float(si.prev_close),
            prior_limit_up_streak=getattr(si, "prior_limit_up_streak", None),
        )

    # ─────────────────────────────────────────
    #  啟動 / 停止
    # ─────────────────────────────────────────

    def start(self):
        self._running = True
        self._started_at = self._current_datetime()
        self.on_log("INFO", f"策略啟用時間：{self._started_at.strftime('%Y-%m-%d %H:%M:%S')}")
        self.on_log("INFO", f"引擎啟動，監控市場：{', '.join(self.config.get_markets())}")
        self.on_log("INFO", f"監控 {len(self._states)} 支股票")
        active = self._active_features()
        self.on_log("INFO", f"已啟用篩選功能：{active}")
        self.on_log(
            "INFO",
            f"啟動即鎖判斷模式：{self._startup_limit_up_mode} "
            f"（{LIMIT_UP_DETECTION_MODES.get(self._startup_limit_up_mode, '')}）",
        )
        self.on_log(
            "INFO",
            f"鎖漲停判斷模式：{self._limit_up_mode} "
            f"（{LIMIT_UP_DETECTION_MODES.get(self._limit_up_mode, '')}）",
        )

        # ── Milestone 2：訂閱即時行情 ─────────────────────
        if self.feed is not None and SymbolMeta is not None:
            try:
                meta = {
                    code: SymbolMeta(
                        code=code,
                        limit_up=Decimal(str(s.info.limit_up)),
                        prev_close=Decimal(str(s.info.prev_close)),
                        open_limit_up=s.info.open_limit_up,
                    )
                    for code, s in self._states.items()
                }
                # 注入 log callback，讓 FubonRealtimeFeed 的診斷訊息進 GUI log
                if hasattr(self.feed, "set_log_callback"):
                    self.feed.set_log_callback(self.on_log)
                self.feed.on_tick(self._on_tick)
                self.feed.on_book(self._on_book)
                self.feed.subscribe(list(self._states.keys()), meta)
                self.feed.start()
                self.on_log("INFO", f"即時行情已訂閱（{len(meta)} 檔）")
            except Exception as e:  # noqa: BLE001
                self.on_log("ERROR", f"行情訂閱失敗：{e}")
        else:
            self.on_log("WARN", "未提供即時行情來源，將以靜態資料運作")

        # ── Milestone 5：訂閱券商委託 / 成交回報 ─────────
        if self.broker is not None:
            try:
                self._attach_broker_callbacks()
            except Exception as e:  # noqa: BLE001
                self.on_log("WARN", f"訂閱券商回報失敗：{e}")

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def update_limit_up_mode(self, mode: str) -> str:
        resolved = resolve_limit_up_mode(LOCKED_LIMIT_UP_DETECTION_MODE)
        with self._lock:
            self._limit_up_mode = resolved
            self.config.limit_up_detection_mode = resolved
            now = time.time()
            for state in self._states.values():
                state.active_limit_up_mode = resolved
                self._refresh_limit_up_state(state, source="mode_apply", now=now)
        self.on_log(
            "INFO",
            f"鎖漲停判斷模式已切換為：{resolved} "
            f"（{LIMIT_UP_DETECTION_MODES.get(resolved, '')}）",
        )
        return resolved

    def stop(self):
        self._running = False
        if self.feed is not None:
            try:
                self.feed.stop()
            except Exception as e:  # noqa: BLE001
                self.on_log("WARN", f"停止行情訂閱時發生錯誤：{e}")
        try:
            self._detach_broker_callbacks()
        except Exception as e:  # noqa: BLE001
            self.on_log("WARN", f"解除券商回報訂閱時發生錯誤：{e}")
        self.on_log("INFO", "引擎已停止，登出完成")

    def _attach_broker_callbacks(self) -> None:
        if self.broker is None or self._broker_callbacks_registered:
            return
        if hasattr(self.broker, "on_filled"):
            self.broker.on_filled(self._on_broker_fill)
        if hasattr(self.broker, "on_order"):
            self.broker.on_order(self._on_broker_order)
        self._broker_callbacks_registered = True
        self.on_log("INFO", "已訂閱券商委託 / 成交回報")

    def _detach_broker_callbacks(self) -> None:
        if self.broker is None or not self._broker_callbacks_registered:
            return
        if hasattr(self.broker, "off_filled"):
            self.broker.off_filled(self._on_broker_fill)
        if hasattr(self.broker, "off_order"):
            self.broker.off_order(self._on_broker_order)
        self._broker_callbacks_registered = False

    # ─────────────────────────────────────────
    #  熱替換訂閱清單（盤中改價格區間用）
    # ─────────────────────────────────────────

    def replace_universe(self, new_symbol_infos: Dict[str, object]) -> dict:
        """
        熱替換 _states 內容，呼叫者需自行管控 feed.stop() / 重新訂閱 / feed.start()。

        保留規則（即使不在新清單也不會被移除）：
          - 有持倉（position_qty > 0）
          - 有委託在外（pending）
          - 已有 K 線進場紀錄（candle_index > 0）

        回傳 dict: {"added", "removed", "kept_in_new", "kept_protected"}
        """
        markets = set(self.config.get_markets())
        new_codes: set = set()
        if new_symbol_infos:
            for code, si in new_symbol_infos.items():
                if getattr(si, "market", None) in markets:
                    new_codes.add(code)

        with self._lock:
            old_codes = set(self._states.keys())

            protected = {
                code for code, st in self._states.items()
                if st.position_qty > 0 or st.pending or st.candle_index > 0
            }

            removed = (old_codes - new_codes) - protected
            added = new_codes - old_codes
            kept_in_new = old_codes & new_codes
            kept_protected = (old_codes - new_codes) & protected

            for code in removed:
                self._states.pop(code, None)

            for code in added:
                si = new_symbol_infos[code]
                state = StockState(self._stock_info_from_symbol_info(si))
                state.special_check_completed = True
                state.active_limit_up_mode = self._limit_up_mode
                self._states[code] = state

            for code in kept_in_new:
                self._states[code].info = self._stock_info_from_symbol_info(
                    new_symbol_infos[code])
                self._states[code].special_check_completed = True

        return {
            "added": sorted(added),
            "removed": sorted(removed),
            "kept_in_new": sorted(kept_in_new),
            "kept_protected": sorted(kept_protected),
        }

    def resubscribe_feed(self) -> None:
        """以目前 _states 重新訂閱 feed（呼叫前應確保 feed 已 stop）。"""
        if self.feed is None or SymbolMeta is None:
            return
        meta = {
            code: SymbolMeta(
                code=code,
                limit_up=Decimal(str(s.info.limit_up)),
                prev_close=Decimal(str(s.info.prev_close)),
                open_limit_up=s.info.open_limit_up,
            )
            for code, s in self._states.items()
        }
        if hasattr(self.feed, "set_log_callback"):
            self.feed.set_log_callback(self.on_log)
        self.feed.on_tick(self._on_tick)
        self.feed.on_book(self._on_book)
        self.feed.subscribe(list(self._states.keys()), meta)
        self.feed.start()
        self.on_log("INFO", f"即時行情已重新訂閱（{len(meta)} 檔）")

    def _active_features(self) -> str:
        cfg = self.config
        flags = {
            "①": cfg.f1_enabled,  "④": cfg.f4_enabled,  "⑤": cfg.f5_enabled,
            "⑥": cfg.f6_enabled,  "⑦": cfg.f7_enabled,  "⑧": cfg.f8_enabled,
            "⑨": cfg.f9_enabled,  "⑩": cfg.f10_enabled,
            "⑪": cfg.f11_enabled, "⑫": cfg.f12_enabled, "⑬": cfg.f13_enabled,
            "消化量": getattr(cfg, "f_consume_enabled", False),
        }
        return " ".join(k for k, v in flags.items() if v) or "（無）"

    # ─────────────────────────────────────────
    #  行情事件處理（Milestone 2）
    # ─────────────────────────────────────────

    def _on_tick(self, ev) -> None:
        """RealtimeFeed 每筆 tick 推送進來。"""
        self._tick_recv_count += 1
        n = self._tick_recv_count
        with self._lock:
            state = self._states.get(ev.code)
            if state is None:
                self._tick_miss_count += 1
                if self._tick_miss_count <= 3 or self._tick_miss_count % 100 == 0:
                    known_sample = list(self._states.keys())[:5]
                    self.on_log(
                        "WARN",
                        f"[Engine._on_tick] code={ev.code!r} 不在監控清單（共誤 {self._tick_miss_count} 次）"
                        f"，監控清單前5支={known_sample}"
                    )
                return
            if n == 1:
                self.on_log("INFO",
                    f"[Engine] 第 1 筆 tick 已進入引擎！code={ev.code} price={ev.price} vol={ev.volume}")
            elif n % 1000 == 0:
                self.on_log("DEBUG",
                    f"[Engine] tick 累計 {n} 筆，最新={ev.code} {ev.price}")

            # ── 防呆：忽略 price <= 0 或 vol <= 0 的無效 tick（盤前試撮 / 欄位缺漏）──
            try:
                price_zero = ev.price is None or Decimal(str(ev.price)) <= 0
            except Exception:
                price_zero = True
            if price_zero:
                # 不更新 last_price、不放進 1 秒量視窗，但仍記錄以利除錯
                self._tick_invalid_count = getattr(self, "_tick_invalid_count", 0) + 1
                if self._tick_invalid_count <= 3 or self._tick_invalid_count % 500 == 0:
                    self.on_log(
                        "WARN",
                        f"[Engine._on_tick] 忽略無效 tick：code={ev.code} price={ev.price} "
                        f"vol={ev.volume}（共 {self._tick_invalid_count} 筆）"
                    )
                return

            if bool(getattr(ev, "is_backfill", False)):
                self._tick_backfill_count = getattr(self, "_tick_backfill_count", 0) + 1
                if self._tick_backfill_count <= 5 or self._tick_backfill_count % 100 == 0:
                    self.on_log(
                        "INFO",
                        f"[Engine._on_tick] 忽略 backfill tick：code={ev.code} price={ev.price} "
                        f"vol={ev.volume} event_time={getattr(ev, 'time', None)} "
                        f"recv_time={getattr(ev, 'recv_time', None)}（共 {self._tick_backfill_count} 筆）"
                    )
                return

            now = time.time()
            # 1 秒滑動視窗
            state.tick_vols.append((now, int(ev.volume)))
            while state.tick_vols and now - state.tick_vols[0][0] > 1.0:
                state.tick_vols.popleft()
            state.last_1s_vol = sum(v for _, v in state.tick_vols)
            state.last_price = ev.price
            state.trade_bid = getattr(ev, "bid", None)
            state.trade_ask = getattr(ev, "ask", None)
            state.trade_is_limit_up_price = getattr(ev, "is_limit_up_price", None)
            state.trade_is_limit_up_bid = getattr(ev, "is_limit_up_bid", None)
            state.trade_is_limit_up_ask = getattr(ev, "is_limit_up_ask", None)
            state.last_market_event_time = getattr(ev, "time", None)
            state.last_recv_time = getattr(ev, "recv_time", None)
            self._clock_skew_monitor.add_sample(
                getattr(ev, "api_time", None) or getattr(ev, "time", None),
                state.last_recv_time,
            )

            # 漲停判斷：成交價 == 漲停價
            limit_up = Decimal(str(state.info.limit_up))
            if ev.price >= limit_up:
                state.limit_up_consumed_qty += int(ev.volume)
            self._refresh_limit_up_state(state, source="tick", now=now, event_time=ev.time)
            if state.position_qty > 0 and not state.pending:
                self._record_sell_trigger_candidates(
                    state,
                    self._event_time_to_ts(ev.time, now),
                )
            self._evaluate_realtime_state(state, now)

    def _on_book(self, ev) -> None:
        """RealtimeFeed 五檔推送。"""
        with self._lock:
            state = self._states.get(ev.code)
            if state is None:
                return
            if bool(getattr(ev, "is_backfill", False)):
                self._book_backfill_count = getattr(self, "_book_backfill_count", 0) + 1
                if self._book_backfill_count <= 5 or self._book_backfill_count % 100 == 0:
                    self.on_log(
                        "INFO",
                        f"[Engine._on_book] 忽略 backfill book：code={ev.code} "
                        f"event_time={getattr(ev, 'time', None)} recv_time={getattr(ev, 'recv_time', None)} "
                        f"（共 {self._book_backfill_count} 筆）"
                    )
                return
            if ev.ask:
                state.ask0_price = ev.ask[0].price
                state.ask0_volume = int(ev.ask[0].volume)
            else:
                state.ask0_price = None
                state.ask0_volume = 0
            state.has_ask_levels = bool(ev.ask)
            if ev.bid:
                state.bid0_price = ev.bid[0].price
                state.bid0_volume = int(ev.bid[0].volume)
            else:
                state.bid0_price = None
                state.bid0_volume = 0
            state.has_bid_levels = bool(ev.bid)
            effective_bid = next(
                (
                    level for level in (ev.bid or [])
                    if level is not None
                    and level.price is not None
                    and Decimal(str(level.price)) > 0
                ),
                None,
            )
            if effective_bid is not None:
                state.effective_bid0_price = effective_bid.price
                state.effective_bid0_volume = int(effective_bid.volume)
            else:
                state.effective_bid0_price = None
                state.effective_bid0_volume = 0
            state.last_market_event_time = getattr(ev, "time", None)
            state.last_recv_time = getattr(ev, "recv_time", None)
            self._clock_skew_monitor.add_sample(
                getattr(ev, "api_time", None) or getattr(ev, "time", None),
                state.last_recv_time,
            )
            now = time.time()
            self._refresh_limit_up_state(state, source="book", now=now, event_time=ev.time)
            if state.position_qty > 0 and not state.pending:
                self._record_sell_trigger_candidates(
                    state,
                    self._event_time_to_ts(ev.time, now),
                )
            self._evaluate_realtime_state(state, now)

    def _evaluate_realtime_state(self, state: StockState, now: float) -> None:
        """收到單檔即時事件後，立即重跑該檔策略判斷，避免額外等待 1 秒輪詢。"""
        if not self._running:
            return
        self._tick(state, now)

    def _refresh_limit_up_state(self, state: StockState, *, source: str, now: float, event_time=None) -> None:
        was_at_limit_up = bool(state.is_at_limit_up)
        was_candidate = bool(state.limit_up_candidate_since is not None)
        decision = evaluate_limit_up_state(
            limit_up=Decimal(str(state.info.limit_up)),
            ask0_price=state.ask0_price,
            ask0_volume=state.ask0_volume,
            bid0_price=state.bid0_price,
            bid0_volume=state.bid0_volume,
            last_price=state.last_price,
            trade_bid=state.trade_bid,
            trade_ask=state.trade_ask,
            effective_bid0_price=state.effective_bid0_price,
            effective_bid0_volume=state.effective_bid0_volume,
            has_ask_levels=state.has_ask_levels,
            has_bid_levels=state.has_bid_levels,
            is_limit_up_price=state.trade_is_limit_up_price,
            is_limit_up_bid=state.trade_is_limit_up_bid,
            is_limit_up_ask=state.trade_is_limit_up_ask,
        )
        state.ask_qty_at_limit = int(decision["ask_qty_at_limit"])
        state.limit_up_signal_states = dict(decision["signals"])
        state.limit_up_candidate_states = dict(decision["candidates"])
        effective_lock_candidate = bool(
            decision["candidates"].get("strict_lock_with_effective_bid", False)
        )
        if not effective_lock_candidate:
            state.effective_lock_segment_active = False
            state.effective_lock_segment_tick_confirmed = False
        else:
            if not state.effective_lock_segment_active:
                # Do not let a tick flag from before this book-lock segment confirm it.
                state.effective_lock_segment_active = True
                state.effective_lock_segment_tick_confirmed = False
            if (
                source == "tick"
                and decision["signals"].get("trade_flag_price")
                and decision["signals"].get("trade_flag_bid")
            ):
                state.effective_lock_segment_tick_confirmed = True
        state.limit_up_candidate_states["strict_lock_with_effective_bid_tick_confirmed"] = (
            effective_lock_candidate and state.effective_lock_segment_tick_confirmed
        )
        mode = state.active_limit_up_mode or self._limit_up_mode
        sealed = bool(state.limit_up_candidate_states.get(mode, False))
        startup_mode = self._startup_limit_up_mode or LOCKED_STARTUP_LIMIT_UP_DETECTION_MODE
        startup_sealed = bool(state.limit_up_candidate_states.get(startup_mode, False))
        candidate_sealed = bool(
            decision["signals"].get("last_at_limit")
            or decision["signals"].get("trade_flag_price")
            or (
                decision["signals"].get("bid_at_limit")
                and decision["signals"].get("bid_qty_positive")
            )
        )

        if candidate_sealed:
            if state.limit_up_candidate_since is None:
                state.limit_up_candidate_since = now
            if state.first_limit_up_candidate_event_time is None and isinstance(event_time, datetime):
                state.first_limit_up_candidate_event_time = event_time
        else:
            state.limit_up_candidate_since = None

        if self._started_at is not None and not state.initial_limit_up_checked:
            # 啟動即鎖判斷至少等到收到成交價，再用當下整合過的 book/tick 狀態判斷。
            # 這樣舊版 startup 規則可以利用 tick 旗標，避免第一筆 book 就過早定案。
            startup_ready = state.last_price is not None
            if startup_ready:
                state.initial_limit_up_checked = True
                if startup_sealed:
                    state.is_at_limit_up = True
                    state.startup_limitup_blocked = True
                    state.limit_up_since = None
                    if state.first_limit_up_confirmed_event_time is None and isinstance(event_time, datetime):
                        state.first_limit_up_confirmed_event_time = event_time
                    state.last_skip_reason = "程式啟用後已漲停"
                    self.on_log(
                        "INFO",
                        f"[{state.info.code} {state.info.name}] 啟用時已鎖漲停，"
                        f"先標記為「程式啟用後已漲停」，待撬開後再觀察重鎖進場"
                        f"（判斷={startup_mode}）",
                    )
                    self._log_limit_up_signal_change(
                        state,
                        source=source,
                        signals=decision["signals"],
                        event_time=event_time,
                    )
                    return
        elif self._started_at is None and not state.initial_limit_up_checked:
            state.initial_limit_up_checked = True

        if state.startup_limitup_blocked:
            if startup_sealed:
                state.is_at_limit_up = True
                state.limit_up_since = None
            else:
                state.startup_limitup_blocked = False
                state.last_skip_reason = ""
                state.is_at_limit_up = False
                self.on_log(
                    "INFO",
                    f"[{state.info.code} {state.info.name}] 啟用後既有漲停已撬開，恢復觀察重鎖進場",
                )

        if sealed:
            state.is_at_limit_up = True
            if state.first_limit_up_confirmed_event_time is None and isinstance(event_time, datetime):
                state.first_limit_up_confirmed_event_time = event_time
            if not state.startup_limitup_blocked:
                state.touched_limit_up_today = True
                self._mark_limit_up_touched(state, now)
        else:
            if state.is_at_limit_up and not state.startup_limitup_blocked:
                state.is_at_limit_up = False
                state.limit_up_since = None

        self._log_limit_up_signal_change(
            state,
            source=source,
            signals=decision["signals"],
            event_time=event_time,
        )
        if candidate_sealed and not was_candidate:
            self._emit_decision_event(
                "LIMIT_UP_CANDIDATE",
                state,
                "候選鎖板",
                f"{source}:candidate",
                {
                    "candidate_lock_time": event_time,
                    "candidate_mode": "last_or_trade_flag_price_or_bid_at_limit",
                    "active_mode": state.active_limit_up_mode,
                    "signals": decision["signals"],
                },
                event_time=event_time,
            )
        if (
            self._running
            and not was_at_limit_up
            and state.is_at_limit_up
            and not state.startup_limitup_blocked
        ):
            # 封板首次成立時立即補一次進場評估，避免只靠 1 秒輪詢漏掉短暫鎖板。
            self._evaluate_entry(state, now)

    def _log_limit_up_signal_change(self, state: StockState, *, source: str, signals: dict, event_time=None) -> None:
        prev = getattr(state, "_last_limit_signal_snapshot", None)
        snapshot = (
            bool(state.is_at_limit_up),
            int(state.ask_qty_at_limit),
            tuple(sorted(state.limit_up_candidate_states.items())),
        )
        if prev == snapshot:
            return
        state._last_limit_signal_snapshot = snapshot  # type: ignore[attr-defined]
        self._emit_decision_event(
            "LIMIT_UP",
            state,
            "鎖板中" if state.is_at_limit_up else "未鎖板",
            f"{source}:{state.active_limit_up_mode}",
            {
                "ask_qty": state.ask_qty_at_limit,
                "active_mode": state.active_limit_up_mode,
                "signals": signals,
                "candidates": dict(state.limit_up_candidate_states),
            },
            event_time=event_time,
        )

    def _mark_limit_up_touched(self, state: StockState, now: float) -> None:
        state.touched_limit_up_today = True
        if state.today_limit_up_counted:
            if state.limit_up_since is None:
                state.limit_up_since = now
            return

        prior_streak = state.info.prior_limit_up_streak
        base_streak = prior_streak if prior_streak is not None else 0
        state.candle_index = base_streak + 1
        state.today_limit_up_counted = True
        state.limit_up_since = now
        if prior_streak is None:
            self.on_log(
                "WARN",
                f"[{state.info.code} {state.info.name}] 缺少昨日前連續漲停日K資料，"
                f"暫以日K第 {state.candle_index} 根判斷",
            )
        self.on_log(
            "INFO",
            f"[{state.info.code} {state.info.name}] 漲停！"
            f"日K第 {state.candle_index} 根，委賣 {state.ask_qty_at_limit} 張，"
            f"判斷={state.active_limit_up_mode}",
        )

    def _loop(self):
        while self._running:
            now = time.time()
            with self._lock:
                self._maybe_daily_reset()
                for code, state in self._states.items():
                    self._tick(state, now)
            self.on_status(self.get_summary())
            self._maybe_report_clock_skew(now)
            time.sleep(1.0)

    def _maybe_report_clock_skew(self, now: float) -> None:
        if now - self._clock_skew_last_report_ts < self.CLOCK_SKEW_REPORT_INTERVAL_SEC:
            return
        self._clock_skew_last_report_ts = now
        snap = self._clock_skew_monitor.snapshot()
        if snap is None:
            return
        median_abs = abs(snap["median_ms"])
        if median_abs >= self.CLOCK_SKEW_ERROR_MS:
            level = "ERROR"
        elif median_abs >= self.CLOCK_SKEW_WARN_MS:
            level = "WARN"
        elif median_abs >= self.CLOCK_SKEW_INFO_MS:
            level = "INFO"
        else:
            level = ""
        snap["level"] = level
        if self.on_clock_skew is not None:
            try:
                self.on_clock_skew(snap)
            except Exception:  # noqa: BLE001
                pass
        if level in ("WARN", "ERROR"):
            self._log_clock_skew(level, snap)
        elif level == "INFO":
            if now - self._clock_skew_last_info_log_ts >= self.CLOCK_SKEW_INFO_LOG_INTERVAL_SEC:
                self._clock_skew_last_info_log_ts = now
                self._log_clock_skew(level, snap)
        self._clock_skew_last_level = level

    def _log_clock_skew(self, level: str, snap: dict) -> None:
        self.on_log(
            level,
            f"[時鐘偏移] 中位數 {snap['median_ms']:.0f}ms / 最大 {snap['max_ms']:.0f}ms "
            f"（{snap['sample_count']} 筆樣本，最近 {int(snap['window_sec'])} 秒）",
        )

    def _maybe_daily_reset(self) -> None:
        """日期變動時重置每日狀態，避免跨日卡單 / 誤賣。"""
        today = date.today()
        if today == self._trading_date:
            return
        self.on_log("INFO", f"偵測到日期變更 {self._trading_date} → {today}，重置每日狀態")
        for st in self._states.values():
            st.entry_blocked = False
            st.entry_blocked_reason = ""
            st.sold_today = False
            st.candle_index = 0
            st.limit_up_since = None
            st.limit_up_candidate_since = None
            st.today_limit_up_counted = False
            st.touched_limit_up_today = False
            st.limit_up_consumed_qty = 0
            st.special_check_completed = False
            st.initial_limit_up_checked = False
            st.startup_limitup_blocked = False
            st.first_limit_up_candidate_event_time = None
            st.first_limit_up_confirmed_event_time = None
            st.effective_lock_segment_active = False
            st.effective_lock_segment_tick_confirmed = False
            self._reset_sell_trigger_state(st)
            # 注意：position_qty 不清空，避免影響真實持倉同步
        self._daily_trade_count = 0
        self._daily_trade_codes.clear()
        self._processed_fill_keys.clear()
        self._today_realized_pnl = Decimal("0")
        self._trading_date = today

    def _tick(self, state: StockState, now: float):
        cfg = self.config
        info = state.info

        # 1 秒視窗自然衰減（即使沒有新 tick 也要清掉舊資料）
        while state.tick_vols and now - state.tick_vols[0][0] > 1.0:
            state.tick_vols.popleft()
        state.last_1s_vol = sum(v for _, v in state.tick_vols)

        # ── 功能 9：股價區間 ──────────────────────────────────────
        if cfg.f9_enabled:
            if not (cfg.price_min <= info.limit_up <= cfg.price_max):
                # 漲停價超出區間 → 軟性略過（不封鎖，讓使用者可即時改設定）
                self._skip_entry(
                    state,
                    f"F9:漲停價 {info.limit_up} 不在 {cfg.price_min}~{cfg.price_max}",
                    log=False,  # 訂閱清單一次就過濾掉，無須每秒寫 log
                )
                return

        # 功能 11 會在所有進場條件與資金確認通過後，於下單前最後確認。

        # ── 取消委託邏輯（功能 6）────────────────────────────────
        if state.pending and state.pending_side == "BUY" and cfg.f6_enabled:
            if state.last_1s_vol > cfg.volume_spike_cancel_threshold:
                self._log_strategy_trigger(
                    "CANCEL", state, "F6",
                    {
                        "last_1s_vol": state.last_1s_vol,
                        "threshold": cfg.volume_spike_cancel_threshold,
                    },
                )
                self.on_log("WARN",
                    f"[{info.code}] 委託中！1秒量 {state.last_1s_vol} 張"
                    f" > {cfg.volume_spike_cancel_threshold} 張，取消委託")
                cancel_ok = False
                if self.broker is not None and state.pending_order_id:
                    try:
                        cancel_ok = bool(self.broker.cancel_order(state.pending_order_id))
                    except Exception as e:  # noqa: BLE001
                        self.on_log("WARN", f"[{info.code}] 取消委託失敗：{e}")
                self._clear_pending_order_state(state)
                state.entry_blocked = True
                state.entry_blocked_reason = "爆量取消"
                return

        if self._is_after_auto_trade_cutoff():
            self._reset_sell_trigger_state(state)
            if state.position_qty <= 0:
                self._skip_entry(
                    state,
                    f"已過自動交易截止 {self.AUTO_TRADE_CUTOFF_TIME.strftime('%H:%M')}",
                    log=False,
                )
            return

        # ── 出場邏輯（功能 4、5）────────────────────────────────
        if state.position_qty > 0:
            # 若已有出場單在途（state.pending=True），跳過本次評估，避免重複下賣單
            # （否則 fill 未回前，下一個 tick 仍會觸發 F4/F5 再送一張）
            if state.pending:
                return
            self._record_sell_trigger_candidates(state, now)
            sell_plan = self._pick_sell_strategy(state)
            if sell_plan:
                self._log_strategy_trigger(
                    "SELL",
                    state,
                    sell_plan["strategy"],
                    sell_plan["details"],
                )
                self.on_log("WARN", f"[{info.code}] 出場觸發：{sell_plan['reason']}")
                self._do_sell(state, info, sell_plan["reason"])
            return

        self._reset_sell_trigger_state(state)
        self._evaluate_entry(state, now)

    def _evaluate_entry(self, state: StockState, now: float) -> None:
        # ── 進場邏輯 ──────────────────────────────────────────────
        cfg = self.config
        info = state.info
        if state.pending or state.entry_blocked or state.candle_index == 0:
            return
        if state.limit_up_since is None or not state.is_at_limit_up:
            return
        if state.startup_limitup_blocked:
            self._skip_entry(state, "程式啟用後已漲停", log=False)
            return

        # 功能 12：開盤即漲停 且 當天已賣過 → 封鎖
        if cfg.f12_enabled and info.open_limit_up and state.sold_today:
            self._skip_entry(state, "F12:開盤即漲停且當日已賣過")
            return

        # 開盤即漲停獨立開關：不論有無賣過，都可選擇不追
        if not getattr(cfg, "f_open_limitup_entry_enabled", True) and info.open_limit_up:
            self._skip_entry(state, "已關閉追開盤即漲停")
            return

        # 功能 13：當天成交檔數上限
        if cfg.f13_enabled and self._daily_trade_count >= cfg.daily_max_trades:
            self._skip_entry(
                state,
                f"F13:已達當日上限 {self._daily_trade_count}/{cfg.daily_max_trades}",
            )
            return

        # 功能 1：時間 + 委賣篩選（漲停價委賣張數）
        ask_qty = state.ask_qty_at_limit
        entry_strategy_ids: List[str] = []
        consume_enabled = bool(getattr(cfg, "f_consume_enabled", False))
        if consume_enabled:
            consume_threshold = int(getattr(cfg, "consume_qty_threshold", 0) or 0)
            if state.limit_up_consumed_qty < consume_threshold:
                self._skip_entry(
                    state,
                    f"消化量 {state.limit_up_consumed_qty} < {consume_threshold} 張",
                )
                return
            entry_strategy_ids.append("消化量")

        apply_f1 = cfg.f1_enabled and not (
            consume_enabled and bool(getattr(cfg, "consume_mutex_with_f1", True))
        )
        f1_lock_bypass = False
        if apply_f1:
            now_time = self._current_datetime().time()
            start_time = self._parse_config_time(getattr(cfg, "start_time", "09:00"), dtime(9, 0))
            cutoff = self._parse_config_time(cfg.entry_before_time, dtime(10, 0))
            market_close = dtime(13, 30)
            if cutoff > market_close:
                cutoff = market_close
            if now_time < start_time:
                self._skip_entry(state, f"F1:未到開始時間 {start_time.strftime('%H:%M')}")
                return
            if now_time >= cutoff:
                self._skip_entry(state, f"F1:已過進場時段 {cutoff.strftime('%H:%M')}")
                return
            if state.is_at_limit_up:
                f1_lock_bypass = True
                self.on_log(
                    "INFO",
                    f"[{info.code} {info.name}] 已鎖漲停，忽略 F1 委賣張數限制"
                    f"（委賣 {ask_qty} 張 / 門檻 {cfg.ask_queue_threshold} 張）",
                )
            elif ask_qty >= cfg.ask_queue_threshold:
                self._skip_entry(
                    state,
                    f"F1:委賣 {ask_qty} ≥ {cfg.ask_queue_threshold} 張",
                )
                return
            entry_strategy_ids.append("F1")

        # 功能 7：只買第N根以內
        if cfg.f7_enabled and state.candle_index > cfg.candle_limit:
            self._skip_entry(
                state,
                f"F7:第 {state.candle_index} 根 > 上限 {cfg.candle_limit}",
            )
            return
        if cfg.f7_enabled:
            entry_strategy_ids.append("F7")

        # 功能 10：委賣價 + 即時量（進場確認）
        f10_lock_bypass = False
        if cfg.f10_enabled:
            if state.is_at_limit_up:
                f10_lock_bypass = True
                self.on_log(
                    "INFO",
                    f"[{info.code} {info.name}] 已鎖漲停，忽略 F10 進場確認"
                    f"（委賣價/委賣價倍率/1 秒量皆不檢查）",
                )
            else:
                # F10-①：委賣價資料是否已到位
                if state.ask0_price is None:
                    self._skip_entry(state, "F10:尚無委賣價資料")
                    return
                # F10-②：委賣價需 ≥ 漲停價 × ask_price_ratio（確認掛在板上）
                min_ask_price = Decimal(str(info.limit_up)) * Decimal(str(cfg.ask_price_ratio))
                if state.ask0_price < min_ask_price:
                    self._skip_entry(
                        state,
                        f"F10:委賣價 {state.ask0_price} < 漲停 × {cfg.ask_price_ratio}",
                    )
                    return
                # F10-③：1秒成交量需 ≥ entry_volume_confirm 張（確認買壓足夠，非假鎖板）
                if state.last_1s_vol < cfg.entry_volume_confirm:
                    self._skip_entry(
                        state,
                        f"F10:1秒量 {state.last_1s_vol} < {cfg.entry_volume_confirm} 張",
                    )
                    return
            entry_strategy_ids.append("F10")

        # 走到這裡：所有過濾條件皆通過，清掉上一次的略過訊息
        state.last_skip_reason = ""
        limit_up_price = Decimal(str(info.limit_up))
        lot_cost = limit_up_price * Decimal("1000")
        per_stock_amount = Decimal(str(cfg.per_stock_amount))
        if lot_cost <= 0 or per_stock_amount <= 0:
            self._block_entry(
                state,
                "資金不足",
                "WARN",
                f"[{info.code}] 每檔金額設定無效（{cfg.per_stock_amount:,.0f} 元），已略過不購買",
            )
            return
        if lot_cost > per_stock_amount:
            self._block_entry(
                state,
                "資金不足",
                "WARN",
                f"[{info.code}] 每檔金額 {per_stock_amount:,.0f} 元不足買進 1 張 @ "
                f"{limit_up_price:,.2f}，預估需 {lot_cost:,.0f} 元，已略過不購買",
            )
            return

        qty = int(per_stock_amount // lot_cost)
        order_amount = lot_cost * Decimal(qty)
        if not self._confirm_buying_power(state, order_amount):
            return
        if not self._confirm_special_stock_status(state):
            return

        state.pending = True
        state.pending_side = "BUY"
        state.pending_order_id = ""
        self._log_strategy_trigger(
            "BUY", state, "+".join(entry_strategy_ids) or "BASE",
            {
                "qty": qty,
                "limit_up": info.limit_up,
                "ask_qty": ask_qty,
                "last_1s_vol": state.last_1s_vol,
                "consume_qty": state.limit_up_consumed_qty,
                "candle": state.candle_index,
            },
        )
        if apply_f1:
            if f1_lock_bypass:
                entry_note = (
                    f"鎖漲停忽略 F1（委賣 {ask_qty} 張 / 門檻 "
                    f"{cfg.ask_queue_threshold} 張）"
                )
            else:
                entry_note = f"委賣 {ask_qty} 張 < {cfg.ask_queue_threshold} 張"
        elif consume_enabled:
            entry_note = (f"漲停消化量 {state.limit_up_consumed_qty} 張 >= "
                          f"{getattr(cfg, 'consume_qty_threshold', 0)} 張")
        else:
            entry_note = "基礎條件符合"
        bypass_tags: List[str] = []
        if f1_lock_bypass:
            bypass_tags.append("F1")
        if f10_lock_bypass:
            bypass_tags.append("F10")
        bypass_note = (
            f"；鎖漲停忽略 {'、'.join(bypass_tags)}" if bypass_tags else ""
        )
        self.on_log("TRADE",
            f"[{info.code}] 進場委託 {qty} 張 @ "
            f"{info.limit_up:,.0f}（{entry_note}，第 {state.candle_index} 根"
            f"{bypass_note}）")

        # ── Milestone 5：透過 broker 下單；無 broker 時退回模擬 ──
        if self.broker is not None and OrderRequest is not None:
            try:
                req = OrderRequest(
                    code=info.code, name=info.name,
                    side=OrderSide.BUY,
                    price=Decimal(str(info.limit_up)),
                    qty=qty, day_trade=True,
                    note=f"BUY-{state.candle_index}",
                )
                self.broker.place_order(req)
                state.last_order_submit_times["BUY"] = self._current_datetime()
            except Exception as e:  # noqa: BLE001
                self._clear_pending_order_state(state)
                state.entry_blocked = True
                state.entry_blocked_reason = "下單失敗"
                self.on_log("ERROR", f"[{info.code}] 下單失敗：{e}")
                self._emit_decision_event(
                    "ORDER",
                    state,
                    "下單失敗",
                    str(e),
                    {"side": "BUY", "qty": qty, "price": info.limit_up},
                )
            return

        # 無 broker：保留原模擬延遲成交（單元測試 / 純離線情境）
        code = info.code
        def fill():
            time.sleep(0.6 + random.random() * 1.2)
            with self._lock:
                if not self._running:
                    return
                st = self._states.get(code)
                if st and st.pending:
                    self._clear_pending_order_state(st)
                    st.position_qty += qty
                    st.entry_blocked_reason = ""
                    st.entry_price = Decimal(str(info.limit_up))
                    self._reset_sell_trigger_state(st)
                    if code not in self._daily_trade_codes:
                        self._daily_trade_codes.add(code)
                        self._daily_trade_count = len(self._daily_trade_codes)
                    self.on_log("INFO", f"[{code}] 成交 {qty} 張 @ {info.limit_up:,.0f}，"
                                        f"今日第 {self._daily_trade_count} 檔")
                    trade_time = datetime.now()
                    self.on_trade({
                        "time": trade_time.strftime("%H:%M:%S"),
                        "detail_time": trade_time.isoformat(timespec="seconds"),
                        "code": code,
                        "name": info.name,
                        "action": "BUY",
                        "price": info.limit_up,
                        "qty": qty,
                        "pnl": 0.0,
                        "note": f"第 {st.candle_index} 根漲停",
                    })
        threading.Thread(target=fill, daemon=True).start()

    def _do_sell(self, state: StockState, info: StockInfo, note: str):
        qty = state.position_qty
        # ── M5：有 broker 時透過下單流程處理；fill 回報到位後再結算 PnL ──
        if self.broker is not None and OrderRequest is not None and qty > 0:
            # ── 賣出前確認：先向券商查庫存，避免空單 / 錯帳 ──
            try:
                acc_svc = None
                if hasattr(self.broker, "account_service"):
                    acc_svc = self.broker.account_service
                if acc_svc is not None and hasattr(acc_svc, "snapshot"):
                    snap = acc_svc.snapshot()
                    pos = next((p for p in (snap.positions or []) if p.code == info.code), None)
                    broker_qty = int(pos.qty) if pos else 0
                    if broker_qty <= 0:
                        self.on_log("WARN",
                            f"[{info.code}] 券商回報無庫存（本地紀錄 {qty} 張），"
                            f"取消賣出避免錯帳；本地部位將清零")
                        state.position_qty = 0
                        state.entry_blocked = True
                        state.sold_today = True
                        state.entry_price = None
                        self._reset_sell_trigger_state(state)
                        return
                    if broker_qty < qty:
                        self.on_log("WARN",
                            f"[{info.code}] 券商庫存 {broker_qty} 張 < 本地 {qty} 張，"
                            f"以券商實際庫存 {broker_qty} 張下單")
                        qty = broker_qty
                        state.position_qty = qty
            except Exception as e:  # noqa: BLE001
                self.on_log("WARN",
                    f"[{info.code}] 查詢券商庫存失敗（使用本地部位 {qty} 張繼續）：{e}")

            sell_price_dec = state.last_price or Decimal(str(info.limit_up))
            try:
                state.pending = True   # 標記掛賣
                state.pending_side = "SELL"
                state.pending_order_id = ""
                state._sell_note = note  # type: ignore[attr-defined]
                self._reset_sell_trigger_state(state)
                req = OrderRequest(
                    code=info.code, name=info.name,
                    side=OrderSide.SELL,
                    price=sell_price_dec,
                    qty=qty, day_trade=True,
                    note=note[:8] if note else "SELL",
                )
                self.on_log("TRADE", f"[{info.code}] 出場委託 {qty} 張 @ {sell_price_dec}（{note}）")
                self.broker.place_order(req)
                state.last_order_submit_times["SELL"] = self._current_datetime()
            except Exception as e:  # noqa: BLE001
                self.on_log("ERROR", f"[{info.code}] 出場下單失敗：{e}")
                self._clear_pending_order_state(state)
            return

        # 無 broker：原本的同步結算
        sell_price_dec: Decimal = state.last_price or Decimal(str(info.limit_up))
        sell_price = float(sell_price_dec)
        pnl_net = 0.0
        if state.entry_price is not None and qty > 0 and realized_pnl is not None:
            pnl = realized_pnl(state.entry_price, sell_price_dec, qty, day_trade=True)
            pnl_net = float(pnl.net)
            self._today_realized_pnl += pnl.net
        cost_basis = (
            float(state.entry_price * Decimal(qty) * Decimal("1000"))
            if state.entry_price is not None and qty > 0
            else 0.0
        )

        state.position_qty = 0
        state.entry_blocked = True
        state.entry_blocked_reason = "已賣出"
        state.sold_today = True   # 功能 12：標記當天已賣過
        state.entry_price = None
        self._reset_sell_trigger_state(state)
        trade_time = datetime.now()
        self.on_trade({
            "time": trade_time.strftime("%H:%M:%S"),
            "detail_time": trade_time.isoformat(timespec="seconds"),
            "code": info.code,
            "name": info.name,
            "action": "SELL",
            "price": sell_price,
            "qty": qty,
            "pnl": pnl_net,
            "cost_basis": cost_basis,
            "realized_total": float(self._today_realized_pnl),
            "note": note,
        })

    def sell_all_strategy_positions(self, reason: str = "manual_sell_all") -> int:
        """手動賣出所有目前由策略引擎記錄的持倉。"""
        sold = 0
        with self._lock:
            for state in list(self._states.values()):
                if state.position_qty <= 0 or state.pending:
                    continue
                self._log_strategy_trigger(
                    "SELL", state, "MANUAL_ALL",
                    {
                        "qty": state.position_qty,
                        "last_price": state.last_price,
                        "reason": reason,
                    },
                )
                self._do_sell(state, state.info, "手動全部策略持股賣出")
                sold += 1
        return sold

    def _open_ticks_from_limit(self, state: StockState) -> int:
        # F4 應以「目前已不屬鎖板」視為開板；若有 ask0 價格再換算實際打開幾檔。
        if state.is_at_limit_up:
            return 0
        limit_up = Decimal(str(state.info.limit_up))
        if state.ask0_price is None:
            return 1
        if state.ask0_price >= limit_up:
            return 1
        tick = self._tick_size(limit_up)
        if tick <= 0:
            return 1
        return max(1, int((limit_up - state.ask0_price) / tick))

    @staticmethod
    def _event_time_to_ts(event_time, fallback: float) -> float:
        if event_time is not None and hasattr(event_time, "timestamp"):
            try:
                return float(event_time.timestamp())
            except Exception:
                return fallback
        return fallback

    @staticmethod
    def _reset_sell_trigger_state(state: StockState) -> None:
        state.f4_first_trigger_at = None
        state.f5_first_trigger_at = None
        state.f4_trigger_snapshot = None
        state.f5_trigger_snapshot = None

    def _reset_post_entry_exit_state(self, state: StockState) -> None:
        """Start exit monitoring from market events received after the entry fill."""
        state.tick_vols.clear()
        state.last_1s_vol = 0
        self._reset_sell_trigger_state(state)

    def _record_sell_trigger_candidates(self, state: StockState, event_ts: float) -> None:
        cfg = self.config
        info = state.info
        has_been_at_limit_today = state.touched_limit_up_today or state.candle_index > 0
        require_today_limit = getattr(cfg, "f4_require_today_limitup", True)
        open_ticks = self._open_ticks_from_limit(state)
        open_tick_threshold = max(1, int(getattr(cfg, "f4_open_ticks_to_sell", 1) or 1))
        f4_ready = (
            cfg.f4_enabled
            and (has_been_at_limit_today or not require_today_limit)
            and open_ticks >= open_tick_threshold
            and state.last_price is not None
        )
        if f4_ready and state.f4_first_trigger_at is None:
            state.f4_first_trigger_at = event_ts
            state.f4_trigger_snapshot = {
                "open_ticks": open_ticks,
                "threshold": open_tick_threshold,
                "ask0_price": state.ask0_price,
                "limit_up": info.limit_up,
                "trigger_time": event_ts,
            }

        if cfg.f5_enabled and state.last_1s_vol >= cfg.volume_spike_sell_threshold:
            if state.f5_first_trigger_at is None:
                state.f5_first_trigger_at = event_ts
                state.f5_trigger_snapshot = {
                    "last_1s_vol": state.last_1s_vol,
                    "threshold": cfg.volume_spike_sell_threshold,
                    "trigger_time": event_ts,
                }

    def _pick_sell_strategy(self, state: StockState) -> Optional[dict]:
        f4_at = state.f4_first_trigger_at
        f5_at = state.f5_first_trigger_at
        if f4_at is None and f5_at is None:
            return None

        def _detail_time(value: Optional[float]) -> Optional[str]:
            if value is None:
                return None
            return datetime.fromtimestamp(value).isoformat(timespec="microseconds")

        if f4_at is None:
            winner = "F5"
        elif f5_at is None:
            winner = "F4"
        elif f5_at <= f4_at:
            winner = "F5"
        else:
            winner = "F4"

        if winner == "F4":
            snapshot = dict(state.f4_trigger_snapshot or {})
            reason = (
                f"漲停板打開 {snapshot.get('open_ticks')} 檔，"
                f"達出場門檻 {snapshot.get('threshold')} 檔"
            )
        else:
            snapshot = dict(state.f5_trigger_snapshot or {})
            reason = (
                f"1秒量 {snapshot.get('last_1s_vol')} 張 >= "
                f"{snapshot.get('threshold')} 張，爆量出場"
            )

        details = {
            **snapshot,
            "winner_strategy": winner,
            "first_f4_time": _detail_time(f4_at),
            "first_f5_time": _detail_time(f5_at),
        }
        return {
            "strategy": winner,
            "reason": reason,
            "details": details,
        }

    def _block_entry(self, state: StockState, reason: str, level: str, message: str) -> None:
        state.entry_blocked = True
        state.entry_blocked_reason = reason
        self.on_log(level, message)
        self._emit_decision_event(
            "ENTRY_BLOCK",
            state,
            "封鎖進場",
            reason,
            {"level": level, "message": message},
        )

    def _skip_entry(self, state: StockState, reason: str, *, log: bool = True) -> None:
        """記錄一次「軟性略過」進場的原因（不會永久封鎖）。

        會把原因寫入 ``state.last_skip_reason``，供 GUI 在「動作」欄顯示，
        使用者可立即看到該檔目前沒進場的原因，而不是只顯示「檢查進場」。
        """
        if state.last_skip_reason != reason:
            state.last_skip_reason = reason
            self._emit_decision_event(
                "ENTRY_SKIP",
                state,
                "未進場",
                reason,
                {},
            )
            if log:
                # 使用 DEBUG 等級，避免每秒刷屏；如需排查可調 log level。
                try:
                    self.on_log("DEBUG", f"[{state.info.code}] 略過進場：{reason}")
                except Exception:  # noqa: BLE001
                    pass

    def _confirm_buying_power(self, state: StockState, order_amount: Decimal) -> bool:
        broker = self.broker
        if broker is None or not hasattr(broker, "account_service"):
            return True
        # 模擬下單模式：跳過真實券商可用額度檢查。
        # 否則當 SDK 回傳 available=0（例如尚未登入、或 API 暫時失敗）會誤判
        # 「資金不足」把每一筆漲停都擋掉，造成模擬時看不到任何成交。
        if bool(getattr(self.config, "order_dry_run", False)):
            return True
        try:
            snap = broker.account_service().snapshot()
            buying_power = Decimal(str(getattr(snap, "buying_power", 0) or 0))
        except Exception as exc:  # noqa: BLE001
            self._block_entry(
                state,
                "額度確認失敗",
                "ERROR",
                f"[{state.info.code}] 無法確認可用額度，已略過不購買：{exc}",
            )
            return False

        if buying_power < order_amount:
            self._block_entry(
                state,
                "資金不足",
                "WARN",
                f"[{state.info.code}] 可用額度 {buying_power:,.0f} 元不足，"
                f"預估買進需 {order_amount:,.0f} 元，已略過不購買",
            )
            return False
        return True

    def _confirm_special_stock_status(self, state: StockState) -> bool:
        cfg = self.config
        info = state.info
        if not cfg.f11_enabled:
            return True

        if not state.special_check_completed and self.broker is not None and hasattr(self.broker, "load_symbol_info"):
            try:
                refreshed = self.broker.load_symbol_info([info.code]) or {}
                fresh = refreshed.get(info.code)
            except Exception as exc:  # noqa: BLE001
                self._block_entry(
                    state,
                    "特殊股確認失敗",
                    "ERROR",
                    f"[{info.code}] 無法透過富邦 API 確認處置/注意/禁當沖，已略過不購買：{exc}",
                )
                return False
            if fresh is None:
                self._block_entry(
                    state,
                    "特殊股確認失敗",
                    "ERROR",
                    f"[{info.code}] 富邦 API 未回傳處置/注意/禁當沖旗標，已略過不購買",
                )
                return False
            info.is_disposal = bool(getattr(fresh, "is_disposal", False))
            info.is_attention = bool(getattr(fresh, "is_attention", False))
            info.is_day_trade_restricted = bool(getattr(fresh, "is_day_trade_restricted", False))
            state.special_check_completed = True
        else:
            state.special_check_completed = True

        reasons = []
        if info.is_disposal:
            reasons.append("處置股")
        if info.is_attention:
            reasons.append("注意股")
        if info.is_day_trade_restricted:
            reasons.append("禁當沖")
        if reasons:
            self._block_entry(
                state,
                "特殊股排除",
                "WARN",
                f"[{info.code}] 富邦 API 確認為{'、'.join(reasons)}，已略過不購買",
            )
            return False
        return True

    @staticmethod
    def _tick_size(price: Decimal) -> Decimal:
        if tick_size is not None:
            return tick_size(price)
        if price < Decimal("10"):
            return Decimal("0.01")
        if price < Decimal("50"):
            return Decimal("0.05")
        if price < Decimal("100"):
            return Decimal("0.1")
        if price < Decimal("500"):
            return Decimal("0.5")
        if price < Decimal("1000"):
            return Decimal("1")
        return Decimal("5")

    @staticmethod
    def _parse_config_time(value: str, fallback: dtime) -> dtime:
        try:
            parts = [int(part) for part in str(value).strip().split(":", 1)]
            if len(parts) != 2:
                return fallback
            return dtime(parts[0], parts[1])
        except Exception:
            return fallback

    def _is_after_auto_trade_cutoff(self, now: Optional[datetime] = None) -> bool:
        if not self._running:
            return False
        current = now or self._current_datetime()
        return current.time() >= self.AUTO_TRADE_CUTOFF_TIME

    @staticmethod
    def _current_datetime() -> datetime:
        return datetime.now()

    def _log_strategy_trigger(self, side: str, state: StockState,
                              strategy: str, details: dict) -> None:
        def _fmt(value) -> str:
            if isinstance(value, Decimal):
                return str(value)
            return str(value)

        detail_txt = "，".join(
            f"{key}={_fmt(value)}" for key, value in details.items()
            if value is not None
        )
        if self.on_strategy_event is not None:
            self.on_strategy_event({
                "time": datetime.now().strftime("%H:%M:%S"),
                "side": side,
                "code": state.info.code,
                "name": state.info.name,
                "strategy": strategy,
                "details": {key: _fmt(value) for key, value in details.items()
                            if value is not None},
            })
        decision_time = self._emit_decision_event(
            "STRATEGY",
            state,
            {
                "BUY": "進場觸發",
                "SELL": "出場觸發",
                "CANCEL": "取消觸發",
            }.get(side, side),
            strategy,
            details,
        )
        if isinstance(decision_time, datetime):
            state.last_strategy_decision_times[str(side or "").upper()] = decision_time
        self.on_log(
            "TRADE",
            f"[策略觸發][{side}][{state.info.code} {state.info.name}] "
            f"策略={strategy}；{detail_txt}",
        )

    # ─────────────────────────────────────────
    #  券商回報處理（Milestone 5）
    # ─────────────────────────────────────────

    def _on_broker_order(self, ev) -> None:
        """委託回報：寫入日誌（GUI 會另外綁定到 orders_table）。"""
        try:
            self.on_log("INFO",
                f"[{ev.code}] 委託 {ev.side.value} {ev.qty} 張 "
                f"@ {ev.price} 狀態={ev.status.value}")
        except Exception:  # noqa: BLE001
            pass
        state = self._states.get(ev.code)
        if state is not None:
            status_value = str(getattr(ev.status, "value", ev.status) or "").upper()
            side_value = str(getattr(ev.side, "value", ev.side) or "").upper()
            order_id_value = str(getattr(ev, "order_id", "") or "")
            if status_value == "PENDING":
                state.pending = True
                state.pending_side = side_value
                state.pending_order_id = order_id_value
            elif status_value in {"CANCELLED", "REJECTED"} and state.pending_order_id == order_id_value:
                self._clear_pending_order_state(state)
            side_key = str(getattr(ev.side, "value", ev.side) or "").upper()
            trigger_decision_time = state.last_strategy_decision_times.get(side_key)
            local_submit_time = state.last_order_submit_times.get(side_key)
            self._emit_decision_event(
                "ORDER",
                state,
                f"委託{ev.status.value}",
                ev.side.value,
                {
                    "order_id": ev.order_id,
                    "qty": ev.qty,
                    "filled_qty": ev.filled_qty,
                    "price": ev.price,
                    "status": ev.status.value,
                    "source": getattr(ev, "source", ""),
                    "trigger_decision_time": trigger_decision_time,
                    "local_order_submit_time": local_submit_time,
                    "decision_to_order_ms": self._calc_delay_ms(
                        trigger_decision_time,
                        local_submit_time,
                    ),
                },
                event_time=ev.time,
            )

    def _on_broker_fill(self, ev) -> None:
        """成交回報：更新部位、累計損益、推送 trade。"""
        with self._lock:
            fill_key = (
                str(getattr(ev, "order_id", "") or ""),
                str(getattr(ev.side, "value", ev.side)),
                str(getattr(ev, "code", "") or ""),
                str(getattr(ev, "price", "") or ""),
                int(getattr(ev, "qty", 0) or 0),
                getattr(getattr(ev, "time", None), "isoformat", lambda: "")(),
            )
            if fill_key in self._processed_fill_keys:
                self.on_log(
                    "WARN",
                    f"[{getattr(ev, 'code', '')}] 忽略重複成交回報 "
                    f"order_id={getattr(ev, 'order_id', '')}",
                )
                return
            self._processed_fill_keys.add(fill_key)
            state = self._states.get(ev.code)
            if state is None:
                return
            info = state.info
            qty = int(ev.qty)
            if ev.side.value == "BUY":
                self._clear_pending_order_state(state)
                state.position_qty += qty
                state.entry_blocked_reason = ""
                self._reset_post_entry_exit_state(state)
                if state.entry_price is None:
                    state.entry_price = ev.price
                else:
                    try:
                        old_qty = max(0, int(state.position_qty) - qty)
                        if old_qty > 0:
                            total_cost = state.entry_price * Decimal(old_qty) + ev.price * Decimal(qty)
                            state.entry_price = (total_cost / Decimal(old_qty + qty)).quantize(Decimal("0.01"))
                        else:
                            state.entry_price = ev.price
                    except Exception:
                        state.entry_price = ev.price
                if ev.code not in self._daily_trade_codes:
                    self._daily_trade_codes.add(ev.code)
                    self._daily_trade_count = len(self._daily_trade_codes)
                self.on_log("INFO",
                    f"[{ev.code}] 買進成交 {qty} 張 @ {ev.price}，"
                    f"累計持倉 {state.position_qty} 張，今日第 {self._daily_trade_count} 檔")
                self.on_trade({
                    "time": ev.time.strftime("%H:%M:%S"),
                    "detail_time": ev.time.isoformat(timespec="seconds"),
                    "code": ev.code,
                    "name": info.name,
                    "action": "BUY",
                    "price": float(ev.price),
                    "qty": qty,
                    "pnl": 0.0,
                    "note": f"第 {state.candle_index} 根漲停",
                })
                self._emit_decision_event(
                    "FILL",
                    state,
                    "買進成交",
                    "BUY",
                    {
                        "order_id": ev.order_id,
                        "qty": qty,
                        "price": ev.price,
                        "daily_trade_count": self._daily_trade_count,
                    },
                    event_time=ev.time,
                )
            else:  # SELL
                pnl_net = 0.0
                if state.entry_price is not None and qty > 0 and realized_pnl is not None:
                    pnl = realized_pnl(state.entry_price, ev.price, qty, day_trade=True)
                    pnl_net = float(pnl.net)
                    self._today_realized_pnl += pnl.net
                cost_basis = (
                    float(state.entry_price * Decimal(qty) * Decimal("1000"))
                    if state.entry_price is not None and qty > 0
                    else 0.0
                )
                note = getattr(state, "_sell_note", "出場")
                # 部分賣出時 position_qty 應該扣掉，而不是直接歸零
                state.position_qty = max(0, int(state.position_qty) - qty)
                self._clear_pending_order_state(state)
                if state.position_qty == 0:
                    state.entry_blocked = True
                    state.entry_blocked_reason = "已賣出"
                    state.sold_today = True
                    state.entry_price = None
                    self._reset_sell_trigger_state(state)
                self.on_log("INFO",
                    f"[{ev.code}] 賣出成交 {qty} 張 @ {ev.price}，"
                    f"剩餘持倉 {state.position_qty} 張，損益 {pnl_net:+,.0f}")
                self.on_trade({
                    "time": ev.time.strftime("%H:%M:%S"),
                    "detail_time": ev.time.isoformat(timespec="seconds"),
                    "code": ev.code,
                    "name": info.name,
                    "action": "SELL",
                    "price": float(ev.price),
                    "qty": qty,
                    "pnl": pnl_net,
                    "cost_basis": cost_basis,
                    "realized_total": float(self._today_realized_pnl),
                    "note": note,
                })
                self._emit_decision_event(
                    "FILL",
                    state,
                    "賣出成交",
                    note,
                    {
                        "order_id": ev.order_id,
                        "qty": qty,
                        "price": ev.price,
                        "pnl": pnl_net,
                        "cost_basis": cost_basis,
                        "realized_total": float(self._today_realized_pnl),
                    },
                    event_time=ev.time,
                )

    @staticmethod
    def _clear_pending_order_state(state: StockState) -> None:
        state.pending = False
        state.pending_side = ""
        state.pending_order_id = ""

    @staticmethod
    def _fmt_decision_value(value):
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (datetime, date, dtime)):
            return value.isoformat()
        if isinstance(value, dict):
            return {k: TradingEngine._fmt_decision_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [TradingEngine._fmt_decision_value(v) for v in value]
        return value

    @staticmethod
    def _calc_delay_ms(start_time, end_time) -> Optional[float]:
        if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
            return None
        return round((end_time - start_time).total_seconds() * 1000, 3)

    def _state_snapshot_details(self, state: StockState, *, decision_time: Optional[datetime] = None) -> dict:
        market_event_time = state.last_market_event_time
        recv_time = state.last_recv_time
        return {
            "candle": state.candle_index,
            "limit_up_mode": state.active_limit_up_mode,
            "startup_limit_up_mode": self._startup_limit_up_mode,
            "is_at_limit_up": state.is_at_limit_up,
            "ask_qty": state.ask_qty_at_limit,
            "ask0_price": state.ask0_price,
            "ask0_volume": state.ask0_volume,
            "bid0_price": state.bid0_price,
            "bid0_volume": state.bid0_volume,
            "effective_bid0_price": state.effective_bid0_price,
            "effective_bid0_volume": state.effective_bid0_volume,
            "last_price": state.last_price,
            "trade_bid": state.trade_bid,
            "trade_ask": state.trade_ask,
            "last_1s_vol": state.last_1s_vol,
            "consume_qty": state.limit_up_consumed_qty,
            "candidate_lock_since": state.limit_up_candidate_since,
            "candidate_lock_event_time": state.first_limit_up_candidate_event_time,
            "confirmed_lock_event_time": state.first_limit_up_confirmed_event_time,
            "market_event_time": market_event_time,
            "recv_time": recv_time,
            "decision_time": decision_time,
            "market_to_recv_ms": self._calc_delay_ms(market_event_time, recv_time),
            "recv_to_decision_ms": self._calc_delay_ms(recv_time, decision_time),
            "market_to_decision_ms": self._calc_delay_ms(market_event_time, decision_time),
            "pending": state.pending,
            "position_qty": state.position_qty,
            "first_f4_time": state.f4_first_trigger_at,
            "first_f5_time": state.f5_first_trigger_at,
            "f4_trigger_snapshot": state.f4_trigger_snapshot,
            "f5_trigger_snapshot": state.f5_trigger_snapshot,
            "blocked": state.entry_blocked,
            "blocked_reason": state.entry_blocked_reason,
            "sold_today": state.sold_today,
            "has_ask_levels": state.has_ask_levels,
            "has_bid_levels": state.has_bid_levels,
            "limit_up_signals": dict(state.limit_up_signal_states),
            "limit_up_candidates": dict(state.limit_up_candidate_states),
        }

    def _emit_decision_event(
        self,
        category: str,
        state: StockState,
        result: str,
        reason: str,
        details: dict,
        *,
        event_time=None,
    ) -> Optional[datetime]:
        if self.on_decision_event is None:
            return None
        decision_time = datetime.now()
        merged = self._state_snapshot_details(state, decision_time=decision_time)
        merged.update(details or {})
        try:
            self.on_decision_event({
                "time": (
                    event_time.strftime("%H:%M:%S")
                    if hasattr(event_time, "strftime")
                    else datetime.now().strftime("%H:%M:%S")
                ),
                "code": state.info.code,
                "name": state.info.name,
                "category": category,
                "result": result,
                "reason": reason,
                "market_event_time": self._fmt_decision_value(state.last_market_event_time),
                "recv_time": self._fmt_decision_value(state.last_recv_time),
                "decision_time": self._fmt_decision_value(decision_time),
                "details": self._fmt_decision_value(merged),
            })
        except Exception:
            pass
        return decision_time

    # ─────────────────────────────────────────
    #  狀態彙整（供 UI 輪詢）
    # ─────────────────────────────────────────

    def get_summary(self) -> List[dict]:
        with self._lock:
            result = []
            cfg = self.config
            # f9（價格區間）相關設定
            f9_on = bool(getattr(cfg, "f9_enabled", False))
            pmin = float(getattr(cfg, "price_min", 0) or 0)
            pmax = float(getattr(cfg, "price_max", 0) or 0)
            for code, s in self._states.items():
                # 價格與漲跌計算
                price = float(s.last_price) if s.last_price is not None else None
                # 防呆：price <= 0 視為無價（盤前 / 試撮 / 欄位異常）
                if price is not None and price <= 0:
                    price = None
                prev_close = s.info.prev_close  # float
                # ── 規則：price 永遠保留最後一次有效 socket 價 ──
                # 尚未收到有效 tick → price=None（UI 顯示「—」），不 fallback 到昨收
                if price is not None and prev_close:
                    change = round(price - prev_close, 2)
                    change_pct = round(change / prev_close * 100, 2)
                else:
                    change = None
                    change_pct = None

                # ── F9：僅在取得即時價後才判斷區間（無即時價 → 不過濾，等行情）──
                # 注意：訂閱時是以「昨收 ±10%」放寬篩出來的，所以這裡若用昨收判斷
                # 會在熱套用設定的瞬間（last_price 暫時為 None / 區間變動）把整張表清空。
                out_of_range = False
                if f9_on and pmax > 0 and price is not None and price > 0:
                    if not (pmin <= price <= pmax):
                        out_of_range = True

                result.append({
                    "code":       code,
                    "name":       s.info.name,
                    "market":     s.info.market,
                    "candle":     s.candle_index,
                    "prior_limit_up_streak": s.info.prior_limit_up_streak,
                    "qty":        s.position_qty,
                    "pending":    s.pending,
                    "vol_1s":     s.last_1s_vol,
                    "blocked":    s.entry_blocked,
                    "blocked_reason": s.entry_blocked_reason,
                    # ── 新增欄位 ──
                    "price":      price,          # 最新成交價（None = 尚無行情）
                    "limit_up":   s.info.limit_up,
                    "prev_close": prev_close,
                    "change":     change,         # 漲跌價差
                    "change_pct": change_pct,     # 漲跌幅 %
                    "ask_qty":    s.ask_qty_at_limit,  # 漲停委賣張數
                    "is_at_limit_up": s.is_at_limit_up,
                    "limit_up_mode": s.active_limit_up_mode,
                    "startup_limit_up_mode": self._startup_limit_up_mode,
                    "ask0_price": (float(s.ask0_price) if s.ask0_price is not None else None),
                    "ask0_volume": s.ask0_volume,
                    "bid0_price": (float(s.bid0_price) if s.bid0_price is not None else None),
                    "bid0_volume": s.bid0_volume,
                    "trade_bid": (float(s.trade_bid) if s.trade_bid is not None else None),
                    "trade_ask": (float(s.trade_ask) if s.trade_ask is not None else None),
                    "has_ask_levels": s.has_ask_levels,
                    "has_bid_levels": s.has_bid_levels,
                    "candidate_lock_event_time": self._fmt_decision_value(s.first_limit_up_candidate_event_time),
                    "confirmed_lock_event_time": self._fmt_decision_value(s.first_limit_up_confirmed_event_time),
                    "limit_up_signals": dict(s.limit_up_signal_states),
                    "limit_up_candidates": dict(s.limit_up_candidate_states),
                    "out_of_range": out_of_range,  # F9 即時價過濾旗標（True = 該檔被排除顯示）
                    "last_skip_reason": s.last_skip_reason,  # 最近一次被略過進場的原因（GUI 動作欄使用）
                    "startup_limitup_blocked": s.startup_limitup_blocked,
                    "engine_started_at": (
                        self._started_at.strftime("%H:%M:%S") if self._started_at else ""
                    ),
                })
            return result
