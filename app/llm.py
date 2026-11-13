"""Provider wrapper for KachraCheck: one generate() call, Groq or Gemini behind it.

Choose the provider with LLM_PROVIDER in .env (groq | gemini).
Keys are read from the environment, never hard-coded.
"""
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()


class LLMError(Exception):
    """Raised when the provider call fails or is misconfigured."""


def _post(url: str, headers: dict, payload: dict, retries: int = 2) -> dict:
    last = "unknown error"
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=30)
        except requests.RequestException as e:
            last = str(e)
        else:
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code not in (429, 500, 502, 503):
                break  # client error: retrying will not help
        time.sleep(1.5 * (attempt + 1))
    raise LLMError(last)


def _groq(system: str, user: str) -> str:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise LLMError("GROQ_API_KEY missing in .env")
    data = _post(
        "https://api.groq.com/openai/v1/chat/completions",
        {"Authorization": f"Bearer {key}"},
        {
            "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
    )
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"Unexpected Groq response shape: {e}")


def _gemini(system: str, user: str) -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise LLMError("GEMINI_API_KEY missing in .env")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    data = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        {"x-goog-api-key": key},
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        },
    )
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"Unexpected Gemini response shape: {e}")


def generate(system: str, user: str, provider: str | None = None) -> str:
    """Send a system + user prompt to the chosen provider and return raw text."""
    provider = (provider or os.getenv("LLM_PROVIDER", "groq")).lower()
    if provider == "groq":
        return _groq(system, user)
    if provider == "gemini":
        return _gemini(system, user)
    raise LLMError(f"Unknown provider: {provider}")
