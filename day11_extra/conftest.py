"""Shared fixtures: a FastAPI test client and a fake LLM so tests never touch the network."""
import json
import sys

import pytest

FINAL_REPLY = json.dumps(
    {"answer": "FAKE ANSWER", "confidence": "high", "follow_up": "FAKE FOLLOW UP"}
)


class FakeLLM:
    """Stands in for app.llm.generate. Replies are consumed one per call (the last one repeats).
    A reply that is an Exception instance is raised instead of returned."""

    def __init__(self):
        self.replies = [FINAL_REPLY]
        self.calls = []

    def __call__(self, system, user, provider=None):
        self.calls.append({"system": system, "user": user, "provider": provider})
        reply = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply

    def script(self, *replies):
        self.replies = list(replies)
        return self


@pytest.fixture(scope="session")
def client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace generate() in every already-imported app module, so it works whichever module
    (chat, agent_loop, an /ask module ...) calls the LLM."""
    fake = FakeLLM()
    for name, mod in list(sys.modules.items()):
        if (name == "app" or name.startswith("app.")) and hasattr(mod, "generate"):
            monkeypatch.setattr(mod, "generate", fake)
    return fake
