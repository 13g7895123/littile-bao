# Isolated Fubon Latency Probe

This folder is a standalone probe for checking whether realtime latency comes from:

- config-based candidate selection
- SDK login
- websocket subscription
- server-side event timestamps vs local receive time

It does not depend on the GUI flow. It only uses:

- the trading config file
- the Fubon SDK
- the previous-trading-days API for candidate selection

Run:

```bash
python3 isolated_fubon_latency_probe/latency_probe.py
```

Non-interactive run:

```bash
python3 isolated_fubon_latency_probe/latency_probe.py --non-interactive
```
