# 專案 Call Graph（被誰呼叫）

每個 function 列出功能說明與被哪些 function 呼叫。
Playwright 事件 callback 以「Playwright runtime」標示。

---

## config/runtime.py

| Function | 功能說明 | 被誰呼叫 |
|----------|---------|---------|
| `load_runtime_config()` | 載入 config.json，正規化 username / viewport 為 list | `test_playwright_wss_listen`（模組載入時）、`mock_data._build_prepend_list()` |
| `build_context_options()` | 依 device / viewport 設定組出 Playwright `new_context()` 參數字典 | `test_playwright_wss_listen.open_and_play()` |

---

## wss/utils.py

| Function | 功能說明 | 被誰呼叫 |
|----------|---------|---------|
| `now_iso()` | 回傳目前時間的 ISO 格式字串 | `WssLogger.record_event()`、`ApiLogger.record_event()`、`wss.listeners` 內的 `on_websocket()` / `on_close()` / `on_socket_error()` / `on_response()` / `on_request_failed()`、`api.mock_router` 內的 `handler()` |
| `safe_ws_url()` | 從 websocket 物件安全取出 url 字串 | `wss.logger.new_logger_for_ws()` |

---

## wss/logger.py

| Function | 功能說明 | 被誰呼叫 |
|----------|---------|---------|
| `_resolve_output_dir()` | 從 config.json 讀取 logs_dir，解析為絕對路徑 | 模組載入時（`OUTPUT_DIR = _resolve_output_dir()`） |
| `_resolve_target_pid()` | 從 config.json 讀取 target_pid，作為 log 子目錄名稱 | 模組載入時（`TARGET_PID = _resolve_target_pid()`） |
| `_serialize_payload()` | 將 payload 統一轉成可記錄格式，並回傳類型（binary / text / unknown） | `WssLogger.record_event()` |
| `_heuristic_decode()` | 簡單解析 bytes，輸出 hex 與可讀字串片段 | `WssLogger.record_event()` |
| `bytes_to_readable()` | 遞迴把 bytes 轉成 UTF-8 字串或 hex | `_apply_typedef_full()`、`_decode_packed_field()`、`_reencode_to_bytes()`、`WssLogger.record_event()` |
| `_uint64_to_double()` | 把 uint64 raw bits 還原成 IEEE 754 double | `_apply_typedef_full()` |
| `_decode_packed_ints_from_bytes()` | 把 packed repeated int bytes 解成 Python int list | `_decode_packed_field()` |
| `_decode_packed_field()` | 把 packed repeated 欄位還原成 int list，支援 bytes 與誤解析為 dict 兩種情況 | `_apply_typedef_full()` |
| `_accumulate_field()` | 將值寫入 result dict，repeated 欄位自動合併成 list | `_apply_typedef_full()` |
| `_reencode_to_bytes()` | 當 blackboxprotobuf 把 bytes 欄位誤解析為 dict 時，重新 encode 回 bytes 再解 | `_apply_typedef_full()` |
| `_apply_typedef_full()` | 對 blackboxprotobuf 原始輸出做 rename / double 轉換 / packed ints 還原，一次完成 | `WssLogger.record_event()`、`_apply_typedef_full()`（遞迴） |
| `decode_protobuf_raw()` | 把 base64 protobuf payload 解碼，回傳 (raw_msg, discovered_types) | `WssLogger.record_event()` |
| `WssLogger.__init__()` | 初始化 WSS logger，開啟長存 `_fh`（ab, buffering=0）；從 `_wss_meta.json` 還原 ws_urls，驗證 run_ts | `get_or_create_wss_logger()` |
| `WssLogger._write_meta()` | 以 tmp+rename 原子寫入 `_wss_meta.json`（run_ts, ws_urls），僅在 ws_urls 變動時呼叫 | `WssLogger.__init__()`、`WssLogger.add_ws_url()` |
| `WssLogger.add_ws_url()` | 將新的 WebSocket URL 加入 ws_urls 清單（去重），並呼叫 `_write_meta` | `new_logger_for_ws()` |
| `WssLogger.record_event()` | 解碼 protobuf payload，透過 `_fh` append 單行 JSON（O(1)，含寫入失敗計數） | `wss.listeners` 內的 `on_websocket()` / `on_frame_sent()` / `on_frame_received()` / `on_close()` / `on_socket_error()`；`wss.mock_router` 內的 `_send_spin_reply()` / `_handle_fake_free_spin()` / `_handle_fake_balance()` / `_maybe_send_push()` / `_setup_fake_connection()` |
| `WssLogger.log_path`（property） | 回傳 log 檔的 Path | （未被呼叫） |
| `WssLogger.close()` | 關閉 `_fh`，若有寫入失敗則印出警告 | （未被主動呼叫，GC 時執行） |
| `ApiLogger.__init__()` | 初始化 API logger，開啟長存 `_fh`（ab, buffering=0）；新檔案寫入 run_ts header 行 | `get_or_create_api_logger()` |
| `ApiLogger.record_event()` | 透過 `_fh` append 單行 JSON（O(1)，含寫入失敗計數） | `wss.listeners` 內的 `on_request()` / `on_response()` / `on_request_failed()`；`api.mock_router` 內的 `handler()` |
| `ApiLogger.log_path`（property） | 回傳 log 檔的 Path | （未被呼叫） |
| `ApiLogger.close()` | 關閉 `_fh`，若有寫入失敗則印出警告 | （未被主動呼叫，GC 時執行） |
| `CsvLogger.__init__()` | 初始化 CSV logger，確保輸出目錄存在 | `get_csv_logger()` |
| `CsvLogger.record()` | 將一筆摘要 append 寫入 summary.csv，檔案為空時補寫 header | `wss.listeners` 內的 `on_websocket()` / `on_close()` / `on_socket_error()` / `on_response()` / `on_request_failed()`；`api.mock_router` 內的 `handler()` |
| `CsvLogger.log_path`（property） | 回傳 CSV 檔的 Path | （未被呼叫） |
| `get_csv_logger()` | 取得全域單例 CsvLogger，所有執行共用同一份 summary.csv | `wss.listeners.attach_ws_listeners()`、`api.mock_router` 內的 `handler()` |
| `get_or_create_wss_logger()` | 依 (run_ts, pair_index) 取得或建立 per-user WssLogger | `new_logger_for_ws()` |
| `new_logger_for_ws()` | 取得 per-user WssLogger 並將此 WebSocket URL 加入 ws_urls | `wss.listeners` 內的 `on_websocket()`、`wss.mock_router` 內的 `handle_ws_route()` |
| `get_or_create_api_logger()` | 依 (run_ts, username) 取得或建立 per-user ApiLogger | `wss.listeners.attach_ws_listeners()`、`api.mock_router` 內的 `handler()` |

