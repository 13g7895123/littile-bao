"""
config.py — 所有可調參數的設定與持久化
"""
import json
import os
from dataclasses import dataclass, asdict, field
from typing import List
# 設定檔放在 exe 同目錄
def _config_path() -> str:
    if getattr(__import__('sys'), 'frozen', False):
        base = os.path.dirname(__import__('sys').executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "config.json")

CONFIG_FILE = _config_path()


@dataclass
class TradingConfig:
    # ── 功能 1：10點前漲停，委賣(漲停價)低於N張才進場 ─────────────────────
    f1_enabled: bool = True
    entry_before_time: str = "10:00"
    ask_queue_threshold: int = 100

    # ── 功能 2：市場選擇 ────────────────────────────────────────────────────
    market_twse: bool = True
    market_tpex: bool = True

    # ── 功能 3：每隻股票投入金額 ────────────────────────────────────────────
    per_stock_amount: int = 100_000

    # ── 功能 4：買到後，委買漲停就市價賣出 ─────────────────────────────────
    f4_enabled: bool = True

    # ── 功能 5：持倉中，1秒成交量超過N張就賣 ──────────────────────────────
    f5_enabled: bool = True
    volume_spike_sell_threshold: int = 499

    # ── 功能 6：委託排隊中，1秒成交量超過N張就取消委託 ─────────────────────
    f6_enabled: bool = True
    volume_spike_cancel_threshold: int = 499

    # ── 功能 7：只買起漲第幾根K棒 ──────────────────────────────────────────
    f7_enabled: bool = True
    candle_limit: int = 2

    # ── 功能 8：當天成交量門檻 ──────────────────────────────────────────────
    f8_enabled: bool = True
    daily_volume_min: int = 500

    # ── 功能 9：股價區間篩選 ────────────────────────────────────────────────
    f9_enabled: bool = True
    price_min: float = 10.0
    price_max: float = 500.0

    # ── 功能 10：委賣價 + 即時量雙重確認 ────────────────────────────────────
    f10_enabled: bool = True
    ask_price_ratio: float = 1.0
    entry_volume_confirm: int = 50

    # ── 功能 11：排除特殊股 ──────────────────────────────────────────────────
    f11_enabled: bool = True   # 排除處置股、注意股、限當沖股

    # ── 功能 12：開盤即漲停 + 當天已賣過就封鎖 ──────────────────────────────
    f12_enabled: bool = True

    # ── 功能 13：限制每天最大成交檔數 ───────────────────────────────────────
    f13_enabled: bool = True
    daily_max_trades: int = 5   # 當天最多成交幾檔

    # ── 下單模式 ────────────────────────────────────────────────────────────
    order_dry_run: bool = True   # True = 模擬下單，不送出真實委託

    # ── 帳號 ────────────────────────────────────────────────────────────────
    api_id: str = ""
    api_key: str = ""
    broker_cert_path: str = ""

    # ── 黑名單 ──────────────────────────────────────────────────────────────
    blacklist: List[str] = field(default_factory=list)

    def save(self, path: str = ""):
        path = path or CONFIG_FILE
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str = "") -> "TradingConfig":
        path = path or CONFIG_FILE
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
                return cls(**valid)
            except Exception as e:
                print(f"[Config] 載入失敗，使用預設值：{e}")
        return cls()

    def get_markets(self) -> List[str]:
        markets = []
        if self.market_twse:
            markets.append("TSE")
        if self.market_tpex:
            markets.append("OTC")
        return markets


# ─────────────────────────────────────────────────────────
#  Broker 設定（Fubon Neo）：從 .env / OS 環境變數載入
# ─────────────────────────────────────────────────────────

def _load_dotenv() -> None:
    """簡易 .env 載入；若已有 python-dotenv 則優先使用。"""
    try:
        from dotenv import load_dotenv  # type: ignore
        # 1) exe / src 同目錄；2) 工作目錄
        for base in [
            os.path.dirname(os.path.abspath(__file__)),
            os.path.dirname(__import__('sys').executable)
                if getattr(__import__('sys'), 'frozen', False) else None,
            os.getcwd(),
        ]:
            if base:
                p = os.path.join(base, ".env")
                if os.path.exists(p):
                    load_dotenv(p, override=False)
                    return
    except ImportError:
        pass

    # fallback：手動解析
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    os.environ.setdefault(k, v)
            break
        except Exception as e:  # noqa: BLE001
            print(f"[Config] 解析 .env 失敗：{e}")


