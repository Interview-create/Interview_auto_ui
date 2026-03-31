import asyncio
import base64
import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import blackboxprotobuf
from playwright.async_api import async_playwright

from configs import GAME_CONFIGS
from mock_data import generate_mock_data

OUTPUT_DIR = Path("logs/playwight_wss_log")
RUN_TS = datetime.now().strftime("%Y%m%d_%H%M%S")
TARGET_PID = "SS02"
# --- WSS Mock 替換設定 ---
MOCK_WSS_ENABLED = True


def _now_iso() -> str:
    return datetime.now().isoformat()


def _safe_ws_url(ws: Any) -> str:
    return str(getattr(ws, "url", ""))


def _serialize_payload(payload: Any) -> Tuple[Any, str]:
    if isinstance(payload, bytes):
        return base64.b64encode(payload).decode("ascii"), "binary"
    if isinstance(payload, str):
        return payload, "text"
    if payload is None:
        return None, "unknown"
    return str(payload), "unknown"


def _heuristic_decode(data: bytes) -> Dict[str, Any]:
    hex_str = data.hex()
    strings = []
    current = []
    for b in data:
        if 32 <= b <= 126:
            current.append(chr(b))
        else:
            if len(current) >= 4:
                strings.append("".join(current))
            current = []
    if len(current) >= 4:
        strings.append("".join(current))
    return {"hex": hex_str, "strings": strings}


def bytes_to_readable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: bytes_to_readable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [bytes_to_readable(x) for x in obj]
    elif isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode("utf-8")
        except UnicodeDecodeError:
            return obj.hex()
    else:
        return obj


def decode_protobuf_to_json(payload_b64: str) -> Optional[str]:
    try:
        decoded = base64.b64decode(payload_b64)
        msg, _ = blackboxprotobuf.decode_message(decoded)
        msg_clean = bytes_to_readable(msg)
        return json.dumps(msg_clean, indent=4, ensure_ascii=False)
    except Exception:
        return None


class WssLogger:
    def __init__(self, ws_url: str, run_ts: str) -> None:
        self.ws_url = ws_url
        self.run_ts = run_ts
        self.events: List[Dict[str, Any]] = []

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Generate a safe filename based on URL hash and UUID to avoid collisions
        url_hash = hashlib.md5(ws_url.encode("utf-8")).hexdigest()[:8]
        unique_id = str(uuid.uuid4())[:8]
        self.output_path = OUTPUT_DIR / f"wss_{url_hash}_{self.run_ts}_{unique_id}.json"
        self._write_log_file()  # Create file on init

    def _write_log_file(self) -> None:
        """Atomically writes the current log state to the JSON file."""
        payload = {
            "run_ts": self.run_ts,
            "ws_url": self.ws_url,
            "events": self.events,
        }
        temp_path = self.output_path.with_suffix(".json.tmp")
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        temp_path.rename(self.output_path)

    def record_event(
        self,
        event_name: str,
        payload: Any = None,
        note: Any = None,
    ) -> None:
        """Records a WebSocket event and persists the log."""
        payload_data, payload_type = _serialize_payload(payload)
        decoded_payload = None
        b64_to_decode = None

        if payload_type == "binary" and isinstance(payload_data, str):
            b64_to_decode = payload_data
            if note is None and isinstance(payload, bytes):
                note = _heuristic_decode(payload)
        elif payload_type == "text" and isinstance(payload_data, str):
            # Handle socket.io text frame format: 42["event", "base64_payload", ...]
            if payload_data.startswith("4"):
                try:
                    json_part_index = payload_data.find("[")
                    if json_part_index != -1:
                        json_part = payload_data[json_part_index:]
                        ws_data = json.loads(json_part)

                        # BFS to find the first likely base64 string
                        queue: List[Any] = [ws_data]
                        found = False
                        while queue and not found:
                            item = queue.pop(0)
                            if (
                                isinstance(item, str)
                                and len(item) > 20
                                and " " not in item
                            ):
                                try:
                                    base64.b64decode(item, validate=True)
                                    b64_to_decode = item
                                    found = True
                                except Exception:
                                    continue
                            elif isinstance(item, list):
                                queue.extend(item)
                            elif isinstance(item, dict):
                                queue.extend(item.values())
                except (json.JSONDecodeError, IndexError):
                    pass

        if b64_to_decode:
            decoded_str = decode_protobuf_to_json(b64_to_decode)
            if decoded_str:
                try:
                    decoded_payload = json.loads(decoded_str)
                except json.JSONDecodeError:
                    decoded_payload = {
                        "error": "Failed to parse JSON from decoded protobuf",
                        "decoded_str": decoded_str,
                    }

        event_data = {
            "ts": _now_iso(),
            "event": event_name,
            "payload": payload_data,
            "payload_type": payload_type,
            "decoded_payload": decoded_payload,
            "note": note,
        }
        self.events.append(event_data)
        self._write_log_file()

    @property
    def log_path(self) -> Path:
        return self.output_path


