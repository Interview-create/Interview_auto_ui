import base64
import copy
import json
import struct
from pathlib import Path
from typing import Any, List

import blackboxprotobuf

from config.runtime import load_runtime_config

# mock_data/ 目錄固定與本檔案同層，不依賴執行時的 CWD
_MOCK_DATA_DIR = Path(__file__).resolve().parent / "mock_data"


def _decode_varint_list(data: bytes) -> List[int]:
    # 將 protobuf 的 varint bytes 逐個解碼成整數列表
    values: List[int] = []
    i = 0
    length = len(data)
    while i < length:
        # 逐個 varint 解析（低 7 bits 累積，直到遇到最高位為 0）
        shift = 0
        value = 0
        while True:
            b = data[i]
            i += 1
            value |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        values.append(value)
    return values


def _to_signed_int32(value: int) -> int:
    # 將無號 32-bit 整數轉成有號 32-bit（處理 -1 這類值）
    value &= 0xFFFFFFFF
    if value >= 0x80000000:
        value -= 0x100000000
    return value


def _decode_double_bits(value: Any) -> Any:
    # 將 double 的 64-bit bit pattern 轉成 float
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return struct.unpack(">d", value.to_bytes(8, "big"))[0]
    return value


def _load_yaml_or_json(path: Path) -> Any:
    # 先嘗試用 YAML 解析；若環境沒有 PyYAML，就退回 JSON 解析
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ImportError:
        return json.loads(text)


def _decode_positions(value: Any, signed: bool = False) -> Any:
    # 將 positions / hit_positions 的不同型別統一成 int list
    if isinstance(value, list):
        return value
    if isinstance(value, (bytes, bytearray)):
        # bytes 直接用 varint 解碼
        numbers = _decode_varint_list(bytes(value))
        return [_to_signed_int32(v) for v in numbers] if signed else numbers
    if isinstance(value, str):
        # 字串可能是 hex 或 latin1 bytes 表示
        stripped = value.strip()
        is_hex = len(stripped) % 2 == 0 and all(
            c in "0123456789abcdefABCDEF" for c in stripped
        )
        raw = bytes.fromhex(stripped) if is_hex else stripped.encode("latin1")
        numbers = _decode_varint_list(raw)
        return [_to_signed_int32(v) for v in numbers] if signed else numbers
    return value


def _normalize_pay_lines(data: dict) -> None:
    # 將 pay_lines 內容正規化為可編碼的 list[int] 結構
    pay_lines_key = "pay_lines" if "pay_lines" in data else "4"
    if pay_lines_key not in data:
        return
    pay_lines = data.get(pay_lines_key, [])
    if isinstance(pay_lines, dict):
        # 單一 payline 也包成 list，統一處理
        pay_lines = [pay_lines]
    if not isinstance(pay_lines, list):
        return
    for item in pay_lines:
        if not isinstance(item, dict):
            continue
        # 同時支援命名 key 與數字 key
        positions_key = "positions" if "positions" in item else "2"
        hit_key = "hit_positions" if "hit_positions" in item else "3"
        if positions_key in item:
            item[positions_key] = _decode_positions(item[positions_key], signed=False)
        if hit_key in item:
            item[hit_key] = _decode_positions(item[hit_key], signed=True)


def _normalize_double_fields(data: dict, typedef: dict, field_nums: List[str]) -> None:
    # 針對 typedef 中標記為 double 的欄位做 bit pattern 轉換
    for field_num in field_nums:
        field_def = typedef.get(field_num, {})
        if field_def.get("type") != "double":
            continue
        if field_num in data:
            data[field_num] = _decode_double_bits(data[field_num])
            continue
        field_name = field_def.get("name")
        if field_name and field_name in data:
            data[field_name] = _decode_double_bits(data[field_name])


def encode_to_base64(data: dict, typedef: dict) -> str:
    # 1. 針對 pay_lines 的 positions / hit_positions 做向後相容正規化
    _normalize_pay_lines(data)
    # 2. 針對 total_payout / bet 的 double 位元表示做正規化
    _normalize_double_fields(data, typedef, ["6", "7"])

    # 3. 透過 blackboxprotobuf 將資料與 typedef 進行 protobuf 編碼
    encoded_bytes = blackboxprotobuf.encode_message(data, typedef)

    # 4. 轉成 base64 字串
    return base64.b64encode(encoded_bytes).decode("utf-8")


