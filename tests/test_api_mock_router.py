"""Unit tests for api/mock_router.py

Covers: route registration, method filtering, body serialization,
ApiLogger/CsvLogger field correctness, exception fall-back, and
closure independence across multiple routes.
"""
import asyncio
from typing import Any, Optional
from unittest.mock import patch

import pytest

from api.mock_router import attach_mock_api_routes, _make_api_mock_handler


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeRoute:
    def __init__(
        self,
        raise_on_fulfill: bool = False,
        raise_on_continue: bool = False,
    ) -> None:
        self.fulfilled: list = []
        self.continued: int = 0
        self._raise_on_fulfill = raise_on_fulfill
        self._raise_on_continue = raise_on_continue

    async def fulfill(self, status: int, headers: dict, body: str) -> None:
        await asyncio.sleep(0)
        if self._raise_on_fulfill:
            raise RuntimeError("fulfill failed")
        self.fulfilled.append({"status": status, "headers": headers, "body": body})

    async def continue_(self) -> None:
        await asyncio.sleep(0)
        if self._raise_on_continue:
            raise RuntimeError("continue_ failed")
        self.continued += 1


class FakeRequest:
    def __init__(
        self,
        method: str = "GET",
        url: str = "https://example.com/api/data",
        resource_type: str = "fetch",
        headers: Optional[dict] = None,
    ) -> None:
        self.method = method
        self.url = url
        self.resource_type = resource_type
        self.headers = headers or {"accept": "application/json"}


class FakeApiLogger:
    def __init__(self) -> None:
        self.events: list = []

    def record_event(self, event: str, **kwargs: Any) -> None:
        self.events.append({"event": event, **kwargs})


class FakeCsvLogger:
    def __init__(self) -> None:
        self.records: list = []

    def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


class FakePage:
    def __init__(self) -> None:
        self.routes: list = []

    async def route(self, pattern: str, handler: Any) -> None:
        self.routes.append((pattern, handler))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_handler_with_fakes(route_config: dict):
    """Return (patched_handler, api_logger, csv_logger) with injected fakes."""
    api_logger = FakeApiLogger()
    csv_logger = FakeCsvLogger()
    handler = _make_api_mock_handler(route_config, run_ts="20240101_000000")

    async def patched_handler(route, request):
        with patch("api.mock_router.get_or_create_api_logger", return_value=api_logger), \
             patch("api.mock_router.get_csv_logger", return_value=csv_logger):
            await handler(route, request)

    return patched_handler, api_logger, csv_logger


# ---------------------------------------------------------------------------
# 7.1 Route registration
# ---------------------------------------------------------------------------

def test_empty_route_list_skips_page_route():
    page = FakePage()

    _run(attach_mock_api_routes(page, [], run_ts="20240101_000000"))

    assert page.routes == []


def test_single_route_registers_correct_pattern():
    page = FakePage()

    _run(attach_mock_api_routes(page, [{"pattern": "**/api/v1/**"}], run_ts="20240101_000000"))

    assert len(page.routes) == 1
    assert page.routes[0][0] == "**/api/v1/**"


def test_multiple_routes_registered_in_order():
    page = FakePage()
    routes = [
        {"pattern": "**/api/a/**"},
        {"pattern": "**/api/b/**"},
        {"pattern": "**/api/c/**"},
    ]

    _run(attach_mock_api_routes(page, routes, run_ts="20240101_000000"))

    assert [p for p, _ in page.routes] == ["**/api/a/**", "**/api/b/**", "**/api/c/**"]


def test_missing_pattern_raises_value_error():
    with pytest.raises(ValueError, match="pattern"):
        _run(attach_mock_api_routes(FakePage(), [{"status": 200}], run_ts="20240101_000000"))


# ---------------------------------------------------------------------------
# 7.2 Method filtering
# ---------------------------------------------------------------------------

def test_no_method_filter_always_fulfills():
    handler, _, _ = _make_handler_with_fakes({"pattern": "**/api/**", "body": None})
    route = FakeRoute()

    _run(handler(route, FakeRequest(method="GET")))

    assert len(route.fulfilled) == 1
    assert route.continued == 0


def test_matching_method_fulfills():
    handler, _, _ = _make_handler_with_fakes({"pattern": "**/api/**", "method": "GET", "body": None})
    route = FakeRoute()

    _run(handler(route, FakeRequest(method="GET")))

    assert len(route.fulfilled) == 1
    assert route.continued == 0


