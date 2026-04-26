#!/usr/bin/env python3
"""
根据 ss01_protobuf.cpp 定义解析 SpinRet 消息
用法: python parse_spinret.py <base64_string>
"""

import base64
import json
import struct
import sys

import blackboxprotobuf


def parse_spinret_b64(b64_str: str) -> dict:
    """解析 SpinRet protobuf 消息"""
    decoded_bytes = base64.b64decode(b64_str)
    msg, _ = blackboxprotobuf.decode_message(decoded_bytes)

    spin_id = msg.get("1", 0)
    spin_type = msg.get("2", 0)
    grid_cells = msg.get("3", [])
    pay_lines = msg.get("4", [])
    scatter = msg.get("5", {})
    total_payout_bits = msg.get("6", 0)

    # 将 fixed64 位表示转换为 double
    total_payout = struct.unpack(">d", total_payout_bits.to_bytes(8, "big"))[0]

    result = {
        "spin_id": spin_id,
        "spin_type": spin_type,
        "spin_type_name": (
            ["base", "free", "mock"][spin_type] if spin_type < 3 else "unknown"
        ),
        "total_payout": total_payout,
        "grid": [],
        "pay_lines": [],
        "scatter": None,
    }

    # 解析盤面
    for cell in grid_cells:
        result["grid"].append(
            {
                "position": cell.get("1"),
                "code": cell.get("2"),
            }
        )

    # 解析支付線
    for line in pay_lines:
        line_id = line.get("1")
        nested_field2 = line.get("2", {})
        multiplier_bits = nested_field2.get("2", 0)
        multiplier = struct.unpack(">f", multiplier_bits.to_bytes(4, "big"))[0]
        payout_bits = line.get("4", 0)
        payout = struct.unpack(">d", payout_bits.to_bytes(8, "big"))[0]

        result["pay_lines"].append(
            {
                "id": line_id,
                "multiplier": multiplier,
                "payout": payout,
            }
        )

    # 解析散點符號
    if scatter:
        result["scatter"] = {
            "count": scatter.get("1"),
            "payout": scatter.get("2"),
            "triggered": scatter.get("3"),
        }

    return result


def print_spinret(result: dict) -> None:
    """打印解析结果"""
    print("\n" + "=" * 60)
    print("SpinRet 消息解析")
    print("=" * 60)

    print("\n【基本信息】")
    print(f"  spin_id: {result['spin_id']} (0x{result['spin_id']:016x})")
    print(f"  spin_type: {result['spin_type']} ({result['spin_type_name']})")
    print(f"  total_payout: {result['total_payout']}")

    print(f"\n【盤面格子】({len(result['grid'])} 個)")
    for cell in result["grid"]:
        print(f"  位置 {cell['position']:2d} → 符號 {cell['code']}")

    print(f"\n【支付線】({len(result['pay_lines'])} 條)")
    for line in result["pay_lines"]:
        print(
            f"  線 {line['id']:2d}: 倍數 {line['multiplier']:8.2f} × 獲利 {line['payout']:6.2f}"
        )

    if result["scatter"]:
        print("\n【散佈符號】")
        print(f"  計數: {result['scatter']['count']}")
        print(f"  獲利: {result['scatter']['payout']}")
        print(f"  已觸發: {result['scatter']['triggered']}")

    print("\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python parse_spinret.py <base64_string>")
        sys.exit(1)

    b64_str = sys.argv[1]
    result = parse_spinret_b64(b64_str)
    print_spinret(result)
    print("【JSON 格式】")
    print(json.dumps(result, indent=2, ensure_ascii=False))
