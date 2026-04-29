"""
broker.realtime — 即時行情訂閱抽象層

提供統一的 RealtimeFeed 介面：
- FubonRealtimeFeed：透過 fubon_neo SDK 訂閱 trades + books
- MockRealtimeFeed：本機產生擬真 tick / book 事件，供無憑證 / 測試使用

Engine 端只需註冊 callback，無需區分資料來源。
"""
from __future__ import annotations

import random
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Callable, Dict, List, Optional

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
            if callable(connect):
                connect()

            on_msg = getattr(self._ws, "on", None)
            if callable(on_msg):
                on_msg("message", self._on_raw_message)

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
            return
        # 分片 200 / connection
        for i in range(0, len(self._subscribed), 200):
            chunk = self._subscribed[i:i + 200]
            try:
                sub({"channel": "trades", "symbols": chunk})
                sub({"channel": "books", "symbols": chunk})
            except Exception as e:  # noqa: BLE001
                print(f"[FubonFeed] subscribe error chunk={chunk[:3]}…: {e}")

    def _on_raw_message(self, msg) -> None:
        """SDK 推送的訊息，依 channel 分派至 tick / book callback。"""
        try:
            data = msg if isinstance(msg, dict) else getattr(msg, "data", None) or {}
            channel = data.get("event") or data.get("channel") or ""
            payload = data.get("data") or data
            if channel == "trades" or "price" in payload:
                self._emit_tick(self._to_tick(payload))
            elif channel == "books" or "asks" in payload or "ask" in payload:
                self._emit_book(self._to_book(payload))
        except Exception as e:  # noqa: BLE001
            print(f"[FubonFeed] parse error: {e}")

    @staticmethod
    def _to_tick(p: dict) -> TickEvent:
        return TickEvent(
            code=str(p.get("symbol") or p.get("code") or ""),
            time=datetime.now(),
            price=Decimal(str(p.get("price") or 0)),
            volume=int(p.get("size") or p.get("volume") or 0),
            cum_volume=int(p.get("total") or p.get("cum_volume") or 0),
            prev_close=Decimal(str(p.get("prev_close") or 0)) if p.get("prev_close") else None,
        )

    @staticmethod
    def _to_book(p: dict) -> BookEvent:
        def _levels(items) -> List[BookLevel]:
            out: List[BookLevel] = []
            for it in items or []:
                out.append(BookLevel(
                    price=Decimal(str(it.get("price") or 0)),
                    volume=int(it.get("size") or it.get("volume") or 0),
                ))
            return out

        return BookEvent(
            code=str(p.get("symbol") or p.get("code") or ""),
            time=datetime.now(),
            ask=_levels(p.get("asks") or p.get("ask")),
            bid=_levels(p.get("bids") or p.get("bid")),
        )
