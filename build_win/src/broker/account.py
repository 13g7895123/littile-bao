"""
broker.account — 帳戶 / 庫存 / 買進力查詢

Milestone 6：
- Position：庫存單檔 DTO
- AccountSnapshot：帳戶總覽（買進力、現金、庫存清單、總損益）
- AccountService（ABC）：snapshot()、start_polling()、stop()
- MockAccountService：以本地累計值產生假資料
- FubonAccountService：呼叫 fubon_neo SDK accounting / inventories API

GUI 端可呼叫 `broker.account_service().start_polling(callback, interval=10.0)`
即可每 10 秒取得最新 AccountSnapshot 並更新儀表板。
"""
from __future__ import annotations
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Callable, Dict, List, Optional

from .errors import FubonNotLoggedInError


@dataclass
class Position:
    code: str
    name: str
    qty: int                      # 張數
    avg_cost: Decimal
    last_price: Decimal = Decimal("0")
    market_value: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    unrealized_pnl_pct: Decimal = Decimal("0")


@dataclass
class AccountSnapshot:
    cash: Decimal = Decimal("0")
    buying_power: Decimal = Decimal("0")
    today_realized_pnl: Decimal = Decimal("0")
    total_unrealized_pnl: Decimal = Decimal("0")
    positions: List[Position] = field(default_factory=list)
    updated_at: datetime = field(default_factory=datetime.now)


SnapshotCallback = Callable[[AccountSnapshot], None]


class AccountService(ABC):
    @abstractmethod
    def snapshot(self) -> AccountSnapshot: ...

    def start_polling(self, callback: SnapshotCallback, interval: float = 10.0) -> None:
        """以背景執行緒每 interval 秒呼叫一次 snapshot 並回呼。"""
        self._poll_stop = threading.Event()
        self._poll_cb = callback

        def _loop():
            while not self._poll_stop.is_set():
                try:
                    snap = self.snapshot()
                    callback(snap)
                except Exception:  # noqa: BLE001
                    pass
                self._poll_stop.wait(interval)

        t = threading.Thread(target=_loop, daemon=True)
        t.start()
        self._poll_thread = t

    def stop(self) -> None:
        ev = getattr(self, "_poll_stop", None)
        if ev is not None:
            ev.set()


class MockAccountService(AccountService):
    """Mock：給定起始買進力，依目前部位推估市值。"""

    def __init__(self, initial_cash: Decimal = Decimal("1000000")) -> None:
        self._cash = initial_cash
        self._positions: List[Position] = []

    def set_positions(self, positions: List[Position]) -> None:
        self._positions = positions

    def snapshot(self) -> AccountSnapshot:
        total_unr = sum((p.unrealized_pnl for p in self._positions), Decimal("0"))
        market = sum((p.market_value for p in self._positions), Decimal("0"))
        return AccountSnapshot(
            cash=self._cash,
            buying_power=self._cash,  # 簡化：現股，買進力=現金
            total_unrealized_pnl=total_unr,
            positions=list(self._positions),
            updated_at=datetime.now(),
        )


