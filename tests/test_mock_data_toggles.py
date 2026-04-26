"""Unit tests for mock_data.py — mock_list_append_enabled 開關行為。

驗證以下情境：
- mock_list_append_enabled=True 時，mock_list_append 內容被加入 mock list
- mock_list_append_enabled=False 時，mock_list_append 內容不被加入 mock list
- mock_list_append_enabled 未設定時，預設行為等同 True（向後相容）
- mock_list_append 為空 list 時，不論開關為何，mock list 不受影響
"""
from unittest.mock import patch


# ---------------------------------------------------------------------------
# 輔助：以受控 config 呼叫 generate_mock_data
# ---------------------------------------------------------------------------

# 任何不在 generate_mock_data pid 分支（SS01/SS01A/SS02/SS03）中的字串皆可，
# 這讓回傳的 list 只反映 mock_list_append 的貢獻，不受 YAML mock 資料影響。
_UNMATCHED_PID = "__PID_NOT_IN_ANY_BRANCH__"


def _run_generate(config: dict) -> list:
    """以指定 config 呼叫 generate_mock_data，並回傳 mock list。

    pid 固定為 sentinel 值，避免走入任何 pid 分支，回傳內容僅反映 mock_list_append 行為。
    """
    with patch("mock_data.load_runtime_config", return_value=config):
        from mock_data import generate_mock_data

        return generate_mock_data(pid=_UNMATCHED_PID, typedef={})


# ---------------------------------------------------------------------------
# mock_list_append_enabled=True（預設）— 內容應被加入
# ---------------------------------------------------------------------------

class TestMockListAppendEnabled:

    def test_string_append_is_added_to_mock_list(self):
        """mock_list_append 為單一字串時，該字串應出現在回傳 list 中。"""
        config = {
            "mock_list_append_enabled": True,
            "game_configs": {
                _UNMATCHED_PID: {"mock_list_append": "SINGLE_MOCK_ITEM"},
            },
        }

        result = _run_generate(config)

        assert "SINGLE_MOCK_ITEM" in result

    def test_list_append_is_expanded_into_mock_list(self):
        """mock_list_append 為 list 時，每個元素都應出現在回傳 list 中。"""
        config = {
            "mock_list_append_enabled": True,
            "game_configs": {
                _UNMATCHED_PID: {"mock_list_append": ["ITEM_A", "ITEM_B", "ITEM_C"]},
            },
        }

        result = _run_generate(config)

        assert "ITEM_A" in result
        assert "ITEM_B" in result
        assert "ITEM_C" in result

    def test_list_append_preserves_order(self):
        """list 展開後順序應與原始 mock_list_append 一致。"""
        items = ["FIRST", "SECOND", "THIRD"]
        config = {
            "mock_list_append_enabled": True,
            "game_configs": {
                _UNMATCHED_PID: {"mock_list_append": items},
            },
        }

        result = _run_generate(config)

        assert result[:3] == items


# ---------------------------------------------------------------------------
# mock_list_append_enabled=False — 內容不應被加入
# ---------------------------------------------------------------------------

class TestMockListAppendDisabled:

    def test_string_append_is_not_added_when_disabled(self):
        """mock_list_append_enabled=False 時，字串型 append 不應出現在 list 中。"""
        config = {
            "mock_list_append_enabled": False,
            "game_configs": {
                _UNMATCHED_PID: {"mock_list_append": "SHOULD_NOT_APPEAR"},
            },
        }

        result = _run_generate(config)

        assert "SHOULD_NOT_APPEAR" not in result

    def test_list_append_is_not_added_when_disabled(self):
        """mock_list_append_enabled=False 時，list 型 append 的每個元素都不應出現。"""
        config = {
            "mock_list_append_enabled": False,
            "game_configs": {
                _UNMATCHED_PID: {"mock_list_append": ["BLOCKED_A", "BLOCKED_B"]},
            },
        }

        result = _run_generate(config)

        assert "BLOCKED_A" not in result
        assert "BLOCKED_B" not in result

    def test_disabled_returns_empty_list_when_pid_unmatched(self):
        """停用開關且 pid 未匹配任何分支時，回傳應為空 list。"""
        config = {
            "mock_list_append_enabled": False,
            "game_configs": {
                _UNMATCHED_PID: {"mock_list_append": "ITEM"},
            },
        }

        result = _run_generate(config)

        assert result == []


# ---------------------------------------------------------------------------
# mock_list_append_enabled 未設定 — 預設行為等同 True
# ---------------------------------------------------------------------------

class TestMockListAppendEnabledDefault:

    def test_missing_flag_defaults_to_enabled_for_backward_compat(self):
        """config 中未包含 mock_list_append_enabled 時，append 應照常加入 list。"""
        config = {
            "game_configs": {
                _UNMATCHED_PID: {"mock_list_append": "DEFAULT_BEHAVIOR_ITEM"},
            },
        }

        result = _run_generate(config)

        assert "DEFAULT_BEHAVIOR_ITEM" in result

    def test_missing_flag_still_expands_list_append(self):
        """config 未含開關、append 為 list 時，所有元素應被展開加入。"""
        config = {
            "game_configs": {
                _UNMATCHED_PID: {"mock_list_append": ["COMPAT_A", "COMPAT_B"]},
            },
        }

        result = _run_generate(config)

        assert "COMPAT_A" in result
        assert "COMPAT_B" in result


# ---------------------------------------------------------------------------
# mock_list_append 為空 list — 不論開關為何，mock list 不受影響
# ---------------------------------------------------------------------------

class TestMockListAppendEmpty:

    def test_empty_append_with_flag_enabled_yields_empty_list(self):
        """mock_list_append 為 [] 時，開關為 True，mock list 應維持空（pid 未匹配）。"""
        config = {
            "mock_list_append_enabled": True,
            "game_configs": {
                _UNMATCHED_PID: {"mock_list_append": []},
            },
        }

        result = _run_generate(config)

        assert result == []

    def test_empty_append_with_flag_disabled_yields_empty_list(self):
        """mock_list_append 為 [] 時，開關為 False，mock list 應維持空（pid 未匹配）。"""
        config = {
            "mock_list_append_enabled": False,
            "game_configs": {
                _UNMATCHED_PID: {"mock_list_append": []},
            },
        }

        result = _run_generate(config)

        assert result == []

    def test_missing_append_key_yields_empty_list(self):
        """config 中完全未設定 mock_list_append 時，mock list 應維持空（pid 未匹配）。"""
        config = {}

        result = _run_generate(config)

        assert result == []
