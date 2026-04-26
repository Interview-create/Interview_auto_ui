"""
capture_navigation.py

自動截圖並用 Claude Vision 分析 Unity Canvas 遊戲的可點擊元素，
遞迴建立導航樹並儲存截圖與路徑文字記錄。

執行方式：
  python capture_navigation.py --pid SS01A
  python capture_navigation.py --pid SS01A --url "https://..." --max-depth 2
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
import cv2
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 模組常數
# ---------------------------------------------------------------------------

PIXEL_NOISE_THRESHOLD = 10  # 灰階值差異低於此值視為噪點，容忍抗鋸齒與壓縮 artifact
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="自動截圖並以 Claude Vision 建立 Unity Canvas 遊戲導航樹"
    )
    parser.add_argument("--pid", required=True, help="遊戲 PID，如 SS01A")
    parser.add_argument("--url", default=None, help="覆蓋 config.json 的 URL")
    parser.add_argument("--max-depth", type=int, default=3, help="最大遞迴深度")
    parser.add_argument(
        "--stable-threshold",
        type=float,
        default=0.01,
        help="像素差分閾值（1% 表示 1%% 的像素發生變化視為不穩定）",
    )
    parser.add_argument(
        "--stable-seconds",
        type=int,
        default=2,
        help="連續 N 次截圖穩定確認",
    )
    parser.add_argument(
        "--max-elements",
        type=int,
        default=5,
        help="每層最多探索幾個元素",
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="不重載頁面，只探索一層",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="半自動模式：截圖後等待 Claude 寫入 click_targets.json 再點擊",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# 資料結構
# ---------------------------------------------------------------------------

@dataclass
class ClickableElement:
    name: str
    x: int
    y: int
    width: int
    height: int
    confidence: float = 1.0


@dataclass
class NavNode:
    node_id: str          # 如 "A.1"
    path: str             # 如 "開始遊戲>設定"
    x: int
    y: int
    screenshot_path: str  # 相對路徑，如 "sample/SS01A/nav_001.png"
    depth: int
    parent_path: str


# ---------------------------------------------------------------------------
# Pixel diff helpers
# ---------------------------------------------------------------------------

def compute_pixel_diff_ratio(img_bytes_a: bytes, img_bytes_b: bytes) -> float:
    """比較兩張截圖的像素差異比例（0.0 ~ 1.0）。"""
    arr_a = np.frombuffer(img_bytes_a, dtype=np.uint8)
    arr_b = np.frombuffer(img_bytes_b, dtype=np.uint8)
    img_a = cv2.imdecode(arr_a, cv2.IMREAD_GRAYSCALE)
    img_b = cv2.imdecode(arr_b, cv2.IMREAD_GRAYSCALE)

    if img_a is None or img_b is None:
        return 1.0

    if img_a.shape != img_b.shape:
        print(f"[diff] 截圖尺寸不一致：{img_a.shape} vs {img_b.shape}，已 resize")
        img_b = cv2.resize(img_b, (img_a.shape[1], img_a.shape[0]))

    diff = cv2.absdiff(img_a, img_b)
    changed_pixels = int(np.sum(diff > PIXEL_NOISE_THRESHOLD))
    total_pixels = img_a.size
    return changed_pixels / total_pixels if total_pixels > 0 else 0.0


def _perceptual_hash(screenshot_bytes: bytes) -> str:
    """Average hash：縮放到 16x16 灰階 → 與平均值比較 → hex 字串。"""
    arr = np.frombuffer(screenshot_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return ""
    small = cv2.resize(img, (16, 16), interpolation=cv2.INTER_AREA)
    avg = float(small.mean())
    bits = (small > avg).flatten()
    hash_int = int("".join("1" if b else "0" for b in bits), 2)
    return f"{hash_int:064x}"


# ---------------------------------------------------------------------------
# Claude Vision client
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a UI automation assistant analyzing screenshots of a Unity Canvas game.
Unity Canvas games do NOT use HTML DOM elements — all UI is rendered on a canvas.
Your task is to identify clickable UI elements from the screenshot.

Response format: Return ONLY a valid JSON array. No markdown, no explanation.
Each element must have:
- "name": string, display text or descriptive name
- "x": integer, center X coordinate in pixels
- "y": integer, center Y coordinate in pixels
- "width": integer, estimated element width in pixels
- "height": integer, estimated element height in pixels
- "confidence": float 0.0-1.0

Return [] if no clickable elements are visible.\
"""