---

## wss/listeners.py

| Function | 功能說明 | 被誰呼叫 |
|----------|---------|---------|
| `attach_ws_listeners()` | 在 page 上註冊 websocket / HTTP 監聽，將事件寫入 log | `test_playwright_wss_listen.open_and_play()` |
| `on_websocket()` *(closure)* | WebSocket 連線建立時建立 logger 並記錄 open 事件 | Playwright runtime（`page.on("websocket", ...)`） |
| `on_frame_sent()` *(closure)* | 記錄前端送出的 WebSocket frame | Playwright runtime（`ws.on("framesent", ...)`） |
| `on_frame_received()` *(closure)* | 記錄前端收到的 WebSocket frame | Playwright runtime（`ws.on("framereceived", ...)`） |
| `on_close()` *(closure)* | 記錄 WebSocket 關閉事件 | Playwright runtime（`ws.on("close", ...)`） |
| `on_socket_error()` *(closure)* | 記錄 WebSocket 錯誤事件 | Playwright runtime（`ws.on("socketerror", ...)`） |
| `on_request()` *(closure)* | 記錄 HTTP request，並記下發送時間供計算 duration | Playwright runtime（`page.on("request", ...)`） |
| `on_response()` *(closure)* | 記錄 HTTP response，計算 duration，寫入 API log 與 CSV | Playwright runtime（`page.on("response", ...)`） |
| `on_request_failed()` *(closure)* | 記錄 HTTP 失敗請求，寫入 API log 與 CSV | Playwright runtime（`page.on("requestfailed", ...)`） |

