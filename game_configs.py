# 欄位 name 採用 server 端 protobuf 原始命名，部分為 camelCase（如 GridStop、totalPayout、triggerCount）。
# 這是刻意保留以對應真實協定，非命名錯誤。

SS01_TYPEDEF = {
    "1": {"type": "int", "name": "spin_id"},
    "2": {"type": "int", "name": "spin_type"},
    "3": {
        "type": "message",
        "name": "grid",
        "message_typedef": {
            "1": {"type": "int", "name": "position"},
            "2": {"type": "int", "name": "code"},
        },
    },
    "4": {
        "type": "message",
        "name": "pay_lines",
        "message_typedef": {
            "1": {"type": "int", "name": "id"},
            "2": {"type": "packed_int", "name": "positions"},
            "3": {"type": "packed_int", "name": "hit_positions"},
            "4": {"type": "double", "name": "payout"},
        },
    },
    "5": {
        "type": "message",
        "name": "scatter",
        "message_typedef": {
            "1": {"type": "int", "name": "count"},
            "2": {"type": "double", "name": "payout"},
            "3": {"type": "int", "name": "triggered"},
        },
    },
    "6": {"type": "double", "name": "total_payout"},
    "7": {"type": "double", "name": "bet"},
}

MONEY_TYPEDEF = {
    "1": {"type": "bytes", "name": "value"},
    "2": {"type": "bytes", "name": "currency_code"},
    "3": {"type": "int", "name": "display_scale"},
    "4": {"type": "int", "name": "compact_notation"},
}

# SS02/SS03: BalanceChanged { Money balance = 1; }
BALANCE_CHANGED_TYPEDEF = {
    "1": {"type": "message", "name": "balance", "message_typedef": MONEY_TYPEDEF},
}

# SS01: BalanceChanged { double balance = 1; }
BALANCE_CHANGED_SS01_TYPEDEF = {
    "1": {"type": "double", "name": "balance"},
}

FREE_SPIN_TRIGGERED_MONEY_TYPEDEF = {
    "1": {"type": "int", "name": "triggered_spin_id"},
    "2": {"type": "int", "name": "triggered_type"},
    "3": {"type": "string", "name": "tokens", "rule": "repeated"},
    "4": {"type": "message", "name": "bet", "message_typedef": MONEY_TYPEDEF},
}

FREE_SPIN_REQUEST_TYPEDEF = {
    "1": {"type": "string", "name": "token"},
}

SS02_TYPEDEF = {
    "1": {"type": "int", "name": "spin_id"},
    "2": {"type": "int", "name": "spin_type"},
    "3": {
        "type": "message",
        "name": "scenarios",
        "message_typedef": {
            "1": {"type": "int", "name": "id"},
            "2": {
                "type": "message",
                "name": "grid",
                "message_typedef": {
                    "1": {"type": "int", "name": "position"},
                    "2": {"type": "int", "name": "code"},
                },
            },
            "3": {
                "type": "message",
                "name": "win_symbol",
                "message_typedef": {
                    "1": {"type": "int", "name": "code"},
                    "2": {"type": "int", "name": "count"},
                    "3": {
                        "type": "message",
                        "name": "payout",
                        "message_typedef": MONEY_TYPEDEF,
                    },
                },
            },
        },
    },
    "4": {
        "type": "message",
        "name": "multiplier",
        "message_typedef": {
            "1": {"type": "int", "name": "code"},
            "2": {"type": "double", "name": "value"},
        },
    },
    "5": {
        "type": "message",
        "name": "scatter",
        "message_typedef": {
            "1": {"type": "int", "name": "count"},
            "2": {"type": "int", "name": "triggered"},
        },
    },
    "6": {"type": "message", "name": "total_payout", "message_typedef": MONEY_TYPEDEF},
    "7": {"type": "message", "name": "bet", "message_typedef": MONEY_TYPEDEF},
}

SS03_TYPEDEF = {
    "1": {"type": "int", "name": "spin_id"},
    "2": {"type": "int", "name": "spin_type"},
    "3": {"type": "packed_int", "name": "GridStop"},
    "4": {
        "type": "message",
        "name": "scenarios",
        "message_typedef": {
            "1": {"type": "int", "name": "id"},
            "2": {
                "type": "message",
                "name": "grid",
                "message_typedef": {
                    "1": {"type": "int", "name": "position"},
                    "2": {"type": "int", "name": "code"},
                },
            },
            "3": {
                "type": "message",
                "name": "win_symbol",
                "message_typedef": {
                    "1": {"type": "int", "name": "code"},
                    "2": {"type": "int", "name": "column"},
                    "3": {"type": "int", "name": "ways"},
                    "4": {"type": "int", "name": "multiplier"},
                    "5": {
                        "type": "message",
                        "name": "payout",
                        "message_typedef": MONEY_TYPEDEF,
                    },
                    "6": {
                        "type": "message",
                        "name": "totalPayout",
                        "message_typedef": MONEY_TYPEDEF,
                    },
                },
            },
        },
    },
    "5": {
        "type": "message",
        "name": "scatter",
        "message_typedef": {
            "1": {"type": "int", "name": "code"},
            "2": {"type": "int", "name": "count"},
            "3": {"type": "int", "name": "triggered"},
            "4": {"type": "int", "name": "triggerCount"},
        },
    },
    "6": {"type": "message", "name": "total_payout", "message_typedef": MONEY_TYPEDEF},
    "7": {"type": "message", "name": "bet", "message_typedef": MONEY_TYPEDEF},
}

TYPEDEFS = {
    "SS01": SS01_TYPEDEF,
    "SS01A": SS01_TYPEDEF,
    "SS02": SS02_TYPEDEF,
    "SS03": SS03_TYPEDEF,
}


def get_event_typedefs(pid: str) -> dict:
    """依 PID 回傳對應的 event-level typedef 覆寫字典。"""
    balance_typedef = (
        BALANCE_CHANGED_SS01_TYPEDEF if pid in ("SS01", "SS01A") else BALANCE_CHANGED_TYPEDEF
    )
    return {
        "server:balance:changed": balance_typedef,
        "server:free_spin:triggered": FREE_SPIN_TRIGGERED_MONEY_TYPEDEF,
        "client:free_spin": FREE_SPIN_REQUEST_TYPEDEF,
    }
