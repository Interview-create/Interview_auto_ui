# Playwright WebSocket 測試與 Mock 工具

這是一個基於 Python Playwright 的自動化測試與除錯腳本。主要用於攔截遊戲前端與後端之間的 WebSocket (WSS) 通訊，特別針對以 **Protobuf (Protocol Buffers)** 格式傳輸的資料進行動態解碼、記錄以及 Mock。

## ✨ 核心功能

1. **自動化 WSS 攔截與解析**：
   - 監聽 Playwright 頁面中的所有 WebSocket 連線。
   - 自動過濾並解析 Socket.io 格式（如 `42[...]`）。
   - 內建 `blackboxprotobuf`，可將 Base64 編碼的 Protobuf 封包動態解碼為易讀的 JSON 格式。
2. **自動化 Log 記錄 (`WssLogger`)**：
   - 將所有送出 (`frame_sent`) 與接收 (`frame_received`) 的封包詳細記錄。
   - 記錄檔自動儲存於 `logs/playwight_wss_log/` 目錄下，包含時間戳記與解碼後的 JSON 資料。
3. **動態 Mock 封包攔截 (`MOCK_WSS_ENABLED`)**：
   - 可攔截 Client 發出的 `client:spin` 請求，不將其送往 Server。
   - 腳本會直接從本地端編碼預設的 Mock 資料，並偽裝成 Server 的 ACK 回傳給 Client，實現完全前端的離線/異常測試。
4. **多遊戲結構支援 (`GAME_CONFIGS`)**：
   - 透過 Python Dict 定義各遊戲 (SS01, SS02, SS03) 的 Protobuf Typedef 結構，無須預先編譯 `.proto` 檔案。

---

## 🚀 環境與依賴

請確保安裝以下 Python 套件：

```bash
pip install playwright blackboxprotobuf
playwright install chromium
```

---

## ⚙️ 基礎設定

所有核心設定皆位於腳本 `test_playwright_wss_listen.py` 頂部：

- **`TARGET_PID`**：設定當前要執行的遊戲 PID (例如 `"SS01"`, `"SS02"`, `"SS03"`)。
- **`MOCK_WSS_ENABLED`**：
  - `False` (預設): 僅開啟瀏覽器並側錄 WebSocket 封包至 log 資料夾中。
  - `True`: 啟用 Mock 模式，攔截 `client:spin` 並回傳 `generate_mock_data` 中生成的假封包。

---

## 📂 專案架構與關鍵模組

### 1. Protobuf Typedefs (`*_TYPEDEF`)
取代傳統的 `.proto` 檔案，本專案將 Protobuf 結構定義轉換為 Python 字典：
- `SS01_TYPEDEF`
- `SS02_TYPEDEF`
- `SS03_TYPEDEF`
- `MONEY_TYPEDEF` (共用金額結構)

### 2. 遊戲配置 (`GAME_CONFIGS`)
統一管理各 PID 的測試網址 (`url`) 與對應的 Protobuf 解析結構 (`typedef`)。若要新增遊戲，請在此處擴充。

### 3. Mock 資料生成 (`generate_mock_data`)
當啟用 Mock 時，此函式會依據 `TARGET_PID` 準備對應的假資料 JSON。
- 透過 `blackboxprotobuf.encode_message` 將 JSON 資料結合對應的 Typedef 編碼為 Bytes。
- 再轉換為 Base64 字串，以便 Playwright 注入回 WebSocket 中。

---

## 🛠️ 如何擴充新遊戲？

若要新增一款遊戲（例如 `SS04`）：

1. **定義 Typedef**：
   參考 `SS01_TYPEDEF`，依據 `ss04_protobuf.cpp` 的結構建立 `SS04_TYPEDEF` 字典。
2. **註冊 Config**：
   在 `GAME_CONFIGS` 中加入 `"SS04"`，填入其測試 URL 與 `SS04_TYPEDEF`。
3. **撰寫 Mock 邏輯 (可選)**：
   在 `generate_mock_data` 中加入 `elif pid == "SS04":` 分支，放入你想測試的回傳假資料 JSON。

---

## 📝 Log 輸出說明

每次執行都會在 `logs/playwight_wss_log/` 產生一個唯一的 JSON 檔案，格式範例如下：

```json
{
  "run_ts": "20260323_120000",
  "ws_url": "wss://socket.server...",
  "events": [
    {
      "ts": "2026-03-23T12:00:05.123456",
      "event": "frame_received",
      "payload": "42[\"server:spin:ret\", \"base64_string_here\"]",
      "payload_type": "text",
      "decoded_payload": {
        "spin_id": 123456789, ...
      }
    }
  ]
}
```