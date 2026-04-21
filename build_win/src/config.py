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
