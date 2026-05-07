"""
broker.realtime — 即時行情訂閱抽象層

提供統一的 RealtimeFeed 介面：
- FubonRealtimeFeed：透過 fubon_neo SDK 訂閱 trades + books
- MockRealtimeFeed：本機產生擬真 tick / book 事件，供無憑證 / 測試使用

Engine 端只需註冊 callback，無需區分資料來源。
"""
from __future__ import annotations

import json
import random
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from .errors import FubonNetworkError, FubonNotLoggedInError
from .models import BookEvent, BookLevel, TickEvent

TickCallback = Callable[[TickEvent], None]
BookCallback = Callable[[BookEvent], None]


# ─────────────────────────────────────────────────────────
#  抽象介面
# ─────────────────────────────────────────────────────────

class RealtimeFeed(ABC):
    """所有即時行情來源需實作的最小介面。"""

    def __init__(self) -> None:
        self._tick_cb: Optional[TickCallback] = None
        self._book_cb: Optional[BookCallback] = None

    def on_tick(self, cb: TickCallback) -> None:
        self._tick_cb = cb

    def on_book(self, cb: BookCallback) -> None:
        self._book_cb = cb

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def subscribe(
        self,
        codes: List[str],
        meta: Dict[str, "SymbolMeta"],
    ) -> None:
        """訂閱代碼清單；meta 提供漲停價等資訊（Mock 用，FubonFeed 可忽略）。"""

    def _emit_tick(self, ev: TickEvent) -> None:
        if self._tick_cb is not None:
            try:
                self._tick_cb(ev)
            except Exception as e:  # noqa: BLE001
                print(f"[Realtime] tick callback error: {e}")

    def _emit_book(self, ev: BookEvent) -> None:
        if self._book_cb is not None:
            try:
                self._book_cb(ev)
            except Exception as e:  # noqa: BLE001
                print(f"[Realtime] book callback error: {e}")


@dataclass
class SymbolMeta:
    """訂閱時提供的個股 meta，主要供 Mock feed 產生擬真行情。"""
    code: str
    limit_up: Decimal
    prev_close: Decimal
    open_limit_up: bool = False


# ─────────────────────────────────────────────────────────
#  Mock 實作（無憑證 / 測試）
# ─────────────────────────────────────────────────────────

