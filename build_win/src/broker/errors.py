"""
broker.errors — 適配層例外階層

所有與券商互動失敗的情境都應拋出 BrokerError 子類，方便上層統一捕捉。
"""
from __future__ import annotations


class BrokerError(Exception):
    """所有 broker 層例外的基底類別。"""


class FubonAuthError(BrokerError):
    """憑證 / 帳密 / API Key 驗證失敗。"""


class FubonNotLoggedInError(BrokerError):
    """尚未登入即嘗試呼叫需要登入的功能。"""


class FubonNetworkError(BrokerError):
    """SDK 連線中斷、HTTP / WebSocket 異常。"""


class FubonOrderError(BrokerError):
    """下單 / 改單 / 撤單失敗。"""


class FubonConfigError(BrokerError):
    """設定錯誤：缺少必要欄位或格式不正確。"""
