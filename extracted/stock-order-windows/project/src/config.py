"""
config.py — 所有可調參數的設定與持久化
"""
import json
import os
from dataclasses import dataclass, asdict, field
from typing import List

CONFIG_FILE = "config.json"


@dataclass
class TradingConfig:
    # ── 功能 1：10點前漲停，委賣(漲停價)低於N張才進場 ─────────────────────
    f1_enabled: bool = True
    entry_before_time: str = "10:00"        # 格式 HH:MM
    ask_queue_threshold: int = 100          # 委賣張數上限

    # ── 功能 2：市場選擇 ────────────────────────────────────────────────────
    market_twse: bool = True                # 上市
    market_tpex: bool = True                # 上櫃

    # ── 功能 3：每隻股票投入金額 ────────────────────────────────────────────
    per_stock_amount: int = 100_000         # 元

    # ── 功能 4：買到後，委買漲停就市價賣出 ─────────────────────────────────
    f4_enabled: bool = True

    # ── 功能 5：持倉中，1秒成交量超過N張就賣 ──────────────────────────────
    f5_enabled: bool = True
    volume_spike_sell_threshold: int = 499  # 張/秒

    # ── 功能 6：委託排隊中，1秒成交量超過N張就取消委託 ─────────────────────
    f6_enabled: bool = True
    volume_spike_cancel_threshold: int = 499

    # ── 功能 7：只買起漲第幾根K棒 ──────────────────────────────────────────
    f7_enabled: bool = True
    candle_limit: int = 2                   # 1 = 只買第1根；2 = 第1或第2根

    # ── 功能 8：當天成交量門檻 ──────────────────────────────────────────────
    f8_enabled: bool = True
    daily_volume_min: int = 500             # 張，低於不進場

    # ── 功能 9：股價區間篩選 ────────────────────────────────────────────────
    f9_enabled: bool = True
    price_min: float = 10.0                 # 元
    price_max: float = 500.0                # 元

    # ── 功能 10：委賣價 + 即時量雙重確認 ────────────────────────────────────
    f10_enabled: bool = True
    ask_price_ratio: float = 1.0            # 委賣價 ≤ 漲停價 × ratio
    entry_volume_confirm: int = 50          # 進場前1秒成交量須 ≥ 此數（張）

    # ── 其他 ────────────────────────────────────────────────────────────────
    broker_account: str = ""
    broker_password: str = ""
    broker_cert_path: str = ""
    log_level: str = "INFO"                 # DEBUG / INFO / WARNING

    # ── 帳號憑證（永豐 Shioaji） ────────────────────────────────────────────
    api_id: str = ""
    api_key: str = ""

    # ── 黑名單（不交易的股票代號） ──────────────────────────────────────────
    blacklist: List[str] = field(default_factory=list)

    def save(self, path: str = CONFIG_FILE):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str = CONFIG_FILE) -> "TradingConfig":
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 過濾掉未知欄位（版本升級容錯）
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
