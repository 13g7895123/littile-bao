# Diagnostic Workflow

## Evidence Locations

Search in this order:

1. `build_win/dist/log/`
2. `build_win/src/log/`
3. repository `log/`
4. Windows runtime directories documented by `docs/skills/utils/windows_runtime_paths.skill.md`

Required artifacts where available:

- `log/recordings/YYYYMMDD/session_*.ticks.ndjson.gz`
- matching `session_*.meta.json`
- `decision_events.YYYYMMDD.jsonl`
- `dry_run_audit_YYYYMMDD.jsonl` or broker order/fill records
- `program.log.YYYYMMDD`

## Useful Commands

```bash
python3 build_win/src/analyze_limitup_logs.py <ticks-file> --code <code>
python3 build_win/src/replay_limitup_trace.py <ticks-file> --code <code> --mode <mode>
python3 -m unittest build_win.src.tests.test_engine_strategy
python3 -m unittest discover -s build_win/src/tests -p 'test_*.py'
git diff --check
```

Inspect `meta.json` before interpreting results. It records the session configuration and symbol universe.

## Time Comparison

Calculate and report separately:

- detection error = confirmed lock market event - human true lock
- feed latency = receive time - market event
- decision latency = decision time - receive time
- order latency = submit time - decision time
- fill latency = fill time - submit time

Do not call total order/fill latency a detection-rule error.

## Event Sequence Cases To Test

Always consider:

1. Book candidate, then confirming tick.
2. True tick flag before book candidate; it must not confirm the new segment.
3. Candidate opens, closes, then reopens; the new segment must reconfirm.
4. `bid[0].price=0` with a later effective bid at limit.
5. Ask remains at limit with positive volume.
6. Empty ask with no valid bid.
7. Tick touches limit but book never locks.
8. Duplicate, delayed, or out-of-order tick/book events.
9. Startup while already locked.
10. Short lock segment that opens before the one-second loop.

## Regression Matrix

For each change, maintain a matrix:

| Category | Minimum sample |
|---|---|
| Current reported problem | Every reported stock |
| Previous fix | 6174 and any other affected historical stock |
| Positive control | One normal lock |
| Negative control | One touch-without-lock or false flag |
| Timing/order edge | One stale-flag or reordered-event sequence |

Do not accept a change that fixes the current sample while regressing a previous sample.

## Analyzer Parity Check

The production engine may add stateful meaning on top of `evaluate_limit_up_state()`. Before using analyzer output as the optimized production time:

1. Compare analyzer state fields with `StockState`.
2. Compare event application order.
3. Compare candidate-segment reset and confirmation behavior.
4. Add a parity test using the same synthetic event sequence.

If parity is absent, describe analyzer output as a stateless candidate time, not a production confirmed-lock time.
