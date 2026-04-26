"""Unit tests for wss/mock_router.py logging behaviour.

驗證以下 log 事件的名稱、payload、note 是否符合預期：
- free_spin_response_sent
- free_spin_response_not_matched
- push_message_sent
"""
from typing import Any

from wss.mock_router import (
    _handle_fake_free_spin,
    _handle_fake_spin,
    _maybe_send_push,
    _send_spin_reply,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeLogger:
    """收集 record_event 呼叫，供測試驗證 log 內容。"""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def record_event(
        self, event_name: str, payload: Any = None, note: Any = None
    ) -> None:
        self.events.append({"event": event_name, "payload": payload, "note": note})


class FakeWsRoute:
    """收集 send 呼叫，供測試驗證送出的訊息。"""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, msg: str) -> None:
        self.sent.append(msg)


# ---------------------------------------------------------------------------
# _handle_fake_free_spin
# ---------------------------------------------------------------------------

def test_free_spin_matched_records_correct_event():
    ws = FakeWsRoute()
    logger = FakeLogger()
    # ack_id 為空（42 後直接接 [）
    msg = '42["client:free_spin","PAYLOAD_KEY"]'
    free_spin_responses = {"PAYLOAD_KEY": "RESPONSE_DATA"}

    _handle_fake_free_spin(ws, logger, msg, free_spin_responses)

    assert len(logger.events) == 1
    event = logger.events[0]
    assert event["event"] == "free_spin_response_sent"
    assert "RESPONSE_DATA" in event["payload"]
    assert event["note"]["request_payload"] == "PAYLOAD_KEY"


def test_free_spin_matched_payload_contains_ack_id():
    ws = FakeWsRoute()
    logger = FakeLogger()
    msg = '4212["client:free_spin","KEY"]'  # ack_id 為 "12"
    free_spin_responses = {"KEY": "DATA"}

    _handle_fake_free_spin(ws, logger, msg, free_spin_responses)

    assert logger.events[0]["payload"] == '4312["DATA"]'


def test_free_spin_not_matched_records_correct_event():
    ws = FakeWsRoute()
    logger = FakeLogger()
    msg = '42["client:free_spin","UNKNOWN_KEY"]'
    free_spin_responses = {}

    _handle_fake_free_spin(ws, logger, msg, free_spin_responses)

    assert len(logger.events) == 1
    event = logger.events[0]
    assert event["event"] == "free_spin_response_not_matched"
    assert event["payload"] == "43[]"
    assert event["note"]["request_payload"] == "UNKNOWN_KEY"


def test_free_spin_not_matched_sends_empty_reply():
    ws = FakeWsRoute()
    logger = FakeLogger()
    msg = '4299["client:free_spin","KEY"]'  # ack_id 為 "99"
    free_spin_responses = {}

    _handle_fake_free_spin(ws, logger, msg, free_spin_responses)

    assert ws.sent[-1] == "4399[]"
    assert logger.events[0]["payload"] == "4399[]"


def test_free_spin_handles_malformed_msg():
    """regex 無法解析 payload key 時，應走 not_matched 並記錄空字串的 request_payload。"""
    ws = FakeWsRoute()
    logger = FakeLogger()
    # 缺少第二個參數，_FREE_SPIN_PAYLOAD_RE 不會 match
    msg = '42["client:free_spin"]'
    free_spin_responses = {"SOME_KEY": "DATA"}

    _handle_fake_free_spin(ws, logger, msg, free_spin_responses)

    assert len(logger.events) == 1
    event = logger.events[0]
    assert event["event"] == "free_spin_response_not_matched"
    assert event["note"]["request_payload"] == ""


# ---------------------------------------------------------------------------
# _maybe_send_push
# ---------------------------------------------------------------------------

def test_push_not_sent_before_threshold():
    ws = FakeWsRoute()
    logger = FakeLogger()
    state = {"push_sent": False}

    _maybe_send_push(ws, logger, "PUSH_MSG", push_after_spin=3, spin_count=2, state=state)

    assert not state["push_sent"]
    assert ws.sent == []
    assert logger.events == []


def test_push_sent_at_threshold():
    ws = FakeWsRoute()
    logger = FakeLogger()
    state = {"push_sent": False}

    _maybe_send_push(ws, logger, "PUSH_MSG", push_after_spin=3, spin_count=3, state=state)

    assert state["push_sent"]
    assert ws.sent == ["PUSH_MSG"]
    assert logger.events == [{"event": "push_message_sent", "payload": "PUSH_MSG", "note": None}]


def test_push_sent_only_once():
    ws = FakeWsRoute()
    logger = FakeLogger()
    state = {"push_sent": False}

    for spin in range(1, 5):
        _maybe_send_push(ws, logger, "PUSH_MSG", push_after_spin=1, spin_count=spin, state=state)

    assert ws.sent == ["PUSH_MSG"]
    assert len(logger.events) == 1


def test_push_skipped_when_already_sent():
    """push_sent=True 時即使 spin_count >= threshold 也不再送出。"""
    ws = FakeWsRoute()
    logger = FakeLogger()
    state = {"push_sent": True}

    _maybe_send_push(ws, logger, "PUSH_MSG", push_after_spin=1, spin_count=99, state=state)

    assert ws.sent == []
    assert logger.events == []


def test_push_skipped_when_message_is_none():
    ws = FakeWsRoute()
    logger = FakeLogger()
    state = {"push_sent": False}

    _maybe_send_push(ws, logger, None, push_after_spin=1, spin_count=5, state=state)

    assert ws.sent == []
    assert logger.events == []