---

## wss/mock_router.py

| Function | 功能說明 | 被誰呼叫 |
|----------|---------|---------|
| `_parse_ack_id()` | 從 Socket.IO 訊息中解析 ack_id | `_send_spin_reply()`、`_handle_fake_free_spin()`、`_handle_fake_balance()` |
| `_send_spin_reply()` | 依 spin_count 取出對應 mock 資料並送出，同時記錄 log | `_handle_fake_spin()`、`_setup_real_connection` 內的 `on_page_message()` |
| `_handle_fake_free_spin()` | 根據請求 payload 查表，回傳對應的 free spin mock response | `_setup_fake_connection` 內的 `on_page_message()` |
| `attach_mock_ws_routes()` | 將 WebSocket 路由掛到 page 上，攔截 client:spin 並回 mock | `test_playwright_wss_listen.open_and_play()` |
| `handle_ws_route()` *(closure)* | 每個 WebSocket 連線的路由進入點，依 fake_connection 決定走哪條分支 | Playwright runtime（`page.route_web_socket("**/*", ...)`） |
| `_setup_fake_connection()` | 不連真實 server，模擬 Socket.IO 握手並用 mock 資料回應 | `handle_ws_route()` |
| `_handle_fake_balance()` | 回應 client:balance 請求，送出 mock_balance_message | `_setup_fake_connection` 內的 `on_page_message()` |
| `_maybe_send_push()` | 達到指定 spin 次數後送出 push_message，每次執行只送一次 | `_handle_fake_spin()`、`_setup_real_connection` 內的 `on_page_message()` |
| `_handle_fake_spin()` | 處理 client:spin，累加 spin_count 並送出 mock 回應 | `_setup_fake_connection` 內的 `on_page_message()` |
| `_setup_real_connection()` | 連接真實 server，僅攔截 client:spin 並插入 mock 資料 | `handle_ws_route()` |
| `on_page_message()` *(closure in _setup_fake_connection)* | 攔截前端訊息並依指令類型路由（ping / connect / spin / balance / free_spin） | Playwright runtime（`ws_route.on_message(...)`） |
| `on_page_message()` *(closure in _setup_real_connection)* | 攔截 client:spin 並插入 mock，其餘訊息轉送真實 server | Playwright runtime（`ws_route.on_message(...)`） |
| `on_server_message()` *(closure in _setup_real_connection)* | 將真實 server 回應轉送給前端 | Playwright runtime（`server.on_message(...)`） |

---

## api/mock_router.py

| Function | 功能說明 | 被誰呼叫 |
|----------|---------|---------|
| `_make_api_mock_handler()` | 依 route_config 建立 HTTP mock handler closure | `attach_mock_api_routes()` |
| `handler()` *(closure)* | 攔截 HTTP request，回傳 mock response 並寫入 API log 與 CSV | Playwright runtime（`page.route(...)`） |
| `attach_mock_api_routes()` | 依 mock_api_routes 設定，對每個 pattern 掛上對應的 mock handler | `test_playwright_wss_listen.open_and_play()` |

---

## automation/image_clicker.py

| Function | 功能說明 | 被誰呼叫 |
|----------|---------|---------|
| `run_image_click_sequence()` | 依序對每張 sample 圖片執行 OpenCV template matching，找到後點擊 N 次 | `test_playwright_wss_listen.open_and_play()` |

---

## mock_data.py

