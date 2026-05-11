"""
broker.recording — 盤中行情錄製模組（Phase 1）

提供 RecordingWriter，把 SDK 推送的原始 JSON 訊息以及解析後的
TickEvent / BookEvent 寫入 gzip-NDJSON 檔，供事後分析或日後復盤使用。

設計重點：
- 背景 thread + bounded Queue，避免阻塞 SDK callback / engine 主流程
- queue 滿時優先丟棄 "raw" 行（保留結構化 tick / book）
- 主程式結束時呼叫 close()，flush 殘餘訊息並寫入 meta.json 的 stats
- 對既有流程零侵入：FubonRealtimeFeed.attach_recorder() 後才開始錄
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import queue
import shutil
import threading
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .models import BookEvent, BookLevel, TickEvent

_logger = logging.getLogger("broker.recording")
_logger.setLevel(logging.DEBUG)


# ─────────────────────────────────────────────────────────
#  JSON 序列化輔助
# ─────────────────────────────────────────────────────────

def _json_default(o: Any) -> Any:
    if isinstance(o, Decimal):
        # 保留字串形式避免浮點精度損失
        return str(o)
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if is_dataclass(o):
        return asdict(o)
    if isinstance(o, BookLevel):
        return {"price": str(o.price), "volume": int(o.volume)}
    if hasattr(o, "__dict__"):
        return o.__dict__
    return str(o)


def _dumps(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, default=_json_default)


# ─────────────────────────────────────────────────────────
#  RecordingWriter
# ─────────────────────────────────────────────────────────

class RecordingWriter:
    """
    錄製盤中行情至 gzip-ndjson。

    檔案結構：
        <out_root>/<YYYYMMDD>/session_<HHMMSS>.ticks.ndjson.gz
        <out_root>/<YYYYMMDD>/session_<HHMMSS>.meta.json

    用法：
        writer = RecordingWriter(out_root="log/recordings")
        writer.start(meta={...})
        writer.write_raw("<raw json string>")
        writer.write_tick(tick_event)
        writer.write_book(book_event)
        writer.close()
    """

    def __init__(
        self,
        out_root: str | Path,
        queue_size: int = 20000,
        log_cb: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._out_root = Path(out_root)
        self._queue_size = max(1000, int(queue_size))
        self._log_cb = log_cb
        self._queue: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=self._queue_size)
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        # 開檔資訊
        self._session_id: str = ""
        self._session_dir: Optional[Path] = None
        self._ticks_path: Optional[Path] = None
        self._meta_path: Optional[Path] = None
        self._fp: Optional[gzip.GzipFile] = None

        # 統計
        self._raw_count: int = 0
        self._tick_count: int = 0
        self._book_count: int = 0
        self._dropped_count: int = 0
        self._start_ts: Optional[float] = None
        self._end_ts: Optional[float] = None

    # ── 對外 API ──────────────────────────────────────────

    def start(self, meta: Optional[dict] = None) -> Path:
        """建立檔案、啟動 writer thread。回傳 session 目錄。"""
        with self._lock:
            if self._running:
                return self._session_dir  # type: ignore[return-value]

            now = datetime.now()
            day = now.strftime("%Y%m%d")
            hms = now.strftime("%H%M%S")
            self._session_id = f"{day}_{hms}"
            self._session_dir = self._out_root / day
            self._session_dir.mkdir(parents=True, exist_ok=True)
            self._ticks_path = self._session_dir / f"session_{hms}.ticks.ndjson.gz"
            self._meta_path = self._session_dir / f"session_{hms}.meta.json"

            self._fp = gzip.open(self._ticks_path, "wb", compresslevel=5)
            self._start_ts = time.time()
            self._raw_count = 0
            self._tick_count = 0
            self._book_count = 0
            self._dropped_count = 0
            self._running = True

            # 先寫一份初始 meta（含 config_snapshot / symbol_universe），收尾再覆寫
            self._initial_meta = dict(meta or {})
            self._initial_meta["session_id"] = self._session_id
            self._initial_meta["start_ts"] = now.isoformat()
            self._write_meta_snapshot(final=False)

            self._thread = threading.Thread(
                target=self._writer_loop,
                name=f"RecordingWriter-{self._session_id}",
                daemon=True,
            )
            self._thread.start()
            self._log("INFO", f"[Recording] 開始錄製 → {self._ticks_path}")
            return self._session_dir

    def write_raw(self, raw_msg: Any) -> None:
        if not self._running:
            return
        try:
            line = _dumps({"t": time.time(), "kind": "raw", "msg": str(raw_msg)})
        except Exception:
            return
        self._enqueue(line, drop_if_full=True)

    def write_tick(self, ev: TickEvent) -> None:
        if not self._running:
            return
        try:
            line = _dumps({
                "t": time.time(),
                "kind": "tick",
                "code": ev.code,
                "time": ev.time.isoformat() if ev.time else None,
                "price": str(ev.price) if ev.price is not None else None,
                "volume": int(ev.volume or 0),
                "cum_volume": int(getattr(ev, "cum_volume", 0) or 0),
                "prev_close": str(ev.prev_close) if getattr(ev, "prev_close", None) else None,
            })
        except Exception as e:
            self._log("WARN", f"[Recording] write_tick 序列化失敗：{e}")
            return
        self._enqueue(line, drop_if_full=False)
        self._tick_count += 1

    def write_book(self, ev: BookEvent) -> None:
        if not self._running:
            return
        try:
            line = _dumps({
                "t": time.time(),
                "kind": "book",
                "code": ev.code,
                "time": ev.time.isoformat() if ev.time else None,
                "ask": [{"price": str(l.price), "volume": int(l.volume)} for l in (ev.ask or [])],
                "bid": [{"price": str(l.price), "volume": int(l.volume)} for l in (ev.bid or [])],
            })
        except Exception as e:
            self._log("WARN", f"[Recording] write_book 序列化失敗：{e}")
            return
        self._enqueue(line, drop_if_full=False)
        self._book_count += 1

    def close(self, timeout: float = 5.0) -> None:
        """停止錄製，flush queue 後寫入最終 meta.json。"""
        with self._lock:
            if not self._running:
                return
            self._running = False
            # 用 None 作為 sentinel 通知 writer thread 結束
            try:
                self._queue.put(None, timeout=1.0)
            except queue.Full:
                pass

        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

        # 收尾：關檔 + 寫 meta
        if self._fp is not None:
            try:
                self._fp.close()
            except Exception:
                pass
            self._fp = None

        self._end_ts = time.time()
        self._write_meta_snapshot(final=True)
        try:
            size_mb = self._ticks_path.stat().st_size / (1024 * 1024) if self._ticks_path else 0
        except Exception:
            size_mb = 0
        self._log("INFO",
            f"[Recording] 結束錄製 raw={self._raw_count} tick={self._tick_count} "
            f"book={self._book_count} dropped={self._dropped_count} "
            f"size={size_mb:.2f}MB → {self._ticks_path}")

    # ── 屬性 ──────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def session_dir(self) -> Optional[Path]:
        return self._session_dir

    def stats(self) -> dict:
        return {
            "raw_count": self._raw_count,
            "tick_count": self._tick_count,
            "book_count": self._book_count,
            "dropped_count": self._dropped_count,
        }

    # ── 內部 ──────────────────────────────────────────────

    def _enqueue(self, line: str, *, drop_if_full: bool) -> None:
        data = (line + "\n").encode("utf-8")
        try:
            self._queue.put_nowait(data)
        except queue.Full:
            if drop_if_full:
                # raw 訊息可丟棄（保留結構化的 tick/book）
                self._dropped_count += 1
                return
            # 結構化資料：阻塞短時間後再丟一次
            try:
                self._queue.put(data, timeout=0.5)
            except queue.Full:
                self._dropped_count += 1

    def _writer_loop(self) -> None:
        """背景 thread：批次寫入檔案，每 N 筆或每 1 秒 flush 一次。"""
        BATCH = 200
        FLUSH_INTERVAL = 1.0
        buf: List[bytes] = []
        last_flush = time.time()
        while True:
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                item = b""  # 空輪詢 → 觸發 flush 檢查
            if item is None:
                # sentinel：把剩餘的寫完就結束
                if buf and self._fp is not None:
                    try:
                        self._fp.write(b"".join(buf))
                    except Exception as e:
                        self._log("ERROR", f"[Recording] 收尾 flush 失敗：{e}")
                break
            if item:
                buf.append(item)
                # 統計（粗略；raw 行的判斷用 prefix 即可）
                # 已在 write_tick/write_book 累加；raw 在這裡累加
                if b'"kind": "raw"' in item or b'"kind":"raw"' in item:
                    self._raw_count += 1

            now = time.time()
            if buf and (len(buf) >= BATCH or (now - last_flush) >= FLUSH_INTERVAL):
                try:
                    if self._fp is not None:
                        self._fp.write(b"".join(buf))
                except Exception as e:
                    self._log("ERROR", f"[Recording] 寫檔失敗：{e}")
                buf.clear()
                last_flush = now

    def _write_meta_snapshot(self, *, final: bool) -> None:
        if self._meta_path is None:
            return
        try:
            meta = dict(self._initial_meta)
            if final:
                meta["end_ts"] = datetime.fromtimestamp(self._end_ts).isoformat() if self._end_ts else None
                meta["duration_sec"] = round((self._end_ts or 0) - (self._start_ts or 0), 2)
            meta["stats"] = self.stats()
            with open(self._meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2, default=_json_default)
        except Exception as e:
            self._log("WARN", f"[Recording] 寫 meta.json 失敗：{e}")

    def _log(self, level: str, msg: str) -> None:
        _logger.log(
            {"DEBUG": logging.DEBUG, "INFO": logging.INFO,
             "WARN": logging.WARNING, "ERROR": logging.ERROR}.get(level, logging.DEBUG),
            msg,
        )
        if self._log_cb is not None:
            try:
                self._log_cb(level, msg)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────
#  目錄管理
# ─────────────────────────────────────────────────────────

def cleanup_old_recordings(
    out_root: str | Path,
    keep_days: int,
    log_cb: Optional[Callable[[str, str], None]] = None,
) -> int:
    """
    刪除 out_root 底下日期目錄（YYYYMMDD），保留最近 keep_days 天。
    回傳刪除的目錄數。keep_days <= 0 視為「不清理」。
    """
    if keep_days is None or keep_days <= 0:
        return 0
    root = Path(out_root)
    if not root.exists():
        return 0
    today = date.today()
    removed = 0
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        name = entry.name
        if len(name) != 8 or not name.isdigit():
            continue
        try:
            d = date(int(name[:4]), int(name[4:6]), int(name[6:8]))
        except Exception:
            continue
        if (today - d).days > keep_days:
            try:
                shutil.rmtree(entry)
                removed += 1
                if log_cb:
                    try:
                        log_cb("INFO", f"[Recording] 清除過期錄製：{entry}")
                    except Exception:
                        pass
            except Exception as e:
                if log_cb:
                    try:
                        log_cb("WARN", f"[Recording] 清除失敗 {entry}：{e}")
                    except Exception:
                        pass
    return removed


def default_recording_root() -> Path:
    """預設錄製存放路徑：與 exe / src 同層 log/recordings/。"""
    import sys
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "log" / "recordings"