# ---------------------------------------------------------------------------
# _send_spin_reply — modulo 索引計算
# ---------------------------------------------------------------------------

def test_send_spin_reply_uses_modulo_when_spin_count_exceeds_list_length():
    """spin_count=28、list 長度=15 時 index=(28-1)%15=12，應送出第 13 筆資料並在 log 帶上 spin_count。"""
    ws = FakeWsRoute()
    logger = FakeLogger()

    mock_list = [f"ITEM_{i}" for i in range(15)]
    spin_count = 28
    msg = '4299["client:spin","anything"]'

    _send_spin_reply(ws, logger, msg, mock_list, spin_count, "TEST")

    assert len(ws.sent) == 1
    assert "ITEM_12" in ws.sent[0]
    assert logger.events[0]["note"]["spin_count"] == spin_count


def test_send_spin_reply_first_spin_uses_index_zero():
    """spin_count=1 時，index 應為 0，選出第一筆資料。"""
    ws = FakeWsRoute()
    logger = FakeLogger()

    mock_list = ["FIRST", "SECOND", "THIRD"]
    msg = '42["client:spin","x"]'

    _send_spin_reply(ws, logger, msg, mock_list, spin_count=1, label="TEST")

    assert "FIRST" in ws.sent[0]


def test_send_spin_reply_wraps_around_at_list_boundary():
    """spin_count 恰好等於 list 長度時，index 為 len-1（最後一筆），下一筆循環回 0。"""
    ws = FakeWsRoute()
    logger = FakeLogger()

    mock_list = ["A", "B", "C"]
    msg = '42["client:spin","x"]'

    # spin_count=3 → index=(3-1)%3=2 → "C"
    _send_spin_reply(ws, logger, msg, mock_list, spin_count=3, label="TEST")
    assert "C" in ws.sent[0]

    ws2 = FakeWsRoute()
    logger2 = FakeLogger()

    # spin_count=4 → index=(4-1)%3=0 → "A"（循環）
    _send_spin_reply(ws2, logger2, msg, mock_list, spin_count=4, label="TEST")
    assert "A" in ws2.sent[0]


# ---------------------------------------------------------------------------
# _handle_fake_spin — 外部 state 傳入後 spin_count 正確累加
# ---------------------------------------------------------------------------

def test_handle_fake_spin_increments_spin_count_in_shared_state():
    """呼叫 _handle_fake_spin 後，外部傳入的 state 中 spin_count 應累加 1。"""
    ws = FakeWsRoute()
    logger = FakeLogger()
    state = {"spin_count": 0, "push_sent": False}
    mock_list = ["MOCK_ITEM"]
    msg = '42["client:spin","x"]'

    # Act
    _handle_fake_spin(ws, logger, msg, mock_list, push_message=None, push_after_spin=1, state=state)

    # Assert
    assert state["spin_count"] == 1


def test_handle_fake_spin_accumulates_across_multiple_calls():
    """模擬斷線重連：每次呼叫共用同一個 state，spin_count 應持續累加，不歸零。"""
    ws = FakeWsRoute()
    logger = FakeLogger()
    state = {"spin_count": 5, "push_sent": False}  # 模擬重連前已有 5 次 spin
    mock_list = ["DATA_A", "DATA_B"]
    msg = '42["client:spin","x"]'

    # Act：模擬重連後再 spin 3 次
    for _ in range(3):
        _handle_fake_spin(ws, logger, msg, mock_list, push_message=None, push_after_spin=99, state=state)

    # Assert：spin_count 從 5 累加到 8，不從 0 開始
    assert state["spin_count"] == 8


def test_handle_fake_spin_uses_correct_index_from_existing_spin_count():
    """重連後 spin_count 為 14 時，第一次 spin 後 count=15，index=(15-1)%3=2，應選第 3 筆。"""
    ws = FakeWsRoute()
    logger = FakeLogger()
    state = {"spin_count": 14, "push_sent": False}
    mock_list = ["ITEM_0", "ITEM_1", "ITEM_2"]
    msg = '42["client:spin","x"]'

    _handle_fake_spin(ws, logger, msg, mock_list, push_message=None, push_after_spin=99, state=state)

    # spin_count 應為 15，index = (15-1) % 3 = 2
    assert state["spin_count"] == 15
    assert "ITEM_2" in ws.sent[0]


def test_handle_fake_spin_does_not_send_when_mock_list_empty():
    """mock_wss_receive_list 為空時，不應送出任何訊息（也不 crash）。"""
    ws = FakeWsRoute()
    logger = FakeLogger()
    state = {"spin_count": 0, "push_sent": False}
    msg = '42["client:spin","x"]'

    _handle_fake_spin(ws, logger, msg, [], push_message=None, push_after_spin=99, state=state)

    assert state["spin_count"] == 1  # count 仍應累加
    assert ws.sent == []             # 無資料可送


def test_handle_fake_spin_preserves_push_sent_across_calls():
    """重連情境：push_sent=True 時，後續 spin 不應再送 push_message（跨重連不重發）。"""
    ws = FakeWsRoute()
    logger = FakeLogger()
    # 模擬重連前已送過 push
    state = {"spin_count": 10, "push_sent": True}
    mock_list = ["DATA"]
    msg = '42["client:spin","x"]'

    _handle_fake_spin(
        ws, logger, msg, mock_list,
        push_message="PUSH_PAYLOAD", push_after_spin=1, state=state,
    )

    # 僅送出 spin 回覆，不應再送 PUSH_PAYLOAD
    assert "PUSH_PAYLOAD" not in ws.sent
    assert state["push_sent"] is True
