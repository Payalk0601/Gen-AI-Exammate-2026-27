"""Tiny wrapper around two LLM providers: Groq and Google Gemini (plain HTTPS with `requests`).

Keys live in a local `.env` file (NOT committed; `.env.example` shows the names):
  GROQ_API_KEY / GEMINI_API_KEY      at least one of them
  LLM_PROVIDER                       optional: groq | gemini (otherwise the one that has a key)
  GROQ_MODEL / GEMINI_MODEL          optional model names (providers retire models, so they are settings)
"""
import os
from pathlib import Path
from typing import Optional

import requests

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODELS = {"groq": "llama-3.3-70b-versatile", "gemini": "gemini-2.5-flash"}
KEY_NAMES = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY"}
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class LLMError(RuntimeError):
    """Any problem talking to a provider. The message never contains the API key."""


def load_env(path=None) -> None:
    """Read KEY=VALUE lines from .env into os.environ (existing variables win)."""
    path = Path(path) if path else ROOT / ".env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if value and key.strip() not in os.environ:
            os.environ[key.strip()] = value


def available_provider() -> Optional[str]:
    """The provider to use, or None if no key is configured."""
    load_env()
    wanted = (os.environ.get("LLM_PROVIDER") or "").lower()
    if wanted in KEY_NAMES and os.environ.get(KEY_NAMES[wanted]):
        return wanted
    for name in ("groq", "gemini"):
        if os.environ.get(KEY_NAMES[name]):
            return name
    return None


def model_name(provider: str) -> str:
    return os.environ.get(f"{provider.upper()}_MODEL") or DEFAULT_MODELS[provider]


def complete(system: str, user: str, provider: Optional[str] = None, model: Optional[str] = None,
             temperature: float = 0.0, max_tokens: int = 500, timeout=(5, 40)) -> str:
    """Send one system + user message and return the reply text. Raises LLMError on any failure."""
    provider = provider or available_provider()
    if provider not in KEY_NAMES:
        raise LLMError("no LLM key configured: copy .env.example to .env and add GROQ_API_KEY or GEMINI_API_KEY")
    key = os.environ.get(KEY_NAMES[provider])
    if not key:
        raise LLMError(f"{KEY_NAMES[provider]} is not set")
    model = model or model_name(provider)
    try:
        if provider == "groq":
            resp = requests.post(
                GROQ_URL, timeout=timeout, headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "temperature": temperature, "max_tokens": max_tokens,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        else:
            resp = requests.post(
                GEMINI_URL.format(model=model), timeout=timeout,
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json={"system_instruction": {"parts": [{"text": system}]},
                      "contents": [{"role": "user", "parts": [{"text": user}]}],
                      "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}})
        resp.raise_for_status()
        data = resp.json()
        if provider == "groq":
            return data["choices"][0]["message"]["content"].strip()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except requests.exceptions.Timeout:
        raise LLMError(f"{provider} timed out")
    except requests.exceptions.HTTPError as err:
        raise LLMError(f"{provider} returned HTTP {err.response.status_code} for model '{model}'")
    except requests.exceptions.RequestException as err:
        raise LLMError(f"{provider} request failed: {type(err).__name__}")
    except (KeyError, IndexError, ValueError, TypeError):
        raise LLMError(f"{provider} sent a reply in an unexpected shape (blocked or empty answer?)")