def generate_mocks_by_symbol_codes(
    base_data: dict,
    symbol_codes: List[int],
    typedef: dict,
    grid_key: str = "3",
    code_key: str = "2",
) -> List[str]:
    """根據提供的 symbol_codes 列表，替換盤面代碼並產生對應的 Base64 Mock 資料列表"""
    results = []
    for code in symbol_codes:
        # 每個 symbol code 都複製一份 base_data
        data = copy.deepcopy(base_data)
        # 逐格替換 code
        for item in data.get(grid_key, []):
            item[code_key] = code
        # 編碼成 base64 供 websocket 回傳
        results.append(encode_to_base64(data, typedef))
    return results


def _build_prepend_list(pid: str) -> List[Any]:
    """讀取 config → mock_list_append_enabled → 組前置封包"""
    config = load_runtime_config()
    if not config.get("mock_list_append_enabled", True):
        return []
    items = config.get("game_configs", {}).get(pid, {}).get("mock_list_append")
    if not items:
        return []
    return list(items) if isinstance(items, list) else [items]


def _generate_grid_scenario_mocks(
    cfg: dict, extra_key: str, typedef: dict
) -> List[str]:
    """SS02 / SS03 共用：替換 grid 盤面 symbol code，再接上額外完整範例資料"""
    results = []
    base_spin = cfg["json_str_base"]
    for code in cfg["symbol_codes"]:
        data = copy.deepcopy(base_spin)
        scenarios = data.get("scenarios", {})
        targets = [scenarios] if isinstance(scenarios, dict) else scenarios
        for scenario in targets:
            for item in scenario.get("grid", []):
                item["code"] = code
        results.append(encode_to_base64(data, typedef))
    data_list = cfg[extra_key]
    if not isinstance(data_list, list):
        data_list = [data_list]
    for data in data_list:
        results.append(encode_to_base64(data, typedef))
    return results


def _mocks_ss01(typedef: dict) -> List[str]:
    """產生 SS01 / SS01A 的 Mock 資料"""
    results = []
    # 讀取 SS01 的 YAML 設定
    ss01_cfg = _load_yaml_or_json(_MOCK_DATA_DIR / "ss01.yaml")
    base_spin = ss01_cfg["json_str_base"]
    base_data1 = copy.deepcopy(base_spin)
    symbol_codes = ss01_cfg["symbol_codes"]
    # 產生「整盤同一 symbol」的多筆 mock
    results.extend(
        generate_mocks_by_symbol_codes(
            base_data1, symbol_codes, typedef, grid_key="grid", code_key="code"
        )
    )

    pay_lines_variants = ss01_cfg["pay_lines_variants"]
    base_data2 = copy.deepcopy(base_spin)
    for pay_lines in pay_lines_variants:
        # 每一組 pay_lines 產生一筆 mock
        data = copy.deepcopy(base_data2)
        data["pay_lines"] = pay_lines
        # total_payout 直接由 pay_lines 的 payout 加總
        data["total_payout"] = sum(
            line.get("payout", 0.0) for line in pay_lines if isinstance(line, dict)
        )
        results.append(encode_to_base64(data, typedef))
    return results


def _mocks_ss02(typedef: dict) -> List[str]:
    """產生 SS02 的 Mock 資料"""
    cfg = _load_yaml_or_json(_MOCK_DATA_DIR / "ss02.yaml")
    return _generate_grid_scenario_mocks(cfg, "json_str_ss02", typedef)


def _mocks_ss03(typedef: dict) -> List[str]:
    """產生 SS03 的 Mock 資料"""
    cfg = _load_yaml_or_json(_MOCK_DATA_DIR / "ss03.yaml")
    return _generate_grid_scenario_mocks(cfg, "json_str_ss03", typedef)


_PID_GENERATORS = {
    "SS01": _mocks_ss01,
    "SS01A": _mocks_ss01,
    "SS02": _mocks_ss02,
    "SS03": _mocks_ss03,
}


def generate_mock_data(pid: str, typedef: dict) -> List[Any]:
    """產生對應 pid 遊戲的 Mock 資料"""
    mock_list = _build_prepend_list(pid)
    generator = _PID_GENERATORS.get(pid)
    if generator:
        mock_list.extend(generator(typedef))
    else:
        print(f"[mock_data] pid {pid!r} not in _PID_GENERATORS, no mock generated")
    return mock_list
