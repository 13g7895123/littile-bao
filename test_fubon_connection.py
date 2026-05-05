"""
test_fubon_connection.py
驗證 fubon_neo SDK 可正常連線富邦證券。

使用方式：
  1. 直接執行（互動輸入）：
       python3 test_fubon_connection.py

  2. 透過 .env 環境變數執行（建議）：
       cp .env.example .env   # 填入真實帳號資料
       python3 test_fubon_connection.py
"""

import os
import sys
import getpass

# ─── 嘗試從 .env 載入 ────────────────────────────────────────────
def _load_dotenv():
    for path in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]:
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)
        print(f"[✓] 已從 {path} 載入環境變數")
        return
    print("[i] 未找到 .env 檔，改用互動輸入模式")

_load_dotenv()

# ─── 取得連線參數 ─────────────────────────────────────────────────
def _get(env_key: str, prompt: str, secret: bool = False) -> str:
    val = os.environ.get(env_key, "").strip()
    if val:
        masked = val[:2] + "****" if len(val) > 2 else "****"
        print(f"  {env_key} = {masked}  (來自環境變數)")
        return val
    if secret:
        return getpass.getpass(f"  請輸入 {prompt}：")
    return input(f"  請輸入 {prompt}：").strip()

print("\n========== 富邦 Neo SDK 連線測試 ==========")
print("  套件版本：", end="")
try:
    import fubon_neo
    print(getattr(fubon_neo, "__version__", "未知"))
except Exception as e:
    print(f"無法取得版本 ({e})")

print("\n[*] 讀取連線設定…")
personal_id  = _get("FUBON_PERSONAL_ID",  "身分證字號 (personal_id)")
password     = _get("FUBON_PASSWORD",     "網路下單密碼",      secret=True)
cert_path    = _get("FUBON_CERT_PATH",    "憑證檔路徑 (.pfx/.p12)")
cert_password= _get("FUBON_CERT_PASSWORD","憑證密碼（預設同身分證）", secret=True) or personal_id
branch_no    = _get("FUBON_BRANCH_NO",    "分行代號 (branch_no)")
account_no   = _get("FUBON_ACCOUNT_NO",   "帳號 (account_no)")

# ─── 執行連線 ─────────────────────────────────────────────────────
print("\n[*] 初始化 FubonSDK …")
try:
    from fubon_neo.sdk import FubonSDK, Mode  # type: ignore
except ImportError:
    from fubon_neo.sdk import FubonSDK         # type: ignore
    Mode = None

sdk = FubonSDK()

print("[*] 呼叫 sdk.login() …")
try:
    if Mode is not None:
        result = sdk.login(personal_id, password, cert_path, cert_password)
    else:
        result = sdk.login(personal_id, password, cert_path, cert_password)
except TypeError:
    # 某些版本參數順序不同，嘗試位置參數
    result = sdk.login(personal_id, password, cert_path)

print("\n========== 登入結果 ==========")
print(f"  result type : {type(result)}")

# 相容不同版本的 result 結構
success = False
accounts = []

if hasattr(result, "is_success"):
    success = result.is_success
elif hasattr(result, "success"):
    success = result.success
elif isinstance(result, bool):
    success = result

if hasattr(result, "data"):
    accounts = result.data or []
elif hasattr(result, "accounts"):
    accounts = result.accounts or []

if success or accounts:
    print(f"  [✓] 登入成功！取得帳號數：{len(accounts)}")
    for i, acc in enumerate(accounts, 1):
        print(f"    帳號 {i}：{acc}")
else:
    msg = getattr(result, "message", "") or getattr(result, "msg", "") or str(result)
    print(f"  [✗] 登入失敗：{msg}")
    sys.exit(1)

# ─── 登出 ──────────────────────────────────────────────────────────
print("\n[*] 登出…")
try:
    sdk.logout()
    print("  [✓] 已正常登出")
except Exception as e:
    print(f"  [!] 登出時發生例外（可忽略）：{e}")

print("\n========== 連線測試完成 ==========")
