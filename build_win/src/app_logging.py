"""
app_logging.py — 集中管理實體 log 檔、stdout/stderr 與未捕捉例外。
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
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

_BASE64_LINE_RE = re.compile(r"^[A-Za-z0-9+/=]+$")
_SDK_PREFIX_RE = re.compile(r"^\[(?P<prefix>[^\]]+)\]\s*(?P<message>.*)$")
_SENSITIVE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r'personal_id\s*=\s*"[^"]+"', re.IGNORECASE), 'personal_id="<redacted>"'),
    (re.compile(r'"(idno|personal_id|token|value|auth)"\s*:\s*"[^"]+"', re.IGNORECASE), r'"\1":"<redacted>"'),
)
_SDK_NOISE_TOKENS = (
    "tungstenite::",
    "sdk_core::",
    "[ws response body]",
    "[ws system body]",
    "[method call]",
    "future_option_mapping",
    "getnfomacomext",
)
_SDK_NOISE_MESSAGES = (
    "trying to connect to",
    "trying to contact wss:",
    "successfully connected to websocket",
    "start ping pong schedule",
    "[login] personal_id=",
)
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_TRACEBACK_HEADER = "Traceback (most recent call last):"
_TRACEBACK_CHAIN_PREFIXES = (
    "During handling of the above exception",
    "The above exception was the direct cause",
)
_EXCEPTION_SUMMARY_RE = re.compile(
    r"^(?:[A-Za-z_]\w*\.)*[A-Z][A-Za-z_]\w*"
    r"(?:Error|Exception|Warning|Interrupt|Exit|Abort|Fault)?(?::\s?.*)$"
)


def strip_log_control_codes(text: str) -> str:
    cleaned = _ANSI_ESCAPE_RE.sub("", str(text))
    return "".join(
        char for char in cleaned
        if char in "\n\r\t" or ord(char) >= 32
    )


def _is_traceback_noise(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped == _TRACEBACK_HEADER:
        return True
    if stripped.startswith("File \""):
        return True
    if any(stripped.startswith(prefix) for prefix in _TRACEBACK_CHAIN_PREFIXES):
        return True
    if stripped and all(char in "^~ " for char in stripped):
        return True
    return False


def _is_exception_summary(line: str) -> bool:
    stripped = line.strip()
    if ":" not in stripped:
        return False
    return bool(_EXCEPTION_SUMMARY_RE.match(stripped))


def normalize_log_lines_for_file(text: str) -> list[str]:
    raw_lines = strip_log_control_codes(str(text)).splitlines() or [str(text)]
    lines = [line.strip() for line in raw_lines if line.strip()]
    if not lines:
        return []

    if _TRACEBACK_HEADER not in lines:
        return [line for line in lines if not _is_traceback_noise(line)]

    context_lines: list[str] = []
    exception_summary = ""
    in_traceback = False
    for line in lines:
        if line == _TRACEBACK_HEADER:
            in_traceback = True
            continue
        if in_traceback:
            if _is_exception_summary(line):
                exception_summary = line
            continue
        if not _is_traceback_noise(line):
            context_lines.append(line)

    if exception_summary and all(exception_summary not in line for line in context_lines):
        context_lines.append(exception_summary)
    return context_lines


def _looks_like_base64_line(text: str) -> bool:
    stripped = text.strip()
    return len(stripped) >= 40 and len(stripped) % 4 == 0 and bool(_BASE64_LINE_RE.fullmatch(stripped))


def _decode_base64_line(text: str) -> str:
    if not _looks_like_base64_line(text):
        return text
    try:
        decoded = base64.b64decode(text.strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return text
    printable = sum(ch.isprintable() or ch in "\r\n\t" for ch in decoded)
    if not decoded or printable / len(decoded) < 0.9:
        return text
    return decoded


def _sanitize_stream_line(text: str) -> Optional[str]:
    normalized = strip_log_control_codes(_decode_base64_line(text)).strip()
    if not normalized:
        return None

    match = _SDK_PREFIX_RE.match(normalized)
    if match:
        prefix = match.group("prefix")
        message = match.group("message").strip()
        haystack = f"{prefix} {message}".lower()
        if any(token in haystack for token in _SDK_NOISE_TOKENS):
            return None
        if any(token in message.lower() for token in _SDK_NOISE_MESSAGES):
            return None
        normalized = message or normalized

    lowered = normalized.lower()
    if any(token in lowered for token in _SDK_NOISE_TOKENS):
        return None
    if any(token in lowered for token in _SDK_NOISE_MESSAGES):
        return None
    if len(normalized) > 800 and normalized.count("{") >= 2:
        return None

    for pattern, replacement in _SENSITIVE_PATTERNS:
        normalized = pattern.sub(replacement, normalized)

    return normalized.strip() or None


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
        self._stream_traceback_active = {"STDOUT": False, "STDERR": False}
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
            self._stream_traceback_active = {"STDOUT": False, "STDERR": False}
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
            clean_lines = self._filter_stream_lines(
                stream_name,
                [line.rstrip("\r\n") for line in lines],
            )
            self._write_lines_locked(stream_name, clean_lines)

    def _filter_stream_lines(self, stream_name: str, lines: list[str]) -> list[str]:
        clean_lines: list[str] = []
        for raw_line in lines:
            sanitized = _sanitize_stream_line(raw_line)
            if not sanitized:
                continue
            for item in sanitized.splitlines():
                line = item.strip()
                if not line:
                    continue
                if stream_name == "STDERR":
                    if line == _TRACEBACK_HEADER:
                        self._stream_traceback_active[stream_name] = True
                        continue
                    if self._stream_traceback_active.get(stream_name, False):
                        if _is_exception_summary(line):
                            clean_lines.append(line)
                            self._stream_traceback_active[stream_name] = False
                        continue
                    if _is_traceback_noise(line):
                        continue
                clean_lines.append(line)
        return clean_lines

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
            lines = normalize_log_lines_for_file(text)
            self._write_lines_locked(tag, lines)

    def _write_lines_locked(self, tag: str, lines: list[str]) -> None:
        if not lines:
            return
        path = build_runtime_log_path(self._base_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as f:
            for line in lines:
                cleaned = strip_log_control_codes(line).strip()
                if cleaned:
                    f.write(f"{timestamp} [{tag}] {cleaned}\n")


_MANAGER = RuntimeLogManager()


def configure_runtime_logging(enabled: bool, base_dir: str = "") -> Optional[str]:
    return _MANAGER.configure(enabled, base_dir)


def write_log_event(level: str, message: object) -> None:
    _MANAGER.write_event(level, message)


def get_runtime_log_path() -> Optional[str]:
    return _MANAGER.get_path()


def is_runtime_logging_enabled() -> bool:
    return _MANAGER.is_enabled()