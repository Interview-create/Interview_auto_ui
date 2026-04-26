# 使用 OpenCV template matching 在 Playwright 頁面上找圖片並點擊
import asyncio
import traceback
from pathlib import Path
from typing import Any, List

import cv2
import numpy as np


async def run_image_click_sequence(
    page: Any,
    image_click_config: List[dict],
    sample_dir: Path,
    click_delay_ms: int = 500,
    threshold: float = 0.80,
) -> None:
    """
    依序對每張 sample 圖片執行 template matching，找到後點擊 N 次。
    找不到或圖片不存在時印出警告並跳過，不中斷整體流程。
    """
    if not 0.0 <= threshold <= 1.0:
        print(f"[image_clicker] 警告：threshold={threshold} 應在 0.0-1.0 之間")

    for item in image_click_config:
        filename = item.get("file", "")
        clicks = max(1, int(item.get("clicks", 1)))
        img_path = sample_dir / filename

        if not img_path.exists():
            print(f"[image_clicker] 圖片不存在，跳過: {img_path}")
            continue

        try:
            # 截取頁面截圖
            screenshot_bytes = await page.screenshot(type="png")
            scene_array = np.frombuffer(screenshot_bytes, dtype=np.uint8)
            scene = cv2.imdecode(scene_array, cv2.IMREAD_COLOR)

            # 讀取 template 圖片
            template = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
            if template is None:
                print(f"[image_clicker] 無法讀取圖片: {img_path}")
                continue

            # Template matching
            if template.shape[0] > scene.shape[0] or template.shape[1] > scene.shape[1]:
                print(
                    f"[image_clicker] template 尺寸 {template.shape[:2]} "
                    f"大於 scene {scene.shape[:2]}，跳過: {filename}"
                )
                continue
            result = cv2.matchTemplate(scene, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val < threshold:
                print(
                    f"[image_clicker] 匹配分數不足 ({max_val:.2f} < {threshold})，"
                    f"跳過: {filename}"
                )
                continue

            # 計算中心點
            cx = max_loc[0] + template.shape[1] // 2
            cy = max_loc[1] + template.shape[0] // 2
            print(
                f"[image_clicker] 找到 {filename}（分數={max_val:.2f}），"
                f"點擊 ({cx}, {cy}) 共 {clicks} 次"
            )

            for i in range(clicks):
                await page.mouse.click(cx, cy)
                if i < clicks - 1:
                    await asyncio.sleep(click_delay_ms / 1000)

        except Exception as e:
            print(f"[image_clicker] 處理 {filename} 時發生例外: {e}")
            traceback.print_exc()
            continue
