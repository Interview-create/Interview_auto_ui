import re
import uuid
from typing import Any, Dict, List, Optional, Protocol

from .logger import new_logger_for_ws


class EventLogger(Protocol):
    """mock_router 依賴的 logger 介面。"""

    def record_event(
        self, event_name: str, payload: Any = None, note: Any = None
    ) -> None: ...

_ACK_ID_RE = re.compile(r"^42(\d*)\[")
_FREE_SPIN_PAYLOAD_RE = re.compile(r'"client:free_spin",\s*"([^"]+)"')


def _parse_ack_id(msg: str) -> str:
    m = _ACK_ID_RE.match(msg)
    return m.group(1) if m else ""


def _send_spin_reply(
    ws_route: Any,
    logger: EventLogger,
    msg: str,
    mock_wss_receive_list: List[str],
    spin_count: int,
    label: str,
) -> None:
    """選出對應的 mock 資料並送出，同時記錄 log。"""
    idx = (spin_count - 1) % len(mock_wss_receive_list)
    mock_data_item = mock_wss_receive_list[idx]
    logger.record_event(
        "mock_data_item",
        payload=mock_data_item,
        note={"spin_count": spin_count},
    )
    ack_id = _parse_ack_id(msg)
    items = mock_data_item if isinstance(mock_data_item, list) else [mock_data_item]
    for data in items:
        reply = (
            data
            if isinstance(data, str) and data.startswith("4")
            else f'43{ack_id}["{data}"]'
        )
        print(f"[{label}] spin #{spin_count}: {reply[:80]}...")
        ws_route.send(reply)


def _handle_fake_free_spin(
    ws_route: Any,
    logger: EventLogger,
    msg: str,
    free_spin_responses: Dict[str, str],
) -> None:
    """根據請求 payload 查表，回傳對應的 mock response。"""
    ack_id = _parse_ack_id(msg)
    m = _FREE_SPIN_PAYLOAD_RE.search(msg)
    request_payload = m.group(1) if m else ""
    reply_data = free_spin_responses.get(request_payload)
    if reply_data:
        reply = f'43{ack_id}["{reply_data}"]'
        ws_route.send(reply)
        print(f"[FAKE] client:free_spin matched, ack_id={ack_id}")
        logger.record_event(
            "free_spin_response_sent",
            payload=reply,
            note={"request_payload": request_payload},
        )
    else:
        empty_reply = f"43{ack_id}[]"
        print(f"[FAKE] client:free_spin no match for payload: {request_payload[:40]}...")
        ws_route.send(empty_reply)
        logger.record_event(
            "free_spin_response_not_matched",
            payload=empty_reply,
            note={"request_payload": request_payload},
        )


async def attach_mock_ws_routes(
    page: Any,
    mock_wss_receive_list: List[str],
    push_message: Optional[str] = None,
    push_after_spin: int = 1,
    run_ts: str = "mock",
    message_typedef: Optional[dict] = None,
    event_typedefs: Optional[Dict[str, dict]] = None,
    fake_connection: bool = False,
    mock_balance_message: Optional[str] = None,
    free_spin_responses: Optional[Dict[str, str]] = None,
    pair_index: int = 0,
    username: str = "",
) -> None:
    # 將 websocket 的路由掛到 page 上，用來攔截 client:spin 並回 mock
    # state 放在此層，跨 WebSocket 重連共享，確保 spin_count 不因斷線重連而重置
    shared_state = {"spin_count": 0, "push_sent": False}

    def handle_ws_route(ws_route: Any) -> None:
        try:
            logger = new_logger_for_ws(
                ws_route,
                run_ts=run_ts,
                pair_index=pair_index,
                message_typedef=message_typedef,
                event_typedefs=event_typedefs,
                username=username,
            )
            if fake_connection:
                _setup_fake_connection(
                    ws_route,
                    logger,
                    mock_wss_receive_list,
                    push_message,
                    push_after_spin,
                    mock_balance_message,
                    free_spin_responses or {},
                    shared_state,
                )
            else:
                _setup_real_connection(
                    ws_route,
                    logger,
                    mock_wss_receive_list,
                    push_message,
                    push_after_spin,
                    shared_state,
                )
        except Exception as e:
            print(f"WebSocket mock error: {e}")

    await page.route_web_socket("**/*", handle_ws_route)


