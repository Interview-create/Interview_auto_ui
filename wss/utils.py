import logging
from datetime import datetime
from typing import Any

_logger = logging.getLogger(__name__)


def now_iso() -> str:
    # 取得目前時間的 ISO 格式字串，方便寫入 log
    return datetime.now().isoformat()


def safe_ws_url(ws: Any) -> str:
    # 從 websocket 物件取出 url（避免屬性不存在而報錯）
    return str(getattr(ws, "url", ""))