class MockRealtimeFeed(RealtimeFeed):
    """
    在背景執行緒以隨機方式產生 trade / book 事件，
    行為盡量貼近舊 engine.py 的 random 邏輯，方便 demo 與單元測試。
    """

    def __init__(
        self,
        tick_interval: float = 0.25,
        book_interval: float = 0.5,
    ) -> None:
        super().__init__()
        self._tick_interval = tick_interval
        self._book_interval = book_interval
        self._symbols: Dict[str, SymbolMeta] = {}
        self._cum_volume: Dict[str, int] = {}
        self._at_limit: Dict[str, bool] = {}
        self._running = False
        self._threads: List[threading.Thread] = []
        self._lock = threading.Lock()

    def subscribe(self, codes: List[str], meta: Dict[str, SymbolMeta]) -> None:
        with self._lock:
            for code in codes:
                if code in meta:
                    self._symbols[code] = meta[code]
                    self._cum_volume.setdefault(code, 0)
                    # 開盤即漲停的股票，初始就是漲停狀態
                    self._at_limit[code] = bool(meta[code].open_limit_up)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        t1 = threading.Thread(target=self._tick_loop, daemon=True, name="MockFeed-Tick")
        t2 = threading.Thread(target=self._book_loop, daemon=True, name="MockFeed-Book")
        t1.start()
        t2.start()
        self._threads = [t1, t2]

    def stop(self) -> None:
        self._running = False

    # ── 內部 ────────────────────────────────

    def _tick_loop(self) -> None:
        while self._running:
            try:
                with self._lock:
                    items = list(self._symbols.items())
                for code, meta in items:
                    self._gen_tick(code, meta)
                time.sleep(self._tick_interval)
            except Exception as e:  # noqa: BLE001
                print(f"[MockFeed] tick loop error: {e}")
                time.sleep(0.5)

    def _book_loop(self) -> None:
        while self._running:
            try:
                with self._lock:
                    items = list(self._symbols.items())
                for code, meta in items:
                    self._gen_book(code, meta)
                time.sleep(self._book_interval)
            except Exception as e:  # noqa: BLE001
                print(f"[MockFeed] book loop error: {e}")
                time.sleep(0.5)

    def _gen_tick(self, code: str, meta: SymbolMeta) -> None:
        # 是否進入 / 維持漲停（沿用舊 engine 的概率 0.75 / 0.85）
        at_limit = self._at_limit.get(code, False)
        if not at_limit:
            if random.random() > 0.75:
                at_limit = True
        else:
            if random.random() > 0.85:
                at_limit = False
        self._at_limit[code] = at_limit

        if at_limit:
            price = meta.limit_up
        else:
            # 在漲停價以下浮動
            offset = Decimal(random.randint(-30, 30)) / Decimal(10)
            price = max(meta.prev_close, meta.limit_up - offset)

        vol = random.randint(10, 200)
        self._cum_volume[code] = self._cum_volume.get(code, 0) + vol
        ev = TickEvent(
            code=code,
            time=datetime.now(),
            price=price,
            volume=vol,
            cum_volume=self._cum_volume[code],
            prev_close=meta.prev_close,
        )
        self._emit_tick(ev)

    def _gen_book(self, code: str, meta: SymbolMeta) -> None:
        at_limit = self._at_limit.get(code, False)
        ask: List[BookLevel] = []
        bid: List[BookLevel] = []
        if at_limit:
            # 漲停板掛單：ask[0] 為漲停價，量隨機
            ask.append(BookLevel(price=meta.limit_up, volume=random.randint(5, 130)))
            ask.append(BookLevel(price=meta.limit_up, volume=random.randint(0, 80)))
            # 委買多在漲停一檔下方
            bid.append(BookLevel(
                price=meta.limit_up - Decimal("0.5"),
                volume=random.randint(50, 400),
            ))
        else:
            # 板已打開或尚未漲停：ask[0] 不等於漲停價
            ask.append(BookLevel(
                price=meta.limit_up - Decimal("0.5"),
                volume=random.randint(20, 200),
            ))
            bid.append(BookLevel(
                price=meta.limit_up - Decimal("1"),
                volume=random.randint(20, 200),
            ))
        ev = BookEvent(code=code, time=datetime.now(), ask=ask, bid=bid)
        self._emit_book(ev)


# ─────────────────────────────────────────────────────────
#  Fubon 實作（骨架）
# ─────────────────────────────────────────────────────────

