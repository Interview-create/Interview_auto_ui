"""Unit tests for config/runtime.py — build_context_options()"""
import logging
import pytest
from config.runtime import build_context_options

# 模擬 playwright p.devices，只需是個 dict
FAKE_DEVICES = {
    "iPhone 13": {
        "viewport": {"width": 390, "height": 844},
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)",
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": 3,
    }
}


def test_device_only_returns_device_settings():
    result = build_context_options(FAKE_DEVICES, viewport=None, device_name="iPhone 13")
    assert result["is_mobile"] is True
    assert result["viewport"] == {"width": 390, "height": 844}


def test_viewport_only_returns_viewport_dict():
    vp = {"width": 1280, "height": 720}
    result = build_context_options({}, viewport=vp, device_name=None)
    assert result == {"viewport": {"width": 1280, "height": 720}}


def test_both_none_returns_empty_dict():
    result = build_context_options({}, viewport=None, device_name=None)
    assert result == {}


def test_device_takes_priority_over_viewport(caplog):
    vp = {"width": 1280, "height": 720}
    with caplog.at_level(logging.WARNING, logger="config.runtime"):
        result = build_context_options(FAKE_DEVICES, viewport=vp, device_name="iPhone 13")
    assert result["is_mobile"] is True
    assert "忽略 viewport" in caplog.text


def test_unknown_device_raises_value_error():
    with pytest.raises(ValueError):
        build_context_options(FAKE_DEVICES, viewport=None, device_name="Unknown Device XYZ")
