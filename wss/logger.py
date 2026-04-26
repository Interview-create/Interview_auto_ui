import base64
import csv
import json
import struct
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

import blackboxprotobuf

from .utils import now_iso, safe_ws_url


def _resolve_output_dir() -> Path:
    """從 config.json 讀取 logs_dir（預設 "logs"），解析為絕對路徑。
    相對路徑以 playwright/ 目錄為基準；絕對路徑直接使用。
    """
    config_path = Path(__file__).resolve().parent.parent / "config.json"
    try:
        with config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)
        logs_dir = config.get("logs_dir", "logs")
    except Exception:
        logs_dir = "logs"
    path = Path(logs_dir)
    base = Path(__file__).resolve().parent.parent  # playwright/
    return path if path.is_absolute() else base / path


def _resolve_target_pid() -> str:
    """從 config.json 讀取 target_pid，作為 log 子目錄名稱。"""
    config_path = Path(__file__).resolve().parent.parent / "config.json"
    try:
        with config_path.open("r", encoding="utf-8") as f:
            return json.load(f).get("target_pid", "")
    except Exception:
        return ""


OUTPUT_DIR = _resolve_output_dir()
TARGET_PID = _resolve_target_pid()


def _serialize_payload(payload: Any) -> Tuple[Any, str]:
    # 將 payload 統一轉成可記錄格式，並回傳類型（binary/text/unknown）
    if isinstance(payload, bytes):
        return base64.b64encode(payload).decode("ascii"), "binary"
    if isinstance(payload, str):
        return payload, "text"
    if payload is None:
        return None, "unknown"
    return str(payload), "unknown"