def test_mismatched_method_continues_not_fulfills():
    handler, _, _ = _make_handler_with_fakes({"pattern": "**/api/**", "method": "POST", "body": None})
    route = FakeRoute()

    _run(handler(route, FakeRequest(method="GET")))

    assert route.continued == 1
    assert len(route.fulfilled) == 0


def test_method_filter_is_case_insensitive():
    handler, _, _ = _make_handler_with_fakes({"pattern": "**/api/**", "method": "get", "body": None})
    route = FakeRoute()

    _run(handler(route, FakeRequest(method="GET")))

    assert len(route.fulfilled) == 1
    assert route.continued == 0


# ---------------------------------------------------------------------------
# 7.3 Body serialization
# ---------------------------------------------------------------------------

def test_dict_body_serialized_to_json():
    handler, _, _ = _make_handler_with_fakes({"pattern": "**/api/**", "body": {"key": "value"}})
    route = FakeRoute()

    _run(handler(route, FakeRequest()))

    assert route.fulfilled[0]["body"] == '{"key": "value"}'
    assert route.fulfilled[0]["headers"]["content-type"] == "application/json"


def test_list_body_serialized_to_json():
    handler, _, _ = _make_handler_with_fakes({"pattern": "**/api/**", "body": [{"id": 1}, {"id": 2}]})
    route = FakeRoute()

    _run(handler(route, FakeRequest()))

    assert route.fulfilled[0]["body"] == '[{"id": 1}, {"id": 2}]'
    assert route.fulfilled[0]["headers"]["content-type"] == "application/json"


def test_string_body_passed_through_as_text():
    handler, _, _ = _make_handler_with_fakes({"pattern": "**/api/**", "body": "plain text"})
    route = FakeRoute()

    _run(handler(route, FakeRequest()))

    assert route.fulfilled[0]["body"] == "plain text"
    assert route.fulfilled[0]["headers"]["content-type"] == "text/plain"


def test_none_body_becomes_empty_string():
    handler, _, _ = _make_handler_with_fakes({"pattern": "**/api/**", "body": None})
    route = FakeRoute()

    _run(handler(route, FakeRequest()))

    assert route.fulfilled[0]["body"] == ""
    assert route.fulfilled[0]["headers"]["content-type"] == "text/plain"


def test_non_string_body_converted_to_str():
    handler, _, _ = _make_handler_with_fakes({"pattern": "**/api/**", "body": 42})
    route = FakeRoute()

    _run(handler(route, FakeRequest()))

    assert route.fulfilled[0]["body"] == "42"
    assert route.fulfilled[0]["headers"]["content-type"] == "text/plain"


def test_dict_body_preserves_unicode_characters():
    handler, _, _ = _make_handler_with_fakes({"pattern": "**/api/**", "body": {"msg": "你好"}})
    route = FakeRoute()

    _run(handler(route, FakeRequest()))

    assert "你好" in route.fulfilled[0]["body"]
    assert "\\u" not in route.fulfilled[0]["body"]


def test_unserializable_body_records_error_and_still_fulfills():
    handler, api_logger, _ = _make_handler_with_fakes({"pattern": "**/api/**", "body": {"x": {1, 2, 3}}})
    route = FakeRoute()

    _run(handler(route, FakeRequest()))

    assert len(route.fulfilled) == 1
    assert "serialization_error" in api_logger.events[0]["note"]


# ---------------------------------------------------------------------------
# 7.4 ApiLogger field correctness
# ---------------------------------------------------------------------------

def test_api_logger_records_mock_response_event():
    handler, api_logger, _ = _make_handler_with_fakes({"pattern": "**/api/**", "body": None})

    _run(handler(FakeRoute(), FakeRequest()))

    assert len(api_logger.events) == 1
    assert api_logger.events[0]["event"] == "mock_response"


def test_api_logger_note_contains_mock_flag_and_pattern():
    handler, api_logger, _ = _make_handler_with_fakes({"pattern": "**/api/users/**", "body": None})

    _run(handler(FakeRoute(), FakeRequest()))

    note = api_logger.events[0]["note"]
    assert note["mock"] is True
    assert note["pattern"] == "**/api/users/**"


