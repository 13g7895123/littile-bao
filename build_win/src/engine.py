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

from config import TradingConfig

try:
    from broker import (
        BookEvent, FillEvent, OrderEvent, OrderSide, RealtimeFeed, SymbolMeta, TickEvent,
        realized_pnl,
    )
    from broker.orders import OrderRequest
except ImportError:  # 套件初始化失敗時退回為 None，避免阻擋既有測試
    BookEvent = SymbolMeta = TickEvent = RealtimeFeed = FillEvent = None  # type: ignore
    OrderEvent = OrderSide = OrderRequest = None  # type: ignore
    realized_pnl = None  # type: ignore


# ─────────────────────────────────────────────────────────────
#  資料結構
# ─────────────────────────────────────────────────────────────

class StockInfo:
    def __init__(self, code: str, name: str, limit_up: float, market: str,
                 is_disposal: bool = False, is_attention: bool = False,
                 is_day_trade_restricted: bool = False,
                 open_limit_up: bool = False,
                 prev_close: float = 0.0):
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
        # ── Milestone 2：行情驅動欄位 ───────────────────────
        self.last_price: Optional[Decimal] = None
        self.ask0_price: Optional[Decimal] = None
        self.ask0_volume: int = 0
        self.bid0_price: Optional[Decimal] = None
        self.bid0_volume: int = 0
        self.ask_qty_at_limit: int = 0    # 漲停價委賣張數（不為漲停時 = 0）
        self.is_at_limit_up: bool = False
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
#  引擎
# ─────────────────────────────────────────────────────────────

