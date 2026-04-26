import base64
import time
from typing import Any, Dict, Optional

from .logger import get_csv_logger, get_or_create_api_logger, new_logger_for_ws
from .utils import now_iso


def attach_ws_listeners(
    page: Any,
    run_ts: str,
    pair_index: int = 0,
    message_typedef: Optional[dict] = None,
    event_typedefs: Optional[Dict[str, dict]] = None,
    username: str = "",
) -> None:
    # 在 page 上註冊 websocket 監聽，並把事件寫入 log
    csv_logger = get_csv_logger()

    def on_websocket(ws: Any) -> None:
        ws_url = getattr(ws, "url", "")
        # new_logger_for_ws 回傳同一個 per-user logger，並把此 URL 加入 ws_urls
        logger = new_logger_for_ws(
            ws, run_ts, pair_index=pair_index,
            message_typedef=message_typedef, event_typedefs=event_typedefs, username=username,
        )
        ts = now_iso()
        logger.record_event("websocket_open", ws_url=ws_url)
        csv_logger.record(run_ts=run_ts, type_="wss", ts=ts,
                          event="websocket_open", url=ws_url)

        def on_frame_sent(payload: Any) -> None:
            logger.record_event("frame_sent", payload=payload, ws_url=ws_url)

        def on_frame_received(payload: Any) -> None:
            logger.record_event("frame_received", payload=payload, ws_url=ws_url)

        def on_close() -> None:
            ts_close = now_iso()
            logger.record_event("websocket_close", ws_url=ws_url)
            csv_logger.record(run_ts=run_ts, type_="wss", ts=ts_close,
                              event="websocket_close", url=ws_url)

        def on_socket_error(err: Any) -> None:
            ts_err = now_iso()
            note_text = str(err)
            logger.record_event("websocket_error", note=note_text, ws_url=ws_url)
            csv_logger.record(run_ts=run_ts, type_="wss", ts=ts_err,
                              event="websocket_error", url=ws_url, note=note_text)

        ws.on("framesent", on_frame_sent)
        ws.on("framereceived", on_frame_received)
        ws.on("close", on_close)

        try:
            # Playwright 某些版本不支援 socketerror
            ws.on("socketerror", on_socket_error)
        except Exception as e:
            ts_err = now_iso()
            note_text = f"socketerror listener not supported: {e}"
            logger.record_event("websocket_error", note=note_text, ws_url=ws_url)
            csv_logger.record(run_ts=run_ts, type_="wss", ts=ts_err,
                              event="websocket_error", url=ws_url, note=note_text)

    # 監聽所有 websocket 連線
    page.on("websocket", on_websocket)

    # 監聽所有 HTTP 請求與回應，寫入獨立的 API log（per-user）
    api_logger = get_or_create_api_logger(run_ts, username)
    _pending_requests: Dict[Any, float] = {}

    def on_request(request: Any) -> None:
        # request 事件只寫 api_logger，不寫 summary.csv（僅記錄 response 與 failed）
        _pending_requests[request] = time.time()
        api_logger.record_event(
            event="request",
            resource_type=request.resource_type,
            method=request.method,
            url=request.url,
            request_headers=dict(request.headers),
            payload=request.post_data,
            payload_type="text" if request.post_data else None,
        )

    async def on_response(response: Any) -> None:
        # duration 以 headers 抵達時計算，不含 body 下載時間
        start = _pending_requests.pop(response.request, None)
        duration_ms = round((time.time() - start) * 1000, 2) if start is not None else None

        payload: Optional[str] = None
        payload_type: Optional[str] = None
        try:
            payload = await response.text()
            payload_type = "text"
        except Exception:
            try:
                raw = await response.body()
                payload = base64.b64encode(raw).decode("ascii")
                payload_type = "binary"
            except Exception:
                pass

        ts_resp = now_iso()
        api_logger.record_event(
            event="response",
            resource_type=response.request.resource_type,
            method=response.request.method,
            url=response.url,
            response_headers=dict(response.headers),
            payload=payload,
            payload_type=payload_type,
            status=response.status,
            api_duration_ms=duration_ms,
        )
        csv_logger.record(
            run_ts=run_ts,
            type_="api",
            ts=ts_resp,
            event="response",
            method=response.request.method,
            url=response.url,
            status=response.status,
            resource_type=response.request.resource_type,
            api_duration_ms=duration_ms,
            payload_type=payload_type,
        )

    def on_request_failed(request: Any) -> None:
        start = _pending_requests.pop(request, None)
        duration_ms = round((time.time() - start) * 1000, 2) if start is not None else None
        ts_fail = now_iso()
        api_logger.record_event(
            event="request_failed",
            resource_type=request.resource_type,
            method=request.method,
            url=request.url,
            api_duration_ms=duration_ms,
            note=request.failure,
        )
        csv_logger.record(
            run_ts=run_ts,
            type_="api",
            ts=ts_fail,
            event="request_failed",
            method=request.method,
            url=request.url,
            resource_type=request.resource_type,
            api_duration_ms=duration_ms,
            note=request.failure,
        )

    page.on("request", on_request)
    page.on("response", on_response)
    page.on("requestfailed", on_request_failed)
