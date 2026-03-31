import base64
import copy
import json
from typing import Any, List

import blackboxprotobuf

from configs import FREE_SPIN_TRIGGERED_MONEY_TYPEDEF


def encode_to_base64(data: dict, typedef: dict) -> str:
    # 1. 由於原本 decode 後無法轉成 utf-8 的 bytes 會被轉為 hex 字串
    # 以及部分跳脫字元會變成 unicode，我們需要在編碼前將它們還原為 Python bytes
    for item in data.get("4", []):
        if "2" in item and isinstance(item["2"], str):
            # 將 \u000b 等字串還原為原本的 bytes
            item["2"] = item["2"].encode("latin1")
        if "3" in item and isinstance(item["3"], str):
            # 將 hex 字串還原為原本的 bytes
            item["3"] = bytes.fromhex(item["3"])

    # 2. 定義此 JSON 結構對應的 Protobuf Typedef (已移至 GAME_CONFIGS 字典統一管理)
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
        data = copy.deepcopy(base_data)
        for item in data.get(grid_key, []):
            item[code_key] = code
        results.append(encode_to_base64(data, typedef))
    return results


def generate_mock_data(pid: str, typedef: dict) -> List[Any]:
    """產生對應 pid 遊戲的 Mock 資料"""
    mock_list = []
    if pid in ["SS01", "SS01A"]:
        json_str1 = """{
            "1": 159100023551139840,
            "2": 0,
            "3": [
                {"1": 11, "2": 1}, {"1": 21, "2": 1}, {"1": 31, "2": 1},
                {"1": 12, "2": 1}, {"1": 22, "2": 1}, {"1": 32, "2": 1},
                {"1": 13, "2": 1}, {"1": 23, "2": 1}, {"1": 33, "2": 1},
                {"1": 14, "2": 1}, {"1": 24, "2": 1}, {"1": 34, "2": 1},
                {"1": 15, "2": 1}, {"1": 25, "2": 1}, {"1": 35, "2": 1}
            ],
            "5": {},
            "7": 4602678819172646912
        }"""
        base_data1 = json.loads(json_str1)
        symbol_codes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 101, 102, 105, 110]
        mock_list.extend(
            generate_mocks_by_symbol_codes(base_data1, symbol_codes, typedef)
        )

        json_str2 = """{
            "1": 159100023551139840,
            "2": 0,
            "3": [
                {"1": 11, "2": 1}, {"1": 21, "2": 1}, {"1": 31, "2": 1},
                {"1": 12, "2": 1}, {"1": 22, "2": 1}, {"1": 32, "2": 1},
                {"1": 13, "2": 1}, {"1": 23, "2": 1}, {"1": 33, "2": 1},
                {"1": 14, "2": 1}, {"1": 24, "2": 1}, {"1": 34, "2": 1},
                {"1": 15, "2": 1}, {"1": 25, "2": 1}, {"1": 35, "2": 1}
            ],
            "4": [],
            "5": {},
            "6": 4603579539098121011,
            "7": 4602678819172646912
        }"""
        pay_line = [
            [
                {
                    "1": 1,
                    "2": "\u000b\u0016\r\u0018\u000f",
                    "3": "0b160dffffffffffffffffff01ffffffffffffffffff01",
                    "4": 4600877379321698714,
                },
                {
                    "1": 2,
                    "2": "\u000b\u0016\r\u0018\u000f",
                    "3": "0b160dffffffffffffffffff01ffffffffffffffffff01",
                    "4": 4600877379321698714,
                },
                {
                    "1": 3,
                    "2": "\u000b\u0016\r\u0018\u000f",
                    "3": "0b160dffffffffffffffffff01ffffffffffffffffff01",
                    "4": 4600877379321698714,
                },
                {
                    "1": 4,
                    "2": "\u000b\u0016\r\u0018\u000f",
                    "3": "0b160dffffffffffffffffff01ffffffffffffffffff01",
                    "4": 4600877379321698714,
                },
                {
                    "1": 5,
                    "2": "\u000b\u0016\r\u0018\u000f",
                    "3": "0b160dffffffffffffffffff01ffffffffffffffffff01",
                    "4": 4600877379321698714,
                },
                {
                    "1": 6,
                    "2": "\u000b\u0016\r\u0018\u000f",
                    "3": "0b160dffffffffffffffffff01ffffffffffffffffff01",
                    "4": 4600877379321698714,
                },
                {
                    "1": 7,
                    "2": "\u000b\u0016\r\u0018\u000f",
                    "3": "0b160dffffffffffffffffff01ffffffffffffffffff01",
                    "4": 4600877379321698714,
                },
                {
                    "1": 8,
                    "2": "\u000b\u0016\r\u0018\u000f",
                    "3": "0b160dffffffffffffffffff01ffffffffffffffffff01",
                    "4": 4600877379321698714,
                },
                {
                    "1": 9,
                    "2": "\u000b\u0016\r\u0018\u000f",
                    "3": "0b160dffffffffffffffffff01ffffffffffffffffff01",
                    "4": 4600877379321698714,
                },
                {
                    "1": 10,
                    "2": "\u000b\u0016\r\u0018\u000f",
                    "3": "0b160dffffffffffffffffff01ffffffffffffffffff01",
                    "4": 4600877379321698714,
                },
                {
                    "1": 11,
                    "2": "\u000b\u0016\r\u0018\u000f",
                    "3": "0b160dffffffffffffffffff01ffffffffffffffffff01",
                    "4": 4600877379321698714,
                },
                {
                    "1": 12,
                    "2": "\u000b\u0016\r\u0018\u000f",
                    "3": "0b160dffffffffffffffffff01ffffffffffffffffff01",
                    "4": 4600877379321698714,
                },
                {
                    "1": 13,
                    "2": "\u000b\u0016\r\u0018\u000f",
                    "3": "0b160dffffffffffffffffff01ffffffffffffffffff01",
                    "4": 4600877379321698714,
                },
                {
                    "1": 14,
                    "2": "\u000b\u0016\r\u0018\u000f",
                    "3": "0b160dffffffffffffffffff01ffffffffffffffffff01",
                    "4": 4600877379321698714,
                },
            ]
        ]
        base_data2 = json.loads(json_str2)
        for i in pay_line:
            data = copy.deepcopy(base_data2)
            data["4"] = i
            mock_list.append(encode_to_base64(data, typedef))

    elif pid == "SS02":
        # SS02 基礎範例 Mock
        json_str_ss02 = """{
    "spin_id": 161516243523497985,
    "scenarios": [
        {
            "grid": [
                {
                    "position": 11,
                    "code": 1
                },
                {
                    "position": 12,
                    "code": 7
                },
                {
                    "position": 13,
                    "code": 1
                },
                {
                    "position": 14,
                    "code": 8
                },
                {
                    "position": 15,
                    "code": 4
                },
                {
                    "position": 16,
                    "code": 3
                },
                {
                    "position": 21,
                    "code": 3
                },
                {
                    "position": 22,
                    "code": 1
                },
                {
                    "position": 23,
                    "code": 2
                },
                {
                    "position": 24,
                    "code": 4
                },
                {
                    "position": 25,
                    "code": 7
                },
                {
                    "position": 26,
                    "code": 6
                },
                {
                    "position": 31,
                    "code": 8
                },
                {
                    "position": 32,
                    "code": 7
                },
                {
                    "position": 33,
                    "code": 8
                },
                {
                    "position": 34,
                    "code": 5
                },
                {
                    "position": 35,
                    "code": 5
                },
                {
                    "position": 36,
                    "code": 7
                },
                {
                    "position": 41,
                    "code": 8
                },
                {
                    "position": 42,
                    "code": 4
                },
                {
                    "position": 43,
                    "code": 6
                },
                {
                    "position": 44,
                    "code": 7
                },
                {
                    "position": 45,
                    "code": 7
                },
                {
                    "position": 46,
                    "code": 7
                },
                {
                    "position": 51,
                    "code": 6
                },
                {
                    "position": 52,
                    "code": 3
                },
                {
                    "position": 53,
                    "code": 3
                },
                {
                    "position": 54,
                    "code": 7
                },
                {
                    "position": 55,
                    "code": 8
                },
                {
                    "position": 56,
                    "code": 3
                }
            ],
            "win_symbol": {
                "code": 7,
                "count": 8,
                "payout": {
                    "value": "0.200",
                    "currency_code": "USD",
                    "display_scale": 2
                }
            }
        },
        {
            "id": 1,
            "grid": [
                {
                    "position": 11,
                    "code": 1
                },
                {
                    "position": 12,
                    "code": 5
                },
                {
                    "position": 13,
                    "code": 1
                },
                {
                    "position": 14,
                    "code": 4
                },
                {
                    "position": 15,
                    "code": 7
                },
                {
                    "position": 16,
                    "code": 7
                },
                {
                    "position": 21,
                    "code": 3
                },
                {
                    "position": 22,
                    "code": 8
                },
                {
                    "position": 23,
                    "code": 2
                },
                {
                    "position": 24,
                    "code": 8
                },
                {
                    "position": 25,
                    "code": 6
                },
                {
                    "position": 26,
                    "code": 4
                },
                {
                    "position": 31,
                    "code": 8
                },
                {
                    "position": 32,
                    "code": 1
                },
                {
                    "position": 33,
                    "code": 8
                },
                {
                    "position": 34,
                    "code": 8
                },
                {
                    "position": 35,
                    "code": 4
                },
                {
                    "position": 36,
                    "code": 3
                },
                {
                    "position": 41,
                    "code": 8
                },
                {
                    "position": 42,
                    "code": 4
                },
                {
                    "position": 43,
                    "code": 6
                },
                {
                    "position": 44,
                    "code": 4
                },
                {
                    "position": 45,
                    "code": 5
                },
                {
                    "position": 46,
                    "code": 6
                },
                {
                    "position": 51,
                    "code": 6
                },
                {
                    "position": 52,
                    "code": 3
                },
                {
                    "position": 53,
                    "code": 3
                },
                {
                    "position": 54,
                    "code": 5
                },
                {
                    "position": 55,
                    "code": 8
                },
                {
                    "position": 56,
                    "code": 3
                }
            ]
        }
    ],
    "scatter": {},
    "total_payout": {
        "value": "0.200",
        "currency_code": "USD",
        "display_scale": 2
    },
    "bet": {
        "value": "0.5",
        "currency_code": "USD",
        "display_scale": 2
    }
}"""
        base_data = json.loads(json_str_ss02)

        # 第一筆：Base Spin，盤面出現 3 個 Scatter 以觸發 Free Spin
        trigger_data = copy.deepcopy(base_data)
        trigger_data["scatter"] = {"count": 3, "triggered": 1}

        # 準備 server:free_spin:triggered 推播封包
        fs_triggered_data = {
            "triggered_spin_id": trigger_data["spin_id"],
            "triggered_type": 0,  # 0 代表 Scatter 觸發
            "bet": trigger_data["bet"],
        }
        fs_triggered_b64 = encode_to_base64(
            fs_triggered_data, FREE_SPIN_TRIGGERED_MONEY_TYPEDEF
        )
        fs_triggered_msg = f'42["server:free_spin:triggered", "{fs_triggered_b64}"]'

        # 將 SpinRet (當作 ACK) 與 free_spin:triggered (當作 Push) 包裝在同一個 List 一起回傳
        mock_list.append([encode_to_base64(trigger_data, typedef), fs_triggered_msg])

        # 第二筆：Free Spin，設定 spin_type=1，並加入免費旋轉特有的倍數
        free_spin_data = copy.deepcopy(base_data)
        free_spin_data["spin_id"] += 1
        free_spin_data["spin_type"] = 1
        free_spin_data["scatter"] = {"count": 0, "triggered": 0}
        free_spin_data["multiplier"] = [{"code": 1, "value": 3.0}]
        mock_list.append(encode_to_base64(free_spin_data, typedef))

    elif pid == "SS03":
        # SS03 基礎範例 Mock
        json_str_ss03 = """{
    "spin_id": 161516248528019456,
    "spin_type": 0,
    "GridStop": [
        1,
        1,
        1,
        1,
        1
    ],
    "scenarios": [
        {
            "grid": [
                {
                    "position": 11,
                    "code": 1
                },
                {
                    "position": 21,
                    "code": 5
                },
                {
                    "position": 31,
                    "code": 2
                },
                {
                    "position": 41,
                    "code": 8
                },
                {
                    "position": 51,
                    "code": 6
                },
                {
                    "position": 61,
                    "code": -1
                },
                {
                    "position": 12,
                    "code": 4
                },
                {
                    "position": 22,
                    "code": 1
                },
                {
                    "position": 32,
                    "code": 7
                },
                {
                    "position": 42,
                    "code": 5
                },
                {
                    "position": 52,
                    "code": 2
                },
                {
                    "position": 62,
                    "code": 6
                },
                {
                    "position": 13,
                    "code": 201
                },
                {
                    "position": 23,
                    "code": 6
                },
                {
                    "position": 33,
                    "code": 6
                },
                {
                    "position": 43,
                    "code": 5
                },
                {
                    "position": 53,
                    "code": 7
                },
                {
                    "position": 63,
                    "code": 2
                },
                {
                    "position": 14,
                    "code": 1
                },
                {
                    "position": 24,
                    "code": 7
                },
                {
                    "position": 34,
                    "code": 5
                },
                {
                    "position": 44,
                    "code": 5
                },
                {
                    "position": 54,
                    "code": 5
                },
                {
                    "position": 64,
                    "code": 5
                },
                {
                    "position": 15,
                    "code": 4
                },
                {
                    "position": 25,
                    "code": 4
                },
                {
                    "position": 35,
                    "code": 7
                },
                {
                    "position": 45,
                    "code": 3
                },
                {
                    "position": 55,
                    "code": 7
                },
                {
                    "position": 65,
                    "code": -1
                }
            ],
            "win_symbol": [
                {
                    "code": 2,
                    "column": 3,
                    "ways": 1,
                    "multiplier": 1,
                    "payout": {
                        "value": "0.150",
                        "currency_code": "USD",
                        "display_scale": 2
                    },
                    "totalPayout": {
                        "value": "0.150",
                        "currency_code": "USD",
                        "display_scale": 2
                    }
                },
                {
                    "code": 5,
                    "column": 4,
                    "ways": 4,
                    "multiplier": 1,
                    "payout": {
                        "value": "0.500",
                        "currency_code": "USD",
                        "display_scale": 2
                    },
                    "totalPayout": {
                        "value": "0.500",
                        "currency_code": "USD",
                        "display_scale": 2
                    }
                },
                {
                    "code": 6,
                    "column": 3,
                    "ways": 2,
                    "multiplier": 1,
                    "payout": {
                        "value": "0.100",
                        "currency_code": "USD",
                        "display_scale": 2
                    },
                    "totalPayout": {
                        "value": "0.100",
                        "currency_code": "USD",
                        "display_scale": 2
                    }
                }
            ]
        },
        {
            "id": 1,
            "grid": [
                {
                    "position": 11,
                    "code": 7
                },
                {
                    "position": 21,
                    "code": 1
                },
                {
                    "position": 31,
                    "code": 7
                },
                {
                    "position": 41,
                    "code": 1
                },
                {
                    "position": 51,
                    "code": 8
                },
                {
                    "position": 61,
                    "code": -1
                },
                {
                    "position": 12,
                    "code": 0
                },
                {
                    "position": 22,
                    "code": 6
                },
                {
                    "position": 32,
                    "code": 6
                },
                {
                    "position": 42,
                    "code": 4
                },
                {
                    "position": 52,
                    "code": 1
                },
                {
                    "position": 62,
                    "code": 7
                },
                {
                    "position": 13,
                    "code": 3
                },
                {
                    "position": 23,
                    "code": 0
                },
                {
                    "position": 33,
                    "code": 6
                },
                {
                    "position": 43,
                    "code": 202
                },
                {
                    "position": 53,
                    "code": 201
                },
                {
                    "position": 63,
                    "code": 7
                },
                {
                    "position": 14,
                    "code": 2
                },
                {
                    "position": 24,
                    "code": 1
                },
                {
                    "position": 34,
                    "code": 1
                },
                {
                    "position": 44,
                    "code": 8
                },
                {
                    "position": 54,
                    "code": 1
                },
                {
                    "position": 64,
                    "code": 7
                },
                {
                    "position": 15,
                    "code": 4
                },
                {
                    "position": 25,
                    "code": 4
                },
                {
                    "position": 35,
                    "code": 7
                },
                {
                    "position": 45,
                    "code": 3
                },
                {
                    "position": 55,
                    "code": 7
                },
                {
                    "position": 65,
                    "code": -1
                }
            ],
            "win_symbol": [
                {
                    "code": 1,
                    "column": 4,
                    "ways": 6,
                    "multiplier": 2,
                    "payout": {
                        "value": "3.000",
                        "currency_code": "USD",
                        "display_scale": 2
                    },
                    "totalPayout": {
                        "value": "6.000",
                        "currency_code": "USD",
                        "display_scale": 2
                    }
                },
                {
                    "code": 7,
                    "column": 5,
                    "ways": 4,
                    "multiplier": 2,
                    "payout": {
                        "value": "0.600",
                        "currency_code": "USD",
                        "display_scale": 2
                    },
                    "totalPayout": {
                        "value": "1.200",
                        "currency_code": "USD",
                        "display_scale": 2
                    }
                }
            ]
        },
        {
            "id": 2,
            "grid": [
                {
                    "position": 11,
                    "code": 5
                },
                {
                    "position": 21,
                    "code": 8
                },
                {
                    "position": 31,
                    "code": 4
                },
                {
                    "position": 41,
                    "code": 7
                },
                {
                    "position": 51,
                    "code": 8
                },
                {
                    "position": 61,
                    "code": -1
                },
                {
                    "position": 12,
                    "code": 0
                },
                {
                    "position": 22,
                    "code": 2
                },
                {
                    "position": 32,
                    "code": 0
                },
                {
                    "position": 42,
                    "code": 6
                },
                {
                    "position": 52,
                    "code": 6
                },
                {
                    "position": 62,
                    "code": 4
                },
                {
                    "position": 13,
                    "code": 1
                },
                {
                    "position": 23,
                    "code": 4
                },
                {
                    "position": 33,
                    "code": 3
                },
                {
                    "position": 43,
                    "code": 0
                },
                {
                    "position": 53,
                    "code": 6
                },
                {
                    "position": 63,
                    "code": 201
                },
                {
                    "position": 14,
                    "code": 105
                },
                {
                    "position": 24,
                    "code": 3
                },
                {
                    "position": 34,
                    "code": 1
                },
                {
                    "position": 44,
                    "code": 6
                },
                {
                    "position": 54,
                    "code": 2
                },
                {
                    "position": 64,
                    "code": 8
                },
                {
                    "position": 15,
                    "code": 3
                },
                {
                    "position": 25,
                    "code": 3
                },
                {
                    "position": 35,
                    "code": 4
                },
                {
                    "position": 45,
                    "code": 4
                },
                {
                    "position": 55,
                    "code": 3
                },
                {
                    "position": 65,
                    "code": -1
                }
            ],
            "win_symbol": [
                {
                    "code": 4,
                    "column": 3,
                    "ways": 1,
                    "multiplier": 3,
                    "payout": {
                        "value": "0.075",
                        "currency_code": "USD",
                        "display_scale": 2
                    },
                    "totalPayout": {
                        "value": "0.225",
                        "currency_code": "USD",
                        "display_scale": 2
                    }
                }
            ]
        },
        {
            "id": 3,
            "grid": [
                {
                    "position": 11,
                    "code": 7
                },
                {
                    "position": 21,
                    "code": 5
                },
                {
                    "position": 31,
                    "code": 8
                },
                {
                    "position": 41,
                    "code": 7
                },
                {
                    "position": 51,
                    "code": 8
                },
                {
                    "position": 61,
                    "code": -1
                },
                {
                    "position": 12,
                    "code": 104
                },
                {
                    "position": 22,
                    "code": 0
                },
                {
                    "position": 32,
                    "code": 2
                },
                {
                    "position": 42,
                    "code": 0
                },
                {
                    "position": 52,
                    "code": 6
                },
                {
                    "position": 62,
                    "code": 6
                },
                {
                    "position": 13,
                    "code": 105
                },
                {
                    "position": 23,
                    "code": 1
                },
                {
                    "position": 33,
                    "code": 3
                },
                {
                    "position": 43,
                    "code": 0
                },
                {
                    "position": 53,
                    "code": 6
                },
                {
                    "position": 63,
                    "code": 201
                },
                {
                    "position": 14,
                    "code": 102
                },
                {
                    "position": 24,
                    "code": 3
                },
                {
                    "position": 34,
                    "code": 1
                },
                {
                    "position": 44,
                    "code": 6
                },
                {
                    "position": 54,
                    "code": 2
                },
                {
                    "position": 64,
                    "code": 8
                },
                {
                    "position": 15,
                    "code": 8
                },
                {
                    "position": 25,
                    "code": 3
                },
                {
                    "position": 35,
                    "code": 4
                },
                {
                    "position": 45,
                    "code": 4
                },
                {
                    "position": 55,
                    "code": 3
                },
                {
                    "position": 65,
                    "code": -1
                }
            ]
        }
    ],
    "scatter": {
        "code": -1
    },
    "total_payout": {
        "value": "8.175",
        "currency_code": "USD",
        "display_scale": 2
    },
    "bet": {
        "value": "0.5",
        "currency_code": "USD",
        "display_scale": 2
    }
}"""
        data = json.loads(json_str_ss03)
        mock_list.append(encode_to_base64(data, typedef))

    return mock_list
