"""
app_logging.py — 集中管理實體 log 檔、stdout/stderr 與未捕捉例外。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from datetime import datetime
from types import TracebackType
from typing import Optional, TextIO

ExcInfo = tuple[
    Optional[type[BaseException]],
    Optional[BaseException],
    Optional[TracebackType],
]


def runtime_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def build_runtime_log_path(base_dir: str = "", now: Optional[datetime] = None) -> str:
    base = base_dir or runtime_base_dir()
    stamp = (now or datetime.now()).strftime("%Y%m%d")
    return os.path.join(base, "log", f"program.log.{stamp}")


def read_file_logging_flag(config_path: str, default: bool = True) -> bool:
    if not os.path.exists(config_path):
        return default
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        value = data.get("file_logging_enabled", default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}
    except Exception:
        return default


def compose_log_message(
    level: str,
    message: object,
    *,
    include_traceback: Optional[bool] = None,
    exc_info: Optional[ExcInfo] = None,
) -> str:
    text = str(message)
    current_exc = exc_info or sys.exc_info()
    if include_traceback is None:
        include_traceback = level.upper() in {"ERROR", "WARN", "DEBUG"} and current_exc[0] is not None
    if include_traceback and current_exc[0] is not None and current_exc[1] is not None:
        details = "".join(
            traceback.format_exception(current_exc[0], current_exc[1], current_exc[2])
        ).rstrip()
        if details and details not in text:
            text = f"{text}\n{details}"
    return text


class _TeeStream:
    def __init__(self, manager: "RuntimeLogManager", stream: Optional[TextIO], name: str):
        self._manager = manager
        self._stream = stream
        self._name = name
        self.encoding = getattr(stream, "encoding", "utf-8")

    def write(self, data: str) -> int:
        if self._stream is not None:
            written = self._stream.write(data)
            self._stream.flush()
        else:
            written = len(data)
        self._manager.write_stream(self._name, data)
        return written

    def flush(self) -> None:
        if self._stream is not None:
            self._stream.flush()

    def __getattr__(self, item):
        if self._stream is None:
            raise AttributeError(item)
        return getattr(self._stream, item)


class RuntimeLogManager:
    def __init__(self) -> None:
        self._enabled = False
        self._base_dir = runtime_base_dir()
        self._lock = threading.Lock()
        self._stream_buffers = {"STDOUT": "", "STDERR": ""}
        self._stdout_installed = False
        self._hooks_installed = False
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        self._orig_sys_excepthook = sys.excepthook
        self._orig_threading_excepthook = getattr(threading, "excepthook", None)

    def configure(self, enabled: bool, base_dir: str = "") -> Optional[str]:
        if base_dir:
            self._base_dir = base_dir
        self._enabled = enabled
        if not enabled:
            self.uninstall()
            return None
        self.install()
        path = build_runtime_log_path(self._base_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def install(self) -> None:
        if not self._stdout_installed:
            sys.stdout = _TeeStream(self, self._orig_stdout, "STDOUT")
            sys.stderr = _TeeStream(self, self._orig_stderr, "STDERR")
            self._stdout_installed = True
        if not self._hooks_installed:
            sys.excepthook = self._handle_exception
            if hasattr(threading, "excepthook"):
                threading.excepthook = self._handle_thread_exception
            self._hooks_installed = True

    def uninstall(self) -> None:
        if self._stdout_installed:
            sys.stdout = self._orig_stdout
            sys.stderr = self._orig_stderr
            self._stdout_installed = False
            self._stream_buffers = {"STDOUT": "", "STDERR": ""}
        if self._hooks_installed:
            sys.excepthook = self._orig_sys_excepthook
            if hasattr(threading, "excepthook") and self._orig_threading_excepthook is not None:
                threading.excepthook = self._orig_threading_excepthook
            self._hooks_installed = False

    def is_enabled(self) -> bool:
        return self._enabled

    def get_path(self) -> Optional[str]:
        if not self._enabled:
            return None
        return build_runtime_log_path(self._base_dir)

    def write_event(self, level: str, message: object) -> None:
        if not self._enabled:
            return
        self._write_lines(level.upper(), str(message))

    def write_stream(self, stream_name: str, data: str) -> None:
        if not self._enabled or not data:
            return
        with self._lock:
            buffer = self._stream_buffers[stream_name] + data
            lines = buffer.splitlines(keepends=True)
            if lines and not lines[-1].endswith(("\n", "\r")):
                self._stream_buffers[stream_name] = lines.pop()
            else:
                self._stream_buffers[stream_name] = ""
            self._write_lines_locked(stream_name, [line.rstrip("\r\n") for line in lines if line.strip("\r\n")])

    def _handle_exception(self, exc_type, exc_value, exc_traceback) -> None:
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)).rstrip()
        self.write_event("ERROR", details)
        self._orig_sys_excepthook(exc_type, exc_value, exc_traceback)

    def _handle_thread_exception(self, args) -> None:
        details = "".join(
            traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
        ).rstrip()
        thread_name = args.thread.name if args.thread is not None else "unknown"
        self.write_event("ERROR", f"執行緒未捕捉例外：{thread_name}\n{details}")
        if self._orig_threading_excepthook is not None:
            self._orig_threading_excepthook(args)

    def _write_lines(self, tag: str, text: str) -> None:
        with self._lock:
            lines = text.splitlines() or [text]
            self._write_lines_locked(tag, lines)

    def _write_lines_locked(self, tag: str, lines: list[str]) -> None:
        if not lines:
            return
        path = build_runtime_log_path(self._base_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as f:
            for line in lines:
                f.write(f"{timestamp} [{tag}] {line}\n")


_MANAGER = RuntimeLogManager()


def configure_runtime_logging(enabled: bool, base_dir: str = "") -> Optional[str]:
    return _MANAGER.configure(enabled, base_dir)


def write_log_event(level: str, message: object) -> None:
    _MANAGER.write_event(level, message)


def get_runtime_log_path() -> Optional[str]:
    return _MANAGER.get_path()


def is_runtime_logging_enabled() -> bool:
    return _MANAGER.is_enabled()