def _setup_fake_connection(
    ws_route: Any,
    logger: EventLogger,
    mock_wss_receive_list: List[str],
    push_message: Optional[str],
    push_after_spin: int,
    mock_balance_message: Optional[str],
    free_spin_responses: Dict[str, str],
    state: dict,
) -> None:
    """不連接真實 server，模擬 Socket.IO 握手並用 mock 資料回應。"""
    sid = str(uuid.uuid4())

    # websocket_open 後立即送出 Socket.IO 握手兩包
    ws_route.send(
        f'0{{"sid":"{sid}","upgrades":[],"pingInterval":10000,"pingTimeout":60000}}'
    )
    print(f"[FAKE] Connection simulated, sid={sid}")

    def on_page_message(msg: Any) -> None:
        if not isinstance(msg, str):
            return

        if msg == "2":  # Engine.IO ping → pong
            ws_route.send("3")
        elif msg.startswith("40"):  # Socket.IO CONNECT → CONNECTED
            ws_route.send(f'40{{"sid":"{sid}"}}')
        elif "client:balance" in msg:
            _handle_fake_balance(ws_route, logger, msg, mock_balance_message)
        elif "client:free_spin" in msg:
            _handle_fake_free_spin(ws_route, logger, msg, free_spin_responses)
        elif "client:spin" in msg:
            _handle_fake_spin(
                ws_route,
                logger,
                msg,
                mock_wss_receive_list,
                push_message,
                push_after_spin,
                state,
            )
        else:
            print(f"[FAKE] Ignored: {msg[:80]}")

    ws_route.on_message(on_page_message)


def _handle_fake_balance(
    ws_route: Any, logger: Any, msg: str, mock_balance_message: Optional[str]
) -> None:
    ack_id = _parse_ack_id(msg)
    if mock_balance_message:
        ws_route.send(mock_balance_message)
        logger.record_event("mock_balance_sent", payload=mock_balance_message)
    else:
        print("[FAKE] mock_balance_message not set, skipping balance response")
    ws_route.send(f"43{ack_id}[]")


def _maybe_send_push(
    ws_route: Any,
    logger: EventLogger,
    push_message: Optional[str],
    push_after_spin: int,
    spin_count: int,
    state: dict,
) -> None:
    """若條件成立則送出 push_message（每次執行只送一次）。"""
    if push_message and not state["push_sent"] and spin_count >= push_after_spin:
        ws_route.send(push_message)
        state["push_sent"] = True
        logger.record_event("push_message_sent", payload=push_message)


def _handle_fake_spin(
    ws_route: Any,
    logger: EventLogger,
    msg: str,
    mock_wss_receive_list: List[str],
    push_message: Optional[str],
    push_after_spin: int,
    state: dict,
) -> None:
    state["spin_count"] += 1
    spin_count = state["spin_count"]
    print(f"[FAKE] client:spin #{spin_count}")

    if mock_wss_receive_list:
        _send_spin_reply(
            ws_route, logger, msg, mock_wss_receive_list, spin_count, "FAKE"
        )

    _maybe_send_push(ws_route, logger, push_message, push_after_spin, spin_count, state)


def _setup_real_connection(
    ws_route: Any,
    logger: EventLogger,
    mock_wss_receive_list: List[str],
    push_message: Optional[str],
    push_after_spin: int,
    state: dict,
) -> None:
    """連接真實 server，僅攔截 client:spin 並回 mock 資料。"""
    server = ws_route.connect_to_server()

    def on_page_message(msg: Any) -> None:
        if isinstance(msg, str) and "client:spin" in msg and mock_wss_receive_list:
            state["spin_count"] += 1
            spin_count = state["spin_count"]
            print(f"[MOCK] Detected client:spin (Count: {spin_count})")
            _send_spin_reply(
                ws_route, logger, msg, mock_wss_receive_list, spin_count, "MOCK"
            )
            _maybe_send_push(ws_route, logger, push_message, push_after_spin, spin_count, state)
            return
        server.send(msg)

    def on_server_message(msg: Any) -> None:
        ws_route.send(msg)

    ws_route.on_message(on_page_message)
    server.on_message(on_server_message)