def test_api_logger_records_configured_status():
    handler, api_logger, _ = _make_handler_with_fakes({"pattern": "**/api/**", "status": 404, "body": None})

    _run(handler(FakeRoute(), FakeRequest()))

    assert api_logger.events[0]["status"] == 404


def test_api_logger_defaults_status_to_200():
    handler, api_logger, _ = _make_handler_with_fakes({"pattern": "**/api/**", "body": None})

    _run(handler(FakeRoute(), FakeRequest()))

    assert api_logger.events[0]["status"] == 200


def test_api_logger_duration_is_non_negative():
    handler, api_logger, _ = _make_handler_with_fakes({"pattern": "**/api/**", "body": None})

    _run(handler(FakeRoute(), FakeRequest()))

    assert api_logger.events[0]["api_duration_ms"] >= 0


# ---------------------------------------------------------------------------
# 7.5 CsvLogger field correctness
# ---------------------------------------------------------------------------

def test_csv_logger_type_is_api():
    handler, _, csv_logger = _make_handler_with_fakes({"pattern": "**/api/**", "body": None})

    _run(handler(FakeRoute(), FakeRequest()))

    assert csv_logger.records[0]["type_"] == "api"


def test_csv_logger_event_is_mock_response():
    handler, _, csv_logger = _make_handler_with_fakes({"pattern": "**/api/**", "body": None})

    _run(handler(FakeRoute(), FakeRequest()))

    assert csv_logger.records[0]["event"] == "mock_response"


def test_csv_logger_note_contains_pattern():
    handler, _, csv_logger = _make_handler_with_fakes({"pattern": "**/api/orders/**", "body": None})

    _run(handler(FakeRoute(), FakeRequest()))

    note = csv_logger.records[0]["note"]
    assert note.startswith("mock pattern=")
    assert "**/api/orders/**" in note


def test_csv_logger_records_request_fields():
    handler, _, csv_logger = _make_handler_with_fakes({"pattern": "**/api/**", "status": 201, "body": None})
    request = FakeRequest(method="POST", url="https://example.com/api/orders", resource_type="xhr")

    _run(handler(FakeRoute(), request))

    rec = csv_logger.records[0]
    assert rec["method"] == "POST"
    assert rec["url"] == "https://example.com/api/orders"
    assert rec["status"] == 201
    assert rec["resource_type"] == "xhr"


# ---------------------------------------------------------------------------
# 7.6 No log when method mismatches
# ---------------------------------------------------------------------------

def test_mismatched_method_skips_api_logger():
    handler, api_logger, _ = _make_handler_with_fakes({"pattern": "**/api/**", "method": "POST", "body": None})

    _run(handler(FakeRoute(), FakeRequest(method="GET")))

    assert api_logger.events == []


# ---------------------------------------------------------------------------
# 7.7 Exception fall-back
# ---------------------------------------------------------------------------

def test_fulfill_exception_falls_back_to_continue_and_logs_error():
    handler, api_logger, _ = _make_handler_with_fakes({"pattern": "**/api/**", "body": None})
    route = FakeRoute(raise_on_fulfill=True)

    _run(handler(route, FakeRequest()))

    assert route.continued == 1
    assert api_logger.events[0]["event"] == "mock_error"


def test_mock_error_note_contains_error_message():
    handler, api_logger, _ = _make_handler_with_fakes({"pattern": "**/api/**", "body": None})

    _run(handler(FakeRoute(raise_on_fulfill=True), FakeRequest()))

    note = api_logger.events[0]["note"]
    assert "error" in note
    assert "fulfill failed" in note["error"]


def test_double_exception_still_logs_mock_error():
    handler, api_logger, _ = _make_handler_with_fakes({"pattern": "**/api/**", "body": None})
    route = FakeRoute(raise_on_fulfill=True, raise_on_continue=True)

    _run(handler(route, FakeRequest()))

    assert api_logger.events[0]["event"] == "mock_error"
    assert "continue_ also failed" in api_logger.events[0]["note"]["error"]


# ---------------------------------------------------------------------------
# Closure independence
# ---------------------------------------------------------------------------