class ClaudeVisionClient:
    """同步 anthropic.Anthropic client 包裝，支援 prompt caching。"""

    def __init__(self, model: str = DEFAULT_CLAUDE_MODEL):
        self._client = anthropic.Anthropic()
        self._model = model

    def analyze(self, screenshot_bytes: bytes, nav_path: str) -> list[ClickableElement]:
        """呼叫 Claude Vision 分析截圖，回傳 ClickableElement 列表。"""
        image_data = base64.standard_b64encode(screenshot_bytes).decode("utf-8")
        user_content = [
            {
                "type": "text",
                "text": (
                    f"Current navigation path: {nav_path!r}\n\n"
                    "Please identify all clickable UI elements in this screenshot. "
                    "Include buttons, interactive icons, and menu items. "
                    "Exclude purely decorative elements."
                ),
            },
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_data,
                },
            },
        ]

        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_content}],
        )

        raw_text = response.content[0].text if response.content else "[]"
        return _parse_elements(raw_text)


def _parse_elements(raw_text: str) -> list[ClickableElement]:
    """解析 Claude 回傳的 JSON，容錯處理。"""

    def _build_elements(data: list) -> list[ClickableElement]:
        elements = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                elements.append(
                    ClickableElement(
                        name=str(item.get("name", "unknown")),
                        x=int(item.get("x", 0)),
                        y=int(item.get("y", 0)),
                        width=int(item.get("width", 50)),
                        height=int(item.get("height", 30)),
                        confidence=float(item.get("confidence", 1.0)),
                    )
                )
            except (TypeError, ValueError) as e:
                logger.warning("跳過無效元素 %s：%s", item, e)
        return elements

    # 先嘗試直接解析（Claude 正確回傳純 JSON 時）
    try:
        data = json.loads(raw_text.strip())
        if isinstance(data, list):
            return _build_elements(data)
    except json.JSONDecodeError:
        pass

    # fallback：從文字中以非貪婪方式萃取 JSON array
    match = re.search(r"\[[\s\S]*\]", raw_text)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return _build_elements(data)
        except json.JSONDecodeError as e:
            logger.warning("JSON 解析失敗：%s\n原始文字：%s", e, raw_text[:200])

    return []


# ---------------------------------------------------------------------------
# NavigationExplorer
# ---------------------------------------------------------------------------