def _attach_ws_listeners(page: Any) -> None:
    def on_websocket(ws: Any) -> None:
        ws_url = _safe_ws_url(ws)

        # Create a logger specifically for this WebSocket connection
        logger = WssLogger(ws_url, RUN_TS)
        logger.record_event("websocket_open")

        def on_frame_sent(payload: Any) -> None:
            logger.record_event("frame_sent", payload=payload)

        def on_frame_received(payload: Any) -> None:
            logger.record_event("frame_received", payload=payload)

        def on_close() -> None:
            logger.record_event("websocket_close")

        def on_socket_error(err: Any) -> None:
            logger.record_event("websocket_error", note=str(err))

        ws.on("framesent", on_frame_sent)
        ws.on("framereceived", on_frame_received)
        ws.on("close", on_close)

        try:
            ws.on("socketerror", on_socket_error)
        except Exception as e:
            logger.record_event(
                "websocket_error",
                note=f"socketerror listener not supported: {e}",
            )

    page.on("websocket", on_websocket)


async def open_and_play(
    p: Any, test_url: str, mock_wss_receive_list: List[str]
) -> None:

    browser = await p.chromium.launch(headless=False)

    try:
        page = await browser.new_page()

        if MOCK_WSS_ENABLED:

            def handle_ws_route(ws_route: Any) -> None:
                try:
                    server = ws_route.connect_to_server()
                    spin_count = 0

                    def on_page_message(msg: Any) -> None:
                        nonlocal spin_count
                        # 攔截 Client 傳給 Server 的訊息（這裡直接轉發）
                        if isinstance(msg, str) and "client:spin" in msg:
                            spin_count += 1
                            print(f"[MOCK] Detected client:spin (Count: {spin_count})")

                            if mock_wss_receive_list:
                                idx = max(0, spin_count - 1) % len(
                                    mock_wss_receive_list
                                )
                                mock_data_item = mock_wss_receive_list[idx]

                                # 解析 Socket.io 格式，取得 ACK ID (如 4212[...] 取出 12)
                                match = re.match(r"^42(\d+)\[", msg)
                                ack_id = match.group(1) if match else ""

                                # 若為陣列，代表這回合要回傳多包 (例如 ACK + Push)
                                items_to_send = (
                                    mock_data_item
                                    if isinstance(mock_data_item, list)
                                    else [mock_data_item]
                                )

                                for data in items_to_send:
                                    # 若 data 已經是完整的 socket.io 訊息則直接用，否則包裝成 ACK
                                    mock_msg = (
                                        data
                                        if data.startswith("4")
                                        else f'43{ack_id}["{data}"]'
                                    )
                                    print(
                                        f"[MOCK] Replied with mock data for spin #{spin_count}: {mock_msg[:80]}..."
                                    )
                                    ws_route.send(mock_msg)

                                return  # 短路：攔截此訊息，不再傳給 Server

                        # 若未被攔截（例如不是 client:spin），則正常轉發給 Server
                        server.send(msg)

                    def on_server_message(msg: Any) -> None:
                        # 攔截 Server 傳回給 Client 的訊息（原封不動轉發）
                        ws_route.send(msg)

                    ws_route.on_message(on_page_message)
                    server.on_message(on_server_message)
                except Exception as e:
                    print(f"WebSocket mock error: {e}")

            await page.route_web_socket("**/*", handle_ws_route)

        _attach_ws_listeners(page)

        try:
            await page.goto(test_url, wait_until="load", timeout=60000)
        except Exception as e:
            print(f"Navigation error: {e}")
            return

        print(await page.title())

        # Keep the page open for a while to capture WebSocket traffic
        await asyncio.Event().wait()

    finally:
        await browser.close()


async def main(pid: str) -> None:
    config = GAME_CONFIGS.get(pid)
    if not config or not config.get("url"):
        print(f"[{pid}] Configuration or URL not found.")
        return

    test_url = config["url"]
    typedef = config.get("typedef", {})
    mock_wss_receive_list = generate_mock_data(pid, typedef) if MOCK_WSS_ENABLED else []

    async with async_playwright() as p:
        tasks = []
        for _ in range(2, 3):
            tasks.append(
                asyncio.create_task(open_and_play(p, test_url, mock_wss_receive_list))
            )
            await asyncio.sleep(5)
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main(TARGET_PID))