def test_multiple_route_handlers_have_independent_closures():
    page = FakePage()
    routes = [
        {"pattern": "**/api/a/**", "status": 200, "body": {"route": "a"}},
        {"pattern": "**/api/b/**", "status": 404, "body": {"route": "b"}},
    ]
    _run(attach_mock_api_routes(page, routes, run_ts="20240101_000000"))

    _, handler_a = page.routes[0]
    _, handler_b = page.routes[1]

    api_logger_a, csv_logger_a = FakeApiLogger(), FakeCsvLogger()
    api_logger_b, csv_logger_b = FakeApiLogger(), FakeCsvLogger()
    route_a, route_b = FakeRoute(), FakeRoute()

    async def run_both():
        with patch("api.mock_router.get_or_create_api_logger", return_value=api_logger_a), \
             patch("api.mock_router.get_csv_logger", return_value=csv_logger_a):
            await handler_a(route_a, FakeRequest())
        with patch("api.mock_router.get_or_create_api_logger", return_value=api_logger_b), \
             patch("api.mock_router.get_csv_logger", return_value=csv_logger_b):
            await handler_b(route_b, FakeRequest())

    _run(run_both())

    assert route_a.fulfilled[0]["status"] == 200
    assert route_b.fulfilled[0]["status"] == 404
    assert '{"route": "a"}' in route_a.fulfilled[0]["body"]
    assert '{"route": "b"}' in route_b.fulfilled[0]["body"]


# ---------------------------------------------------------------------------
# 7.9 responses 陣列功能
# ---------------------------------------------------------------------------

def test_responses_array_iterates_in_order():
    """3 個 response 的陣列，依序呼叫三次應各自回傳對應的 status 與 body。"""
    route_config = {
        "pattern": "**/api/auth*",
        "responses": [
            {"status": 200, "body": {"step": 0}},
            {"status": 201, "body": {"step": 1}},
            {"status": 202, "body": {"step": 2}},
        ],
    }
    handler, _, _ = _make_handler_with_fakes(route_config)
    route = FakeRoute()
    request = FakeRequest()

    _run(handler(route, request))
    _run(handler(route, request))
    _run(handler(route, request))

    assert route.fulfilled[0]["status"] == 200
    assert route.fulfilled[1]["status"] == 201
    assert route.fulfilled[2]["status"] == 202
    assert '{"step": 0}' in route.fulfilled[0]["body"]
    assert '{"step": 1}' in route.fulfilled[1]["body"]
    assert '{"step": 2}' in route.fulfilled[2]["body"]


def test_responses_array_repeats_last_after_exhausted():
    """2 個 response 的陣列，第 4 次呼叫仍應回傳 responses[1]（不循環回頭）。"""
    route_config = {
        "pattern": "**/api/auth*",
        "responses": [
            {"status": 200, "body": {"phase": "first"}},
            {"status": 401, "body": {"phase": "second"}},
        ],
    }
    handler, _, _ = _make_handler_with_fakes(route_config)
    route = FakeRoute()
    request = FakeRequest()

    for _ in range(4):
        _run(handler(route, request))

    assert route.fulfilled[2]["status"] == 401
    assert route.fulfilled[3]["status"] == 401
    assert '{"phase": "second"}' in route.fulfilled[2]["body"]
    assert '{"phase": "second"}' in route.fulfilled[3]["body"]


def test_responses_array_single_item_always_returns_same():
    """只有 1 個 response 的陣列，連續三次呼叫都應回傳相同的 status 與 body。"""
    route_config = {
        "pattern": "**/api/ping",
        "responses": [
            {"status": 204, "body": None},
        ],
    }
    handler, _, _ = _make_handler_with_fakes(route_config)
    route = FakeRoute()
    request = FakeRequest()

    for _ in range(3):
        _run(handler(route, request))

    assert all(f["status"] == 204 for f in route.fulfilled)
    assert all(f["body"] == "" for f in route.fulfilled)


def test_responses_array_method_filter_still_works():
    """method 不符合時應呼叫 route.continue_()，且計數器不應遞增。"""
    route_config = {
        "pattern": "**/api/auth*",
        "method": "POST",
        "responses": [
            {"status": 200, "body": {"ok": True}},
            {"status": 401, "body": {"error": "unauthorized"}},
        ],
    }
    handler, api_logger, _ = _make_handler_with_fakes(route_config)
    route = FakeRoute()
    wrong_request = FakeRequest(method="GET")
    correct_request = FakeRequest(method="POST")

    _run(handler(route, wrong_request))
    _run(handler(route, wrong_request))
    _run(handler(route, correct_request))

    assert route.continued == 2
    assert len(route.fulfilled) == 1
    assert route.fulfilled[0]["status"] == 200
    assert api_logger.events[0]["note"]["response_index"] == 0