class NavigationExplorer:
    def __init__(
        self,
        page,
        pid: str,
        output_dir: Path,
        claude_client: ClaudeVisionClient,
        max_depth: int = 3,
        stable_threshold: float = 0.01,
        stable_poll_interval: float = 1.0,
        stable_consecutive: int = 2,
        click_wait_ms: int = 500,
        max_elements: int = 5,
        no_reload: bool = False,
    ):
        self._page = page
        self._pid = pid
        self._output_dir = output_dir
        self._claude = claude_client
        self._max_depth = max_depth
        self._stable_threshold = stable_threshold
        self._stable_poll_interval = stable_poll_interval
        self._stable_consecutive = stable_consecutive
        self._click_wait_ms = click_wait_ms
        self._max_elements = max_elements
        self._no_reload = no_reload

        self._screenshot_counter = 0
        self._all_nodes: list[NavNode] = []

    async def wait_for_stable(self) -> bytes:
        """每隔 stable_poll_interval 秒截圖，連續 stable_consecutive 次差異 < threshold 則確認穩定。
        超過 30 秒強制返回最後一張截圖。
        """
        max_wait = 30.0
        deadline = time.monotonic() + max_wait
        prev_bytes: Optional[bytes] = await self._page.screenshot(type="png")
        consecutive = 0

        while time.monotonic() < deadline:
            await asyncio.sleep(self._stable_poll_interval)
            current_bytes: bytes = await self._page.screenshot(type="png")
            ratio = compute_pixel_diff_ratio(prev_bytes, current_bytes)
            if ratio < self._stable_threshold:
                consecutive += 1
                if consecutive >= self._stable_consecutive:
                    logger.debug("畫面穩定（連續 %d 次差異 < %.1f%%）", consecutive, self._stable_threshold * 100)
                    return current_bytes
            else:
                consecutive = 0
            prev_bytes = current_bytes

        logger.warning("等待穩定超時（%.0f 秒），強制返回截圖", max_wait)
        return prev_bytes

    async def capture_and_analyze(
        self, screenshot_bytes: bytes, nav_path: str
    ) -> list[ClickableElement]:
        """呼叫 ClaudeVisionClient，回傳 ClickableElement 列表（依 confidence 排序）。"""
        loop = asyncio.get_running_loop()
        elements: list[ClickableElement] = await loop.run_in_executor(
            None, self._claude.analyze, screenshot_bytes, nav_path
        )
        elements.sort(key=lambda e: e.confidence, reverse=True)
        return elements

    def save_screenshot(self, screenshot_bytes: bytes, filename: str) -> str:
        """儲存完整截圖到 output_dir，回傳相對路徑字串。"""
        dest = self._output_dir / filename
        dest.write_bytes(screenshot_bytes)
        return str(Path("sample") / self._pid / filename)

    def crop_element(
        self, screenshot_bytes: bytes, element: ClickableElement, filename: str
    ) -> str:
        """裁切元素矩形（加 20px padding），儲存到 output_dir，回傳相對路徑。"""
        try:
            from PIL import Image
            import io

            img = Image.open(io.BytesIO(screenshot_bytes))
            w, h = img.size
            padding = 20
            x1 = max(0, element.x - element.width // 2 - padding)
            y1 = max(0, element.y - element.height // 2 - padding)
            x2 = min(w, element.x + element.width // 2 + padding)
            y2 = min(h, element.y + element.height // 2 + padding)
            cropped = img.crop((x1, y1, x2, y2))
            dest = self._output_dir / filename
            cropped.save(str(dest), format="PNG")
            return str(Path("sample") / self._pid / filename)
        except Exception as e:
            logger.warning("裁切元素失敗 %s：%s", element.name, e)
            return self.save_screenshot(screenshot_bytes, filename)

    async def _navigate_back_to_parent(self, target_path: str) -> None:
        """重載頁面，按 target_path 的各步驟重播點擊（從已記錄 nodes 找座標）。"""
        if not target_path:
            return

        logger.info("重載並重播路徑：%s", target_path)
        await self._page.reload(wait_until="load", timeout=60000)
        await self.wait_for_stable()

        steps = [s for s in target_path.split(">") if s]
        current_path = ""
        for step in steps:
            current_path = f"{current_path}>{step}" if current_path else step
            # 找有對應 path 的 node
            node = next(
                (n for n in self._all_nodes if n.path == current_path), None
            )
            if node is None:
                logger.warning("找不到路徑步驟 %r 的座標，停止重播", current_path)
                break
            logger.debug("重播點擊 %r 在 (%d, %d)", step, node.x, node.y)
            await self._page.mouse.click(node.x, node.y)
            await asyncio.sleep(self._click_wait_ms / 1000.0)
            await self.wait_for_stable()

    def _next_screenshot_name(self) -> str:
        self._screenshot_counter += 1
        return f"nav_{self._screenshot_counter:03d}.png"

    async def explore(
        self,
        nav_path: str = "",
        depth: int = 0,
        visited_states: Optional[set] = None,
        node_counter: Optional[list] = None,
    ) -> list[NavNode]:
        """遞迴探索 UI，建立並回傳 NavNode 列表。"""
        if visited_states is None:
            visited_states = set()
        if node_counter is None:
            node_counter = [0]

        if depth >= self._max_depth:
            logger.debug("達到最大深度 %d，停止遞迴", self._max_depth)
            return []

        logger.info("[深度 %d] 探索路徑：%r", depth, nav_path or "<root>")

        screenshot_bytes = await self.wait_for_stable()

        # 檢查是否已訪問過此狀態（perceptual hash）
        state_hash = _perceptual_hash(screenshot_bytes)
        if state_hash and state_hash in visited_states:
            logger.info("狀態已訪問過（hash=%s），跳過", state_hash[:8])
            return []
        if state_hash:
            visited_states.add(state_hash)

        # 儲存截圖
        screenshot_filename = self._next_screenshot_name()
        screenshot_rel = self.save_screenshot(screenshot_bytes, screenshot_filename)

        # 分析可點擊元素
        elements = await self.capture_and_analyze(screenshot_bytes, nav_path)
        if not elements:
            logger.info("此畫面無可點擊元素")
            return []

        # 只探索前 max_elements 個（依 confidence 排序）
        candidates = elements[: self._max_elements]
        logger.info("找到 %d 個元素，探索前 %d 個", len(elements), len(candidates))

        collected_nodes: list[NavNode] = []

        for idx, elem in enumerate(candidates):
            node_counter[0] += 1
            node_id = f"{chr(65 + depth)}.{idx + 1}"  # A.1, A.2 … B.1 …
            child_path = f"{nav_path}>{elem.name}" if nav_path else elem.name

            # 記錄此節點（使用整頁截圖路徑）
            node = NavNode(
                node_id=node_id,
                path=child_path,
                x=elem.x,
                y=elem.y,
                screenshot_path=screenshot_rel,
                depth=depth,
                parent_path=nav_path,
            )
            collected_nodes.append(node)
            self._all_nodes.append(node)

            if self._no_reload:
                logger.info("--no-reload 模式：記錄元素 %r，不遞迴", elem.name)
                continue

            # 點擊元素
            logger.info("點擊元素 %r 在 (%d, %d) confidence=%.2f", elem.name, elem.x, elem.y, elem.confidence)
            try:
                await self._page.mouse.click(elem.x, elem.y)
            except Exception as e:
                logger.warning("點擊失敗：%s", e)
                continue

            await asyncio.sleep(self._click_wait_ms / 1000.0)

            # 遞迴探索子節點
            child_nodes = await self.explore(
                nav_path=child_path,
                depth=depth + 1,
                visited_states=visited_states,
                node_counter=node_counter,
            )
            collected_nodes.extend(child_nodes)

            # 返回父層（重載並重播路徑）
            if depth > 0 or idx < len(candidates) - 1:
                await self._navigate_back_to_parent(nav_path)
            else:
                # 最後一個元素不需要返回
                pass

        return collected_nodes


# ---------------------------------------------------------------------------
# Interactive mode helpers
# ---------------------------------------------------------------------------

async def _poll_for_file(path: Path, interval: float = 2.0, timeout: float = 300.0) -> bool:
    """每 interval 秒檢查 path 是否存在，timeout 秒後返回 False。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        await asyncio.sleep(interval)
    return False


def _load_session_state(output_dir: Path) -> dict:
    """讀取 session_state.json，若不存在則回傳預設值。"""
    state_path = output_dir / "session_state.json"
    if state_path.exists():
        try:
            with state_path.open(encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"nav_path": "", "depth": 0, "node_count": 0}


def _save_session_state(output_dir: Path, state: dict) -> None:
    """將 state 寫入 session_state.json。"""
    try:
        path = output_dir / "session_state.json"
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"[interactive] 警告：無法寫入 session_state.json：{e}")


def _update_navigation_map(
    output_dir: Path,
    pid: str,
    nav_path: str,
    x: int,
    y: int,
    screenshot_rel: str,
    node_index: int,
) -> None:
    """
    將一筆記錄 append 到 navigation_map.txt。
    若檔案不存在，先寫入標頭。
    node_id 格式：用全域計數器，如 A.1、A.2...（depth 從 session_state.json 讀取）
    """
    map_path = output_dir / "navigation_map.txt"
    state = _load_session_state(output_dir)
    depth = state.get("depth", 0)
    depth_letter = chr(65 + depth) if depth < 26 else f"Z{depth - 25}"
    node_id = f"{depth_letter}.{node_index}"

    if not map_path.exists():
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = (
            f"# {pid} Navigation Map (interactive)\n"
            f"# Generated: {now_str}\n"
            "# format: node_id | path | x,y | screenshot\n\n"
        )
        map_path.write_text(header, encoding="utf-8")

    with map_path.open("a", encoding="utf-8") as f:
        f.write(f"{node_id} | {nav_path} | {x},{y} | {screenshot_rel}\n")

    logger.info("已更新 navigation_map.txt：%s | %s", node_id, nav_path)


async def run_interactive_mode(page, pid: str, output_dir: Path, max_depth: int) -> None:
    """
    半自動導航模式主邏輯：
    1. 等待畫面穩定 → 截圖存為 current_screen.png
    2. 刪除舊的 click_targets.json（若存在）
    3. 印出提示訊息給用戶
    4. 輪詢等待 click_targets.json 出現（每 2 秒檢查一次）
    5. 讀取 click_targets.json，依序處理每個 element：
       a. 點擊座標 (x, y)
       b. 等待畫面穩定
       c. 截圖存為 current_screen.png（覆蓋）
       d. 將此 element 記錄到 navigation_map.txt
       e. 刪除 click_targets.json，印出提示，再次等待
    6. 若 click_targets.json 包含空的 elements 陣列，視為探索結束，退出
    7. depth 超過 max_depth 時退出
    """
    current_screen_path = output_dir / "current_screen.png"
    click_targets_path = output_dir / "click_targets.json"
    screen_rel = str(Path("sample") / pid / "current_screen.png")

    # 建立一個暫時的 explorer 物件，只借用 wait_for_stable
    _explorer = NavigationExplorer(
        page=page,
        pid=pid,
        output_dir=output_dir,
        claude_client=None,  # type: ignore[arg-type]
        max_depth=max_depth,
    )

    # 初始化 session_state
    state = _load_session_state(output_dir)
    _save_session_state(output_dir, state)

    # 清掉舊的 click_targets.json（若殘留）
    if click_targets_path.exists():
        click_targets_path.unlink()

    # 第一次截圖
    logger.info("等待畫面穩定中...")
    screenshot_bytes = await _explorer.wait_for_stable()
    current_screen_path.write_bytes(screenshot_bytes)

    while True:
        state = _load_session_state(output_dir)
        nav_path = state.get("nav_path", "")
        depth = state.get("depth", 0)

        if depth >= max_depth:
            print(f"[interactive] 已達最大深度 {max_depth}，結束探索")
            break

        print(f"[interactive] 截圖已存至: {screen_rel}")
        print(f"[interactive] 目前路徑: {nav_path!r} (depth={depth})")
        print("[interactive] 請在 Claude Code 輸入「分析截圖」，Claude 將寫入 click_targets.json")
        print("[interactive] 等待 click_targets.json...")

        found = await _poll_for_file(click_targets_path, interval=2.0, timeout=300.0)
        if not found:
            print("[interactive] 等待逾時（300 秒），結束探索")
            break

        # 讀取 click_targets.json
        try:
            with click_targets_path.open(encoding="utf-8") as f:
                targets = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[interactive] 讀取 click_targets.json 失敗：{e}，跳過本輪")
            click_targets_path.unlink(missing_ok=True)
            continue

        elements = targets.get("elements", [])
        new_nav_path = targets.get("nav_path", nav_path)

        # 空 elements → 探索結束
        if not elements:
            print("[interactive] elements 為空，視為探索結束，退出")
            click_targets_path.unlink(missing_ok=True)
            break

        # 讀取後立刻刪除，避免誤觸發
        click_targets_path.unlink(missing_ok=True)

        node_count = state.get("node_count", 0)

        for elem in elements:
            x = int(elem.get("x", 0))
            y = int(elem.get("y", 0))
            name = str(elem.get("name", "unknown"))
            child_path = f"{new_nav_path}>{name}" if new_nav_path else name

            node_count += 1

            print(f"[interactive] 點擊元素 {name!r} 在 ({x}, {y})")
            try:
                await page.mouse.click(x, y)
            except Exception as e:
                logger.warning("點擊失敗：%s", e)
                continue

            await asyncio.sleep(0.5)

            # 等待畫面穩定並截圖（覆蓋 current_screen.png）
            screenshot_bytes = await _explorer.wait_for_stable()
            current_screen_path.write_bytes(screenshot_bytes)

            # 更新 navigation_map.txt
            _update_navigation_map(
                output_dir=output_dir,
                pid=pid,
                nav_path=child_path,
                x=x,
                y=y,
                screenshot_rel=screen_rel,
                node_index=node_count,
            )

            # 更新 session_state
            state["nav_path"] = child_path
            state["node_count"] = node_count
            _save_session_state(output_dir, state)

            print(f"[interactive] 截圖已更新：{screen_rel}")

        # 一批 elements 處理完畢，depth 遞增，回到外層 while 迴圈統一等待下一個 click_targets.json
        state["depth"] += 1
        _save_session_state(output_dir, state)

    map_path = output_dir / "navigation_map.txt"
    if map_path.exists():
        logger.info("互動模式結束，導航記錄：%s", map_path)
    else:
        logger.info("互動模式結束，未產生任何記錄")


# ---------------------------------------------------------------------------
# NavigationMap
# ---------------------------------------------------------------------------

class NavigationMap:
    def __init__(self, pid: str, nodes: list[NavNode]):
        self._pid = pid
        self._nodes = nodes

    def save_txt(self, output_path: Path) -> None:
        """儲存導航樹文字記錄。"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            f"# {self._pid} Navigation Map",
            f"# Generated: {now_str}",
            "# format: node_id | path | x,y | screenshot",
            "",
        ]
        for node in self._nodes:
            lines.append(
                f"{node.node_id} | {node.path} | {node.x},{node.y} | {node.screenshot_path}"
            )
        output_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("導航樹已儲存：%s", output_path)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

async def main() -> None:
    args = parse_args()

    if not args.interactive and not os.environ.get("ANTHROPIC_API_KEY"):
        print("[錯誤] 請設定環境變數 ANTHROPIC_API_KEY")
        print("  export ANTHROPIC_API_KEY='your-api-key'")
        sys.exit(1)
    pid = args.pid

    # 讀取 config.json
    config_path = Path(__file__).resolve().parent / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"找不到 config.json：{config_path}")

    with config_path.open(encoding="utf-8") as f:
        config = json.load(f)

    # 取得 URL
    if args.url:
        url = args.url
    else:
        game_configs = config.get("game_configs", {})
        pid_config = game_configs.get(pid)
        if not pid_config or not pid_config.get("url"):
            raise ValueError(f"找不到 PID {pid!r} 的 URL 設定")
        url_template: str = pid_config["url"]
        usernames: list = config.get("username", [""])
        username = usernames[0] if usernames else ""
        url = url_template.replace("{username}", username)

    logger.info("目標 URL：%s", url)

    # 輸出目錄
    output_dir = Path(__file__).resolve().parent / "sample" / pid
    output_dir.mkdir(parents=True, exist_ok=True)

    # 啟動 Playwright
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--use-angle=metal"],
        )
        try:
            context = await browser.new_context()
            page = await context.new_page()

            logger.info("開啟頁面…")
            try:
                await page.goto(url, wait_until="load", timeout=60000)
            except Exception as e:
                logger.error("頁面載入失敗：%s", e)
                return

            if args.interactive:
                # 半自動模式：Claude 分析截圖，腳本只負責截圖與點擊
                await run_interactive_mode(
                    page=page,
                    pid=pid,
                    output_dir=output_dir,
                    max_depth=args.max_depth,
                )
            else:
                # 原有的 auto 模式（NavigationExplorer + Claude Vision API）
                claude_client = ClaudeVisionClient(model=DEFAULT_CLAUDE_MODEL)

                explorer = NavigationExplorer(
                    page=page,
                    pid=pid,
                    output_dir=output_dir,
                    claude_client=claude_client,
                    max_depth=args.max_depth,
                    stable_threshold=args.stable_threshold,
                    stable_poll_interval=1.0,
                    stable_consecutive=args.stable_seconds,
                    click_wait_ms=500,
                    max_elements=args.max_elements,
                    no_reload=args.no_reload,
                )

                nodes = await explorer.explore()
                logger.info("探索完成，共發現 %d 個節點", len(nodes))

                # 儲存導航樹
                nav_map = NavigationMap(pid=pid, nodes=nodes)
                map_path = output_dir / "navigation_map.txt"
                nav_map.save_txt(map_path)

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
