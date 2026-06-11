---
name: optimize-limit-up-strategy
description: Investigate, repair, validate, and continuously improve limit-up lock detection and entry timing in the little-bao trading project. Use when a stock is detected or bought too early, too late, or not at all; when tick/book signals disagree; when changing limit-up modes; when replaying recordings; or when comparing program decisions with a human-observed true lock time.
---

# Optimize Limit-Up Strategy

Use evidence-driven replay and cross-stock regression. Do not tune a rule only to match one stock.

## Start Here

1. Locate the project root containing `build_win/src/engine.py`.
2. Read:
   - `docs/鎖漲策略問題修復與持續優化手冊.zh-tw.md`
   - `docs/skills/limitup/limitup_detection.skill.md`
   - `docs/skills/engine/market_input.skill.md`
   - `docs/skills/utils/analyze_limitup_logs.skill.md`
3. Read [references/diagnostic-workflow.md](references/diagnostic-workflow.md) before diagnosing or editing.

## Required Workflow

1. State the target date, stock codes, reported true lock times, and whether the symptom is early, late, or missing detection.
2. Collect raw recording, meta, decision events, audit/order records, and program log. Search Windows runtime paths when project-local logs are incomplete.
3. Separate these timestamps:
   - human-observed true lock
   - candidate lock market event
   - confirmed lock market event
   - local receive
   - strategy decision
   - order submit
   - fill
4. Confirm the mode actually used that day from `meta.json` or runtime logs. Never substitute the current default.
5. Replay the exact event order. Treat tick and book as asynchronous streams.
6. Classify the root cause before editing:
   - rule too broad or too strict
   - zero-price placeholder level
   - stale tick flag reused by a new book segment
   - event-order or state-reset bug
   - market-to-receive latency
   - decision/order latency
   - entry filter or monitoring-pool exclusion
7. Add a failing regression test that reproduces the event sequence.
8. Implement the smallest general rule. Prefer explicit segment/state transitions over additional snapshot booleans.
9. Validate the original problem stock, every previously fixed stock affected by the same logic, a normal positive sample, and a negative touch-without-lock sample.
10. Run the complete test suite and update the project handbook and related `docs/skills/`.

## Hard Rules

- Never add stock-code exceptions.
- Never invent missing buy, order, or fill timestamps.
- Never use a fixed delay solely to match a human timestamp.
- Never treat a broker API flag as an official single source of truth for a complete lock.
- Never claim analyzer output equals production behavior unless analyzer, replay, and engine semantics are verified equivalent.
- Never finish after only unit-testing the newly added case.

## Implementation Guidance

- Keep stateless signal extraction in `limitup_detection.py`.
- Keep cross-event and continuous-segment state in `engine.py`.
- Ignore `price <= 0` placeholder book levels when deriving an effective best bid.
- Reset confirmation when a continuous lock candidate segment ends.
- Require a new confirming tick inside a new segment when using tick-confirmed lock mode.
- Preserve candidate, confirmed, decision, order, and fill timestamps independently.

## Expected Output

Produce a concise investigation table with:

| Stock | Program decision/buy time | True lock time | Optimized time | Root cause | Evidence |
|---|---|---|---|---|---|

Mark unavailable values as unavailable and name the missing artifact.

Report:

- files changed
- behavior before and after
- replay or test evidence
- complete test result
- residual uncertainty and required next recording
