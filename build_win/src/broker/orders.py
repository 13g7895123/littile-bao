"""
broker.orders — 下單 / 改價 / 改量 / 刪單

Milestone 5：
- OrderRequest：跨適配層的下單參數 DTO
- OrderManager (ABC)：place / cancel / modify
- MockOrderManager：以 thread + Timer 模擬委託回報與成交回報
- DryRunOrderManager：登入真實券商與行情，但下單只模擬並寫 audit log
- FubonOrderManager：呼叫 fubon_neo SDK 執行真實下單

委託 / 成交事件透過 BrokerAdapter.dispatch_order / dispatch_fill 廣播給 GUI、引擎。
"""
from __future__ import annotations
import json
import os
import random
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .errors import FubonNotLoggedInError, FubonOrderError
from .models import FillEvent, OrderEvent, OrderSide, OrderStatus


# ─────────────────────────────────────────
#  下單請求
# ─────────────────────────────────────────

@dataclass
class OrderRequest:
    """跨適配層的下單參數。"""
    code: str
    name: str = ""
    side: OrderSide = OrderSide.BUY
    price: Decimal = Decimal("0")     # 限價；市價單可填 0 並設 order_type
    qty: int = 1                       # 張數（一張 = 1000 股）
    order_type: str = "LIMIT"          # LIMIT / MARKET
    time_in_force: str = "ROD"         # ROD / IOC / FOK
    day_trade: bool = True             # 是否現股當沖
    note: str = ""

    def __post_init__(self):
        if self.qty <= 0:
            raise ValueError("qty 必須 > 0")
        if self.order_type == "LIMIT" and self.price <= 0:
            raise ValueError("LIMIT 單必須提供 price > 0")


# ─────────────────────────────────────────
#  抽象介面
# ─────────────────────────────────────────

class OrderManager(ABC):
    @abstractmethod
    def place_order(self, req: OrderRequest) -> str:
        """送出委託，回傳 order_id。"""

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """刪單。"""

    def modify_price(self, order_id: str, new_price: Decimal) -> bool:
        raise NotImplementedError

    def modify_qty(self, order_id: str, new_qty: int) -> bool:
        raise NotImplementedError


# ─────────────────────────────────────────
#  Mock 實作
# ─────────────────────────────────────────

class MockOrderManager(OrderManager):
    """無券商 / Demo 用：以 Timer 模擬委託與成交流程。"""

    def __init__(self, adapter, fill_delay_range=(0.6, 1.8)) -> None:
        self.adapter = adapter
        self.fill_delay_range = fill_delay_range
        self._lock = threading.Lock()
        self._orders: dict[str, OrderRequest] = {}
        self._cancelled: set[str] = set()

    def place_order(self, req: OrderRequest) -> str:
        order_id = f"M{uuid.uuid4().hex[:10].upper()}"
        with self._lock:
            self._orders[order_id] = req

        # 立即送出委託回報
        self.adapter.dispatch_order(OrderEvent(
            order_id=order_id, code=req.code, side=req.side,
            price=req.price, qty=req.qty, filled_qty=0,
            status=OrderStatus.PENDING, time=datetime.now(),
            name=req.name, source="MOCK",
        ))

        # 排程模擬成交
        import random
        delay = random.uniform(*self.fill_delay_range)
        timer = threading.Timer(delay, self._simulate_fill, args=(order_id,))
        timer.daemon = True
        timer.start()
        return order_id

    def _simulate_fill(self, order_id: str) -> None:
        with self._lock:
            req = self._orders.get(order_id)
            if req is None or order_id in self._cancelled:
                return

        now = datetime.now()
        # 委託回報：FILLED
        self.adapter.dispatch_order(OrderEvent(
            order_id=order_id, code=req.code, side=req.side,
            price=req.price, qty=req.qty, filled_qty=req.qty,
            status=OrderStatus.FILLED, time=now,
            name=req.name, source="MOCK",
        ))
        # 成交回報
        self.adapter.dispatch_fill(FillEvent(
            order_id=order_id, code=req.code, name=req.name,
            side=req.side, price=req.price, qty=req.qty, time=now,
        ))

    def cancel_order(self, order_id: str) -> bool:
        with self._lock:
            if order_id not in self._orders:
                return False
            self._cancelled.add(order_id)
            req = self._orders[order_id]

        self.adapter.dispatch_order(OrderEvent(
            order_id=order_id, code=req.code, side=req.side,
            price=req.price, qty=req.qty, filled_qty=0,
            status=OrderStatus.CANCELLED, time=datetime.now(),
            name=req.name, source="MOCK",
        ))
        return True


# ─────────────────────────────────────────
#  Dry-run 實作（真實行情 / 模擬下單）
# ─────────────────────────────────────────