class FubonRealtimeFeed(RealtimeFeed):
    """
    透過 fubon_neo SDK 訂閱 trades + books。
    Milestone 2 提供骨架；實際送出 SDK 訂閱請求的細節，
    待真實環境連線後再驗證並補完訊息解析。
    """

    def __init__(self, adapter, mode: str = "speed") -> None:
        super().__init__()
        self._adapter = adapter
        self._mode = mode
        self._ws = None
        self._subscribed: List[str] = []
        self._started = False
        self._lock = threading.Lock()

    def subscribe(self, codes: List[str], meta: Dict[str, SymbolMeta]) -> None:
        with self._lock:
            self._subscribed = list(dict.fromkeys(codes))
        if self._started:
            self._do_subscribe()

    def start(self) -> None:
        if self._started:
            return
        try:
            sdk = self._adapter.sdk  # 會在未登入時拋 FubonNotLoggedInError
        except FubonNotLoggedInError:
            raise
        try:
            # SDK 介面在不同版本可能略異；以下是常見路徑：
            #   sdk.init_realtime(Mode.Speed)
            #   ws = sdk.marketdata.websocket_client.stock
            init_rt = getattr(sdk, "init_realtime", None)
            if callable(init_rt):
                try:
                    from fubon_neo.constant import Mode  # type: ignore
                    init_rt(Mode.Speed if self._mode == "speed" else Mode.Normal)
                except ImportError:
                    init_rt()
            md = getattr(sdk, "marketdata", None)
            ws_client = getattr(md, "websocket_client", None) if md else None
            self._ws = getattr(ws_client, "stock", None) if ws_client else None
            if self._ws is None:
                raise FubonNetworkError("無法取得 WebSocket client（SDK 介面異常）")

            connect = getattr(self._ws, "connect", None)
            on_msg = getattr(self._ws, "on", None)
            if callable(on_msg):
                # 多個事件全部註冊，方便除錯與訂閱失敗時及早察覺
                on_msg("message", self._on_raw_message)
                on_msg("connect", lambda *a, **k: print("[FubonFeed] websocket connected"))
                on_msg("disconnect",
                       lambda *a, **k: print(f"[FubonFeed] websocket disconnected args={a} kwargs={k}"))
                on_msg("error",
                       lambda *a, **k: print(f"[FubonFeed] websocket error args={a} kwargs={k}"))
            if callable(connect):
                connect()

            self._started = True
            if self._subscribed:
                self._do_subscribe()
        except FubonNetworkError:
            raise
        except Exception as e:  # noqa: BLE001
            raise FubonNetworkError(f"啟動 Fubon WebSocket 失敗：{e}") from e

    def stop(self) -> None:
        if self._ws is None:
            return
        try:
            disconnect = getattr(self._ws, "disconnect", None)
            if callable(disconnect):
                disconnect()
        finally:
            self._ws = None
            self._started = False

    # ── 內部 ────────────────────────────────

    def _do_subscribe(self) -> None:
        if self._ws is None:
            return
        sub = getattr(self._ws, "subscribe", None)
        if not callable(sub):
            print("[FubonFeed] websocket has no subscribe()")
            return
        # 分片 200 / connection
        total = len(self._subscribed)
        ok_chunks = 0
        for i in range(0, total, 200):
            chunk = self._subscribed[i:i + 200]
            try:
                sub({"channel": "trades", "symbols": chunk})
                sub({"channel": "books", "symbols": chunk})
                ok_chunks += 1
            except Exception as e:  # noqa: BLE001
                print(f"[FubonFeed] subscribe error chunk={chunk[:3]}…: {e}")
        print(f"[FubonFeed] subscribed: {total} symbols in {ok_chunks} chunk(s)")

    def _on_raw_message(self, msg) -> None:
        """SDK 推送的訊息（多半是 JSON 字串），依 channel 分派到 tick / book callback。

        實測 fubon_neo Stock WS 推送格式概略為：
          {"event":"data",   "data":{"symbol":"2330","type":"trade","price":...,"size":...}}
          {"event":"snapshot","data":{"symbol":"2330","asks":[...],"bids":[...]}}
          {"event":"data",   "data":{"symbol":"2330","asks":[...],"bids":[...]}}
        舊版亦可能直接以 channel="trades"/"books" 推送。
        因此本函式對多種變體都做容錯解析。
        """
        try:
            payload = self._extract_payload(msg)
            if not payload:
                return

            event = str(payload.get("event") or payload.get("channel") or "").lower()
            data = payload.get("data")
            if isinstance(data, list):
                # 有些訊息 data 是 list（多筆），逐筆派發
                for item in data:
                    self._dispatch(event, item if isinstance(item, dict) else {})
                return
            if not isinstance(data, dict):
                # 沒包 data 欄位時，整個 payload 就是內容
                data = payload
            self._dispatch(event, data)
        except Exception as e:  # noqa: BLE001
            print(f"[FubonFeed] parse error: {e} | raw={str(msg)[:200]}")

    @staticmethod
    def _extract_payload(msg: Any) -> Optional[dict]:
        """把多型訊息（dict / str / 物件）轉成統一的 dict。"""
        if msg is None:
            return None
        if isinstance(msg, dict):
            return msg
        if isinstance(msg, (bytes, bytearray)):
            try:
                msg = msg.decode("utf-8", errors="ignore")
            except Exception:
                return None
        if isinstance(msg, str):
            text = msg.strip()
            if not text:
                return None
            try:
                obj = json.loads(text)
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None
        # 其他物件型別：嘗試讀 .data / .__dict__
        data_attr = getattr(msg, "data", None)
        if isinstance(data_attr, dict):
            return data_attr
        if isinstance(data_attr, str):
            try:
                obj = json.loads(data_attr)
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None
        return getattr(msg, "__dict__", None)

    def _dispatch(self, event: str, data: dict) -> None:
        """依事件名稱 + payload 形狀，派發到 tick / book。"""
        if not isinstance(data, dict):
            return
        type_ = str(data.get("type") or "").lower()

        # ── 判斷是否為 tick（成交） ──
        is_trade_event = event in ("trades", "trade")
        is_trade_type = type_ in ("trade", "trades")
        has_tick_fields = ("price" in data and ("size" in data or "volume" in data)) \
                          and not ("asks" in data or "bids" in data or "ask" in data or "bid" in data)
        if is_trade_event or is_trade_type or has_tick_fields:
            self._emit_tick(self._to_tick(data))
            return

        # ── 判斷是否為 book（五檔） ──
        has_book_fields = any(k in data for k in ("asks", "bids", "ask", "bid"))
        if event in ("books", "book", "snapshot") or has_book_fields:
            self._emit_book(self._to_book(data))
            return

        # event="data" 但沒有可辨識欄位 → 忽略（例如 heartbeat）

    @staticmethod
    def _to_tick(p: dict) -> TickEvent:
        # 價格容錯：price / lastPrice / closePrice / matchPrice
        price_raw = (p.get("price") or p.get("lastPrice")
                     or p.get("closePrice") or p.get("matchPrice") or 0)
        # 量容錯：size / volume / lastSize / qty
        vol_raw = (p.get("size") or p.get("volume")
                   or p.get("lastSize") or p.get("qty") or 0)
        # 累計量容錯
        cum_raw = (p.get("total") or p.get("cum_volume")
                   or p.get("totalVolume") or p.get("accVolume") or 0)
        prev = p.get("prev_close") or p.get("previousClose") or p.get("referencePrice")
        return TickEvent(
            code=str(p.get("symbol") or p.get("code") or ""),
            time=datetime.now(),
            price=Decimal(str(price_raw or 0)),
            volume=int(vol_raw or 0),
            cum_volume=int(cum_raw or 0),
            prev_close=Decimal(str(prev)) if prev else None,
        )

    @staticmethod
    def _to_book(p: dict) -> BookEvent:
        def _levels(items) -> List[BookLevel]:
            out: List[BookLevel] = []
            for it in items or []:
                if not isinstance(it, dict):
                    continue
                price_raw = (it.get("price") or it.get("p") or 0)
                vol_raw = (it.get("size") or it.get("volume") or it.get("v") or 0)
                out.append(BookLevel(
                    price=Decimal(str(price_raw or 0)),
                    volume=int(vol_raw or 0),
                ))
            return out

        # 兼容兩種五檔結構：
        #   1) {"asks":[{price,size},...], "bids":[...]}
        #   2) {"ask":[{price,size},...],  "bid":[...]}
        #   3) 單檔扁平：{"askPrice":..., "askSize":..., "bidPrice":..., "bidSize":...}
        ask_list = p.get("asks") or p.get("ask")
        bid_list = p.get("bids") or p.get("bid")
        ask_levels = _levels(ask_list) if isinstance(ask_list, list) else []
        bid_levels = _levels(bid_list) if isinstance(bid_list, list) else []
        if not ask_levels and ("askPrice" in p or "ask_price" in p):
            ap = p.get("askPrice") or p.get("ask_price") or 0
            av = p.get("askSize") or p.get("ask_size") or p.get("askVolume") or 0
            ask_levels = [BookLevel(price=Decimal(str(ap or 0)), volume=int(av or 0))]
        if not bid_levels and ("bidPrice" in p or "bid_price" in p):
            bp = p.get("bidPrice") or p.get("bid_price") or 0
            bv = p.get("bidSize") or p.get("bid_size") or p.get("bidVolume") or 0
            bid_levels = [BookLevel(price=Decimal(str(bp or 0)), volume=int(bv or 0))]

        return BookEvent(
            code=str(p.get("symbol") or p.get("code") or ""),
            time=datetime.now(),
            ask=ask_levels,
            bid=bid_levels,
        )
