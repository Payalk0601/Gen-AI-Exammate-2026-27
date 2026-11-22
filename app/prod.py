"""Production hardening for the KachraCheck API (Day 13).

Everything here is additive. In app/main.py add:   from app.prod import install; install(app)

What it does
* Logs latency and LLM token usage for every request (logs/requests.jsonl) and serves GET /metrics.
* Caches LLM responses (TTL + size limit) so repeated questions are instant and cost no tokens.
* Rejects oversized request bodies and over-long questions before they reach the model.
* Flags prompt-injection attempts (and can block them) and redacts leaked API keys from responses.

It is plain ASGI middleware plus a wrapper around app.llm._post, so no endpoint code changes.
"""
import copy
import hashlib
import importlib
import json
import logging
import math
import os
import re
import sys
import threading
import time
from collections import OrderedDict, deque
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("kachracheck")
ROOT = Path(__file__).resolve().parent.parent
QUESTION_KEYS = ("question", "query", "q", "text", "message", "prompt")
SKIP_LOG_PATHS = {"/metrics", "/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}

INJECTION_PATTERNS = {
    "ignore_instructions": re.compile(
        r"\b(ignore|disregard|forget|override)\b.{0,40}\b(instructions?|rules?|prompts?|guidelines?)\b", re.I | re.S
    ),
    "reveal_prompt": re.compile(
        r"\b(reveal|show|print|repeat|leak|display)\b.{0,40}\b(system prompt|your prompt|your instructions|hidden instructions|initial prompt)\b",
        re.I | re.S,
    ),
    "reveal_secrets": re.compile(
        r"\b(api[ _-]?key|secret|password|\.env)\b.{0,40}\b(show|print|reveal|give|tell)\b"
        r"|\b(show|print|reveal|give|tell)\b.{0,40}\b(api[ _-]?key|secret|password|\.env)\b",
        re.I | re.S,
    ),
    "role_override": re.compile(
        r"\b(you are now|pretend to be|pretend you are|developer mode|jailbreak|do anything now|you must act as|act as if you)\b",
        re.I,
    ),
    "delimiter_break": re.compile(r"(</?system>|\[/?INST\]|###\s*(system|instruction))", re.I),
}
KEY_PATTERNS = [
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),  # Groq
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),  # Google / Gemini
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
]


# ---------- settings (read on every use, so tests and .env changes apply immediately) ----------
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def settings() -> dict:
    return {
        "max_body_bytes": _env_int("KC_MAX_BODY_BYTES", 8192),
        "max_question_chars": _env_int("KC_MAX_QUESTION_CHARS", 500),
        "cache_ttl_seconds": _env_int("KC_CACHE_TTL_SECONDS", 600),
        "cache_max_entries": _env_int("KC_CACHE_MAX_ENTRIES", 256),
        "block_injection": os.getenv("KC_BLOCK_INJECTION", "0") == "1",
        "log_dir": os.getenv("KC_LOG_DIR", str(ROOT / "logs")),
    }


# ---------- per-request stats ----------
_STATS: ContextVar = ContextVar("kc_stats", default=None)


def new_stats() -> dict:
    return {"llm_calls": 0, "cache_hits": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "llm_ms": 0.0, "tokens_estimated": False}


# ---------- TTL cache ----------
class TTLCache:
    def __init__(self):
        self._data = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str, ttl: float):
        now = time.monotonic()
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            stamp, value = item
            if now - stamp > ttl:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def put(self, key: str, value, max_entries: int):
        with self._lock:
            self._data[key] = (time.monotonic(), value)
            self._data.move_to_end(key)
            while len(self._data) > max_entries:
                self._data.popitem(last=False)

    def clear(self):
        with self._lock:
            self._data.clear()

    def __len__(self):
        return len(self._data)


CACHE = TTLCache()
RECENT: deque = deque(maxlen=1000)


