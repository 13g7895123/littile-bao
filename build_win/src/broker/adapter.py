"""
broker.adapter — 券商適配層

提供統一介面 BrokerAdapter，讓 engine / gui 不必區分真實 SDK 與 Mock。
- FubonAdapter：實際呼叫 Fubon Neo SDK
- MockAdapter：無憑證情境下回傳假資料，沿用既有 random 行為

之後 Milestone 2~6 會在 BrokerAdapter 介面陸續擴充：
  subscribe_realtime / place_order / inventories / on_order / on_filled / ...
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Callable, List, Optional

from .errors import FubonAuthError, FubonConfigError, FubonNotLoggedInError
from .models import AccountRef, ConnectionState, FillEvent, LoginResult, OrderEvent

FillCallback = Callable[[FillEvent], None]
OrderCallback = Callable[[OrderEvent], None]


# ─────────────────────────────────────────
#  抽象介面
# ─────────────────────────────────────────

class BrokerAdapter(ABC):
    """所有券商適配器需實作的最小介面（Milestone 1 範圍）。"""

    @abstractmethod
    def login(self) -> LoginResult: ...

    @abstractmethod
    def logout(self) -> None: ...

    @property
    @abstractmethod
    def state(self) -> ConnectionState: ...

    @property
    @abstractmethod
    def account(self) -> Optional[AccountRef]: ...

    @abstractmethod
    def select_account(self, branch_no: str, account_no: str) -> AccountRef: ...

    @abstractmethod
    def create_realtime_feed(self):
        """建立即時行情訂閱實例（RealtimeFeed）。"""

    @abstractmethod
    def load_symbol_info(self, codes):
        """載入個股基本資料（昨收 / 漲跌停 / 特殊股）。"""

    # ── Milestone 4：成交回報訂閱 ──
    def on_filled(self, callback: FillCallback) -> None:
        """註冊成交回報 callback；同一適配器可註冊多個。"""
        if not hasattr(self, "_fill_subs"):
            self._fill_subs: List[FillCallback] = []
        self._fill_subs.append(callback)

    def dispatch_fill(self, ev: FillEvent) -> None:
        """由 SDK 回報或模擬流程觸發；對所有訂閱者廣播。"""
        for cb in getattr(self, "_fill_subs", []):
            try:
                cb(ev)
            except Exception:  # noqa: BLE001
                pass

    # ── Milestone 5：委託回報與下單 ──
    def on_order(self, callback: OrderCallback) -> None:
        if not hasattr(self, "_order_subs"):
            self._order_subs: List[OrderCallback] = []
        self._order_subs.append(callback)

    def dispatch_order(self, ev: OrderEvent) -> None:
        for cb in getattr(self, "_order_subs", []):
            try:
                cb(ev)
            except Exception:  # noqa: BLE001
                pass

    def place_order(self, req) -> str:
        """送出委託，回傳 order_id。子類需提供 _order_manager 或覆寫。"""
        mgr = self._get_order_manager()
        return mgr.place_order(req)

    def cancel_order(self, order_id: str) -> bool:
        mgr = self._get_order_manager()
        return mgr.cancel_order(order_id)

    def _get_order_manager(self):
        raise NotImplementedError


# ─────────────────────────────────────────
#  Mock 適配器（無憑證情境）
# ─────────────────────────────────────────

class MockAdapter(BrokerAdapter):
    """無憑證情境下使用，僅供開發 / Demo。"""

    def __init__(self) -> None:
        self._state = ConnectionState.DISCONNECTED
        self._accounts: List[AccountRef] = []
        self._selected: Optional[AccountRef] = None

    def login(self) -> LoginResult:
        self._state = ConnectionState.CONNECTED
        self._accounts = [
            AccountRef(branch_no="0000", account_no="0000000",
                       account_type="MOCK", account_name="模擬帳號"),
        ]
        self._selected = self._accounts[0]
        return LoginResult(
            success=True,
            accounts=list(self._accounts),
            selected=self._selected,
            message="MockAdapter 已啟用（未連線真實券商）",
        )

    def logout(self) -> None:
        self._state = ConnectionState.DISCONNECTED
        self._selected = None

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def account(self) -> Optional[AccountRef]:
        return self._selected

    def select_account(self, branch_no: str, account_no: str) -> AccountRef:
        for acc in self._accounts:
            if acc.branch_no == branch_no and acc.account_no == account_no:
                self._selected = acc
                return acc
        raise ValueError(f"找不到帳號 {branch_no}-{account_no}")

    def create_realtime_feed(self):
        from .realtime import MockRealtimeFeed
        return MockRealtimeFeed()

    def load_symbol_info(self, codes):
        from .universe import DEFAULT_MOCK_INFOS, StaticSymbolInfoLoader
        infos = {i.code: i for i in DEFAULT_MOCK_INFOS}
        return StaticSymbolInfoLoader(infos).load(codes)

    def _get_order_manager(self):
        if not hasattr(self, "_order_mgr"):
            from .orders import MockOrderManager
            self._order_mgr = MockOrderManager(self)
        return self._order_mgr

    def account_service(self):
        if not hasattr(self, "_acc_svc"):
            from .account import MockAccountService
            self._acc_svc = MockAccountService()
            # 自動同步：成交時更新 mock 帳戶部位
            self._mock_positions: dict = {}
            self.on_filled(self._sync_mock_account)
        return self._acc_svc

    def _sync_mock_account(self, ev) -> None:
        from decimal import Decimal as _D
        from .account import Position
        positions = getattr(self, "_mock_positions", None)
        if positions is None:
            return
        if ev.side.value == "BUY":
            existing = positions.get(ev.code)
            if existing is None:
                positions[ev.code] = Position(
                    code=ev.code, name=ev.name or ev.code,
                    qty=ev.qty, avg_cost=ev.price,
                    last_price=ev.price,
                    market_value=ev.price * _D(ev.qty * 1000),
                    unrealized_pnl=_D("0"), unrealized_pnl_pct=_D("0"),
                )
            else:
                # 加碼（簡化平均成本）
                total_qty = existing.qty + ev.qty
                avg = (existing.avg_cost * _D(existing.qty)
                       + ev.price * _D(ev.qty)) / _D(total_qty)
                existing.qty = total_qty
                existing.avg_cost = avg
        else:  # SELL
            positions.pop(ev.code, None)
        self._acc_svc.set_positions(list(positions.values()))


# ─────────────────────────────────────────
#  Fubon 適配器
# ─────────────────────────────────────────

class FubonAdapter(BrokerAdapter):
    """
    包裝 fubon_neo SDK 的單例適配器。

    使用方式：
        adapter = FubonAdapter.from_config(cfg)
        result = adapter.login()
        if result.success:
            print("已登入：", result.selected.display)
    """

    _instance: Optional["FubonAdapter"] = None
    _lock = threading.Lock()

    def __init__(
        self,
        personal_id: str,
        password: str,
        cert_path: str,
        cert_password: str,
        branch_no: str,
        account_no: str,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        dry_run: bool = True,
        dry_run_use_market_price: bool = False,
        dry_run_fill_min_sec: float = 0.5,
        dry_run_fill_max_sec: float = 1.5,
        dry_run_audit_dir: str = "",
    ) -> None:
        # 依登入模式決定必填欄位
        has_apikey = bool(api_key)
        has_cert   = bool(cert_path)
        if has_apikey:
            # apikey_dma 或 apikey 模式
            if not personal_id:
                raise FubonConfigError("FubonAdapter（API Key 模式）缺少 personal_id")
        else:
            # 傳統密碼模式
            if not all([personal_id, password, cert_path, branch_no, account_no]):
                raise FubonConfigError(
                    "FubonAdapter 缺少必填欄位（personal_id/password/cert_path/branch_no/account_no）"
                )

        self._personal_id = personal_id
        self._password = password
        self._cert_path = cert_path
        self._cert_password = cert_password or personal_id  # v1.3.2+ 預設值
        self._branch_no = branch_no
        self._account_no = account_no
        self._api_key = api_key
        self._api_secret = api_secret
        self.dry_run = dry_run
        self.dry_run_use_market_price = dry_run_use_market_price
        self.dry_run_fill_min_sec = dry_run_fill_min_sec
        self.dry_run_fill_max_sec = dry_run_fill_max_sec
        self.dry_run_audit_dir = dry_run_audit_dir

        self._sdk = None  # type: ignore[assignment]
        self._state = ConnectionState.DISCONNECTED
        self._accounts: List[AccountRef] = []
        self._selected: Optional[AccountRef] = None

    # ── 工廠 ────────────────────────────────

    @classmethod
    def from_config(cls, cfg) -> "FubonAdapter":
        """由 BrokerSettings 建立實例。"""
        return cls(
            personal_id=cfg.personal_id,
            password=cfg.password,
            cert_path=cfg.cert_path,
            cert_password=cfg.cert_password,
            branch_no=cfg.branch_no,
            account_no=cfg.account_no,
            api_key=cfg.api_key or None,
            api_secret=cfg.api_secret or None,
            dry_run=cfg.dry_run,
            dry_run_use_market_price=cfg.dry_run_use_market_price,
            dry_run_fill_min_sec=cfg.dry_run_fill_min_sec,
            dry_run_fill_max_sec=cfg.dry_run_fill_max_sec,
            dry_run_audit_dir=cfg.dry_run_audit_dir,
        )

    @classmethod
    def instance(cls, cfg=None) -> "FubonAdapter":
        """單例存取，第一次呼叫需提供 cfg。"""
        with cls._lock:
            if cls._instance is None:
                if cfg is None:
                    raise FubonConfigError("第一次取得 FubonAdapter 實例必須提供 cfg")
                cls._instance = cls.from_config(cfg)
            return cls._instance

    # ── 生命週期 ────────────────────────────

    def login(self) -> LoginResult:
        try:
            from fubon_neo.sdk import FubonSDK  # type: ignore
        except ImportError as exc:
            self._state = ConnectionState.LOGIN_FAILED
            raise FubonAuthError(
                "未安裝 fubon_neo SDK，請至 "
                "https://www.fbs.com.tw/TradeAPI/docs/download/download-sdk 下載 wheel 後安裝"
            ) from exc

        self._state = ConnectionState.CONNECTING
        try:
            self._sdk = FubonSDK()

            # ── 依登入模式選擇 SDK 方法 ──────────────────
            if self._api_key and not self._cert_path:
                # apikey_dma 模式：只需 personal_id + api_key
                res = self._sdk.apikey_dma_login(self._personal_id, self._api_key)
            elif self._api_key and self._cert_path:
                # apikey 模式：personal_id + api_key + cert_path [+ cert_pass]
                res = self._sdk.apikey_login(
                    self._personal_id,
                    self._api_key,
                    self._cert_path,
                    self._cert_password,
                )
            else:
                # 傳統密碼模式
                res = self._sdk.login(
                    self._personal_id,
                    self._password,
                    self._cert_path,
                    self._cert_password,
                )

            if not getattr(res, "is_success", False):
                msg = getattr(res, "message", "登入失敗")
                self._state = ConnectionState.LOGIN_FAILED
                raise FubonAuthError(f"Fubon login 失敗：{msg}")

            raw_accounts = getattr(res, "data", []) or []
            self._accounts = [self._to_ref(a) for a in raw_accounts]
            # 預設選擇 .env 指定的帳號
            self._selected = self._match_account(self._branch_no, self._account_no)
            self._state = ConnectionState.CONNECTED

            # 若已有 on_filled 訂閱者，於登入完成後掛載 SDK 回報
            if getattr(self, "_fill_subs", None):
                self._attach_sdk_fill_handler()

            return LoginResult(
                success=True,
                accounts=list(self._accounts),
                selected=self._selected,
                message="登入成功",
            )
        except FubonAuthError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._state = ConnectionState.ERROR
            raise FubonAuthError(f"登入時發生未預期錯誤：{exc}") from exc

    def logout(self) -> None:
        if self._sdk is not None:
            try:
                logout = getattr(self._sdk, "logout", None)
                if callable(logout):
                    logout()
            finally:
                self._sdk = None
        self._state = ConnectionState.DISCONNECTED
        self._selected = None

    # ── 屬性 ────────────────────────────────

    @property
    def sdk(self):
        if self._sdk is None:
            raise FubonNotLoggedInError("尚未登入，請先呼叫 login()")
        return self._sdk

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def account(self) -> Optional[AccountRef]:
        return self._selected

    @property
    def accounts(self) -> List[AccountRef]:
        return list(self._accounts)

    def select_account(self, branch_no: str, account_no: str) -> AccountRef:
        acc = self._match_account(branch_no, account_no)
        self._selected = acc
        return acc

    def create_realtime_feed(self):
        from .realtime import FubonRealtimeFeed
        return FubonRealtimeFeed(self)

    def load_symbol_info(self, codes):
        from .universe import FubonSymbolInfoLoader
        return FubonSymbolInfoLoader(self).load(codes)

    def _get_order_manager(self):
        if not hasattr(self, "_order_mgr"):
            if self.dry_run:
                from .orders import DryRunOrderManager
                self._order_mgr = DryRunOrderManager(
                    self,
                    fill_delay_range=(self.dry_run_fill_min_sec, self.dry_run_fill_max_sec),
                    audit_dir=self.dry_run_audit_dir,
                    use_market_price=self.dry_run_use_market_price,
                )
            else:
                from .orders import FubonOrderManager
                self._order_mgr = FubonOrderManager(self)
        return self._order_mgr

    def set_dry_run(self, enabled: bool) -> None:
        self.dry_run = bool(enabled)
        if hasattr(self, "_order_mgr"):
            delattr(self, "_order_mgr")

    def account_service(self):
        if not hasattr(self, "_acc_svc"):
            from .account import FubonAccountService
            self._acc_svc = FubonAccountService(self)
        return self._acc_svc

    def on_filled(self, callback: FillCallback) -> None:  # type: ignore[override]
        super().on_filled(callback)
        # 已登入時將回報 callback 掛上 SDK；尚未登入則於 login() 後再行掛載
        if self._sdk is not None and len(getattr(self, "_fill_subs", [])) == 1:
            self._attach_sdk_fill_handler()

    def _attach_sdk_fill_handler(self) -> None:
        """將 SDK 的 on_filled 事件轉為 FillEvent 並廣播。"""
        if self._sdk is None:
            return
        setter = getattr(self._sdk, "set_on_filled", None)
        if not callable(setter):
            return

        def _handler(err, content):
            if err:
                return
            try:
                ev = self._convert_sdk_fill(content)
            except Exception:  # noqa: BLE001
                return
            if ev is not None:
                self.dispatch_fill(ev)

        setter(_handler)

    @staticmethod
    def _convert_sdk_fill(content) -> Optional[FillEvent]:
        """將 fubon_neo 回傳的成交內容轉為 FillEvent；欄位以 SDK 文件為準。"""
        from decimal import Decimal as _D
        from datetime import datetime as _dt
        from .models import OrderSide as _OS

        def _g(name, default=None):
            return getattr(content, name, default) if not isinstance(content, dict) else content.get(name, default)

        code = _g("stock_no") or _g("symbol")
        if code is None:
            return None
        side_raw = (_g("buy_sell") or _g("side") or "").upper()
        side = _OS.BUY if side_raw.startswith("B") else _OS.SELL
        return FillEvent(
            order_id=str(_g("order_no") or ""),
            code=str(code),
            name=str(_g("stock_name") or ""),
            side=side,
            price=_D(str(_g("filled_price") or _g("price") or 0)),
            qty=int(_g("filled_qty") or _g("quantity") or 0),
            time=_dt.now(),
        )

    # ── 私有 ────────────────────────────────

    def _match_account(self, branch_no: str, account_no: str) -> AccountRef:
        for acc in self._accounts:
            if acc.branch_no == branch_no and acc.account_no == account_no:
                return acc
        if self._accounts:
            # 找不到對應 → 退而求其次選第一個並記錄
            return self._accounts[0]
        raise FubonAuthError("登入成功但未取得任何帳號")

    @staticmethod
    def _to_ref(raw) -> AccountRef:
        """SDK Account 物件 → AccountRef。"""
        return AccountRef(
            branch_no=str(getattr(raw, "branch_no", "") or ""),
            account_no=str(getattr(raw, "account", "") or ""),
            account_type=str(getattr(raw, "account_type", "") or ""),
            account_name=str(getattr(raw, "account_name", "") or ""),
        )
