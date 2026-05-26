# gui 套件

> `build_win/src/gui.py` 為 PyQt6 主視窗，~4500 行單檔。為避免單一 skill 過於龐大，依「分頁 / 子主題」拆成多份 skill。

| 子主題 | skill |
|--------|-------|
| 概觀：主視窗 / 配色 / UI 元件工廠 | [`app_overview.skill.md`](./app_overview.skill.md) |
| 標題列 + 分頁切換 | [`header_tabs.skill.md`](./header_tabs.skill.md) |
| 儀表板分頁 | [`dashboard.skill.md`](./dashboard.skill.md) |
| 策略設定面板 / 設定頁 | [`strategy_settings.skill.md`](./strategy_settings.skill.md) |
| 券商設定頁 | [`broker_settings_page.skill.md`](./broker_settings_page.skill.md) |
| 委託 / 成交 / 持倉 / 事件 / 鎖板測試 / 決策明細 分頁 | [`other_tabs.skill.md`](./other_tabs.skill.md) |
| 策略啟動 / 停止流程 | [`trading_lifecycle.skill.md`](./trading_lifecycle.skill.md) |
| 即時行情錄製 hook | [`recorder_hook.skill.md`](./recorder_hook.skill.md) |
| Log 訊息流程（push_log / 過濾） | [`logging_pipeline.skill.md`](./logging_pipeline.skill.md) |
| 帳戶 polling 與成交統計 | [`account_polling.skill.md`](./account_polling.skill.md) |
