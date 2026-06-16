"""
broker.realtime — 即時行情訂閱抽象層

提供統一的 RealtimeFeed 介面：
- FubonRealtimeFeed：透過 fubon_neo SDK 訂閱 trades + books
- MockRealtimeFeed：本機產生擬真 tick / book 事件，供無憑證 / 測試使用

Engine 端只需註冊 callback，無需區分資料來源。
"""
from __future__ import annotations

import json
import logging
import random
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

from .errors import FubonNetworkError, FubonNotLoggedInError
from .models import BookEvent, BookLevel, TickEvent

# ── 模組層級 logger（不干擾 GUI log，寫到 Python logging 體系）──────────
_logger = logging.getLogger("broker.realtime")
_logger.setLevel(logging.DEBUG)  # 確保 DEBUG 訊息不被過濾（root handler 可另行設定）

TickCallback = Callable[[TickEvent], None]
BookCallback = Callable[[BookEvent], None]
DisconnectCallback = Callable[[str], None]

FUBON_REALTIME_SUBSCRIPTION_LIMIT_PER_CONNECTION = 200
FUBON_REALTIME_MAX_CONNECTIONS = 5
FUBON_REALTIME_CHANNELS: Tuple[str, ...] = ("trades", "books")
FUBON_REALTIME_SYMBOL_LIMIT = (
    FUBON_REALTIME_SUBSCRIPTION_LIMIT_PER_CONNECTION
    * FUBON_REALTIME_MAX_CONNECTIONS
    // len(FUBON_REALTIME_CHANNELS)
)


# ─────────────────────────────────────────────────────────
#  抽象介面
# ─────────────────────────────────────────────────────────