class TradingEngine:

    def __init__(
        self,
        config: TradingConfig,
        on_log: Callable[[str, str], None],   # (level, msg)
        on_trade: Callable[[dict], None],
        on_status: Callable[[List[dict]], None],
        feed: Optional["RealtimeFeed"] = None,
        symbol_infos: Optional[Dict[str, "object"]] = None,
        broker: Optional[object] = None,
    ):
        self.config = config
        self.on_log = on_log
        self.on_trade = on_trade
        self.on_status = on_status
        self.feed = feed
        self.broker = broker

        self._states: Dict[str, StockState] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._daily_trade_count: int = 0   # 功能 13：當天已成交檔數
        self._today_realized_pnl: Decimal = Decimal("0")  # M4：當日已實現損益
        self._trading_date: date = date.today()  # 跨日重置使用

        # ── 篩選市場 ─────────────────────────────────────────
        markets = config.get_markets()

        if symbol_infos:
            # Milestone 3：使用 broker.load_symbol_info() 提供的真實基本資料
            for code, si in symbol_infos.items():
                if si.market not in markets:
                    continue
                info = StockInfo(
                    code=si.code,
                    name=si.name,
                    limit_up=float(si.limit_up_price),
                    market=si.market,
                    is_disposal=si.is_disposal,
                    is_attention=si.is_attention,
                    is_day_trade_restricted=si.is_day_trade_restricted,
                    open_limit_up=si.open_limit_up,
                    prev_close=float(si.prev_close),
                )
                self._states[code] = StockState(info)
        else:
            # 退回 MOCK_STOCKS 預設清單
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
                if hasattr(self.broker, "on_filled"):
                    self.broker.on_filled(self._on_broker_fill)
                if hasattr(self.broker, "on_order"):
                    self.broker.on_order(self._on_broker_order)
                self.on_log("INFO", "已訂閱券商委託 / 成交回報")
            except Exception as e:  # noqa: BLE001
                self.on_log("WARN", f"訂閱券商回報失敗：{e}")

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self.feed is not None:
            try:
                self.feed.stop()
            except Exception as e:  # noqa: BLE001
                self.on_log("WARN", f"停止行情訂閱時發生錯誤：{e}")
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
    #  行情事件處理（Milestone 2）
    # ─────────────────────────────────────────

    def _on_tick(self, ev) -> None:
        """RealtimeFeed 每筆 tick 推送進來。"""
        with self._lock:
            state = self._states.get(ev.code)
            if state is None:
                return
            now = time.time()
            # 1 秒滑動視窗
            state.tick_vols.append((now, int(ev.volume)))
            while state.tick_vols and now - state.tick_vols[0][0] > 1.0:
                state.tick_vols.popleft()
            state.last_1s_vol = sum(v for _, v in state.tick_vols)
            state.last_price = ev.price

            # 漲停判斷：成交價 == 漲停價
            limit_up = Decimal(str(state.info.limit_up))
            if ev.price >= limit_up:
                if state.limit_up_since is None and not state.entry_blocked:
                    cfg = self.config
                    if state.candle_index < (cfg.candle_limit if cfg.f7_enabled else 99):
                        state.limit_up_since = now
                        state.candle_index += 1
                        self.on_log(
                            "INFO",
                            f"[{state.info.code} {state.info.name}] 漲停！"
                            f"第 {state.candle_index} 根，委賣 {state.ask_qty_at_limit} 張",
                        )

    def _on_book(self, ev) -> None:
        """RealtimeFeed 五檔推送。"""
        with self._lock:
            state = self._states.get(ev.code)
            if state is None:
                return
            if ev.ask:
                state.ask0_price = ev.ask[0].price
                state.ask0_volume = int(ev.ask[0].volume)
            else:
                state.ask0_price = None
                state.ask0_volume = 0
            if ev.bid:
                state.bid0_price = ev.bid[0].price
                state.bid0_volume = int(ev.bid[0].volume)
            else:
                state.bid0_price = None
                state.bid0_volume = 0

            limit_up = Decimal(str(state.info.limit_up))
            # 委賣張數（漲停板）
            if state.ask0_price is not None and state.ask0_price == limit_up:
                state.ask_qty_at_limit = state.ask0_volume
                state.is_at_limit_up = True
            else:
                state.ask_qty_at_limit = 0
                # 漲停板被打開：ask[0] 不再是漲停價
                if state.is_at_limit_up:
                    state.is_at_limit_up = False
                    state.limit_up_since = None



    def _loop(self):
        while self._running:
            now = time.time()
            with self._lock:
                self._maybe_daily_reset()
                for code, state in self._states.items():
                    self._tick(state, now)
            self.on_status(self.get_summary())
            time.sleep(1.0)

    def _maybe_daily_reset(self) -> None:
        """日期變動時重置每日狀態，避免跨日卡單 / 誤賣。"""
        today = date.today()
        if today == self._trading_date:
            return
        self.on_log("INFO", f"偵測到日期變更 {self._trading_date} → {today}，重置每日狀態")
        for st in self._states.values():
            st.entry_blocked = False
            st.sold_today = False
            st.candle_index = 0
            st.limit_up_since = None
            # 注意：position_qty 不清空，避免影響真實持倉同步
        self._daily_trade_count = 0
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
                return

        # ── 功能 11：排除處置股、注意股、限當沖股 ────────────────
        if cfg.f11_enabled:
            if info.is_disposal or info.is_attention or info.is_day_trade_restricted:
                return

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

            # 功能 4：板被打開（曾為漲停 → 目前 ask[0] 不再是漲停價）
            # 必須當日曾達漲停（candle_index > 0）才生效，避免隔日庫存誤賣
            has_been_at_limit_today = state.candle_index > 0
            if (cfg.f4_enabled and has_been_at_limit_today
                    and not state.is_at_limit_up and state.last_price is not None):
                reason = "委買漲停，市場打開，市價出場"

            # 功能 5：1秒爆量
            if cfg.f5_enabled and reason is None:
                if state.last_1s_vol > cfg.volume_spike_sell_threshold:
                    reason = (f"1秒量 {state.last_1s_vol} 張 > "
                              f"{cfg.volume_spike_sell_threshold} 張，爆量出場")

            if reason:
                self.on_log("WARN", f"[{info.code}] 出場觸發：{reason}")
                self._do_sell(state, info, reason)
            return

        # ── 進場邏輯 ──────────────────────────────────────────────
        if state.pending or state.entry_blocked or state.candle_index == 0:
            return
        if state.limit_up_since is None or not state.is_at_limit_up:
            return

        # 功能 12：開盤即漲停 且 當天已賣過 → 封鎖
        if cfg.f12_enabled and info.open_limit_up and state.sold_today:
            return

        # 功能 13：當天成交檔數上限
        if cfg.f13_enabled and self._daily_trade_count >= cfg.daily_max_trades:
            return

        # 功能 1：時間 + 委賣篩選（漲停價委賣張數）
        ask_qty = state.ask_qty_at_limit
        if cfg.f1_enabled:
            now_time = datetime.now().time()
            cutoff = dtime(*map(int, cfg.entry_before_time.split(":")))
            if now_time >= cutoff:
                return
            if ask_qty >= cfg.ask_queue_threshold:
                return

        # 功能 7：只買第N根以內
        if cfg.f7_enabled and state.candle_index > cfg.candle_limit:
            return

        # 功能 10：委賣價 + 即時量
        if cfg.f10_enabled:
            if state.ask0_price is None:
                return
            min_ask_price = Decimal(str(info.limit_up)) * Decimal(str(cfg.ask_price_ratio))
            if state.ask0_price < min_ask_price:
                return
            if state.last_1s_vol < cfg.entry_volume_confirm:
                return

        qty = max(1, int(cfg.per_stock_amount / (info.limit_up * 1000)))
        state.pending = True
        self.on_log("TRADE",
            f"[{info.code}] 進場委託 {qty} 張 @ "
            f"{info.limit_up:,.0f}（委賣 {ask_qty} 張 < {cfg.ask_queue_threshold} 張，"
            f"第 {state.candle_index} 根）")

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
            except Exception as e:  # noqa: BLE001
                state.pending = False
                state.entry_blocked = True
                self.on_log("ERROR", f"[{info.code}] 下單失敗：{e}")
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
                    st.pending = False
                    st.position_qty = qty
                    st.entry_price = Decimal(str(info.limit_up))
                    self._daily_trade_count += 1
                    self.on_log("INFO", f"[{code}] 成交 {qty} 張 @ {info.limit_up:,.0f}，"
                                        f"今日第 {self._daily_trade_count} 檔")
                    self.on_trade({
                        "time": datetime.now().strftime("%H:%M:%S"),
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
            sell_price_dec = state.last_price or Decimal(str(info.limit_up))
            try:
                state.pending = True   # 標記掛賣
                state._sell_note = note  # type: ignore[attr-defined]
                req = OrderRequest(
                    code=info.code, name=info.name,
                    side=OrderSide.SELL,
                    price=sell_price_dec,
                    qty=qty, day_trade=True,
                    note=note[:8] if note else "SELL",
                )
                self.on_log("TRADE", f"[{info.code}] 出場委託 {qty} 張 @ {sell_price_dec}（{note}）")
                self.broker.place_order(req)
            except Exception as e:  # noqa: BLE001
                self.on_log("ERROR", f"[{info.code}] 出場下單失敗：{e}")
                state.pending = False
            return

        # 無 broker：原本的同步結算
        sell_price_dec: Decimal = state.last_price or Decimal(str(info.limit_up))
        sell_price = float(sell_price_dec)
        pnl_net = 0.0
        if state.entry_price is not None and qty > 0 and realized_pnl is not None:
            pnl = realized_pnl(state.entry_price, sell_price_dec, qty, day_trade=True)
            pnl_net = float(pnl.net)
            self._today_realized_pnl += pnl.net

        state.position_qty = 0
        state.entry_blocked = True
        state.sold_today = True   # 功能 12：標記當天已賣過
        state.entry_price = None
        self.on_trade({
            "time": datetime.now().strftime("%H:%M:%S"),
            "code": info.code,
            "name": info.name,
            "action": "SELL",
            "price": sell_price,
            "qty": qty,
            "pnl": pnl_net,
            "realized_total": float(self._today_realized_pnl),
            "note": note,
        })

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

    def _on_broker_fill(self, ev) -> None:
        """成交回報：更新部位、累計損益、推送 trade。"""
        with self._lock:
            state = self._states.get(ev.code)
            if state is None:
                return
            info = state.info
            qty = int(ev.qty)
            if ev.side.value == "BUY":
                state.pending = False
                state.position_qty = qty
                state.entry_price = ev.price
                self._daily_trade_count += 1
                self.on_log("INFO",
                    f"[{ev.code}] 買進成交 {qty} 張 @ {ev.price}，今日第 {self._daily_trade_count} 檔")
                self.on_trade({
                    "time": ev.time.strftime("%H:%M:%S"),
                    "code": ev.code,
                    "name": info.name,
                    "action": "BUY",
                    "price": float(ev.price),
                    "qty": qty,
                    "pnl": 0.0,
                    "note": f"第 {state.candle_index} 根漲停",
                })
            else:  # SELL
                pnl_net = 0.0
                if state.entry_price is not None and qty > 0 and realized_pnl is not None:
                    pnl = realized_pnl(state.entry_price, ev.price, qty, day_trade=True)
                    pnl_net = float(pnl.net)
                    self._today_realized_pnl += pnl.net
                note = getattr(state, "_sell_note", "出場")
                state.position_qty = 0
                state.pending = False
                state.entry_blocked = True
                state.sold_today = True
                state.entry_price = None
                self.on_log("INFO",
                    f"[{ev.code}] 賣出成交 {qty} 張 @ {ev.price}，"
                    f"損益 {pnl_net:+,.0f}")
                self.on_trade({
                    "time": ev.time.strftime("%H:%M:%S"),
                    "code": ev.code,
                    "name": info.name,
                    "action": "SELL",
                    "price": float(ev.price),
                    "qty": qty,
                    "pnl": pnl_net,
                    "realized_total": float(self._today_realized_pnl),
                    "note": note,
                })

    # ─────────────────────────────────────────
    #  狀態彙整（供 UI 輪詢）
    # ─────────────────────────────────────────

    def get_summary(self) -> List[dict]:
        with self._lock:
            result = []
            for code, s in self._states.items():
                # 價格與漲跌計算
                price = float(s.last_price) if s.last_price is not None else None
                prev_close = s.info.prev_close  # float
                if price is not None and prev_close:
                    change = round(price - prev_close, 2)
                    change_pct = round(change / prev_close * 100, 2)
                else:
                    change = None
                    change_pct = None

                result.append({
                    "code":       code,
                    "name":       s.info.name,
                    "market":     s.info.market,
                    "candle":     s.candle_index,
                    "qty":        s.position_qty,
                    "pending":    s.pending,
                    "vol_1s":     s.last_1s_vol,
                    "blocked":    s.entry_blocked,
                    # ── 新增欄位 ──
                    "price":      price,          # 最新成交價（None = 尚無行情）
                    "limit_up":   s.info.limit_up,
                    "prev_close": prev_close,
                    "change":     change,         # 漲跌價差
                    "change_pct": change_pct,     # 漲跌幅 %
                    "ask_qty":    s.ask_qty_at_limit,  # 漲停委賣張數
                    "is_at_limit_up": s.is_at_limit_up,
                })
            return result