class DryRunOrderManager(OrderManager):
    """登入真實券商但不送單，完整模擬委託與成交並寫入 audit log。"""

    def __init__(
        self,
        adapter,
        fill_delay_range=(0.5, 1.5),
        audit_dir: str = "",
        use_market_price: bool = False,
    ) -> None:
        self.adapter = adapter
        min_delay, max_delay = fill_delay_range
        if min_delay < 0:
            min_delay = 0.0
        if max_delay < min_delay:
            max_delay = min_delay
        self.fill_delay_range = (float(min_delay), float(max_delay))
        self.use_market_price = use_market_price
        self.audit_dir = audit_dir
        self._lock = threading.Lock()
        self._audit_lock = threading.Lock()
        self._orders: dict[str, OrderRequest] = {}
        self._cancelled: set[str] = set()

    def place_order(self, req: OrderRequest) -> str:
        if getattr(self.adapter.state, "value", "") != "connected":
            raise FubonNotLoggedInError("尚未登入券商，無法下單")

        order_id = f"DRY{uuid.uuid4().hex[:10].upper()}"
        with self._lock:
            self._orders[order_id] = req

        now = datetime.now()
        self._write_audit("PLACE", order_id, req, price=req.price, time=now)
        self.adapter.dispatch_order(OrderEvent(
            order_id=order_id, code=req.code, side=req.side,
            price=req.price, qty=req.qty, filled_qty=0,
            status=OrderStatus.PENDING, time=now,
            name=req.name, source="DRY",
        ))

        delay = random.uniform(*self.fill_delay_range)
        timer = threading.Timer(delay, self._simulate_fill, args=(order_id,))
        timer.daemon = True
        timer.start()
        return order_id

    def _simulate_fill(self, order_id: str) -> None:
        with self._lock:
            req = self._orders.get(order_id)
            cancelled = order_id in self._cancelled
        if req is None or cancelled:
            return

        fill_price = self._resolve_fill_price(req)
        now = datetime.now()
        self.adapter.dispatch_order(OrderEvent(
            order_id=order_id, code=req.code, side=req.side,
            price=fill_price, qty=req.qty, filled_qty=req.qty,
            status=OrderStatus.FILLED, time=now,
            name=req.name, source="DRY",
        ))
        self.adapter.dispatch_fill(FillEvent(
            order_id=order_id, code=req.code, name=req.name,
            side=req.side, price=fill_price, qty=req.qty, time=now,
        ))
        self._write_audit("FILL", order_id, req, price=fill_price, time=now)

    def cancel_order(self, order_id: str) -> bool:
        with self._lock:
            req = self._orders.get(order_id)
            if req is None:
                return False
            self._cancelled.add(order_id)

        now = datetime.now()
        self.adapter.dispatch_order(OrderEvent(
            order_id=order_id, code=req.code, side=req.side,
            price=req.price, qty=req.qty, filled_qty=0,
            status=OrderStatus.CANCELLED, time=now,
            name=req.name, source="DRY",
        ))
        self._write_audit("CANCEL", order_id, req, price=req.price, time=now)
        return True

    def _resolve_fill_price(self, req: OrderRequest) -> Decimal:
        if not self.use_market_price:
            return req.price
        getter = getattr(self.adapter, "latest_price", None)
        if callable(getter):
            price = getter(req.code)
            if price is not None:
                return Decimal(str(price))
        return req.price

    def _audit_path(self, day: datetime) -> str:
        base = self.audit_dir or getattr(self.adapter, "dry_run_audit_dir", "")
        if not base:
            if getattr(__import__("sys"), "frozen", False):
                base = os.path.dirname(__import__("sys").executable)
            else:
                base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, f"dry_run_audit_{day:%Y%m%d}.jsonl")

    def _write_audit(self, event_type: str, order_id: str, req: OrderRequest,
                     *, price: Decimal, time: datetime) -> None:
        record = {
            "ts": time.isoformat(timespec="milliseconds"),
            "type": event_type,
            "order_id": order_id,
            "code": req.code,
            "name": req.name,
            "side": req.side.value,
            "price": str(price),
            "qty": req.qty,
            "order_type": req.order_type,
            "time_in_force": req.time_in_force,
            "day_trade": req.day_trade,
            "note": req.note,
            "source": "DRY",
        }
        path = self._audit_path(time)
        with self._audit_lock, open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ─────────────────────────────────────────
#  Fubon 實作骨架
# ─────────────────────────────────────────

class FubonOrderManager(OrderManager):
    """呼叫 fubon_neo SDK 執行真實下單。"""

    def __init__(self, adapter) -> None:
        self.adapter = adapter

    def place_order(self, req: OrderRequest) -> str:
        if self.adapter.state.value != "connected":
            raise FubonNotLoggedInError("尚未登入券商，無法下單")

        try:
            from fubon_neo.constant import (  # type: ignore
                BSAction, OrderType, MarketType, PriceType, TimeInForce,
            )
            from fubon_neo.sdk import Order  # type: ignore
        except ImportError as exc:
            raise FubonOrderError("fubon_neo SDK 未安裝，無法真實下單") from exc

        sdk = self.adapter.sdk
        order = Order(
            buy_sell=BSAction.Buy if req.side == OrderSide.BUY else BSAction.Sell,
            symbol=req.code,
            price=str(req.price),
            quantity=req.qty * 1000,
            market_type=MarketType.Common,
            price_type=PriceType.Limit if req.order_type == "LIMIT" else PriceType.Market,
            time_in_force=getattr(TimeInForce, req.time_in_force, TimeInForce.ROD),
            order_type=OrderType.DayTrade if req.day_trade else OrderType.Stock,
            user_def=req.note[:8] if req.note else "",
        )
        acc = self.adapter.account
        if acc is None:
            raise FubonNotLoggedInError("尚未選擇下單帳號")

        res = sdk.stock.place_order(acc, order)  # type: ignore[attr-defined]
        if not getattr(res, "is_success", False):
            raise FubonOrderError(f"下單失敗：{getattr(res, 'message', '')}")

        order_id = str(getattr(res.data, "order_no", ""))
        return order_id

    def cancel_order(self, order_id: str) -> bool:
        if self.adapter.state.value != "connected":
            raise FubonNotLoggedInError("尚未登入券商")
        sdk = self.adapter.sdk
        acc = self.adapter.account
        res = sdk.stock.cancel_order(acc, order_id)  # type: ignore[attr-defined]
        return bool(getattr(res, "is_success", False))
