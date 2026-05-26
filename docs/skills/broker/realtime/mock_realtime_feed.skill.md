# Skill：`MockRealtimeFeed`

## 檔案位置
- `build_win/src/broker/realtime.py`

## 主要職責
- 在本機背景執行緒以隨機 / 機率方式產生 trade、book 事件。
- 行為盡量貼近舊 `engine.py` 用 `random` 模擬市場的邏輯，讓 Demo / 測試行為穩定。

## 介面
- 繼承 `RealtimeFeed`，實作 `subscribe / start / stop`。
- 預設參數：`tick_interval=0.25` 秒、`book_interval=0.5` 秒。

## 行為摘要
- `subscribe(codes, meta)`：記錄 `_symbols / _cum_volume / _at_limit`；若 meta 有 `open_limit_up=True`，初始即為漲停。
- `_tick_loop()` / `_book_loop()`：兩條 daemon thread。
- `_gen_tick(code, meta)`：
  - 用 0.75 / 0.85 機率切換 `at_limit`。
  - 漲停時 `price = limit_up`，否則於漲停以下浮動。
  - `volume = random(10..200)`。
- `_gen_book(code, meta)`：
  - 漲停時 ask[0] = 漲停價（少量）、bid[0] 為漲停-0.5（大量）。
  - 非漲停時 ask[0] = 漲停-0.5；bid[0] = 漲停-1。

## 注意事項
- 機率 0.75 / 0.85 來自舊版邏輯，**不要任意調整**；若要做新模式請另開 class。
- 不適合在真正 production 使用；僅供測試 / Demo。
- 若新增 SymbolMeta 欄位，可在這裡使用，但需保留向後相容預設值。