def test_responses_array_logs_response_index():
    """使用 responses 陣列時，ApiLogger 的 note 應包含 response_index 欄位。"""
    route_config = {
        "pattern": "**/api/auth*",
        "responses": [
            {"status": 200, "body": {"ok": True}},
            {"status": 401, "body": {"error": "unauthorized"}},
        ],
    }
    handler, api_logger, _ = _make_handler_with_fakes(route_config)
    route = FakeRoute()
    request = FakeRequest()

    _run(handler(route, request))
    _run(handler(route, request))

    assert api_logger.events[0]["note"]["response_index"] == 0
    assert api_logger.events[1]["note"]["response_index"] == 1


def test_responses_empty_list_raises_value_error():
    """responses 為空陣列時，attach_mock_api_routes 應拋出 ValueError。"""
    # Arrange
    page = FakePage()
    route_config = {"pattern": "**/api/auth*", "responses": []}

    with pytest.raises(ValueError, match="不可為空陣列"):
        _run(attach_mock_api_routes(page, [route_config], run_ts="20240101_000000"))


def test_backward_compat_status_body_unchanged():
    """沿用舊格式 status/body（無 responses 鍵）的路由行為應與原本完全一致。"""
    route_config = {"pattern": "**/api/**", "status": 418, "body": {"legacy": True}}
    handler, api_logger, _ = _make_handler_with_fakes(route_config)
    route = FakeRoute()
    request = FakeRequest()

    _run(handler(route, request))

    assert route.fulfilled[0]["status"] == 418
    assert '{"legacy": true}' in route.fulfilled[0]["body"]
    assert "response_index" not in api_logger.events[0]["note"]


def test_responses_array_counters_are_isolated_per_route():
    """兩個各自帶 responses 陣列的 route，計數器應互相獨立，不因另一個 route 被呼叫而推進。"""
    page = FakePage()
    routes = [
        {"pattern": "**/api/a", "responses": [
            {"status": 200, "body": {"r": "a0"}},
            {"status": 201, "body": {"r": "a1"}},
        ]},
        {"pattern": "**/api/b", "responses": [
            {"status": 500, "body": {"r": "b0"}},
            {"status": 502, "body": {"r": "b1"}},
        ]},
    ]
    _run(attach_mock_api_routes(page, routes, run_ts="20240101_000000"))
    _, handler_a = page.routes[0]
    _, handler_b = page.routes[1]

    api_logger = FakeApiLogger()
    csv_logger = FakeCsvLogger()
    route_a = FakeRoute()
    route_b = FakeRoute()

    async def run():
        with patch("api.mock_router.get_or_create_api_logger", return_value=api_logger), \
             patch("api.mock_router.get_csv_logger", return_value=csv_logger):
            await handler_a(route_a, FakeRequest())
            await handler_a(route_a, FakeRequest())
            await handler_b(route_b, FakeRequest())

    _run(run())

    assert route_a.fulfilled[0]["status"] == 200
    assert route_a.fulfilled[1]["status"] == 201
    assert route_b.fulfilled[0]["status"] == 500


def test_responses_takes_precedence_over_top_level_status_body():
    """responses 與頂層 status/body 同時存在時，responses 優先；頂層 status/body 被忽略。"""
    route_config = {
        "pattern": "**/api/x",
        "status": 500,
        "body": {"ignored": True},
        "responses": [{"status": 200, "body": {"used": True}}],
    }
    handler, _, _ = _make_handler_with_fakes(route_config)
    route = FakeRoute()

    _run(handler(route, FakeRequest()))

    assert route.fulfilled[0]["status"] == 200
    assert '{"used": true}' in route.fulfilled[0]["body"]


def test_responses_non_list_raises_value_error():
    """responses 為非 list 型別時，attach_mock_api_routes 應拋出 ValueError。"""
    page = FakePage()
    route_config = {"pattern": "**/api/auth*", "responses": "not-a-list"}

    with pytest.raises(ValueError, match="必須為 list"):
        _run(attach_mock_api_routes(page, [route_config], run_ts="20240101_000000"))
