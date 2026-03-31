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
            "2": {
                "type": "bytes",
                "name": "positions",
            },  # 維持 bytes 確保相容自訂的 hex mock
            "3": {"type": "bytes", "name": "hit_positions"},  # 維持 bytes
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

FREE_SPIN_TRIGGERED_MONEY_TYPEDEF = {
    "1": {"type": "int", "name": "triggered_spin_id"},
    "2": {"type": "int", "name": "triggered_type"},
    "3": {"type": "bytes", "name": "tokens"},
    "4": {"type": "message", "name": "bet", "message_typedef": MONEY_TYPEDEF},
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
    "3": {"type": "int", "name": "GridStop"},
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

# --- Game Configurations ---
GAME_CONFIGS = {
    "SS01": {
        "url": "https:/SS01/ss01?platform=1&username=USD1&pid=KKK&gameid=ABC&session=USD1&isMobile=0",
        "typedef": SS01_TYPEDEF,
    },
    "SS01A": {
        "url": "",
        "typedef": SS01_TYPEDEF,
    },
    "SS02": {
        "url": "https://SS02.com/ss02?platform=1&username=USD1&pid=KKK&gameid=ABC&session=USD1&isMobile=0",  # TODO: 替換為實際 SS02 網址
        "typedef": SS02_TYPEDEF,
    },
    "SS03": {
        "url": "https://SS03.com/ss03?platform=1&username=USD1&pid=KKK&gameid=ABC&session=USD1&isMobile=0",  # TODO: 替換為實際 SS03 網址
        "typedef": SS03_TYPEDEF,
    },
}
