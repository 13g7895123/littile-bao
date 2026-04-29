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
from typing import Callable, List, Optional

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


class FubonAccountService(AccountService):
    """呼叫 fubon_neo SDK 取得真實帳戶資料。"""

    def __init__(self, adapter) -> None:
        self.adapter = adapter

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
            inv_res = sdk.stock.inventories(acc)  # type: ignore[attr-defined]
            data = getattr(inv_res, "data", []) or []
            positions: List[Position] = []
            for item in data:
                code = str(getattr(item, "stock_no", "") or "")
                qty_shares = int(getattr(item, "today_qty", 0) or 0)
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