def _heuristic_decode(data: bytes) -> Dict[str, Any]:
    # 簡單解析 bytes：輸出 hex 與可讀字串片段（方便除錯）
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
    # 遞迴把 bytes 轉成可讀字串或 hex
    if isinstance(obj, dict):
        return {k: bytes_to_readable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [bytes_to_readable(x) for x in obj]
    if isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode("utf-8")
        except UnicodeDecodeError:
            return obj.hex()
    return obj


def _uint64_to_double(val: int) -> float:
    """把 uint64 的 raw bits 還原成 IEEE 754 double。"""
    return struct.unpack(">d", val.to_bytes(8, "big"))[0]


def _decode_packed_ints_from_bytes(data: bytes) -> list:
    """把 packed repeated int32/int64 bytes 解成 Python int list（支援負值）。"""
    result = []
    pos = 0
    while pos < len(data):
        val = 0
        shift = 0
        while pos < len(data):
            b = data[pos]
            pos += 1
            val |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
        # 轉成有號整數（proto int32 的負值以 int64 編碼，佔 10 bytes）
        if val >= (1 << 63):
            val -= (1 << 64)
        result.append(val)
    return result


def _decode_packed_field(raw_value: Any, discovered_field_info: dict) -> Any:
    """把 packed repeated 欄位還原成 int list。
    raw_value 可能是：
      - bytes/bytearray：直接解成 packed ints
      - dict：blackboxprotobuf 把 packed bytes 誤解析成 nested message，
              用 discovered types 重新 encode 回 bytes 再解
    """
    if isinstance(raw_value, (bytes, bytearray)):
        return _decode_packed_ints_from_bytes(bytes(raw_value))
    if isinstance(raw_value, dict):
        try:
            nested_types = discovered_field_info.get("message_typedef", {})
            raw_bytes = blackboxprotobuf.encode_message(raw_value, nested_types)
            return _decode_packed_ints_from_bytes(bytes(raw_bytes))
        except Exception as e:
            print(f"[logger] _decode_packed_field: re-encode failed: {e}")
            return bytes_to_readable(raw_value)
    if isinstance(raw_value, str):
        # 相容舊有流程：已轉成 hex string
        try:
            return _decode_packed_ints_from_bytes(bytes.fromhex(raw_value))
        except Exception as e:
            print(f"[logger] _decode_packed_field: hex decode failed: {e}")
            return raw_value
    return raw_value


def _accumulate_field(result: dict, field_name: str, value: Any) -> None:
    """將 value 寫入 result[field_name]。
    若同名欄位已存在（blackboxprotobuf repeated 欄位的多次出現），合併成 list。
    """
    if field_name in result:
        existing = result[field_name]
        if isinstance(existing, list):
            existing.append(value)
        else:
            result[field_name] = [existing, value]
    else:
        result[field_name] = value


def _reencode_to_bytes(raw_value: dict, discovered_field_info: dict, field_name: str) -> Any:
    """當 blackboxprotobuf 把 bytes 欄位誤解析為 dict 時，重新 encode 回 bytes 再 decode。"""
    try:
        nested_types = discovered_field_info.get("message_typedef", {})
        raw_bytes = blackboxprotobuf.encode_message(raw_value, nested_types)
        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return raw_bytes.hex()
    except Exception as e:
        print(f"[logger] _reencode_to_bytes failed for field={field_name}: {e}")
        return bytes_to_readable(raw_value)


def _apply_typedef_full(raw_msg: Any, discovered_types: dict, typedef: dict) -> Any:
    """Post-process：rename keys、轉換 double、解 packed ints，一次完成。
    raw_msg 是 blackboxprotobuf.decode_message 的直接輸出（未經 bytes_to_readable）。
    利用 discovered_types 還原被誤解析的 packed 欄位。
    規避 blackboxprotobuf v1.0.1 在 named typedef + repeated message 上的 KeyError bug。

    blackboxprotobuf 對 repeated 欄位的多次出現會產生 "N-M" 格式的 key（如 "4-1"、"4-2"），
    此處將其與第一筆 ("N") 合併成 list，統一放在同一個 field_name 下。
    """
    if not isinstance(raw_msg, dict) or not typedef:
        return bytes_to_readable(raw_msg)

    result = {}
    for key, raw_value in raw_msg.items():
        key_str = str(key)
        # 處理 blackboxprotobuf repeated 欄位的 "N-M" 格式（如 "4-1" → base "4"）
        parts = key_str.split("-")
        base_key = parts[0] if len(parts) == 2 and parts[1].isdigit() else key_str
        field_info = typedef.get(base_key)
        discovered_field = discovered_types.get(base_key, {})

        if field_info is None:
            result[key] = bytes_to_readable(raw_value)
            continue

        field_name = field_info.get("name") or base_key
        field_type = field_info.get("type", "")
        nested_typedef = field_info.get("message_typedef")

        if field_type == "double":
            if isinstance(raw_value, int):
                raw_value = _uint64_to_double(raw_value)
            _accumulate_field(result, field_name, raw_value)

        elif field_type.startswith("packed_"):
            _accumulate_field(
                result, field_name, _decode_packed_field(raw_value, discovered_field)
            )

        elif nested_typedef:
            nested_discovered = discovered_field.get("message_typedef", {})
            if isinstance(raw_value, list):
                raw_value = [
                    _apply_typedef_full(item, nested_discovered, nested_typedef)
                    if isinstance(item, dict)
                    else bytes_to_readable(item)
                    for item in raw_value
                ]
            elif isinstance(raw_value, dict):
                raw_value = _apply_typedef_full(
                    raw_value, nested_discovered, nested_typedef
                )
            else:
                raw_value = bytes_to_readable(raw_value)
            _accumulate_field(result, field_name, raw_value)

        else:
            # 若 typedef 說是 "bytes" 但 blackboxprotobuf auto-detect 把它解成 nested message（dict），
            # 需要重新 encode 回 bytes 再解 UTF-8，否則會得到 {"6": 892809262} 這類錯誤結果。
            # 典型情況：Money.value = "5.075" 的 5 bytes 恰好是合法 fixed32 protobuf。
            if field_type == "bytes":
                if isinstance(raw_value, dict):
                    raw_value = _reencode_to_bytes(raw_value, discovered_field, field_name)
                elif isinstance(raw_value, list):
                    raw_value = [
                        _reencode_to_bytes(item, discovered_field, field_name) if isinstance(item, dict)
                        else bytes_to_readable(item)
                        for item in raw_value
                    ]
                else:
                    raw_value = bytes_to_readable(raw_value)
            else:
                raw_value = bytes_to_readable(raw_value)
            _accumulate_field(result, field_name, raw_value)

    return result


def decode_protobuf_raw(
    payload_b64: str,
) -> Optional[Tuple[dict, dict]]:
    """把 base64 protobuf payload 解碼，回傳 (raw_msg, discovered_types)。
    raw_msg 未經 bytes_to_readable 處理，保留 bytes 以供 packed 欄位正確還原。
    """
    try:
        decoded = base64.b64decode(payload_b64)
        msg, discovered_types = blackboxprotobuf.decode_message(decoded, None)
        return msg, discovered_types
    except Exception as e:
        print(f"[logger] decode_protobuf_raw failed: {e}")
        return None


class WssLogger:
    def __init__(self, run_ts, message_typedef=None, event_typedefs=None, pair_index=0, username=""):
        self.run_ts = run_ts
        self.message_typedef = message_typedef
        self.event_typedefs = event_typedefs or {}
        self.ws_urls: List[str] = []
        self._write_failures: int = 0

        date_str = run_ts[:8]
        log_dir = (OUTPUT_DIR / date_str / TARGET_PID) if TARGET_PID else (OUTPUT_DIR / date_str)
        log_dir.mkdir(parents=True, exist_ok=True)

        self.output_path = log_dir / f"{self.run_ts}_{username}_wss.jsonl"
        self._meta_path = log_dir / f"{self.run_ts}_{username}_wss_meta.json"

        # Reload ws_urls from meta file if it exists
        if self._meta_path.exists():
            try:
                meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
                if meta.get("run_ts") != self.run_ts:
                    print(f"[logger] meta run_ts mismatch for {self._meta_path}, resetting ws_urls")
                else:
                    self.ws_urls = meta.get("ws_urls", [])
            except Exception as e:
                print(f"[logger] Failed to load meta {self._meta_path}: {e}")
        else:
            self._write_meta()

        self._fh = self.output_path.open("ab", buffering=0)

    def _write_meta(self) -> None:
        payload = json.dumps({"run_ts": self.run_ts, "ws_urls": self.ws_urls}, ensure_ascii=False).encode("utf-8")
        temp_path = Path(str(self._meta_path) + ".tmp")
        try:
            temp_path.write_bytes(payload)
            temp_path.rename(self._meta_path)
        except Exception as e:
            print(f"[logger] Failed to write meta {self._meta_path}: {e}")

    def add_ws_url(self, ws_url: str) -> None:
        """記錄新的 WebSocket URL（同一 session 可能有多個連線）。"""
        if ws_url and ws_url not in self.ws_urls:
            self.ws_urls.append(ws_url)
            self._write_meta()

    def record_event(
        self,
        event_name: str,
        payload: Any = None,
        note: Any = None,
        ws_url: Optional[str] = None,
    ) -> None:
        # 記錄單一事件（含原始 payload 與可解碼的 protobuf）
        payload_data, payload_type = _serialize_payload(payload)
        decoded_payload = None
        b64_to_decode = None
        decoded_event_name: Optional[str] = None
        typedef_to_use = self.message_typedef

        # binary: 直接視為 base64
        if payload_type == "binary" and isinstance(payload_data, str):
            b64_to_decode = payload_data
            if note is None and isinstance(payload, bytes):
                note = _heuristic_decode(payload)
        elif payload_type == "text" and isinstance(payload_data, str):
            # text: 嘗試解析 Socket.IO 格式，找出 base64
            if payload_data.startswith("4"):
                try:
                    json_part_index = payload_data.find("[")
                    if json_part_index != -1:
                        json_part = payload_data[json_part_index:]
                        ws_data = json.loads(json_part)
                        if (
                            isinstance(ws_data, list)
                            and ws_data
                            and isinstance(ws_data[0], str)
                        ):
                            decoded_event_name = ws_data[0]
                            typedef_to_use = (
                                self.event_typedefs.get(decoded_event_name)
                                or self.message_typedef
                            )

                        # BFS 尋找第一個看起來像 base64 的字串
                        queue: Deque[Any] = deque([ws_data])
                        found = False
                        while queue and not found:
                            item = queue.popleft()
                            if (
                                isinstance(item, str)
                                and len(item) > 8
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

            # 若未找到 Socket.IO 格式，嘗試直接解碼純 base64
            if not b64_to_decode:
                try:
                    base64.b64decode(payload_data, validate=True)
                    b64_to_decode = payload_data
                except Exception:
                    pass

        # 若找到了 base64，就解 protobuf
        # 永遠不帶 typedef 給 blackboxprotobuf（規避 v1.0.1 named typedef + repeated 欄位的 bug），
        # 解完後再用 _apply_typedef_full 做 rename / double 轉換 / packed ints 還原
        if b64_to_decode:
            raw_result = decode_protobuf_raw(b64_to_decode)
            if raw_result is not None:
                raw_msg, discovered_types = raw_result
                if typedef_to_use:
                    decoded_payload = _apply_typedef_full(
                        raw_msg, discovered_types, typedef_to_use
                    )
                else:
                    decoded_payload = bytes_to_readable(raw_msg)

        # 組出 event log 並寫入檔案
        event_data = {
            "ts": now_iso(),
            "event": event_name,
            "ws_url": ws_url,
            "socket_event": decoded_event_name,
            "payload": payload_data,
            "payload_type": payload_type,
            "decoded_payload": decoded_payload,
            "note": note,
        }
        try:
            self._fh.write((json.dumps(event_data, ensure_ascii=False) + "\n").encode("utf-8"))
        except Exception as e:
            self._write_failures += 1
            print(f"[logger] record_event write failed (total={self._write_failures}): {e}")

    @property
    def log_path(self) -> Path:
        # 方便外部取得 log 檔路徑
        return self.output_path

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass
        if self._write_failures:
            print(f"[logger] WssLogger closed with {self._write_failures} write failure(s): {self.output_path}")


class ApiLogger:
    """記錄瀏覽器發出的 HTTP API 請求與回應。"""

    def __init__(self, run_ts: str, username: str = "") -> None:
        self.run_ts = run_ts
        self._write_failures: int = 0

        date_str = run_ts[:8]
        log_dir = (OUTPUT_DIR / date_str / TARGET_PID) if TARGET_PID else (OUTPUT_DIR / date_str)
        log_dir.mkdir(parents=True, exist_ok=True)
        self.output_path = log_dir / f"{run_ts}_{username}_api.jsonl"

        is_new = not self.output_path.exists()
        self._fh = self.output_path.open("ab", buffering=0)
        if is_new:
            try:
                self._fh.write((json.dumps({"run_ts": run_ts}, ensure_ascii=False) + "\n").encode("utf-8"))
            except Exception as e:
                print(f"[logger] Failed to write API log header: {e}")

    def record_event(
        self,
        event: str,
        resource_type: Optional[str],
        method: str,
        url: str,
        request_headers: Optional[Dict[str, str]] = None,
        response_headers: Optional[Dict[str, str]] = None,
        payload: Optional[str] = None,
        payload_type: Optional[str] = None,
        status: Optional[int] = None,
        api_duration_ms: Optional[float] = None,
        note: Any = None,
    ) -> None:
        event_data = {
            "ts": now_iso(),
            "event": event,
            "resource_type": resource_type,
            "method": method,
            "url": url,
            "status": status,
            "request_headers": request_headers,
            "response_headers": response_headers,
            "payload": payload,
            "payload_type": payload_type,
            "api_duration_ms": api_duration_ms,
            "note": note,
        }
        try:
            self._fh.write((json.dumps(event_data, ensure_ascii=False) + "\n").encode("utf-8"))
        except Exception as e:
            self._write_failures += 1
            print(f"[logger] api record_event write failed (total={self._write_failures}): {e}")

    @property
    def log_path(self) -> Path:
        return self.output_path

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass
        if self._write_failures:
            print(f"[logger] ApiLogger closed with {self._write_failures} write failure(s): {self.output_path}")


_CSV_FIELDS = [
    "run_ts", "type", "ts", "event", "method", "url",
    "status", "resource_type", "api_duration_ms", "payload_type", "note",
]


class CsvLogger:
    """統一寫入所有 API 與 WSS 摘要至 summary.csv（append 模式，跨執行累積）。"""

    def __init__(self) -> None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.csv_path = OUTPUT_DIR / "summary.csv"

    def record(
        self,
        run_ts: str,
        type_: str,
        ts: str,
        event: str,
        method: Optional[str] = None,
        url: Optional[str] = None,
        status: Optional[int] = None,
        resource_type: Optional[str] = None,
        api_duration_ms: Optional[float] = None,
        payload_type: Optional[str] = None,
        note: Any = None,
    ) -> None:
        row = {
            "run_ts": run_ts,
            "type": type_,
            "ts": ts,
            "event": event,
            "method": method,
            "url": url,
            "status": status,
            "resource_type": resource_type,
            "api_duration_ms": api_duration_ms,
            "payload_type": payload_type,
            "note": None if note is None else str(note),
        }
        with self.csv_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS, extrasaction="ignore")
            # 檔案為空（新建或被外部刪除後重建）時補寫 header
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow(row)

    @property
    def log_path(self) -> Path:
        return self.csv_path


# WSS logger keyed by (run_ts, pair_index) — one per user session
_logger_registry: Dict[Tuple[str, int], WssLogger] = {}
# API logger keyed by (run_ts, username) — one per user per run
_api_logger_registry: Dict[Tuple[str, str], ApiLogger] = {}
_csv_logger: Optional[CsvLogger] = None


def get_csv_logger() -> CsvLogger:
    # 全域單例，所有執行共用同一份 summary.csv
    global _csv_logger
    if _csv_logger is None:
        _csv_logger = CsvLogger()
    return _csv_logger


def get_or_create_wss_logger(
    run_ts: str,
    pair_index: int = 0,
    username: str = "",
    message_typedef: Optional[dict] = None,
    event_typedefs: Optional[Dict[str, dict]] = None,
) -> WssLogger:
    # 取得或建立 per-user WssLogger；由 attach_ws_listeners 於 session 開始時立即呼叫，
    # 確保即使沒有 WebSocket 連線也會產生 log 檔案
    key = (run_ts, pair_index)
    if key not in _logger_registry:
        _logger_registry[key] = WssLogger(
            run_ts, message_typedef, event_typedefs, pair_index=pair_index, username=username
        )
    return _logger_registry[key]


def new_logger_for_ws(
    ws: Any,
    run_ts: str,
    pair_index: int = 0,
    message_typedef: Optional[dict] = None,
    event_typedefs: Optional[Dict[str, dict]] = None,
    username: str = "",
) -> WssLogger:
    # 取得或建立 per-user logger，並將此 WebSocket 的 URL 記錄到 ws_urls 清單
    ws_url = safe_ws_url(ws)
    logger = get_or_create_wss_logger(run_ts, pair_index, username, message_typedef, event_typedefs)
    logger.add_ws_url(ws_url)
    return logger


def get_or_create_api_logger(run_ts: str, username: str = "") -> ApiLogger:
    # 依照 (run_ts, username) 取得或建立 ApiLogger，每個使用者獨立一份
    key = (run_ts, username)
    if key not in _api_logger_registry:
        _api_logger_registry[key] = ApiLogger(run_ts, username)
    return _api_logger_registry[key]
