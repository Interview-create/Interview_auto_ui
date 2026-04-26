import json
import logging
from pathlib import Path
from typing import Optional

_logger = logging.getLogger(__name__)


def load_runtime_config() -> dict:
    """載入 config.json 並正規化 username / viewport 為 list。

    - username: str → [str]，list 維持不變
    - viewport: null → [None]，單一 dict → [dict]，list 維持不變
    - game_configs URL 保留 {username} 模板，由 main() 依任務展開
    """
    config_path = Path(__file__).resolve().parent.parent / "config.json"
    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)

    # 正規化 username → list[str]
    username = config.get("username", "")
    if isinstance(username, str):
        config["username"] = [username] if username else [""]
    elif isinstance(username, list):
        if len(username) == 0:
            config["username"] = [""]
    else:
        config["username"] = [""]

    if not config["username"] or not config["username"][0]:
        _logger.warning("'username' 未設定，game_configs URL 中的 {username} 將展開為空字串")

    # 正規化 viewport → list[dict | None]
    viewport = config.get("viewport")
    if viewport is None:
        config["viewport"] = [None]
    elif isinstance(viewport, dict):
        config["viewport"] = [viewport]
    elif isinstance(viewport, list) and len(viewport) == 0:
        config["viewport"] = [None]
    # 已是非空 list 則維持原樣

    return config


def build_context_options(
    devices: dict,
    viewport: Optional[dict],
    device_name: Optional[str],
    record_video_dir: Optional[str] = None,
) -> dict:
    """根據設定建立 Playwright new_context() 所需的參數字典。

    優先順序：device > viewport > 空字典（使用 Playwright 預設值）。
    若兩者都有，device 優先並印出警告。
    若 record_video_dir 有傳入，加入錄影相關設定，尺寸從 viewport 推斷。
    """
    if device_name:
        if viewport:
            _logger.warning(
                "device 與 viewport 同時設定，忽略 viewport，使用 device: %s", device_name
            )
        if device_name not in devices:
            raise ValueError(
                f"未知的 device: '{device_name}'，請確認 Playwright 支援的裝置名稱"
            )
        options = dict(devices[device_name])
    elif viewport:
        options = {"viewport": viewport}
    else:
        options = {}

    if record_video_dir is not None:
        options["record_video_dir"] = record_video_dir
        vp = options.get("viewport")
        if isinstance(vp, dict) and vp.get("width") and vp.get("height"):
            options["record_video_size"] = {"width": vp["width"], "height": vp["height"]}

    return options
