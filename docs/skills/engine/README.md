# engine 套件

> `build_win/src/engine.py` 為單一檔 (~1500 行) 的策略引擎，但職責多元。為避免單一 skill 過於龐大，依「子主題」拆成多份 skill。

| 子主題 | skill |
|--------|-------|
| 核心物件與資料結構 | [`core_objects.skill.md`](./core_objects.skill.md) |
| 行情輸入處理（tick / book / 漲停判斷） | [`market_input.skill.md`](./market_input.skill.md) |
| 策略主迴圈與進出場決策 | [`strategy_loop.skill.md`](./strategy_loop.skill.md) |
| 券商回報處理（order / fill） | [`broker_callbacks.skill.md`](./broker_callbacks.skill.md) |
| 對外 API（GUI 呼叫的 surface） | [`public_api.skill.md`](./public_api.skill.md) |
| 事件與決策日誌 | [`events_and_logs.skill.md`](./events_and_logs.skill.md) |
