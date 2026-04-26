"""HTTP API mock router：以 route_config 設定攔截指定 request 並回傳 mock response。

route_config 格式（單一 response）：
    {
        "pattern": "**/api/users/**",        # 必填，Playwright glob
        "method":  "GET",                    # 選填，None 表示不限 method
        "status":  200,                      # 選填，預設 200
        "body":    dict | list | str | None, # 選填；dict/list → JSON，str → text/plain
    }

route_config 格式（多個 response 輪替）：
    {
        "pattern": "**/api/auth*",
        "method":  "GET",
        "responses": [
            {"status": 200, "body": {"ok": True}},
            {"status": 401, "body": {"error": "unauthorized"}},
        ],
    }
    # 依呼叫順序依序使用 responses 陣列，超過最後一項後持續回傳最後一項。

每次 fulfill 會寫入：
- ApiLogger: mock_response 或 mock_error 事件（_api.json）
- CsvLogger: mock pattern=<pattern> 摘要（summary.csv）
"""
import json
import time
from typing import Any, Optional, Tuple

from wss.logger import get_or_create_api_logger, get_csv_logger
from wss.utils import now_iso

_CT_JSON = "application/json"
_CT_TEXT = "text/plain"


def _serialize_body(body: Any) -> Tuple[str, str, Optional[str]]:
    """body 序列化為 (body_str, content_type, serialization_error)。"""
    try:
        if isinstance(body, (dict, list)):
            return json.dumps(body, ensure_ascii=False), _CT_JSON, None
        if isinstance(body, str):
            return body, _CT_TEXT, None
        if body is None:
            return "", _CT_TEXT, None
        return str(body), _CT_TEXT, None
    except Exception as e:
        return str(body), _CT_TEXT, str(e)


async def _try_fulfill(route: Any, status: int, content_type: str, body_str: str) -> Optional[str]:
    """嘗試 fulfill；失敗時 fallback continue_ 並回傳錯誤訊息，成功回傳 None。"""
    try:
        await route.fulfill(
            status=status,
            headers={"content-type": content_type},
            body=body_str,
        )
        return None
    except Exception as e:
        error_msg = str(e)
        try:
            await route.continue_()
        except Exception as ce:
            error_msg += f"; continue_ also failed: {ce}"
        return error_msg


def _resolve_response(
    route_config: dict,
    responses: Optional[list],
    call_index: list,
) -> Tuple[Any, int, Optional[int]]:
    """依 responses 陣列或 fallback 的 status/body，回傳 (body, status, response_index)。"""
    if responses is not None:
        current_index = min(call_index[0], len(responses) - 1)
        call_index[0] += 1
        entry = responses[current_index]
        return entry.get("body"), entry.get("status", 200), current_index
    return route_config.get("body"), route_config.get("status", 200), None


def _make_api_mock_handler(route_config: dict, run_ts: str, username: str = ""):
    responses: Optional[list] = route_config.get("responses")
    _call_index = [0]  # list 包裝以便在 async closure 內修改

    async def handler(route: Any, request: Any) -> None:
        config_method = route_config.get("method")
        if config_method and request.method.upper() != config_method.upper():
            await route.continue_()
            return

        start_time = time.perf_counter()
        body, status, response_index = _resolve_response(route_config, responses, _call_index)
        body_str, content_type, serialization_error = _serialize_body(body)

        api_logger = get_or_create_api_logger(run_ts, username)
        error_msg = await _try_fulfill(route, status, content_type, body_str)

        if error_msg is not None:
            error_note: dict = {"mock": True, "pattern": route_config["pattern"], "error": error_msg}
            if response_index is not None:
                error_note["response_index"] = response_index
            api_logger.record_event(
                event="mock_error",
                resource_type=request.resource_type,
                method=request.method,
                url=request.url,
                request_headers=dict(request.headers),
                note=error_note,
            )
            return

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        note: dict = {"mock": True, "pattern": route_config["pattern"]}
        if serialization_error:
            note["serialization_error"] = serialization_error
        if response_index is not None:
            note["response_index"] = response_index

        api_logger.record_event(
            event="mock_response",
            resource_type=request.resource_type,
            method=request.method,
            url=request.url,
            request_headers=dict(request.headers),
            response_headers={"content-type": content_type},
            payload=body_str,
            payload_type="text",
            status=status,
            api_duration_ms=duration_ms,
            note=note,
        )

        csv_logger = get_csv_logger()
        csv_logger.record(
            run_ts=run_ts,
            type_="api",
            ts=now_iso(),
            event="mock_response",
            method=request.method,
            url=request.url,
            status=status,
            resource_type=request.resource_type,
            api_duration_ms=duration_ms,
            payload_type="text",
            note=f"mock pattern={route_config['pattern']}",
        )

    return handler


async def attach_mock_api_routes(
    page: Any,
    mock_api_routes: list,
    run_ts: str,
    username: str = "",
) -> None:
    for route_config in mock_api_routes:
        if "pattern" not in route_config:
            raise ValueError(f"mock_api_routes 項目缺少必填欄位 'pattern'：{route_config}")
        if "responses" in route_config:
            if not isinstance(route_config["responses"], list):
                raise ValueError(
                    f"mock_api_routes 項目的 'responses' 必須為 list：{route_config}"
                )
            if not route_config["responses"]:
                raise ValueError(
                    f"mock_api_routes 項目的 'responses' 不可為空陣列：{route_config}"
                )
        handler = _make_api_mock_handler(route_config, run_ts, username)
        await page.route(route_config["pattern"], handler)
