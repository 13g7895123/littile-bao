"""
broker — 富邦 Neo API 適配層

本套件封裝所有與券商 API 相關的互動：
- adapter：SDK 單例、登入、生命週期
- realtime：WebSocket 行情訂閱（Milestone 2）
- orders：下單 / 改價 / 改量 / 刪單（Milestone 5）
- account：庫存 / 損益 / 買進力 Poll（Milestone 6）
- events：委託 / 成交 callback 路由（Milestone 4）
- universe：開盤前選股（Milestone 6）
- fees：手續費 / 交易稅
- models：DTO
- errors：例外階層
"""
from .errors import (
    BrokerError,
    FubonAuthError,
    FubonConfigError,
    FubonNetworkError,
    FubonNotLoggedInError,
    FubonOrderError,
)
from .models import AccountRef, ConnectionState, LoginResult
from .adapter import BrokerAdapter, FubonAdapter, MockAdapter
from .realtime import (
    BookCallback,
    FubonRealtimeFeed,
    MockRealtimeFeed,
    RealtimeFeed,
    SymbolMeta,
    TickCallback,
)
from .models import (  # 行情 / 交易 DTO
    BookEvent,
    BookLevel,
    FillEvent,
    OrderEvent,
    OrderSide,
    OrderStatus,
    TickEvent,
)
from .universe import (
    DEFAULT_MOCK_INFOS,
    FubonSymbolInfoLoader,
    StaticSymbolInfoLoader,
    SymbolInfo,
    SymbolInfoLoader,
    build_symbol_info,
    calc_limit_down,
    calc_limit_up,
    round_to_tick,
    tick_size,
)
from .fees import (
    FEE_DISCOUNT,
    FEE_RATE,
    MIN_FEE,
    TAX_RATE,
    TAX_RATE_DAYTRADE,
    TradePnL,
    calc_fee,
    calc_tax,
    realized_pnl,
)
from .orders import (
    FubonOrderManager,
    MockOrderManager,
    OrderManager,
    OrderRequest,
)
from .account import (
    AccountService,
    AccountSnapshot,
    FubonAccountService,
    MockAccountService,
    Position,
)
from .universe import ScanCriteria, scan_daily

__all__ = [
    "BrokerError",
    "FubonAuthError",
    "FubonConfigError",
    "FubonNetworkError",
    "FubonNotLoggedInError",
    "FubonOrderError",
    "AccountRef",
    "ConnectionState",
    "LoginResult",
    "BrokerAdapter",
    "FubonAdapter",
    "MockAdapter",
    "RealtimeFeed",
    "MockRealtimeFeed",
    "FubonRealtimeFeed",
    "SymbolMeta",
    "TickCallback",
    "BookCallback",
    "TickEvent",
    "BookEvent",
    "BookLevel",
    "OrderEvent",
    "FillEvent",
    "OrderSide",
    "OrderStatus",
    "SymbolInfo",
    "SymbolInfoLoader",
    "StaticSymbolInfoLoader",
    "FubonSymbolInfoLoader",
    "DEFAULT_MOCK_INFOS",
    "build_symbol_info",
    "calc_limit_up",
    "calc_limit_down",
    "tick_size",
    "round_to_tick",
    "FEE_RATE",
    "FEE_DISCOUNT",
    "MIN_FEE",
    "TAX_RATE",
    "TAX_RATE_DAYTRADE",
    "TradePnL",
    "calc_fee",
    "calc_tax",
    "realized_pnl",
    "OrderRequest",
    "OrderManager",
    "MockOrderManager",
    "FubonOrderManager",
    "AccountService",
    "AccountSnapshot",
    "Position",
    "MockAccountService",
    "FubonAccountService",
    "ScanCriteria",
    "scan_daily",
]
