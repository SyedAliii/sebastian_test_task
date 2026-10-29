import json
import logging
import secrets
import string
import sys
import threading
import time
from typing import Any

from app.config import Settings

_RANK = {"none": 0, "high": 1, "mid": 2, "low": 3}
_HIGH = 1
_MID = 2
_LOW = 3
_ID_ALPHABET = string.ascii_uppercase + string.digits
_REDACT_PARTS = ("authorization", "signature", "secret", "cookie", "x-signature")

_RESET = "\033[0m"
_BLUE = "\033[34m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_MAGENTA = "\033[35m"
_GREY = "\033[90m"

_EMOJI = {
    "REQ": "📥 ",
    "RES": "📤 ",
    "API_REQUEST_OUT": "📤 ",
    "API_RESPONSE_IN": "📥 ",
    "WEBHOOK_IN": "🔔 ",
    "WEBHOOK_FAIL": "🚫 ",
    "JOB_START": "▶️ ",
    "JOB_END": "⏹️ ",
    "PIPELINE": "🔗 ",
    "BUSINESS": "💼 ",
    "WARN": "⚠️ ",
    "ERROR": "❌ ",
    "SYSTEM": "🖥️ ",
    "LOG_CONFIG": "📋 ",
    "PAYLOAD": "📎 ",
}


class CorrelationManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started: dict[str, float] = {}

    def new_id(self) -> str:
        return "".join(secrets.choice(_ID_ALPHABET) for _ in range(8))

    def start(self, correlation_id: str) -> None:
        with self._lock:
            self._started[correlation_id] = time.perf_counter()

    def elapsed(self, correlation_id: str) -> float:
        with self._lock:
            started = self._started.get(correlation_id)
        if started is None:
            return 0.0
        return time.perf_counter() - started

    def clear_correlation(self, correlation_id: str) -> None:
        with self._lock:
            self._started.pop(correlation_id, None)


correlation_manager = CorrelationManager()


def _redact(value: Any, depth: int, max_depth: int) -> Any:
    if depth > max_depth:
        return "…<truncated>"
    if isinstance(value, dict):
        cleaned: dict[Any, Any] = {}
        for key, item in value.items():
            if any(part in str(key).lower() for part in _REDACT_PARTS):
                cleaned[key] = "<redacted>"
            else:
                cleaned[key] = _redact(item, depth + 1, max_depth)
        return cleaned
    if isinstance(value, list):
        items = [_redact(item, depth + 1, max_depth) for item in value[:50]]
        if len(value) > 50:
            items.append("…<truncated>")
        return items
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "…<truncated>"
    return value


class AppLogger:
    def __init__(self) -> None:
        self._detail_rank = _RANK["mid"]
        self._emojis = True
        self._json_max_size = 50000
        self._json_max_depth = 10
        self._logger = logging.getLogger("moderation")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False

    def apply_log_settings(self, settings: Settings) -> None:
        if sys.platform == "win32":
            reconfigure = getattr(sys.stdout, "reconfigure", None)
            if reconfigure is not None:
                reconfigure(encoding="utf-8", errors="replace")
        self._detail_rank = _RANK[settings.log_detail_level]
        self._emojis = settings.log_enable_emojis
        self._json_max_size = settings.log_json_max_size
        self._json_max_depth = settings.log_json_max_depth
        self._ensure_handler()
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    def log_level_banner(self, service: str, detail_level: str | None = None, extra: str | None = None) -> None:
        self._ensure_handler()
        level = detail_level or self._level_name()
        message = f"{service} log_detail_level={level}"
        if extra:
            message = f"{message} {extra}"
        self._write("LOG_CONFIG", message, None, _CYAN, logging.INFO)

    def server_request_in(self, method: str, path: str, client: str = "-") -> str:
        correlation_id = correlation_manager.new_id()
        correlation_manager.start(correlation_id)
        self._emit(_MID, "REQ", f"{method} {path} from {client}", correlation_id, _CYAN)
        return correlation_id

    def server_response_out(self, status: int, path: str, correlation_id: str | None = None) -> None:
        elapsed = correlation_manager.elapsed(correlation_id) if correlation_id else 0.0
        self._emit(
            _MID,
            "RES",
            f"[{elapsed:.2f}s] {status} {path}",
            correlation_id,
            _status_color(status),
        )

    def api_request_out(
        self,
        url: str,
        method: str = "POST",
        payload: Any = None,
        correlation_id: str | None = None,
    ) -> str:
        cid = correlation_id or correlation_manager.new_id()
        if correlation_id is None:
            correlation_manager.start(cid)
        self._emit(_MID, "API_REQUEST_OUT", f"{method} {url}", cid, _BLUE)
        if payload is not None:
            self._emit(_LOW, "PAYLOAD", self.format_json(payload), cid, _GREY)
        return cid

    def api_response_in(self, url: str, status: int = 0, correlation_id: str | None = None) -> None:
        elapsed = correlation_manager.elapsed(correlation_id) if correlation_id else 0.0
        self._emit(
            _MID,
            "API_RESPONSE_IN",
            f"[{elapsed:.2f}s] {status} {url}",
            correlation_id,
            _status_color(status),
        )

    def webhook_in(self, name: str, payload: Any = None, source: str = "-") -> str:
        correlation_id = correlation_manager.new_id()
        correlation_manager.start(correlation_id)
        self._emit(_HIGH, "WEBHOOK_IN", f"name={name} source={source}", correlation_id, _MAGENTA)
        if payload is not None:
            self._emit(_LOW, "PAYLOAD", self.format_json(payload), correlation_id, _GREY)
        return correlation_id

    def webhook_fail(
        self,
        name: str,
        source: str = "-",
        error: str = "-",
        correlation_id: str | None = None,
    ) -> None:
        self._emit(
            _HIGH,
            "WEBHOOK_FAIL",
            f"name={name} source={source} error={error}",
            correlation_id,
            _YELLOW,
            level=logging.WARNING,
        )

    def job_start(self, msg: str, correlation_id: str | None = None) -> str:
        cid = correlation_id or correlation_manager.new_id()
        if correlation_id is None:
            correlation_manager.start(cid)
        self._emit(_MID, "JOB_START", msg, cid, _BLUE)
        return cid

    def job_end(self, msg: str, status: str = "ok", correlation_id: str | None = None) -> None:
        elapsed = correlation_manager.elapsed(correlation_id) if correlation_id else 0.0
        color = _GREEN if status == "ok" else _RED
        self._emit(_MID, "JOB_END", f"[{elapsed:.2f}s] status={status} {msg}", correlation_id, color)

    def pipeline(self, msg: str, correlation_id: str | None = None) -> None:
        self._emit(_MID, "PIPELINE", msg, correlation_id, _CYAN)

    def business_flow(self, msg: str, step: str = "-", correlation_id: str | None = None) -> None:
        self._emit(_LOW, "BUSINESS", f"step={step} {msg}", correlation_id, _MAGENTA)

    def warning(self, msg: str, correlation_id: str | None = None) -> None:
        self._emit(_HIGH, "WARN", msg, correlation_id, _YELLOW, level=logging.WARNING)

    def error_trace(
        self,
        msg: str,
        exc_info: bool | BaseException = True,
        correlation_id: str | None = None,
    ) -> None:
        self._emit(_HIGH, "ERROR", msg, correlation_id, _RED, level=logging.ERROR, exc_info=exc_info)

    def system_info(self, msg: str, correlation_id: str | None = None) -> None:
        self._emit(_MID, "SYSTEM", msg, correlation_id, _CYAN)

    def format_json(self, data: Any) -> str:
        cleaned = _redact(data, 0, self._json_max_depth)
        text = json.dumps(cleaned, default=str, ensure_ascii=False)
        if len(text) > self._json_max_size:
            return text[: self._json_max_size] + "…<truncated>"
        return text

    def _level_name(self) -> str:
        for name, rank in _RANK.items():
            if rank == self._detail_rank:
                return name
        return "mid"

    def _ensure_handler(self) -> None:
        if self._logger.handlers:
            return
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s.%(msecs)03d - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )
        self._logger.addHandler(handler)

    def _emit(
        self,
        priority: int,
        label: str,
        message: str,
        correlation_id: str | None,
        color: str,
        *,
        level: int = logging.INFO,
        exc_info: bool | BaseException | None = None,
    ) -> None:
        if self._detail_rank < priority:
            return
        self._ensure_handler()
        self._write(label, message, correlation_id, color, level, exc_info=exc_info)

    def _write(
        self,
        label: str,
        message: str,
        correlation_id: str | None,
        color: str,
        level: int,
        *,
        exc_info: bool | BaseException | None = None,
    ) -> None:
        emoji = _EMOJI.get(label, "") if self._emojis else ""
        if correlation_id:
            colored = f"{color}[{correlation_id}] {label}{_RESET}"
        else:
            colored = f"{color}{label}{_RESET}"
        self._logger.log(level, f"{emoji}{colored} {message}", exc_info=exc_info)


def _status_color(status: int) -> str:
    if status >= 500:
        return _RED
    if status >= 400:
        return _YELLOW
    return _GREEN


logger = AppLogger()


def apply_log_settings(settings: Settings) -> None:
    logger.apply_log_settings(settings)


def log_level_banner(service: str, detail_level: str | None = None, extra: str | None = None) -> None:
    logger.log_level_banner(service, detail_level=detail_level, extra=extra)


def format_json(data: Any) -> str:
    return logger.format_json(data)
