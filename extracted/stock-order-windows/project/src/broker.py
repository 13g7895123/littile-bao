"""
broker.py — 券商 API 封裝（以永豐金 Shioaji 為範例）
若使用其他券商，只需實作 BrokerBase 的方法即可。
"""
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional, List

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  資料結構
# ─────────────────────────────────────────────

@dataclass
class Quote:
    symbol: str
    name: str
    market: str           # TSE / OTC
    price: float
    limit_up_price: float
    ask_price: float
    ask_qty: int          # 委賣張數（漲停價那一檔）
    bid_price: float
    bid_qty: int
    volume_1s: int        # 最近1秒成交張數（由引擎計算）
    candle_index: int     # 起漲第幾根（1-based）


@dataclass
class Order:
    order_id: str
    symbol: str
    action: str           # BUY / SELL
    price: float
    quantity: int         # 張
    status: str           # PENDING / FILLED / CANCELLED / PARTIAL


# ─────────────────────────────────────────────
#  抽象基底
# ─────────────────────────────────────────────

class BrokerBase(ABC):

    @abstractmethod
    def login(self, api_id: str, api_key: str, cert_path: str = "") -> bool: ...

    @abstractmethod
    def logout(self): ...

    @abstractmethod
    def subscribe_limit_up_stocks(
        self,
        markets: List[str],
        on_quote: Callable[[Quote], None]
    ): ...

    @abstractmethod
    def place_market_buy(self, symbol: str, quantity: int) -> Order: ...

    @abstractmethod
    def place_limit_sell(self, symbol: str, price: float, quantity: int) -> Order: ...

    @abstractmethod
    def place_market_sell(self, symbol: str, quantity: int) -> Order: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    def get_positions(self) -> List[dict]: ...


# ─────────────────────────────────────────────
#  永豐金 Shioaji 實作
# ─────────────────────────────────────────────

class ShioajiBroker(BrokerBase):
    """
    需安裝：pip install shioaji
    文件：https://sinotrade.github.io/
    """

    def __init__(self):
        self._api = None
        self._subscriptions = []

    def login(self, api_id: str, api_key: str, cert_path: str = "") -> bool:
        try:
            import shioaji as sj
            self._api = sj.Shioaji()
            accounts = self._api.login(
                api_key=api_id,
                secret_key=api_key,
                fetch_contract=True,
            )
            logger.info(f"[Shioaji] 登入成功，帳號：{accounts}")
            return True
        except ImportError:
            logger.error("[Shioaji] 請先安裝 shioaji：pip install shioaji")
            return False
        except Exception as e:
            logger.error(f"[Shioaji] 登入失敗：{e}")
            return False

    def logout(self):
        if self._api:
            try:
                self._api.logout()
            except Exception as e:
                logger.error(f"[Shioaji] 登出失敗：{e}")

    def subscribe_limit_up_stocks(
        self,
        markets: List[str],
        on_quote: Callable[[Quote], None]
    ):
        """
        訂閱即時行情，由引擎篩選漲停股。
        實作需依 shioaji event callback 格式調整。
        """
        if not self._api:
            logger.error("[Shioaji] 尚未登入")
            return

        def _on_tick(exchange, tick):
            try:
                q = self._parse_tick(tick)
                if q:
                    on_quote(q)
            except Exception as e:
                logger.debug(f"[Shioaji] tick parse error: {e}")

        self._api.quote.set_event_callback(_on_tick)
        # 根據 markets 訂閱對應股票（實際需遍歷合約清單）
        logger.info(f"[Shioaji] 開始訂閱市場：{markets}")

    def _parse_tick(self, tick) -> Optional[Quote]:
        """將 shioaji tick 轉為 Quote（依實際 API 欄位調整）"""
        # tick.close, tick.ask_price, tick.ask_volume …
        return None  # TODO: 依實際欄位填入

    def place_market_buy(self, symbol: str, quantity: int) -> Order:
        import shioaji as sj
        contract = self._api.Contracts.Stocks[symbol]
        order = self._api.Order(
            price=0,
            quantity=quantity,
            action=sj.constant.Action.Buy,
            price_type=sj.constant.StockPriceType.MKT,
            order_type=sj.constant.TFTOrderType.ROD,
        )
        trade = self._api.place_order(contract, order)
        return Order(
            order_id=trade.order.id,
            symbol=symbol,
            action="BUY",
            price=0,
            quantity=quantity,
            status="PENDING",
        )

    def place_limit_sell(self, symbol: str, price: float, quantity: int) -> Order:
        import shioaji as sj
        contract = self._api.Contracts.Stocks[symbol]
        order = self._api.Order(
            price=price,
            quantity=quantity,
            action=sj.constant.Action.Sell,
            price_type=sj.constant.StockPriceType.LMT,
            order_type=sj.constant.TFTOrderType.ROD,
        )
        trade = self._api.place_order(contract, order)
        return Order(
            order_id=trade.order.id,
            symbol=symbol,
            action="SELL",
            price=price,
            quantity=quantity,
            status="PENDING",
        )

    def place_market_sell(self, symbol: str, quantity: int) -> Order:
        import shioaji as sj
        contract = self._api.Contracts.Stocks[symbol]
        order = self._api.Order(
            price=0,
            quantity=quantity,
            action=sj.constant.Action.Sell,
            price_type=sj.constant.StockPriceType.MKT,
            order_type=sj.constant.TFTOrderType.ROD,
        )
        trade = self._api.place_order(contract, order)
        return Order(
            order_id=trade.order.id,
            symbol=symbol,
            action="SELL",
            price=0,
            quantity=quantity,
            status="PENDING",
        )

    def cancel_order(self, order_id: str) -> bool:
        try:
            # shioaji 需傳入 trade 物件，此處簡化
            logger.info(f"[Shioaji] 取消委託 {order_id}")
            return True
        except Exception as e:
            logger.error(f"[Shioaji] 取消失敗：{e}")
            return False

    def get_positions(self) -> List[dict]:
        try:
            positions = self._api.list_positions(self._api.stock_account)
            return [{"symbol": p.code, "qty": p.quantity, "cost": p.price} for p in positions]
        except Exception as e:
            logger.error(f"[Shioaji] 取得持倉失敗：{e}")
            return []