| Function | 功能說明 | 被誰呼叫 |
|----------|---------|---------|
| `_decode_varint_list()` | 將 protobuf varint bytes 逐個解碼成 int list | `_decode_positions()` |
| `_to_signed_int32()` | 將無號 32-bit 整數轉成有號 32-bit | `_decode_positions()` |
| `_decode_double_bits()` | 將 double 的 64-bit bit pattern 轉成 float | `_normalize_double_fields()` |
| `_load_yaml_or_json()` | 讀取檔案，優先用 YAML 解析，無 PyYAML 時退回 JSON | `_mocks_ss01()`、`_mocks_ss02()`、`_mocks_ss03()` |
| `_decode_positions()` | 將 positions / hit_positions 的不同型別統一成 int list | `_normalize_pay_lines()` |
| `_normalize_pay_lines()` | 將 pay_lines 內容正規化為可 protobuf 編碼的結構 | `encode_to_base64()` |
| `_normalize_double_fields()` | 針對 typedef 中標記為 double 的欄位做 bit pattern 轉換 | `encode_to_base64()` |
| `encode_to_base64()` | 正規化資料後透過 blackboxprotobuf 編碼，轉成 base64 字串 | `generate_mocks_by_symbol_codes()`、`_mocks_ss01()`、`_generate_grid_scenario_mocks()` |
| `generate_mocks_by_symbol_codes()` | 依 symbol_codes 替換盤面，產生對應的 base64 mock list | `_mocks_ss01()` |
| `_build_prepend_list()` | 讀取 config，依開關決定是否回傳 mock_list_append 前置封包 | `generate_mock_data()` |
| `_generate_grid_scenario_mocks()` | SS02 / SS03 共用：替換 grid symbol code 並接上完整範例資料 | `_mocks_ss02()`、`_mocks_ss03()` |
| `_mocks_ss01()` | 產生 SS01 / SS01A 的 mock 資料（整盤同一 symbol + pay_lines 變體） | `generate_mock_data()`（透過 `_PID_GENERATORS`，對應 SS01 / SS01A） |
| `_mocks_ss02()` | 產生 SS02 的 mock 資料 | `generate_mock_data()`（透過 `_PID_GENERATORS`，對應 SS02） |
| `_mocks_ss03()` | 產生 SS03 的 mock 資料 | `generate_mock_data()`（透過 `_PID_GENERATORS`，對應 SS03） |
| `generate_mock_data()` | 組合前置封包與 pid 對應的 mock 資料，回傳完整 mock list | `test_playwright_wss_listen.main()` |

---

## game_configs.py

| Function | 功能說明 | 被誰呼叫 |
|----------|---------|---------|
| `get_event_typedefs()` | 依 PID 回傳對應的 event-level typedef 覆寫字典（balance / free_spin） | `test_playwright_wss_listen.main()` |

---

## test_playwright_wss_listen.py

| Function | 功能說明 | 被誰呼叫 |
|----------|---------|---------|
| `_save_video()` | 將錄影暫存檔移至 logs 目錄並重命名，清除多餘影片 | `open_and_play()`（finally block） |
| `open_and_play()` | 啟動瀏覽器，掛上 WSS / API mock 與監聽器，進入遊戲頁面 | `main()`（透過 `asyncio.create_task`） |
| `main()` | 依 PID 取得設定，產生 mock 資料，並行啟動多個 browser / viewport 組合 | `asyncio.run(main(TARGET_PID))`（`__main__` 區塊） |

---

## capture_navigation.py

