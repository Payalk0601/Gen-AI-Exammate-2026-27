"""Small shared helpers for the test-suite."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORDS_PATH = ROOT / "data" / "records.json"
QUESTION_NAMES = ("question", "query", "q", "text", "message", "prompt")


def load_records() -> list:
    data = json.loads(RECORDS_PATH.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for key in ("records", "data", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    return data


def _resolve(schema: dict, openapi: dict) -> dict:
    ref = schema.get("$ref")
    if not ref:
        return schema
    node = openapi
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def payload_from_openapi(openapi: dict, path: str, question: str) -> tuple[str, dict]:
    """Work out how to call an endpoint from the app's own OpenAPI schema.

    Returns (http_method, kwargs_for_testclient). This keeps the /ask test working whatever
    the request field is called (question, query, q ...).
    """
    ops = openapi["paths"][path]
    method = "post" if "post" in ops else "get"
    op = ops[method]
    if "requestBody" in op:
        schema = op["requestBody"]["content"]["application/json"]["schema"]
        props = _resolve(schema, openapi).get("properties", {})
        name = next((n for n in QUESTION_NAMES if n in props), None) or next(iter(props), "question")
        return method, {"json": {name: question}}
    params = [p["name"] for p in op.get("parameters", []) if p.get("in") == "query"]
    name = next((n for n in QUESTION_NAMES if n in params), None) or (params[0] if params else "q")
    return method, {"params": {name: question}}