class DryRunAccountService(AccountService):
    """Overlay DRY fills on top of a real account snapshot.

    Fubon dry-run does not send orders to the broker, so broker-side buying
    power and inventories will not change. This service keeps a local overlay
    so the GUI and strategy buying-power checks reflect simulated fills.
    """

    def __init__(self, base: AccountService) -> None:
        self.base = base
        self._lock = threading.Lock()
        self._cash_delta = Decimal("0")
        self._positions: Dict[str, Position] = {}

    def apply_fill(self, ev) -> None:
        shares = Decimal(int(ev.qty) * 1000)
        amount = Decimal(str(ev.price)) * shares
        with self._lock:
            side = str(getattr(ev.side, "value", ev.side) or "").upper()
            if side == "BUY":
                self._cash_delta -= amount
                self._add_position(ev)
            elif side == "SELL":
                self._cash_delta += amount
                self._reduce_position(ev)

    def snapshot(self) -> AccountSnapshot:
        base_snap = self.base.snapshot()
        with self._lock:
            cash_delta = self._cash_delta
            overlay_positions = {
                code: Position(
                    code=p.code,
                    name=p.name,
                    qty=p.qty,
                    avg_cost=p.avg_cost,
                    last_price=p.last_price,
                    market_value=p.market_value,
                    unrealized_pnl=p.unrealized_pnl,
                    unrealized_pnl_pct=p.unrealized_pnl_pct,
                )
                for code, p in self._positions.items()
            }

        merged = {p.code: p for p in base_snap.positions}
        for code, overlay in overlay_positions.items():
            base = merged.get(code)
            if base is None:
                merged[code] = overlay
                continue
            total_qty = base.qty + overlay.qty
            if total_qty <= 0:
                merged.pop(code, None)
                continue
            avg_cost = (
                base.avg_cost * Decimal(base.qty)
                + overlay.avg_cost * Decimal(overlay.qty)
            ) / Decimal(total_qty)
            last_price = overlay.last_price or base.last_price
            shares = Decimal(total_qty * 1000)
            market_value = last_price * shares
            unrealized = (last_price - avg_cost) * shares
            pct = (last_price - avg_cost) / avg_cost * Decimal("100") if avg_cost > 0 else Decimal("0")
            merged[code] = Position(
                code=code,
                name=base.name or overlay.name,
                qty=total_qty,
                avg_cost=avg_cost,
                last_price=last_price,
                market_value=market_value,
                unrealized_pnl=unrealized,
                unrealized_pnl_pct=pct,
            )

        positions = list(merged.values())
        return AccountSnapshot(
            cash=base_snap.cash + cash_delta,
            buying_power=base_snap.buying_power + cash_delta,
            today_realized_pnl=base_snap.today_realized_pnl,
            total_unrealized_pnl=sum((p.unrealized_pnl for p in positions), Decimal("0")),
            positions=positions,
            updated_at=datetime.now(),
        )

    def _add_position(self, ev) -> None:
        existing = self._positions.get(ev.code)
        if existing is None:
            price = Decimal(str(ev.price))
            shares = Decimal(int(ev.qty) * 1000)
            self._positions[ev.code] = Position(
                code=ev.code,
                name=ev.name or ev.code,
                qty=int(ev.qty),
                avg_cost=price,
                last_price=price,
                market_value=price * shares,
                unrealized_pnl=Decimal("0"),
                unrealized_pnl_pct=Decimal("0"),
            )
            return
        total_qty = existing.qty + int(ev.qty)
        if total_qty <= 0:
            self._positions.pop(ev.code, None)
            return
        price = Decimal(str(ev.price))
        avg = (
            existing.avg_cost * Decimal(existing.qty)
            + price * Decimal(int(ev.qty))
        ) / Decimal(total_qty)
        existing.qty = total_qty
        existing.avg_cost = avg
        existing.last_price = price
        existing.market_value = price * Decimal(total_qty * 1000)
        existing.unrealized_pnl = (price - avg) * Decimal(total_qty * 1000)
        existing.unrealized_pnl_pct = (
            (price - avg) / avg * Decimal("100") if avg > 0 else Decimal("0")
        )

    def _reduce_position(self, ev) -> None:
        existing = self._positions.get(ev.code)
        if existing is None:
            return
        existing.qty = max(0, existing.qty - int(ev.qty))
        if existing.qty <= 0:
            self._positions.pop(ev.code, None)
            return
        price = Decimal(str(ev.price))
        existing.last_price = price
        existing.market_value = price * Decimal(existing.qty * 1000)
        existing.unrealized_pnl = (price - existing.avg_cost) * Decimal(existing.qty * 1000)
        existing.unrealized_pnl_pct = (
            (price - existing.avg_cost) / existing.avg_cost * Decimal("100")
            if existing.avg_cost > 0 else Decimal("0")
        )


class FubonAccountService(AccountService):
    """呼叫 fubon_neo SDK 取得真實帳戶資料。"""

    def __init__(self, adapter) -> None:
        self.adapter = adapter

    @staticmethod
    def _int_attr(item, name: str) -> int:
        value = getattr(item, name, 0) or 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _inventory_qty_shares(cls, item) -> int:
        today_qty = cls._int_attr(item, "today_qty")
        if today_qty > 0:
            return today_qty

        tradable_qty = cls._int_attr(item, "tradable_qty")
        if tradable_qty > 0:
            return tradable_qty

        lastday_qty = cls._int_attr(item, "lastday_qty")
        buy_filled_qty = cls._int_attr(item, "buy_filled_qty")
        sell_filled_qty = cls._int_attr(item, "sell_filled_qty")
        return max(0, lastday_qty + buy_filled_qty - sell_filled_qty)

    def snapshot(self) -> AccountSnapshot:
        if self.adapter.state.value != "connected":
            raise FubonNotLoggedInError("尚未登入券商")
        sdk = self.adapter.sdk
        acc = self.adapter.account
        if acc is None:
            raise FubonNotLoggedInError("尚未選擇下單帳號")

        snap = AccountSnapshot()
        # 庫存
        try:
            inv_res = sdk.accounting.inventories(acc)  # type: ignore[attr-defined]
            data = getattr(inv_res, "data", []) or []
            positions: List[Position] = []
            for item in data:
                code = str(getattr(item, "stock_no", "") or "")
                qty_shares = self._inventory_qty_shares(item)
                qty_lots = qty_shares // 1000
                if qty_lots <= 0:
                    continue
                avg = Decimal(str(getattr(item, "cost_price", 0) or 0))
                last = Decimal(str(getattr(item, "last_price", 0) or 0))
                mv = last * Decimal(qty_shares)
                upnl = (last - avg) * Decimal(qty_shares)
                upnl_pct = (
                    (last - avg) / avg * Decimal("100") if avg > 0 else Decimal("0")
                )
                positions.append(Position(
                    code=code,
                    name=str(getattr(item, "stock_name", "") or ""),
                    qty=qty_lots,
                    avg_cost=avg,
                    last_price=last,
                    market_value=mv,
                    unrealized_pnl=upnl,
                    unrealized_pnl_pct=upnl_pct,
                ))
            snap.positions = positions
            snap.total_unrealized_pnl = sum(
                (p.unrealized_pnl for p in positions), Decimal("0")
            )
        except Exception:  # noqa: BLE001
            pass

        # 帳務（買進力 / 現金）
        try:
            acc_res = sdk.accounting.bank_remain(acc)  # type: ignore[attr-defined]
            d = getattr(acc_res, "data", None)
            if d is not None:
                snap.cash = Decimal(str(getattr(d, "balance", 0) or 0))
                snap.buying_power = Decimal(str(getattr(d, "available", 0) or 0))
        except Exception:  # noqa: BLE001
            pass

        snap.updated_at = datetime.now()
        return snap
