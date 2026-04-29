"""
broker.models — 適配層 DTO

把 Fubon SDK / 自製 mock 的物件統一轉換為 dataclass，
讓 engine 層不需直接依賴 SDK 型別。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional


# ─────────────────────────────────────────
#  連線狀態
# ─────────────────────────────────────────

class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    LOGIN_FAILED = "login_failed"
    ERROR = "error"


# ─────────────────────────────────────────
#  帳號
# ─────────────────────────────────────────

@dataclass(frozen=True)
class AccountRef:
    """歸戶帳號摘要。"""
    branch_no: str          # 分公司代號（4 碼）
    account_no: str         # 證券帳號（7 碼）
    account_type: str = ""  # 帳戶類型
    account_name: str = ""  # 戶名

    @property
    def display(self) -> str:
        if self.account_name:
            return f"{self.branch_no}-{self.account_no} ({self.account_name})"
        return f"{self.branch_no}-{self.account_no}"


@dataclass
class LoginResult:
    """登入結果。"""
    success: bool
    accounts: List[AccountRef] = field(default_factory=list)
    selected: Optional[AccountRef] = None
    message: str = ""


# ─────────────────────────────────────────
#  行情 / 交易事件（占位，Milestone 2+ 補完）
# ─────────────────────────────────────────

@dataclass
class TickEvent:
    code: str
    time: datetime
    price: Decimal
    volume: int
    cum_volume: int = 0
    prev_close: Optional[Decimal] = None


@dataclass
class BookLevel:
    price: Decimal
    volume: int


@dataclass
class BookEvent:
    code: str
    time: datetime
    ask: List[BookLevel] = field(default_factory=list)
    bid: List[BookLevel] = field(default_factory=list)


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class OrderEvent:
    order_id: str
    code: str
    side: OrderSide
    price: Decimal
    qty: int
    filled_qty: int
    status: OrderStatus
    time: datetime


@dataclass
class FillEvent:
    order_id: str
    code: str
    name: str
    side: OrderSide
    price: Decimal
    qty: int
    time: datetime
