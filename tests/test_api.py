import json

from helpers import payload_from_openapi
import pytest

QUESTION = "What must a household do about waste segregation?"


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_chat_returns_the_structured_json(client, fake_llm):
    resp = client.post("/chat", json={"question": QUESTION})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"answer": "FAKE ANSWER", "confidence": "high", "follow_up": "FAKE FOLLOW UP"}


def test_chat_sends_the_question_to_the_llm(client, fake_llm):
    client.post("/chat", json={"question": QUESTION, "prompt_version": "v1"})
    assert len(fake_llm.calls) == 1
    assert QUESTION in fake_llm.calls[0]["user"]
    assert "KachraCheck" in fake_llm.calls[0]["system"]


def test_chat_cleans_up_a_bad_confidence_value(client, fake_llm):
    fake_llm.script(json.dumps({"answer": "x", "confidence": "super sure", "follow_up": ""}))
    assert client.post("/chat", json={"question": QUESTION}).json()["confidence"] == "low"


def test_chat_rejects_an_unknown_prompt_version(client, fake_llm):
    resp = client.post("/chat", json={"question": QUESTION, "prompt_version": "v99"})
    assert resp.status_code == 400
    assert fake_llm.calls == []  # the LLM was never called


def test_chat_rejects_a_too_short_question(client):
    assert client.post("/chat", json={"question": "a"}).status_code == 422


def test_chat_turns_an_llm_failure_into_502(client, fake_llm):
    from app.llm import LLMError

    fake_llm.script(LLMError("provider down"))
    resp = client.post("/chat", json={"question": QUESTION})
    assert resp.status_code == 502 and "provider down" in resp.json()["detail"]


def test_chat_turns_an_unusable_model_reply_into_502(client, fake_llm):
    fake_llm.script("sorry, I cannot answer in JSON")
    assert client.post("/chat", json={"question": QUESTION}).status_code == 502


def test_ask_endpoint_with_a_fake_llm(client, fake_llm):
    openapi = client.get("/openapi.json").json()
    if "/ask" not in openapi["paths"]:
        pytest.skip("this API has no /ask route")
    method, kwargs = payload_from_openapi(openapi, "/ask", QUESTION)
    resp = getattr(client, method)("/ask", **kwargs)
    assert resp.status_code == 200, resp.text
    assert resp.json()


def test_payload_from_openapi_finds_the_question_field():
    schema = {
        "paths": {
            "/ask": {"post": {"requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Q"}}}}}},
            "/find": {"get": {"parameters": [{"name": "limit", "in": "query"}, {"name": "q", "in": "query"}]}},
        },
        "components": {"schemas": {"Q": {"properties": {"top_k": {}, "query": {}}}}},
    }
    assert payload_from_openapi(schema, "/ask", "hi") == ("post", {"json": {"query": "hi"}})
    assert payload_from_openapi(schema, "/find", "hi") == ("get", {"params": {"q": "hi"}})