def cache_key(url: str, payload: dict) -> str:
    return hashlib.sha256(json.dumps({"url": url, "payload": payload}, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# ---------- LLM wrapper: cache + token usage ----------
def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def extract_usage(data):
    """(prompt_tokens, completion_tokens) from a Groq or Gemini response, or None if absent."""
    if not isinstance(data, dict):
        return None
    usage = data.get("usage")
    if isinstance(usage, dict) and ("prompt_tokens" in usage or "total_tokens" in usage):
        prompt = int(usage.get("prompt_tokens", 0))
        total = int(usage.get("total_tokens", prompt + int(usage.get("completion_tokens", 0))))
        return prompt, max(total - prompt, 0)
    meta = data.get("usageMetadata")
    if isinstance(meta, dict) and ("promptTokenCount" in meta or "totalTokenCount" in meta):
        prompt = int(meta.get("promptTokenCount", 0))
        total = int(meta.get("totalTokenCount", prompt + int(meta.get("candidatesTokenCount", 0))))
        return prompt, max(total - prompt, 0)  # includes any "thinking" tokens
    return None


def wrap_post(original):
    """Wrap app.llm._post with a response cache and token counting."""
    if getattr(original, "_kc_wrapped", False):
        return original

    def wrapped(url, headers, payload, *args, **kwargs):
        stats = _STATS.get()
        cfg = settings()
        key = cache_key(url, payload)
        if cfg["cache_ttl_seconds"] > 0:
            hit = CACHE.get(key, cfg["cache_ttl_seconds"])
            if hit is not None:
                if stats is not None:
                    stats["llm_calls"] += 1
                    stats["cache_hits"] += 1
                return copy.deepcopy(hit)
        started = time.perf_counter()
        data = original(url, headers, payload, *args, **kwargs)
        elapsed_ms = (time.perf_counter() - started) * 1000
        usage = extract_usage(data)
        estimated = usage is None
        if usage is None:
            usage = (estimate_tokens(json.dumps(payload, ensure_ascii=False)), estimate_tokens(json.dumps(data, ensure_ascii=False)))
        _account(stats, usage, estimated, elapsed_ms)
        if cfg["cache_ttl_seconds"] > 0:
            CACHE.put(key, copy.deepcopy(data), cfg["cache_max_entries"])
        return data

    wrapped._kc_wrapped = True
    return wrapped


def _account(stats, usage, estimated: bool, elapsed_ms: float):
    if stats is None:
        return
    stats["llm_calls"] += 1
    stats["prompt_tokens"] += usage[0]
    stats["completion_tokens"] += usage[1]
    stats["total_tokens"] += usage[0] + usage[1]
    stats["llm_ms"] += elapsed_ms
    stats["tokens_estimated"] = stats["tokens_estimated"] or estimated


def _dump(value) -> str:
    return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)


def wrap_complete(original):
    """Cache + token counting for app.llm.complete(system, user, provider=None, model=None, ...).

    complete() returns text, so token counts are estimates (about 4 characters per token) unless the
    function returns a dict that carries real usage numbers."""
    if getattr(original, "_kc_wrapped", False):
        return original

    def wrapped(*args, **kwargs):
        stats = _STATS.get()
        cfg = settings()
        call = _dump([args, kwargs])
        key = hashlib.sha256(call.encode("utf-8")).hexdigest()
        if cfg["cache_ttl_seconds"] > 0:
            hit = CACHE.get(key, cfg["cache_ttl_seconds"])
            if hit is not None:
                if stats is not None:
                    stats["llm_calls"] += 1
                    stats["cache_hits"] += 1
                return copy.deepcopy(hit)
        started = time.perf_counter()
        result = original(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - started) * 1000
        usage = extract_usage(result)
        estimated = usage is None
        if usage is None:
            usage = (estimate_tokens(call), estimate_tokens(result if isinstance(result, str) else _dump(result)))
        _account(stats, usage, estimated, elapsed_ms)
        if cfg["cache_ttl_seconds"] > 0:
            CACHE.put(key, copy.deepcopy(result), cfg["cache_max_entries"])
        return result

    wrapped._kc_wrapped = True
    return wrapped


def patch_llm() -> bool:
    """Hook caching and token counting into app.llm. Supports a low-level _post() or a complete() function."""
    try:
        llm = importlib.import_module("app.llm")
    except ImportError:
        log.warning("app.llm not found: caching and token counting are off")
        return False
    if hasattr(llm, "_post"):
        llm._post = wrap_post(llm._post)
        return True
    if hasattr(llm, "complete"):
        original = llm.complete
        wrapped = wrap_complete(original)
        llm.complete = wrapped
        # modules that did `from app.llm import complete` keep their own reference: swap those too
        for name, module in list(sys.modules.items()):
            if name.startswith("app.") and getattr(module, "complete", None) is original:
                module.complete = wrapped
        return True
    log.warning("app.llm has neither _post() nor complete(): caching and token counting are off")
    return False


# ---------- guards ----------
def injection_flags(text: str) -> list:
    return [name for name, pattern in INJECTION_PATTERNS.items() if pattern.search(text or "")]


def secret_values() -> list:
    suffixes = ("_API_KEY", "_TOKEN", "_SECRET", "_PASSWORD")
    return [v for k, v in os.environ.items() if len(v) >= 8 and k.upper().endswith(suffixes)]


def redact(text: str) -> tuple:
    """Replace API keys (from the environment or matching known key formats). Returns (text, count)."""
    count = 0
    for secret in secret_values():
        if secret in text:
            count += text.count(secret)
            text = text.replace(secret, "[redacted]")
    for pattern in KEY_PATTERNS:
        text, n = pattern.subn("[redacted]", text)
        count += n
    return text, count


# ---------- metrics ----------
def percentile(values: list, pct: float):
    if not values:
        return None
    ordered = sorted(values)
    index = max(math.ceil(pct / 100 * len(ordered)) - 1, 0)
    return round(ordered[index], 1)


def summarize(records: list) -> dict:
    served = [r for r in records if not r.get("blocked")]
    llm = [r for r in served if r.get("llm_calls", 0) > 0]
    cold = [r for r in llm if r.get("cache_hits", 0) == 0]
    warm = [r for r in llm if r.get("cache_hits", 0) == r.get("llm_calls", 0)]
    calls = sum(r["llm_calls"] for r in llm)
    hits = sum(r["cache_hits"] for r in llm)

    def lat(rows):
        return [r["latency_ms"] for r in rows]

    def avg(rows, key):
        return round(sum(r.get(key, 0) for r in rows) / len(rows), 1) if rows else None

    return {
        "requests": len(records),
        "served": len(served),
        "blocked": len(records) - len(served),
        "errors_5xx": sum(1 for r in records if r.get("status", 0) >= 500),
        "latency_ms": {"p50": percentile(lat(served), 50), "p95": percentile(lat(served), 95)},
        "cold": {
            "count": len(cold),
            "p50": percentile(lat(cold), 50),
            "p95": percentile(lat(cold), 95),
            "avg_prompt_tokens": avg(cold, "prompt_tokens"),
            "avg_completion_tokens": avg(cold, "completion_tokens"),
            "avg_total_tokens": avg(cold, "total_tokens"),
        },
        "cached": {"count": len(warm), "p50": percentile(lat(warm), 50), "p95": percentile(lat(warm), 95)},
        "llm_calls": calls,
        "cache_hits": hits,
        "cache_hit_rate": round(hits / calls, 3) if calls else None,
        "injection_flagged": sum(1 for r in records if r.get("injection")),
        "tokens_estimated_requests": sum(1 for r in llm if r.get("tokens_estimated")),
    }


def write_log(record: dict):
    RECENT.append(record)
    try:
        folder = Path(settings()["log_dir"])
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / "requests.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        log.warning("could not write request log: %s", e)
    log.info(
        "%s %s -> %s in %.0f ms | llm_calls=%d cache_hits=%d tokens=%d",
        record["method"], record["path"], record["status"], record["latency_ms"],
        record["llm_calls"], record["cache_hits"], record["total_tokens"],
    )


# ---------- ASGI middleware ----------
async def _send_json(send, status: int, payload: dict, started: float):
    body = json.dumps(payload).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        (b"x-process-time-ms", f"{(time.perf_counter() - started) * 1000:.1f}".encode()),
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class ProdMiddleware:
    """Input limits, injection flagging, secret redaction, latency and token logging."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        stats = new_stats()
        token = _STATS.set(stats)
        info = {"injection": [], "blocked": "", "bytes": 0, "chars": 0, "redacted": 0}
        status = 500
        try:
            receive, rejection = await self._inspect(scope, receive, info)
            if rejection:
                status, detail = rejection
                info["blocked"] = detail
                await _send_json(send, status, {"detail": detail}, started)
            else:
                status = await self._forward(scope, receive, send, started, info)
        finally:
            _STATS.reset(token)
            self._record(scope, status, started, stats, info)

    async def _inspect(self, scope, receive, info):
        """Read the body (if any), apply limits, then hand the app a receive() that replays it."""
        if scope["method"] not in ("POST", "PUT", "PATCH"):
            return receive, None
        cfg = settings()
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        declared = headers.get(b"content-length", b"0") or b"0"
        try:
            if int(declared) > cfg["max_body_bytes"]:
                return receive, (413, f"Request body too large (max {cfg['max_body_bytes']} bytes)")
        except ValueError:
            pass
        body = b""
        more = True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                return receive, None
            body += message.get("body", b"")
            if len(body) > cfg["max_body_bytes"]:
                return receive, (413, f"Request body too large (max {cfg['max_body_bytes']} bytes)")
            more = message.get("more_body", False)
        info["bytes"] = len(body)

        if b"json" in headers.get(b"content-type", b""):
            try:
                data = json.loads(body or b"{}")
            except ValueError:
                data = None
            if isinstance(data, dict):
                for key in QUESTION_KEYS:
                    value = data.get(key)
                    if not isinstance(value, str):
                        continue
                    info["chars"] = max(info["chars"], len(value))
                    if len(value) > cfg["max_question_chars"]:
                        return receive, (422, f"Question too long (max {cfg['max_question_chars']} characters)")
                    for name in injection_flags(value):
                        if name not in info["injection"]:
                            info["injection"].append(name)
                if info["injection"] and cfg["block_injection"]:
                    return receive, (400, "Request blocked: it looks like a prompt-injection attempt")

        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return replay, None

    async def _forward(self, scope, receive, send, started, info) -> int:
        status = 0
        start_message = None
        chunks = []
        is_json = False

        def timing_header():
            return (b"x-process-time-ms", f"{(time.perf_counter() - started) * 1000:.1f}".encode())

        async def send_wrapper(message):
            nonlocal status, start_message, is_json
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                content_type = next((v for k, v in headers if k.lower() == b"content-type"), b"")
                is_json = b"application/json" in content_type
                if is_json:
                    start_message = message  # held back until we have scanned the body
                    return
                await send({**message, "headers": headers + [timing_header()]})
                return
            if message["type"] == "http.response.body" and is_json:
                chunks.append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                text, count = redact(b"".join(chunks).decode("utf-8", "replace"))
                info["redacted"] = count
                body = text.encode("utf-8")
                headers = [(k, v) for k, v in start_message.get("headers", []) if k.lower() != b"content-length"]
                headers += [(b"content-length", str(len(body)).encode()), timing_header()]
                await send({**start_message, "headers": headers})
                await send({"type": "http.response.body", "body": body})
                return
            await send(message)

        await self.app(scope, receive, send_wrapper)
        return status

    def _record(self, scope, status, started, stats, info):
        path = scope.get("path", "")
        if path in SKIP_LOG_PATHS:
            return
        write_log({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "method": scope.get("method", ""),
            "path": path,
            "status": status,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "llm_calls": stats["llm_calls"],
            "cache_hits": stats["cache_hits"],
            "llm_ms": round(stats["llm_ms"], 1),
            "prompt_tokens": stats["prompt_tokens"],
            "completion_tokens": stats["completion_tokens"],
            "total_tokens": stats["total_tokens"],
            "tokens_estimated": stats["tokens_estimated"],
            "injection": info["injection"],
            "blocked": info["blocked"],
            "redacted": info["redacted"],
            "request_bytes": info["bytes"],
            "question_chars": info["chars"],
        })


def metrics_endpoint() -> dict:
    out = summarize(list(RECENT))
    out["cache_entries"] = len(CACHE)
    out["settings"] = {k: v for k, v in settings().items() if k != "log_dir"}
    return out


def install(app) -> bool:
    """Wire everything into a FastAPI app. Returns True if LLM caching/token counting is active."""
    patched = patch_llm()
    app.add_middleware(ProdMiddleware)
    app.add_api_route("/metrics", metrics_endpoint, methods=["GET"])
    return patched