| Function | 功能說明 | 被誰呼叫 |
|----------|---------|---------|
| `parse_args()` | 解析 CLI 參數（--pid / --url / --max-depth 等） | `main()` |
| `compute_pixel_diff_ratio()` | 計算兩張截圖的像素差異比例，用於判斷畫面是否穩定 | `NavigationExplorer.wait_for_stable()` |
| `_perceptual_hash()` | 計算截圖的 average hash，用於偵測重複畫面狀態 | `NavigationExplorer.explore()` |
| `ClaudeVisionClient.__init__()` | 初始化 anthropic 同步 client | `main()`（auto 模式） |
| `ClaudeVisionClient.analyze()` | 傳送截圖給 Claude Vision，回傳可點擊元素列表 | `NavigationExplorer.capture_and_analyze()`（透過 `run_in_executor`） |
| `_parse_elements()` | 解析 Claude 回傳的 JSON，容錯處理非標準格式 | `ClaudeVisionClient.analyze()` |
| `_build_elements()` *(inner function)* | 將 dict list 逐筆轉換為 ClickableElement，跳過無效項目 | `_parse_elements()` |
| `NavigationExplorer.__init__()` | 初始化探索器，設定穩定偵測參數與輸出目錄 | `main()`（auto 模式）、`run_interactive_mode()`（借用 `wait_for_stable`） |
| `NavigationExplorer.wait_for_stable()` | 每秒截圖並比較像素差，連續 N 次穩定後回傳截圖，超時 30 秒強制返回 | `NavigationExplorer.explore()`、`NavigationExplorer._navigate_back_to_parent()`、`run_interactive_mode()` |
| `NavigationExplorer.capture_and_analyze()` | 呼叫 ClaudeVisionClient 分析截圖，依 confidence 排序後回傳 | `NavigationExplorer.explore()` |
| `NavigationExplorer.save_screenshot()` | 儲存完整截圖到 output_dir，回傳相對路徑字串 | `NavigationExplorer.explore()`、`NavigationExplorer.crop_element()`（例外 fallback） |
| `NavigationExplorer.crop_element()` | 裁切元素矩形（加 20px padding）並儲存，例外時 fallback 至 save_screenshot | （未被呼叫） |
| `NavigationExplorer._navigate_back_to_parent()` | 重載頁面並依路徑步驟重播點擊，回到指定的父層狀態 | `NavigationExplorer.explore()` |
| `NavigationExplorer._next_screenshot_name()` | 產生遞增的截圖檔名（nav_001.png、nav_002.png…） | `NavigationExplorer.explore()` |
| `NavigationExplorer.explore()` | 遞迴探索 UI：截圖 → 分析 → 點擊 → 子節點遞迴 → 返回父層 | `main()`（auto 模式）、`NavigationExplorer.explore()`（遞迴） |
| `NavigationMap.__init__()` | 初始化導航樹，儲存 pid 與 nodes | `main()`（auto 模式） |
| `NavigationMap.save_txt()` | 將導航樹輸出為純文字檔 navigation_map.txt | `main()`（auto 模式） |
| `_poll_for_file()` | 每 N 秒輪詢檔案是否存在，逾時回傳 False | `run_interactive_mode()` |
| `_load_session_state()` | 讀取 session_state.json，若不存在回傳預設值 | `run_interactive_mode()`、`_update_navigation_map()` |
| `_save_session_state()` | 將 session state 寫入 session_state.json，失敗時印出警告 | `run_interactive_mode()` |
| `_update_navigation_map()` | Append 一筆導航記錄到 navigation_map.txt，檔案不存在時先寫標頭 | `run_interactive_mode()` |
| `run_interactive_mode()` | 半自動模式主邏輯：截圖 → 等待 Claude 寫入 click_targets.json → 點擊 → 循環 | `main()`（interactive 模式） |
| `main()` | 解析參數、讀 config、啟動 Playwright，依模式分流至 auto 或 interactive | `asyncio.run(main())`（`__main__` 區塊） |

---

## parse_spinret.py

| Function | 功能說明 | 被誰呼叫 |
|----------|---------|---------|
| `parse_spinret_b64()` | 解析 base64 SpinRet protobuf，回傳結構化 dict | `__main__` 區塊 |
| `print_spinret()` | 格式化印出 SpinRet 解析結果 | `__main__` 區塊 |

---

## tests/test_mock_data_toggles.py

| Function | 功能說明 | 被誰呼叫 |
|----------|---------|---------|
| `_run_generate()` | 以受控 config 呼叫 `generate_mock_data`，回傳 mock list 供測試驗證 | 各 `test_*` 方法 |
| `test_*` 方法 | 驗證 mock_list_append_enabled 開關行為 | pytest runner |

## tests/test_mock_router.py

| Function | 功能說明 | 被誰呼叫 |
|----------|---------|---------|
| `FakeLogger.record_event()` | 收集 record_event 呼叫，供測試驗證 log 內容 | 被測函式（`_handle_fake_free_spin()` 等）呼叫 |
| `FakeWsRoute.send()` | 收集 send 呼叫，供測試驗證送出的訊息 | 被測函式（`_handle_fake_free_spin()` 等）呼叫 |
| `test_*` 函式 | 驗證 mock_router 的 log 事件名稱、payload、note | pytest runner |

## tests/test_utils.py

| Function | 功能說明 | 被誰呼叫 |
|----------|---------|---------|
| `test_*` 函式 | 驗證 `build_context_options()` 的各種參數組合行為 | pytest runner |