def _env_bool(key: str, default: bool = False) -> bool:
    v = os.environ.get(key)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on", "y")


def _env_float(key: str, default: float = 0.0) -> float:
    v = os.environ.get(key)
    if v is None:
        return default
    try:
        return float(v.strip())
    except ValueError:
        return default


@dataclass
class BrokerSettings:
    """富邦 Neo SDK 連線設定（從環境變數載入）。"""
    personal_id: str = ""
    password: str = ""
    cert_path: str = ""
    cert_password: str = ""
    branch_no: str = ""
    account_no: str = ""
    api_key: str = ""
    api_secret: str = ""
    dry_run: bool = True
    dry_run_use_market_price: bool = False
    dry_run_fill_min_sec: float = 0.5
    dry_run_fill_max_sec: float = 1.5
    dry_run_audit_dir: str = ""
    mock_mode: bool = False  # 無憑證時改用 MockAdapter

    @classmethod
    def from_env(cls) -> "BrokerSettings":
        _load_dotenv()
        return cls(
            personal_id=os.environ.get("FUBON_PERSONAL_ID", "").strip(),
            password=os.environ.get("FUBON_PASSWORD", ""),
            cert_path=os.environ.get("FUBON_CERT_PATH", "").strip(),
            cert_password=os.environ.get("FUBON_CERT_PASSWORD", ""),
            branch_no=os.environ.get("FUBON_BRANCH_NO", "").strip(),
            account_no=os.environ.get("FUBON_ACCOUNT_NO", "").strip(),
            api_key=os.environ.get("FUBON_API_KEY", "").strip(),
            api_secret=os.environ.get("FUBON_API_SECRET", "").strip(),
            dry_run=_env_bool("FUBON_DRY_RUN", default=True),
            dry_run_use_market_price=_env_bool("FUBON_DRY_RUN_USE_MARKET_PRICE", default=False),
            dry_run_fill_min_sec=_env_float("FUBON_DRY_RUN_FILL_MIN_SEC", default=0.5),
            dry_run_fill_max_sec=_env_float("FUBON_DRY_RUN_FILL_MAX_SEC", default=1.5),
            dry_run_audit_dir=os.environ.get("FUBON_DRY_RUN_AUDIT_DIR", "").strip(),
            mock_mode=_env_bool("MOCK_MODE", default=False),
        )

    @property
    def login_mode(self) -> str:
        """決定使用哪種 SDK 登入方式。
        - 'apikey_dma' : 只需 personal_id + api_key（無憑證）
        - 'apikey'     : personal_id + api_key + cert_path
        - 'password'   : 傳統 personal_id + password + cert + branch + account
        """
        if self.api_key:
            if self.cert_path:
                return "apikey"
            return "apikey_dma"
        return "password"

    def is_complete(self) -> bool:
        """是否已備齊登入所需欄位。"""
        mode = self.login_mode
        if mode == "apikey_dma":
            return bool(self.personal_id and self.api_key)
        if mode == "apikey":
            return bool(self.personal_id and self.api_key and self.cert_path)
        # password mode
        return bool(self.personal_id and self.password and
                    self.cert_path and self.branch_no and self.account_no)

    def missing_fields(self) -> list:
        """回傳目前模式下缺少的欄位名稱清單。"""
        mode = self.login_mode
        checks = []
        if mode == "apikey_dma":
            if not self.personal_id: checks.append("身分證字號")
            if not self.api_key:     checks.append("API Key")
        elif mode == "apikey":
            if not self.personal_id: checks.append("身分證字號")
            if not self.api_key:     checks.append("API Key")
            if not self.cert_path:   checks.append("憑證檔案路徑")
        else:
            if not self.personal_id: checks.append("身分證字號")
            if not self.password:    checks.append("網路下單密碼")
            if not self.cert_path:   checks.append("憑證檔案路徑")
            if not self.branch_no:   checks.append("分行代號")
            if not self.account_no:  checks.append("帳號")
        return checks

