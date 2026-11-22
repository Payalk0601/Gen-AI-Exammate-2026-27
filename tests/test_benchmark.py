"""The benchmark script turns measurements into README text. These tests feed it fake numbers."""
from scripts import benchmark

LOAD = {
    "cold": [(200, 900.0, ""), (200, 1100.0, ""), (500, 40.0, "")],
    "warm": [(200, 4.0, ""), (200, 6.0, ""), (200, 5.0, "")],
}
GUARD = {"long_question_status": 422, "big_body_status": 413, "key_leaks": 0, "injection_prompts": 3}
SERVER = {
    "cold": {"avg_prompt_tokens": 700.0, "avg_completion_tokens": 120.0, "avg_total_tokens": 820.0},
    "cache_hit_rate": 0.5,
    "injection_flagged": 3,
    "tokens_estimated_requests": 0,
}
CHECKS = {"tests_passed": 40, "tests_failed": 0, "ruff_clean": True}


def stats():
    return benchmark.collect(LOAD, GUARD, SERVER, CHECKS, "/chat")


def test_collect_ignores_failed_requests_when_measuring_latency():
    s = stats()
    assert s["requests"] == 6 and s["failures"] == 1
    assert s["cold_p50"] == 900.0 and s["warm_p50"] == 5.0
    assert s["speedup"] == 180.0 and s["limits_ok"] is True


def test_render_block_contains_the_measured_numbers():
    block = benchmark.render_block(stats())
    assert "900 ms / 1.1 s" in block
    assert "180.0x faster" in block
    assert "50%" in block and "820 (700 in / 120 out)" in block
    assert "40 passed, 0 failed" in block and "clean" in block
    assert "3 of 3 attack prompts flagged, 0 keys leaked" in block


def test_render_bullet_uses_real_numbers_and_stays_honest_without_them():
    bullet = benchmark.render_bullet(stats())
    assert bullet.startswith("- Hardened the API") and "40 automated tests" in bullet and "180.0x" in bullet
    empty = dict(stats(), avg_total_tokens=None, speedup=None, tests_passed=None)
    assert "x faster" not in benchmark.render_bullet(empty)


def test_replace_between_only_touches_the_marked_block():
    text = "before\n<!-- BENCH:START -->\nold table\n<!-- BENCH:END -->\nafter"
    new = benchmark.replace_between(text, benchmark.BENCH, "NEW TABLE")
    assert "NEW TABLE" in new and "old table" not in new
    assert new.startswith("before") and new.endswith("after")
    assert benchmark.replace_between("no markers", benchmark.BENCH, "x") == "no markers"


def test_update_file_reports_whether_it_wrote(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("a\n<!-- BENCH:START -->\nx\n<!-- BENCH:END -->\n", encoding="utf-8")
    assert benchmark.update_file(readme, benchmark.BENCH, "table") is True
    assert "table" in readme.read_text(encoding="utf-8")
    assert benchmark.update_file(tmp_path / "missing.md", benchmark.BENCH, "table") is False


SPEC = {
    "paths": {
        "/ask": {"post": {"requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Ask"}}}}}},
        "/agent": {"post": {"requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Agent"}}}}}},
        "/search": {"get": {"parameters": [{"name": "limit", "in": "query"}, {"name": "q", "in": "query"}]}},
    },
    "components": {"schemas": {"Ask": {"properties": {"top_k": {}, "query": {}}}, "Agent": {"properties": {"question": {}, "require_approval": {}}}}},
}


def test_request_for_reads_field_names_from_the_openapi_schema():
    assert benchmark.request_for(SPEC, "/ask", "hi") == ("post", {"json": {"query": "hi"}})
    assert benchmark.request_for(SPEC, "/agent", "hi") == ("post", {"json": {"question": "hi", "require_approval": False}})
    assert benchmark.request_for(SPEC, "/search", "hi") == ("get", {"params": {"q": "hi"}})
    assert benchmark.request_for(SPEC, "/ask", "hi", {"padding": "x"})[1]["json"]["padding"] == "x"


def test_pick_endpoint_prefers_ask_then_agent():
    assert benchmark.pick_endpoint(SPEC, "auto") == "/ask"
    assert benchmark.pick_endpoint({"paths": {"/agent": {}}}, "auto") == "/agent"
    assert benchmark.pick_endpoint(SPEC, "/agent") == "/agent"


def test_estimated_tokens_are_labelled_honestly():
    server = dict(SERVER, cold={"count": 3, "avg_prompt_tokens": 500.0, "avg_completion_tokens": 100.0, "avg_total_tokens": 600.0}, tokens_estimated_requests=3)
    s = benchmark.collect(LOAD, GUARD, server, CHECKS, "/ask")
    assert s["tokens_all_estimated"] is True
    assert "estimated, about 4 characters per token" in benchmark.render_block(s)
    assert "estimated tokens per LLM call" in benchmark.render_bullet(s)


def test_get_endpoints_report_limits_as_not_applicable():
    guard = dict(GUARD, long_question_status=None, big_body_status=None)
    s = benchmark.collect(LOAD, guard, SERVER, CHECKS, "/search")
    assert s["limits_ok"] is None and "n/a (GET endpoint" in benchmark.render_block(s)
