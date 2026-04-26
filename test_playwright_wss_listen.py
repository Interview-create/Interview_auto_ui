import asyncio
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from playwright.async_api import async_playwright

from config.runtime import build_context_options, load_runtime_config
from game_configs import (
    TYPEDEFS,
    get_event_typedefs,
)
from mock_data import generate_mock_data
from wss.listeners import attach_ws_listeners
from wss.logger import OUTPUT_DIR
from wss.mock_router import attach_mock_ws_routes
from api.mock_router import attach_mock_api_routes

RUN_TS = datetime.now().strftime("%Y%m%d_%H%M%S")

RUNTIME_CONFIG = load_runtime_config()
GAME_CONFIGS = RUNTIME_CONFIG.get("game_configs", {})
TARGET_PID = RUNTIME_CONFIG.get("target_pid", "SS01")
# --- WSS Mock 替換設定 ---
MOCK_WSS_ENABLED = bool(RUNTIME_CONFIG.get("mock_wss_enabled", False))
FAKE_CONNECTION_ENABLED = bool(RUNTIME_CONFIG.get("fake_connection_enabled", False))
MOCK_API_ENABLED = bool(RUNTIME_CONFIG.get("mock_api_enabled", False))
MOCK_API_ROUTES: list = GAME_CONFIGS.get(TARGET_PID, {}).get("mock_api_routes", [])
PUSH_AFTER_SPIN = int(RUNTIME_CONFIG.get("push_after_spin", 1))
MOCK_BALANCE_MESSAGE = GAME_CONFIGS.get(TARGET_PID, {}).get("mock_balance_message")
_FREE_SPIN_ENABLED = bool(RUNTIME_CONFIG.get("free_spin_enabled", True))
PUSH_MESSAGE = GAME_CONFIGS.get(TARGET_PID, {}).get("push_message") if _FREE_SPIN_ENABLED else None
FREE_SPIN_RESPONSES: dict = (
    GAME_CONFIGS.get(TARGET_PID, {}).get("free_spin_responses", {}) if _FREE_SPIN_ENABLED else {}
)
VIEWPORTS: list = RUNTIME_CONFIG.get("viewport", [None])  # list[dict | None]
USERNAMES: list = RUNTIME_CONFIG.get("username", [""])  # list[str]
DEVICE_NAME = RUNTIME_CONFIG.get("device")  # str | None

IMAGE_CLICK_ENABLED = bool(RUNTIME_CONFIG.get("image_click_enabled", False))
IMAGE_CLICK_CONFIG: list = GAME_CONFIGS.get(TARGET_PID, {}).get("image_click_config", [])
IMAGE_CLICK_DELAY_MS = int(RUNTIME_CONFIG.get("image_click_delay_ms", 500))
IMAGE_CLICK_THRESHOLD = float(RUNTIME_CONFIG.get("image_click_threshold", 0.80))
RECORD_VIDEO_ENABLED = bool(RUNTIME_CONFIG.get("record_video_enabled", False))

SAMPLE_DIR = Path(__file__).resolve().parent / "sample" / TARGET_PID


def _save_video(tmp_dir: str, date_str: str, username: str) -> None:
    # Uses module-level RUN_TS to match the timestamp of other artifacts from the same run.
    tmp_dir_path = Path(tmp_dir)
    videos = sorted(
        tmp_dir_path.glob("*.webm"), key=lambda p: p.stat().st_mtime
    )
    if len(videos) > 1:
        print(f"[video] 警告：tmp dir 內有 {len(videos)} 個影片，使用最新的")
    if videos:
        video_file = videos[-1]
        if video_file.stat().st_size > 0:
            dest = OUTPUT_DIR / date_str / f"{RUN_TS}_{username}_video.webm"
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(video_file), str(dest))
                print(f"[video] 已儲存影片: {dest}")
            except Exception as e:
                print(f"[video] 影片重命名失敗: {e}")
        else:
            print(f"[video] 影片檔案為空，跳過: {video_file}")
        # 清掉多餘影片
        for v in videos[:-1]:
            try:
                v.unlink(missing_ok=True)
            except Exception as e:
                print(f"[video] 清除多餘影片失敗 {v}: {e}")
    try:
        tmp_dir_path.rmdir()
    except OSError:
        pass