class RealtimeFeed(ABC):
    """所有即時行情來源需實作的最小介面。"""

    def __init__(self) -> None:
        self._tick_cb: Optional[TickCallback] = None
        self._book_cb: Optional[BookCallback] = None
        self._log_cb: Optional[Callable[[str, str], None]] = None  # (level, msg)
        self._disconnect_cb: Optional[DisconnectCallback] = None

    def on_tick(self, cb: TickCallback) -> None:
        self._tick_cb = cb

    def on_book(self, cb: BookCallback) -> None:
        self._book_cb = cb

    def set_log_callback(self, cb: Callable[[str, str], None]) -> None:
        """注入 log callback（level, msg），供 GUI push_log 使用。"""
        self._log_cb = cb

    def set_disconnect_callback(self, cb: DisconnectCallback) -> None:
        """注入斷線 callback，供 GUI 執行停策略 / 提示 / 重啟。"""
        self._disconnect_cb = cb

    def _log(self, level: str, msg: str) -> None:
        """同時送往 Python logger 與注入的 GUI callback。"""
        _logger.log(
            {"DEBUG": logging.DEBUG, "INFO": logging.INFO,
             "WARN": logging.WARNING, "ERROR": logging.ERROR}.get(level, logging.DEBUG),
            msg,
        )
        if self._log_cb is not None:
            try:
                self._log_cb(level, msg)
            except Exception:  # noqa: BLE001
                pass

    def _notify_disconnect(self, reason: str) -> None:
        if self._disconnect_cb is not None:
            try:
                self._disconnect_cb(reason)
            except Exception:  # noqa: BLE001
                pass

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
                self._log("ERROR", f"[Realtime] tick callback error: {e}")

    def _emit_book(self, ev: BookEvent) -> None:
        if self._book_cb is not None:
            try:
                self._book_cb(ev)
            except Exception as e:  # noqa: BLE001
                self._log("ERROR", f"[Realtime] book callback error: {e}")


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
        now = datetime.now()
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
            time=now,
            price=price,
            volume=vol,
            api_time=now,
            recv_time=now,
            cum_volume=self._cum_volume[code],
            prev_close=meta.prev_close,
        )
        self._emit_tick(ev)

    def _gen_book(self, code: str, meta: SymbolMeta) -> None:
        now = datetime.now()
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
        ev = BookEvent(code=code, time=now, ask=ask, bid=bid, api_time=now, recv_time=now)
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

    def __init__(self, adapter, mode: str = "speed",
                 channels: Optional[List[str]] = None,
                 ws_client_factory: Optional[Callable[[object, str, int], object]] = None) -> None:
        super().__init__()
        self._adapter = adapter
        self._mode = mode
        self._channels: Tuple[str, ...] = tuple(channels or FUBON_REALTIME_CHANNELS)
        if not self._channels:
            raise ValueError("至少需要一個行情 channel")
        self._ws = None
        self._ws_clients: List[Any] = []
        self._ws_client_factory = ws_client_factory
        self._subscribed: List[str] = []
        self._sdk_token: Optional[str] = None
        self._started = False
        self._lock = threading.Lock()
        # ── 診斷計數器 ──────────────────────────────
        self._raw_msg_count: int = 0        # 收到的原始訊息數
        self._tick_emit_count: int = 0      # 成功 emit 的 tick 數
        self._book_emit_count: int = 0      # 成功 emit 的 book 數
        self._unknown_msg_count: int = 0    # 無法識別的訊息數
        self._empty_code_count: int = 0     # code 解析為空字串的次數
        self._event_name_stats: Dict[str, int] = {}  # event 名稱頻率統計
        # ── 連線計時（量測從 start() 到第一筆資料的延遲）──
        self._t_start_once: Optional[float] = None       # _start_once() 進入時
        self._t_connect_done: Dict[int, float] = {}      # ws#{n} connect() 返回時
        self._t_subscribe_done: Optional[float] = None   # _do_subscribe() 全部送出後
        self._t_first_raw: Optional[float] = None        # 第一筆原始訊息到達時
        self._t_first_tick: Optional[float] = None       # 第一筆有效 tick emit 時
        self._t_first_book: Optional[float] = None       # 第一筆有效 book emit 時
        # ── Phase 1：盤中行情錄製 ──────────────────────
        # 透過 attach_recorder() 注入，未注入時零成本（None 判斷）
        self._recorder: Optional[Any] = None
        self._record_raw: bool = True
        self._stopping = False
        self._disconnect_notified = False

    def attach_recorder(self, recorder: Any, *, record_raw: bool = True) -> None:
        """掛上 RecordingWriter；傳 None 可移除。"""
        self._recorder = recorder
        self._record_raw = bool(record_raw)

    # ── 覆寫 base 的 emit：在分派給 callback 前先順手錄製 ──
    def _emit_tick(self, ev: TickEvent) -> None:
        if self._recorder is not None:
            try:
                self._recorder.write_tick(ev)
            except Exception:
                pass
        super()._emit_tick(ev)

    def _emit_book(self, ev: BookEvent) -> None:
        if self._recorder is not None:
            try:
                self._recorder.write_book(ev)
            except Exception:
                pass
        super()._emit_book(ev)

    @property
    def max_symbols(self) -> int:
        return self._symbols_per_connection() * FUBON_REALTIME_MAX_CONNECTIONS

    def subscribe(self, codes: List[str], meta: Dict[str, SymbolMeta]) -> None:
        unique_codes = list(dict.fromkeys(codes))
        max_symbols = self.max_symbols
        if len(unique_codes) > max_symbols:
            self._log(
                "WARN",
                f"[FubonFeed] realtime symbols capped at {max_symbols}; "
                f"requested={len(unique_codes)}"
            )
            unique_codes = unique_codes[:max_symbols]
        with self._lock:
            self._subscribed = unique_codes
        self._log("INFO", f"[FubonFeed] subscribe() 登記 {len(unique_codes)} 支股票代碼")
        if self._started:
            self._do_subscribe()

    def start(self) -> None:
        if self._started:
            return
        self._stopping = False
        self._disconnect_notified = False
        try:
            self._start_once()
        except FubonNetworkError as e:
            # Fubon SDK 的底層 gRPC 連線會 silently 斷線（session timeout / 同帳號別處登入 /
            # 系統休眠 / 網路抖動），登入狀態看起來正常但 init_realtime() 會丟
            # "Unable to make method calls because underlying connection is closed"。
            # 偵測到此類訊息時，自動觸發一次重新登入並再嘗試一次。
            if self._is_connection_dead_error(e) and self._can_relogin():
                self._log(
                    "WARN",
                    f"[FubonFeed] 偵測到 SDK 底層連線已斷，嘗試重新登入後再啟動：{e}",
                )
                try:
                    self._relogin()
                except Exception as relogin_err:  # noqa: BLE001
                    self.stop()
                    raise FubonNetworkError(
                        f"啟動 Fubon WebSocket 失敗（重新登入也失敗）：{relogin_err}"
                    ) from relogin_err
                # 重新登入成功後再試一次（只重試一次，避免無限迴圈）
                self._start_once()
            else:
                raise

    def _start_once(self) -> None:
        """單次啟動嘗試；任何錯誤都包成 FubonNetworkError 拋出。"""
        try:
            sdk = self._adapter.sdk  # 會在未登入時拋 FubonNotLoggedInError
        except FubonNotLoggedInError:
            raise
        try:
            self._t_start_once = time.perf_counter()
            t0_wall = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self._log("INFO", f"[FubonFeed] 啟動中，模式={self._mode}，channels={self._channels}，時刻={t0_wall}")
            init_rt = getattr(sdk, "init_realtime", None)
            if callable(init_rt):
                t_init = time.perf_counter()
                try:
                    init_rt(self._resolve_mode())
                except ImportError:
                    init_rt()
                self._log("INFO", f"[FubonFeed] init_realtime() 完成，耗時 {(time.perf_counter()-t_init)*1000:.0f} ms")

            self._ensure_ws_clients(sdk, self._required_connection_count())
            self._started = True
            elapsed = (time.perf_counter() - self._t_start_once) * 1000
            self._log("INFO", f"[FubonFeed] WebSocket clients 建立完成，共 {len(self._ws_clients)} 條連線，至此累計 {elapsed:.0f} ms")
            if self._subscribed:
                self._do_subscribe()
        except FubonNetworkError:
            self.stop()
            raise
        except Exception as e:  # noqa: BLE001
            self.stop()
            raise FubonNetworkError(f"啟動 Fubon WebSocket 失敗：{e}") from e

    @staticmethod
    def _is_connection_dead_error(err: Exception) -> bool:
        """判斷錯誤是否屬於『SDK 底層連線已死、需重登入』類型。"""
        # 從最外層往內看所有 cause / context 的訊息
        seen = set()
        cur: Optional[BaseException] = err
        while cur is not None and id(cur) not in seen:
            seen.add(id(cur))
            msg = str(cur).lower()
            if (
                "underlying connection is closed" in msg
                or "login error" in msg and "connection" in msg
                or "channel closed" in msg
                or "not connected" in msg
            ):
                return True
            cur = cur.__cause__ or cur.__context__
        return False

    def _can_relogin(self) -> bool:
        adapter = self._adapter
        return adapter is not None and hasattr(adapter, "login") and callable(getattr(adapter, "login"))

    def _relogin(self) -> None:
        """強制 adapter 重新登入；先清掉舊 SDK 物件再呼叫 login()。"""
        adapter = self._adapter
        # 嘗試先登出（忽略失敗），再清空狀態，最後重新登入
        try:
            logout = getattr(adapter, "logout", None)
            if callable(logout):
                logout()
        except Exception:  # noqa: BLE001
            pass
        # 重置本物件的 ws 狀態，避免殘留
        self._ws_clients = []
        self._ws = None
        self._sdk_token = None
        self._started = False
        self._disconnect_notified = False
        adapter.login()
        self._log("INFO", "[FubonFeed] 重新登入完成")

    def stop(self) -> None:
        if not self._ws_clients and self._ws is None:
            return
        self._stopping = True
        try:
            clients = list(self._ws_clients) or ([self._ws] if self._ws is not None else [])
            for ws in clients:
                disconnect = getattr(ws, "disconnect", None)
                if callable(disconnect):
                    disconnect()
        finally:
            self._ws_clients = []
            self._ws = None
            self._sdk_token = None
            self._started = False
            self._disconnect_notified = False

    # ── 內部 ────────────────────────────────

    def _do_subscribe(self) -> None:
        if not self._ws_clients:
            self._log("WARN", "[FubonFeed] _do_subscribe() 但 _ws_clients 為空，略過")
            return
        try:
            self._ensure_ws_clients(self._adapter.sdk, self._required_connection_count())
        except Exception as e:  # noqa: BLE001
            self._log("ERROR", f"[FubonFeed] websocket client expand failed: {e}")
            return

        chunks = self._symbol_chunks()
        ok_chunks = 0
        for index, chunk in enumerate(chunks):
            ws = self._ws_clients[index]
            sub = getattr(ws, "subscribe", None)
            if not callable(sub):
                self._log("WARN", f"[FubonFeed] websocket #{index + 1} has no subscribe()")
                continue
            try:
                for channel in self._channels:
                    sub({"channel": channel, "symbols": chunk})
                ok_chunks += 1
                self._log(
                    "DEBUG",
                    f"[FubonFeed] ws#{index+1} 訂閱 channels={self._channels} "
                    f"前3支={chunk[:3]}… 共{len(chunk)}支",
                )
            except Exception as e:  # noqa: BLE001
                self._log("ERROR", f"[FubonFeed] subscribe error ws=#{index + 1} chunk={chunk[:3]}…: {e}")
        self._t_subscribe_done = time.perf_counter()
        elapsed_sub = (self._t_subscribe_done - self._t_start_once) * 1000 if self._t_start_once else 0
        t_wall = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self._log(
            "INFO",
            f"[FubonFeed] 訂閱完成：{len(self._subscribed)} 支 × {len(self._channels)} channels"
            f"，{ok_chunks}/{len(chunks)} 條連線成功"
            f"，時刻={t_wall}，從 start 累計={elapsed_sub:.0f} ms"
            f"（等待伺服器開始推送行情…）"
        )

    def _symbols_per_connection(self) -> int:
        return FUBON_REALTIME_SUBSCRIPTION_LIMIT_PER_CONNECTION // len(self._channels)

    def _symbol_chunks(self) -> List[List[str]]:
        per_connection = self._symbols_per_connection()
        return [
            self._subscribed[index:index + per_connection]
            for index in range(0, len(self._subscribed), per_connection)
        ]

    def _required_connection_count(self) -> int:
        chunks = len(self._symbol_chunks())
        return max(1, min(FUBON_REALTIME_MAX_CONNECTIONS, chunks))

    def _ensure_ws_clients(self, sdk, required_count: int) -> None:
        while len(self._ws_clients) < required_count:
            index = len(self._ws_clients)
            ws = self._create_stock_ws_client(sdk, index)
            if ws is None:
                raise FubonNetworkError("無法取得 WebSocket client（SDK 介面異常）")
            self._register_ws_handlers(ws, index)
            connect = getattr(ws, "connect", None)
            if callable(connect):
                t_conn = time.perf_counter()
                t_wall = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                self._log("INFO", f"[FubonFeed] ws#{index+1} connect() 開始，時刻={t_wall}")
                connect()
                elapsed_conn = (time.perf_counter() - t_conn) * 1000
                elapsed_total = (time.perf_counter() - self._t_start_once) * 1000 if self._t_start_once else 0
                t_wall2 = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                self._t_connect_done[index] = time.perf_counter()
                self._log("INFO",
                    f"[FubonFeed] ws#{index+1} connect() 完成（含認證），"
                    f"時刻={t_wall2}，connect 耗時={elapsed_conn:.0f} ms，"
                    f"從 start 累計={elapsed_total:.0f} ms")
            self._ws_clients.append(ws)
            if self._ws is None:
                self._ws = ws

    def _create_stock_ws_client(self, sdk, index: int):
        if self._ws_client_factory is not None:
            return self._ws_client_factory(self._adapter, self._mode, index)
        if index == 0:
            existing = self._existing_stock_ws_client(sdk)
            if existing is not None:
                return existing
        built = self._build_stock_ws_client(sdk)
        if built is not None:
            return built
        if index > 0:
            raise FubonNetworkError(
                "SDK 未提供 build_websocket_client / realtime token，無法建立多條行情連線"
            )
        return None

    @staticmethod
    def _existing_stock_ws_client(sdk):
        md = getattr(sdk, "marketdata", None)
        ws_client = getattr(md, "websocket_client", None) if md else None
        return getattr(ws_client, "stock", None) if ws_client else None

    def _build_stock_ws_client(self, sdk):
        try:
            from fubon_neo.adapter import build_websocket_client  # type: ignore
        except ImportError:
            return None
        token = self._realtime_token(sdk)
        wrapper = build_websocket_client(self._resolve_mode(), token)
        return getattr(wrapper, "stock", None)

    def _realtime_token(self, sdk) -> str:
        if self._sdk_token:
            return self._sdk_token
        exchange = getattr(sdk, "exchange_realtime_token", None)
        if callable(exchange):
            self._sdk_token = str(exchange())
            return self._sdk_token
        for attr in ("sdk_token", "_sdk_token", "token", "access_token"):
            value = getattr(sdk, attr, None)
            if value:
                self._sdk_token = str(value)
                return self._sdk_token
        raise FubonNetworkError("無法取得 realtime token，無法建立額外 WebSocket 連線")

    def _resolve_mode(self):
        try:
            from fubon_neo.constant import Mode  # type: ignore
        except ImportError:
            from fubon_neo.adapter import Mode  # type: ignore
        return Mode.Speed if self._mode == "speed" else Mode.Normal

    def _register_ws_handlers(self, ws, index: int) -> None:
        on_msg = getattr(ws, "on", None)
        if not callable(on_msg):
            self._log("WARN", f"[FubonFeed] ws#{index+1} 無 on() 方法，無法掛載事件處理器！")
            return
        on_msg("message", self._on_raw_message)
        on_msg("connect", lambda *args, _index=index, **kwargs:
               self._log("INFO", f"[FubonFeed] websocket #{_index + 1} connected"))
        on_msg("disconnect", lambda *args, _index=index, **kwargs:
               self._handle_ws_disconnect(_index, args, kwargs))
        on_msg("error", lambda *args, _index=index, **kwargs:
               self._handle_ws_error(_index, args, kwargs))
        self._log("INFO", f"[FubonFeed] ws#{index+1} 事件處理器已掛載（message/connect/disconnect/error）")

    def _handle_ws_disconnect(self, index: int, args: tuple, kwargs: dict) -> None:
        msg = f"[FubonFeed] websocket #{index + 1} disconnected args={args} kwargs={kwargs}"
        if self._stopping:
            self._log("INFO", f"{msg} (ignored during stop)")
            return
        self._log("WARN", msg)
        self._notify_disconnect_once(msg)

    def _handle_ws_error(self, index: int, args: tuple, kwargs: dict) -> None:
        msg = f"[FubonFeed] websocket #{index + 1} error args={args} kwargs={kwargs}"
        self._log("ERROR", msg)
        if self._stopping:
            return
        if self._is_disconnect_like_message(msg):
            self._notify_disconnect_once(msg)

    def _notify_disconnect_once(self, reason: str) -> None:
        if self._disconnect_notified:
            self._log("INFO", f"[FubonFeed] 已通知過斷線事件，略過重複上拋：{reason}")
            return
        self._disconnect_notified = True
        self._notify_disconnect(reason)

    @staticmethod
    def _is_disconnect_like_message(text: object) -> bool:
        msg = str(text).lower()
        keywords = (
            "disconnect",
            "connection closed",
            "connection is closed",
            "channel closed",
            "connection timed out",
            "timed out",
            "remote host was lost",
            "forcibly closed",
            "underlying connection is closed",
            "not connected",
            "強制關閉",
            "連線已中斷",
            "連線中斷",
            "逾時",
        )
        return any(keyword in msg for keyword in keywords)

    def _on_raw_message(self, msg) -> None:
        """SDK 推送的訊息（多半是 JSON 字串），依 channel 分派到 tick / book callback。"""
        self._raw_msg_count += 1
        n = self._raw_msg_count

        # ── 第一筆原始訊息：記錄到達時刻與延遲 ──
        if n == 1:
            self._t_first_raw = time.perf_counter()
            t_wall = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            delay_from_sub = (
                (self._t_first_raw - self._t_subscribe_done) * 1000
                if self._t_subscribe_done else None
            )
            delay_from_start = (
                (self._t_first_raw - self._t_start_once) * 1000
                if self._t_start_once else None
            )
            self._log(
                "INFO",
                f"[FubonFeed][計時] 第 1 筆原始訊息到達！"
                f" 時刻={t_wall}"
                + (f"，距訂閱送出={delay_from_sub:.0f} ms" if delay_from_sub is not None else "")
                + (f"，距 start()={delay_from_start:.0f} ms" if delay_from_start is not None else "")
            )

        # ── Phase 1：錄製原始訊息（不阻塞主流程，內部走 queue+thread） ──
        if self._recorder is not None and self._record_raw:
            try:
                self._recorder.write_raw(msg)
            except Exception:
                # 錄製失敗絕不可影響行情處理
                pass

        # 前 3 筆：完整 log 原始內容
        if n <= 3:
            self._log("DEBUG", f"[FubonFeed] 收到第 {n} 筆原始訊息 type={type(msg).__name__} raw={str(msg)[:300]}")
        elif n % 200 == 0:
            self._log("DEBUG",
                f"[FubonFeed] 累計收訊 {n} 筆 "
                f"（tick_emit={self._tick_emit_count}, book_emit={self._book_emit_count}, "
                f"unknown={self._unknown_msg_count}, empty_code={self._empty_code_count}）")
            # 同時印出未識別 event 名稱的次數統計，協助找出真正的 trade event 名
            if self._event_name_stats:
                top = sorted(self._event_name_stats.items(), key=lambda kv: -kv[1])[:8]
                self._log("DEBUG",
                    f"[FubonFeed] event 統計 top8 = {top}")

        try:
            payload = self._extract_payload(msg)
            if not payload:
                if n <= 3:
                    self._log("DEBUG", f"[FubonFeed] 第 {n} 筆訊息 _extract_payload 回傳空值，略過")
                return

            # ── 抽取 event / channel 名稱（富邦：event='data', channel='trades' or 'books'）──
            raw_event = str(payload.get("event") or "").lower()
            raw_channel = str(payload.get("channel") or "").lower()
            # 統計 event 名稱頻率
            stat_key = f"{raw_event}|{raw_channel}" if raw_channel else raw_event
            self._event_name_stats[stat_key] = self._event_name_stats.get(stat_key, 0) + 1

            # ── 控制 / metadata 類訊息：以 raw_event 為準直接略過 ──
            # 富邦會用 channel='trades' 同時夾帶 event='ticker'（個股基本資料推播）、
            # event='subscribed' / 'unsubscribed' 等控制訊息，這些不能被當成成交 tick。
            if raw_event in ("authenticated", "heartbeat", "pong", "subscribed",
                             "unsubscribed", "ticker", "error", "info"):
                return

            # 富邦標準資料格式：event='data' + channel='trades'|'books'，用 channel 取代 event 來判斷
            event = raw_channel or raw_event

            data = payload.get("data")
            if isinstance(data, list):
                for item in data:
                    self._dispatch(event, item if isinstance(item, dict) else {})
                return
            if not isinstance(data, dict):
                data = payload
            self._dispatch(event, data)
        except Exception as e:  # noqa: BLE001
            self._log("ERROR", f"[FubonFeed] parse error: {e} | raw={str(msg)[:200]}")

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

        # ── 控制 / metadata 訊息（不算 unknown） ─────────────
        # 富邦初始會推 ticker (個股基本資料)、subscribed (訂閱確認)、authenticated、heartbeat、pong
        # 第二道防線：以 payload 形狀判斷 ticker（含個股基本資料、無成交價量）
        # 特徵：有 limitUpPrice/referencePrice/securityStatus，但完全沒有 price/size
        is_ticker_payload = (
            ("limitUpPrice" in data or "referencePrice" in data
             or "securityStatus" in data or "boardLot" in data)
            and ("price" not in data and "size" not in data
                 and "lastPrice" not in data)
        )
        if is_ticker_payload:
            return
        if event in ("authenticated", "heartbeat", "pong", "subscribed",
                     "unsubscribed", "ticker", "error", "info"):
            return

        # ── 判斷是否為 tick（成交） ──
        is_trade_event = event in ("trades", "trade")
        is_trade_type = type_ in ("trade", "trades")
        has_tick_fields = ("price" in data and ("size" in data or "volume" in data)) \
                          and not ("asks" in data or "bids" in data or "ask" in data or "bid" in data)
        if is_trade_event or is_trade_type or has_tick_fields:
            # ── 首 3 筆 trade 原始資料 dump（除錯用，幫忙確認 SDK 欄位名稱）──
            self._trade_dump_count = getattr(self, "_trade_dump_count", 0) + 1
            if self._trade_dump_count <= 3:
                self._log(
                    "DEBUG",
                    f"[FubonFeed] 第 {self._trade_dump_count} 筆 trade 原始 data "
                    f"keys={list(data.keys())} sample={str(data)[:300]}"
                )
            tick = self._to_tick(data)
            if not tick.code:
                self._empty_code_count += 1
                if self._empty_code_count <= 3 or self._empty_code_count % 50 == 0:
                    self._log(
                        "WARN",
                        f"[FubonFeed] tick code 解析為空（共 {self._empty_code_count} 次）"
                        f"，data keys={list(data.keys())} sample={str(data)[:200]}"
                    )
            elif tick.price is None or tick.price <= 0:
                # 解析成功但價格為 0：常見於盤前試撮，仍 emit 讓 engine 自己過濾
                self._tick_zero_price_count = getattr(self, "_tick_zero_price_count", 0) + 1
                if self._tick_zero_price_count <= 3 or self._tick_zero_price_count % 200 == 0:
                    self._log(
                        "WARN",
                        f"[FubonFeed] tick price=0 解析（共 {self._tick_zero_price_count} 筆）"
                        f" code={tick.code} data keys={list(data.keys())} sample={str(data)[:200]}"
                    )
            else:
                self._tick_emit_count += 1
                if self._tick_emit_count == 1:
                    self._t_first_tick = time.perf_counter()
                    t_wall = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    delay_from_sub = (
                        (self._t_first_tick - self._t_subscribe_done) * 1000
                        if self._t_subscribe_done else None
                    )
                    delay_from_start = (
                        (self._t_first_tick - self._t_start_once) * 1000
                        if self._t_start_once else None
                    )
                    self._log(
                        "INFO",
                        f"[FubonFeed][計時] 第 1 筆有效 tick emit！"
                        f" 時刻={t_wall}"
                        f" code={tick.code} price={tick.price} vol={tick.volume}"
                        + (f"，距訂閱送出={delay_from_sub:.0f} ms" if delay_from_sub is not None else "")
                        + (f"，距 start()={delay_from_start:.0f} ms" if delay_from_start is not None else "")
                    )
                elif self._tick_emit_count % 500 == 0:
                    self._log("DEBUG",
                        f"[FubonFeed] tick emit 累計 {self._tick_emit_count} 筆")
            self._emit_tick(tick)
            return

        # ── 判斷是否為 book（五檔） ──
        has_book_fields = any(k in data for k in ("asks", "bids", "ask", "bid"))
        if event in ("books", "book", "snapshot") or has_book_fields:
            book = self._to_book(data)
            self._book_emit_count += 1
            if self._book_emit_count == 1:
                self._t_first_book = time.perf_counter()
                t_wall = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                delay_from_sub = (
                    (self._t_first_book - self._t_subscribe_done) * 1000
                    if self._t_subscribe_done else None
                )
                delay_from_start = (
                    (self._t_first_book - self._t_start_once) * 1000
                    if self._t_start_once else None
                )
                self._log(
                    "INFO",
                    f"[FubonFeed][計時] 第 1 筆有效 book emit！"
                    f" 時刻={t_wall}"
                    f" code={book.code} ask_len={len(book.ask)} bid_len={len(book.bid)}"
                    + (f"，距訂閱送出={delay_from_sub:.0f} ms" if delay_from_sub is not None else "")
                    + (f"，距 start()={delay_from_start:.0f} ms" if delay_from_start is not None else "")
                )
            self._emit_book(book)
            return

        # 無法識別
        self._unknown_msg_count += 1
        if self._unknown_msg_count <= 5 or self._unknown_msg_count % 100 == 0:
            self._log(
                "WARN",
                f"[FubonFeed] 無法識別訊息（共 {self._unknown_msg_count} 次）"
                f" event={event!r} type={type_!r} keys={list(data.keys())} data={str(data)[:200]}"
            )

    @staticmethod
    def _parse_api_datetime(value: Any) -> Optional[datetime]:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            raw = float(value)
        else:
            text = str(value).strip()
            if not text:
                return None
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                try:
                    raw = float(text)
                except ValueError:
                    return None

        abs_raw = abs(raw)
        if abs_raw >= 1_000_000_000_000_000_000:
            seconds = raw / 1_000_000_000
        elif abs_raw >= 1_000_000_000_000_000:
            seconds = raw / 1_000_000
        elif abs_raw >= 1_000_000_000_000:
            seconds = raw / 1_000
        else:
            seconds = raw
        try:
            return datetime.fromtimestamp(seconds)
        except (OverflowError, OSError, ValueError):
            return None

    @staticmethod
    def _to_tick(p: dict) -> TickEvent:
        recv_time = datetime.now()
        api_time = FubonRealtimeFeed._parse_api_datetime(
            p.get("time") or p.get("timestamp") or p.get("matchTime") or p.get("tradeTime")
        )
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
        bid_raw = p.get("bid")
        ask_raw = p.get("ask")
        return TickEvent(
            code=str(p.get("symbol") or p.get("code") or ""),
            time=api_time or recv_time,
            price=Decimal(str(price_raw or 0)),
            volume=int(vol_raw or 0),
            api_time=api_time,
            recv_time=recv_time,
            cum_volume=int(cum_raw or 0),
            prev_close=Decimal(str(prev)) if prev else None,
            bid=Decimal(str(bid_raw)) if bid_raw not in (None, "") else None,
            ask=Decimal(str(ask_raw)) if ask_raw not in (None, "") else None,
            is_limit_up_price=(
                bool(p.get("isLimitUpPrice"))
                if "isLimitUpPrice" in p else None
            ),
            is_limit_up_bid=(
                bool(p.get("isLimitUpBid"))
                if "isLimitUpBid" in p else None
            ),
            is_limit_up_ask=(
                bool(p.get("isLimitUpAsk"))
                if "isLimitUpAsk" in p else None
            ),
            is_trial=bool(p.get("isTrial")) if "isTrial" in p else None,
            is_backfill=bool(p.get("is_backfill")) if "is_backfill" in p else None,
        )

    @staticmethod
    def _to_book(p: dict) -> BookEvent:
        recv_time = datetime.now()
        api_time = FubonRealtimeFeed._parse_api_datetime(
            p.get("time") or p.get("timestamp") or p.get("matchTime") or p.get("tradeTime")
        )

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
            time=api_time or recv_time,
            ask=ask_levels,
            bid=bid_levels,
            api_time=api_time,
            recv_time=recv_time,
            is_backfill=bool(p.get("is_backfill")) if "is_backfill" in p else None,
        )