async def open_and_play(
    browser: Any,
    p: Any,
    test_url: str,
    mock_wss_receive_list: List[str],
    typedef: dict,
    event_typedefs: dict,
    viewport: Optional[dict] = None,
    device_name: Optional[str] = None,
    pair_index: int = 0,
    username: str = "",
) -> None:
    # 開啟瀏覽器並進入遊戲頁面，啟用 WSS 攔截/記錄

    context = None
    date_str = RUN_TS[:8]
    video_tmp_dir = None

    try:
        if RECORD_VIDEO_ENABLED:
            video_tmp_dir = str(
                OUTPUT_DIR / date_str / f"tmp_video_{username}_{RUN_TS}"
            )
            Path(video_tmp_dir).mkdir(parents=True, exist_ok=True)

        context_options = build_context_options(
            p.devices,
            viewport,
            device_name,
            record_video_dir=video_tmp_dir,
        )
        context = await browser.new_context(**context_options)
        page = await context.new_page()

        if MOCK_WSS_ENABLED or FAKE_CONNECTION_ENABLED:
            # 掛上 mock 路由
            # fake_connection=True 時：不連真實 server，模擬 Socket.IO 握手
            # fake_connection=False 時：連真實 server，只攔截 client:spin
            await attach_mock_ws_routes(
                page,
                mock_wss_receive_list,
                push_message=PUSH_MESSAGE,
                push_after_spin=PUSH_AFTER_SPIN,
                run_ts=RUN_TS,
                message_typedef=typedef,
                event_typedefs=event_typedefs,
                fake_connection=FAKE_CONNECTION_ENABLED,
                mock_balance_message=MOCK_BALANCE_MESSAGE,
                free_spin_responses=FREE_SPIN_RESPONSES,
                pair_index=pair_index,
                username=username,
            )

        if MOCK_API_ENABLED:
            await attach_mock_api_routes(
                page,
                MOCK_API_ROUTES,
                run_ts=RUN_TS,
                username=username,
            )

        # 掛上 websocket 監聽器：記錄收發封包
        attach_ws_listeners(
            page,
            RUN_TS,
            pair_index=pair_index,
            message_typedef=typedef,
            event_typedefs=event_typedefs,
            username=username,
        )

        try:
            # 開啟頁面並等待載入完成
            await page.goto(test_url, wait_until="load", timeout=60000)
        except Exception as e:
            print(f"Navigation error: {e}")
            return

        print(await page.title())

        if IMAGE_CLICK_ENABLED and IMAGE_CLICK_CONFIG:
            from automation.image_clicker import run_image_click_sequence

            await run_image_click_sequence(
                page=page,
                image_click_config=IMAGE_CLICK_CONFIG,
                sample_dir=SAMPLE_DIR,
                click_delay_ms=IMAGE_CLICK_DELAY_MS,
                threshold=IMAGE_CLICK_THRESHOLD,
            )
            return  # 完成後直接進入 finally 關閉瀏覽器

        # 持續保持頁面開啟，以便持續攔截 WSS
        await asyncio.Event().wait()

    finally:
        # 結束時關閉 context
        if context:
            try:
                await asyncio.shield(context.close())
            except Exception as e:
                print(f"[cleanup] context.close 失敗: {e}")
        # 錄影重命名（context.close() 之後才能取得完整影片）
        if RECORD_VIDEO_ENABLED and video_tmp_dir is not None:
            _save_video(video_tmp_dir, date_str, username)


async def main(pid: str) -> None:
    # 依據 PID 取得設定並啟動 Playwright
    config = GAME_CONFIGS.get(pid)
    if not config or not config.get("url"):
        print(f"[{pid}] Configuration or URL not found.")
        return

    url_template = config["url"]
    typedef_key = config.get("typedef_key")
    typedef = TYPEDEFS.get(typedef_key, {}) if typedef_key else {}
    event_typedefs = get_event_typedefs(pid)
    # 產生 mock 回傳資料（只有在 MOCK_WSS_ENABLED 時使用）
    need_mock_data = MOCK_WSS_ENABLED or FAKE_CONNECTION_ENABLED
    mock_wss_receive_list = generate_mock_data(pid, typedef) if need_mock_data else []

    # 建立 (viewport, test_url) 組合：viewport[i] 對應 username[i]，超出範圍使用第一個 username
    default_username = USERNAMES[0] if USERNAMES else ""
    pairs = [
        (
            vp,
            url_template.replace(
                "{username}", USERNAMES[i] if i < len(USERNAMES) else default_username
            ),
        )
        for i, vp in enumerate(VIEWPORTS)
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--use-angle=metal", "--auto-open-devtools-for-tabs"],
        )
        try:
            tasks = [
                asyncio.create_task(
                    open_and_play(
                        browser,
                        p,
                        test_url,
                        mock_wss_receive_list,
                        typedef,
                        event_typedefs,
                        viewport=vp,
                        device_name=DEVICE_NAME,
                        pair_index=i,
                        username=USERNAMES[i] if i < len(USERNAMES) else default_username,
                    )
                )
                for i, (vp, test_url) in enumerate(pairs)
            ]
            await asyncio.gather(*tasks)
        finally:
            try:
                await asyncio.shield(browser.close())
            except Exception as e:
                print(f"[cleanup] browser.close 失敗: {e}")


if __name__ == "__main__":
    # 程式入口
    asyncio.run(main(TARGET_PID))
