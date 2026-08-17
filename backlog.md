# 需求清單（Backlog）

新增／變更／刪除的需求都記這裡。狀態：`提出` → `規劃` → `進行` → `完成` / `擱置` / `取消`。
細部進度看各系統文件的「待辦」，這裡只追需求層級。

---

## 進行中

### REQ-001　主 PACS：原始檔不可變 + 出口疊合
- **狀態**：進行（A0/A1/A2/A3/B 全數完成、.191 驗證通過；正式部署暫緩=.234 保留舊版）
- **系統**：主 PACS（HD.Net10）
- **要什麼**：進檔後實體檔唯讀不可變；校正只寫 DB；所有出口送出前把 DB 校正疊上（coerce-on-retrieve）。停止 StudyClose 就地改檔。
- **為什麼**：舊版就地改檔曾寫壞原始影像。
- 詳見 [systems/main-pacs.md](systems/main-pacs.md)

### REQ-002　主 PACS：接入共用日誌
- **狀態**：進行（HD.PACS + WorklistServer 已寫，待部署）
- **系統**：主 PACS
- **要什麼**：運作 log 送 LoggingPlatform，帶 ClientIp/User。
- 詳見 [systems/main-pacs.md](systems/main-pacs.md)、[systems/shared-logging.md](systems/shared-logging.md)

---

## 新提出

### REQ-003　燒錄功能開成 API（打包 / 查狀態 / 下載）
- **狀態**：**薄層 API 完成 + .199 生產端到端驗證通過**（2026-08-06）；剩「Export 拆成獨立專案」為後續。
- **端到端驗證**：POST 建立→201；.191 worker 打包→P；GET 查狀態→通；GET 下載→200（合法 DICOM 包）。過程修 2 個 legacy proc bug（`insert_package_job` patient CASE + accession/patientId TRIM，寫進 v2.0.27）+ burnTemp 搬 NAS（`HD_CONFIG` burnTempPath→`/home/HD/data/burnTemp`）。詳記憶 project_req003_export_webapi。
- **決策**：Export 定案**獨立成一支 API**（不併 DicomWeb，薄殼端點目前在 DicomWeb 待拆）；auth 先用現有 API Key、之後隨 Keycloak 換。進檔字串正規化另立 REQ-009。
- **⚠️ 參數盤點：`BURN_INFO` 有一半欄位 net10 worker 根本不讀（2026-08-17 查證）**。查了三層才確定——API 的 `CreatePackageRequest` → proc `export.insert_package_job` 寫進 `BURN_INFO` → `get_job_package_info()`（[HDPACS_20260811.sql:2498](../Database/HDPACS_20260811.sql)）把 **`burn_info` 整包**丟給 worker → 但 worker 反序列化用的 `HD.Net10/HD.MediaPackage/Class/PackageJob.cs` 只有部分屬性，其餘**靜靜被丟掉**：

  | 參數 | proc | net10 worker | 結論 |
  |---|---|---|---|
  | `anonymous`／`containViewer`／`ignoreCompress`／`dicomStoragePath` | 寫入 | `PackageJob` 有 | ✅ 有效 |
  | `ignoreMultiframe` | **proc 內部當篩選條件**（`CONVERT_STATUS->>'mpeg4'='N'`） | 無此屬性 | ⚠️ 見下 |
  | `packageSevenZip`／`packageSevenZipName` | 寫入 | **無** | ❌ 空頭 |
  | `storageUserId`／`storagePassword`／`opticalDiskDrive` | 寫入 | **無** | ❌ 空頭 |

  全 `HD.Net10` 搜 `SevenZip|7z|storagePassword|storageUserId` 零結果。**已於 2026-08-17 把 `packageSevenZip`／`packageSevenZipName` 從 API 拿掉**（Export 尚未有人使用，拿掉的又是本來就沒作用的東西），並補上 proc/worker 都支援、卻獨漏沒開的 `dicomStoragePath`。`storageUserId`／`storagePassword`／`opticalDiskDrive` 維持不開放。
  **→ 日後真的要「Export 整支取代 hd-media-package」時，這些欄位得先決定是實作還是正式廢掉**，別讓它們一直以「proc 寫得進去、沒人讀」的狀態存在。
- **⚠️ `ignoreMultiframe` 正在失去意義（REQ-008 的交叉影響，只看單一需求的文件看不出來）**：它在 proc 裡的作用是篩 `CONVERT_STATUS->>'mpeg4'='N'`，但 **REQ-008 移除 DicomToVideo 後 `insert_dicom_info` 一律標 `mpeg4='N'`** → 對新資料 true/false 篩出來完全相同，只有 REQ-008 之前的舊資料還有差別。目前保留參數但已在 API 文件註明。
- **API 說明頁（2026-08-17）**：`CreatePackageRequest` 各欄位的預設值與「留空＝不送該欄位、由 proc 套預設」寫進 `///` XML 註解並開 `GenerateDocumentationFile`，`/scalar` 直接看得到。**預設值的正本仍在 proc**（C# 刻意不給預設值，避免兩份定義各自漂移）。兩個實作陷阱：`<remarks>` **不會**進 OpenAPI description（只有 `<summary>` 會）；多行 summary 會把 XML 檔的縮排一起帶進去，4 空格開頭在 markdown 會變成程式碼區塊 → 一律寫成單行。
- **系統**：（待定）DicomWeb 或 主 PACS 媒體模組
- **要什麼**：把現有 CD/DVD 燒錄／媒體打包（HD.MediaPackage）開成 REST API：
  1. **建立打包**：使用者呼叫 API 送出打包需求（指定 study 等）→ 回一個 job id。
  2. **查看打包狀態**：以 job id 查進度（處理中／完成／失敗）。
  3. **下載**：完成後下載打包結果（ISO/zip）。
- **現況分析**（待規劃時確認）：燒錄由傳統 PACS 的 **hd-media-package** worker 執行，讀 `export.EXPORT_JOB` 佇列、靠 `export.get_job_package_info()` 取內容、輸出到 burnTempPath（可含 DICOMDIR / viewer / zip）。所以 API 很可能是「薄層」：
  - 建立 = 寫一筆 `export.EXPORT_JOB`（狀態 'N'）→ 既有 worker 自然接手。
  - 查狀態 = 讀該 job 的 STATUS（worker 會更新 P/E 等）。
  - 下載 = 把 worker 產出的檔案串流回去。
- **放哪裡（待決）**：DicomWeb 已有認證/授權/部署/稽核基礎，適合擺這組 API；但打包執行體在傳統 PACS 端（同一套 DB 可橋接）。需規劃：API 端 vs worker 端的分工、下載檔案路徑的存取（.199 DicomWeb 取 .234 產出的檔）。
- **待辦**：見 [todo.md](todo.md)（REQ-003 規劃）。

### REQ-004　DicomWeb 縮圖效能：目前每次即時渲染、無快取
- **狀態**：提出（2026-08-03，觀察）
- **系統**：DicomWeb（HD.Pacs.DicomWeb）
- **現況**：WADO thumbnail（`HdPacsWadoService.GetThumbnailAsync` → `RenderFrame`）**每次請求都從 DICOM 檔即時解碼→渲染→縮放→編 JPEG**，沒有快取（`CoercedInstanceCache` 只用於取整份 instance，不含 thumbnail/rendered），也沒讀現成 .jpg。縮圖牆（一次幾十上百張）會大量重複解碼，壓縮影像尤其吃 CPU/NAS I/O。
- **優化選項**（待評估）：
  1. **加縮圖快取**（比照 CoercedInstanceCache）：key=SOP UID+maxDimension，記憶體/磁碟 LRU；純 DicomWeb 端改動。
  2. **吃傳統 PACS 已產好的 .jpg**：`hd-dicom-to-image` 進檔時已在影像旁生 .jpg；縮圖改「有現成 jpg 就回、沒有才 render」→ 多數零解碼，最省；但要跨到傳統 PACS 的檔案佈局、確認 jpg 尺寸/存在性。
- **待辦**：評估選 1 或 2；見 [todo.md](todo.md)。

### REQ-005　MediaPackage 燒錄：中文名(ISO_IR 192) study-elements JSON 序列化 NRE
- **狀態**：**完成（2026-08-04，.191 驗證通過）** — 燒錄端到端跑完、study_elements.json 產出、無 NRE
- **系統**：主 PACS（HD.Net10）hd-media-package
- **問題**：燒錄流程建「study-elements JSON（光碟 viewer metadata）」時（`PackageService.cs:383` → `HD.MediaPackage.Dicom.DicomJsonConverter` 序列化含 PersonName 的 dataset）→ fo-dicom `DicomEncoding.GetStrictEncodings` 對 **ISO_IR 192 中文 PersonName 拋 NullReferenceException**。
- **影響**：台灣每份 study 都是中文名 → 疑似**任何中文名 study 燒錄都會在此步掛掉**（fo-dicom 4→5 重寫的 regression；net10 MediaPackage 未經中文名生產驗證）。DICOM 檔本身在 NRE 前已成功產出，coerce 不受影響。
- **修正（2026-08-04，.191 驗證通過）**：`DicomJsonConverter` 兩處（`WriteEncodingJsonElement` line 418 的 `elem.Length`、`WriteJsonPersonName` line 564 的 `Buffer.Data`）都會觸發 fo-dicom string→bytes 編碼 → 對 ISO_IR 192 PersonName NRE。改為讀 bytes 包 try、遇 lazy 元素編碼 NRE 就退回 `Get<string[]>()` 直接取字串（檔案載入元素維持 UTF-8 解碼）。重測 jobRef 3：燒錄跑完、study_elements.json 產出、coerce marker 全中。fix 在 HD.MediaPackage 原始碼（隨主批一起 commit）。

> **REQ-006/007/008 完整實作規劃**：[intake-slimming-design.md](intake-slimming-design.md)（2026-08-04）。

### REQ-006　主 PACS：進檔不再存 `.meta` 檔
- **狀態**：**完成（2026-08-04，.191 驗證通過 + commit/push）**
- **改動**：HD.Net10 `17de498`（DicomStoreProcess.cs / .FileIO.cs / .Validation.cs 停產 .meta；ArchiveCompress/Upload 改「.meta 存在才納入」相容舊資料）+ HD.Pacs.DicomWeb `8fb0562`（HdPacsStowService 停 STOW .meta）。
- **驗證**：.191 更新 hd-pacs 後 C-STORE 新影像（2026/0528/0000000c），磁碟不再產生 .meta（總數維持 11 不變），舊資料 .meta 保留、DB 正常。
- **系統**：主 PACS（HD.Net10）
- **要什麼**：C-STORE 進檔時**不再產生 `<ordinal>.meta`**（metadata-only 的 DICOM 副本）。
- **為什麼**：`.meta` 當初是「檔案會被就地改寫」時代的保險（保留一份原始 metadata）。A3（REQ-001）已停止改檔、校正改走 DB DATASET + 出口疊合，`.meta` 已冗餘。
- **影響面（初掃）**：
  - **產生**：`HD/DicomCore/DicomStoreProcess.cs:120` → `SaveMetaFile`；路徑定義 `DicomStoreProcess.FileIO.cs:23`（`Main.FullName + ".meta"`），錯誤清理 `FileIO.cs:128`。→ 主要移除點。
  - **下游會搬/刪 `.meta` 的流程**（都要能容忍它不存在；多數已有 `.Exists` 判斷，需逐一確認不會硬性依賴）：`HD.ArchiveManager`（NearlineBackupService:120、ArchiveUploadService:115、ArchiveCompressService:129/137/212-213/241-242、ArchiveDecompressService:108）、`HD.CacheDelete`（CacheDeleteService:62）。
  - **待確認**：有沒有**讀** `.meta` 的路徑（初掃只看到 write/copy/delete；要確認沒有任何流程靠 `.meta` 還原 metadata，否則得改讀 DB DATASET）。舊資料既存的 `.meta` 要不要清、還是留著自然淘汰。
- **待辦**：規劃時確認讀取路徑；見 [systems/main-pacs.md](systems/main-pacs.md)。

### REQ-007　主 PACS：移除 DicomToImage（進檔預轉 JPEG）流程
- **狀態**：**PACS/DB 端完成（2026-08-04，.191 驗證通過，route A）**；消費端遷移 DicomWeb 脫鉤待做。詳 [intake-slimming-design.md](intake-slimming-design.md)。
- **做法（route A，低風險）**：不動 3 處 jpeg gate；改讓 `insert_dicom_info`（`db_update_v2.0.28.sql`）一律標 `jpeg='N'`、永不 enqueue DICOM_TO_IMAGE → jpeg 永遠非 null、gate 自然放行。C# `HD.Net10 86ef7bd` 下架 HD.DicomToImage + 清死碼。migration 併入**開著未結案**的 `Database/HDPACS/db_update_sql/db_update_v2.0.27.sql`（當一筆 20260804 Charlie 加在尾）；`DB版本.xlsx` 的 2.0.27 分頁亦加一列。
- **JPEG 政策**：今後取 JPEG 一律走新 DicomWeb（即時 render）。消費端（HD.DicomImageViewer 縮圖/預覽、HD.MediaPackage 燒錄、viewer_station.*/wadouri_query CacheJpegPath）改接 DicomWeb = 脫鉤、日後各自做；連帶 REQ-004。`deleteOriginDcm` 確認=多幀清理、與 jpeg 無關、不動。
- **系統**：主 PACS（HD.Net10）+ HDPACS DB
- **要什麼**：拿掉 `hd-dicom-to-image`（`HD.DicomToImage`）與進檔預轉 JPEG 的整條流程。
- **為什麼**：預轉 JPEG 原本是給舊版 HDWeb WebViewer 用的（舊 web 取圖慢，需預先轉）。新版 **DicomWeb 即時轉很快**，預轉已無必要，還佔存儲 + 拖慢進檔。
- **影響面（初掃）— 牽動廣、且與 A3 相依**：
  - **服務/專案**：`HD.DicomToImage`（.191 本來就沒裝）；`HD/ImageConvert.cs`、`DicomStoreProcess`（進檔時依 `toJpeg` config 產 JPEG + 塞 DICOM_TO_IMAGE job）。
  - **DB（HDPACS SQL）需一併改**：
    - 進檔塞 job：`insert_job_queue` / store 端多處 `DICOM_TO_IMAGE`（~4034/9723/16031）＋ `update_object_convert_status('DICOM_TO_IMAGE',...)`（~4050/9743/16049）＋ `RC_OBJECT_CONVERT` 初始化 `jpeg:null`（15962/25559）；config 開關 `toJpeg`（9691/15755/17256）。
    - **⚠️ 與 A3 直接相依 — STUDY_CLOSE 的 jpeg gate**：`get_next_map_job` 12756-12765（及 10260-10261、10330-10334）**要求所有物件 `CONVERT_STATUS->>'jpeg'` 非 null 才放行 STUDY_CLOSE**。這正是今天 .191 要把 `toJpeg=false` 才繞過的關卡。**移除 DicomToImage 必須同時拿掉/改寫這些 jpeg gate**，否則 STUDY_CLOSE 永遠卡住。
    - **⚠️ 保留 video 分支**：DICOM_TO_VIDEO / mpeg4 / dicomMpeg4 的 gate 與 convert status 跟 jpeg 混在同幾支 proc（如 10330-10334 同時查 jpeg+mpeg4+dicomMpeg4），拆除 jpeg 時**不能誤傷 video**（見 REQ-008）。
    - **⚠️ `deleteOriginDcm`**：`RC_OBJECT_CONVERT` 有 `deleteOriginDcm` 狀態（12429-12431），疑似某轉檔後刪原 DCM 的流程，移除前要查清楚別誤刪原檔。
  - **檔案佈局**：JPEG 目錄 `cacheLocation/JPEG/...`（FileIO.cs:21、get_object_path Jpeg type 13810-13811）。
  - **待確認**：除了舊 HDWeb,還有沒有別的消費者讀預生 JPEG（含 REQ-004 縮圖選項 2 曾考慮吃現成 jpg → 若刪 DicomToImage,該選項作廢,縮圖只能走即時 render+快取選項 1）。
- **待辦**：規劃時完整盤點 DB proc 改動清單 + 確認 JPEG 消費者;見 [systems/main-pacs.md](systems/main-pacs.md)。

### REQ-008　主 PACS：DicomToVideo（轉 MPEG4）流程去留 — 待討論
- **狀態**：提出（2026-08-04，**待討論，暫不動**）
- **系統**：主 PACS（HD.Net10）`HD.DicomToVideo`
- **議題**：DicomToImage 要刪（REQ-007），但 **DicomToVideo（轉 MPEG4）較花時間、去留需討論**——即時轉可能來不及,可能仍需預轉。
- **要點**：與 REQ-007 共用同一批 DB proc / convert status / gate（jpeg 與 mpeg4/dicomMpeg4 混在一起），所以 REQ-007 拆 jpeg 時要**保留 video 路徑完整**。先確認 DicomToVideo 的實際使用場景（哪個 viewer/流程在吃 MP4）再決定。
- **待辦**：先討論保留/移除/改即時；未定前 REQ-007 動 DB 時務必不動 video 分支。

### REQ-009　主 PACS：進檔正規化 DICOM 字串補位（trim 尾空格）
- **狀態**：提出（2026-08-06，起因 REQ-003 測試踩到）
- **系統**：主 PACS（HD.Net10）`insert_dicom_info` / DB
- **要什麼**：進檔時把 DICOM 偶數長度補位的尾空格 trim 掉，DB 只存乾淨正規值（AccessionNumber / PatientID 等識別類字串欄）；含一次性 `UPDATE` 清理既有資料。
- **為什麼**：DICOM 奇數長度字串 VR 尾補一個空格（byte 對齊、不具語意）；未 trim 存進 DB → 精確比對 bug（REQ-003 export 就踩到 accession 尾空格 `'A26R1302506 '` 對不上）。與 REQ-001「原檔不可變、校正只寫 DB」一致：原檔保留補位、DB 存正規值、DICOM 輸出自動重補、零失真。
- **要點**：①決定哪些欄 trim（識別類安全；`RTRIM` 最精準——padding 只在尾；**UID 是 `\0` 補位、不同處理**）②舊資料一次性 UPDATE 清理③下游盤點（確認無消費者依賴帶空格精確值）④**proc 端比對 TRIM 保留當防呆**（不因 ingestion trim 就移除；REQ-003 的 `insert_package_job` 已加）。
- **待辦**：可請 Claude 盤 `insert_dicom_info` 存哪些字串欄、出正規化 + 舊資料清理 SQL 評估。

### REQ-010　WebExport：給客戶用的匯出/燒錄前台
- **狀態**：提出（2026-08-06）
- **系統**：新產品（獨立前台），吃 **HD.Export API**（.199:5090）
- **要什麼**：客戶端（醫院操作人員/醫師）自助介面：選 study → 申請匯出/燒錄 → 看**自己的**進度 → 下載。
- **邊界（與主控台分工）**：主控台的「匯出紀錄」＝內部**唯讀管理視圖**（全量、排障導向，不做建立/下載）；WebExport＝**業務前台**（建立＋自己的 job＋下載）。兩者都以 HD.Export API / export.EXPORT_JOB 為核心，不重工。
- **認證**：Keycloak 登入（人）＋ RBAC `ACCESS.export` 區段（ResolveScopes 已支援，HD.Shared `f52b1fa`）；HD.Export 屆時開 MultiScheme（API Key＋JWT）。
- **長線**：kiosk／取件號／費用等隨「Export 取代 hd-media-package」路線長在這條線上。

### REQ-011　看片端連動：gRPC 改 REST，Executer 是否併入 Viewer
- **狀態**：**暫緩**（2026-08-13 討論並決定延後；已寫好的 REST 實作已還原，只保留 bug 修正）
- **系統**：HD.DicomImageViewer（Executer / LinkClientDesktop）
- **現況鏈路**：HIS → 啟動 `LinkClientDesktop.exe`（位置式參數）→ gRPC 明文 5002 → Executer → Named Pipe → Viewer（登入前先排隊）
- **要什麼**：①gRPC 換成 REST ②評估 Executer 併入 Viewer
- **為什麼**：加一個連動指令要改 `viewerlink.proto`、重新產生程式碼、同步兩個專案的 `Protos\`；HIS 廠商也接不了 gRPC，所以只能一直附一支 `LinkClientDesktop.exe` 當殼。REST 之後加指令＝加一條路徑，HIS 可直接用 HTTP 打，現場也能用 curl 排障。
- **決策一（REST）**：**要做，但延後**。REST 與 gRPC 明文之下**不能共用同一個埠**（h2c 與 HTTP/1.1 的協商要靠 TLS ALPN），所以並存期間 REST 走 **5003**、gRPC 留 5002，全面換裝後才收掉 5002。配套：API Key（`X-HD-Link-Key`，留空＝不驗證）＋防火牆限來源 IP＋回應帶真實送達結果（目前 pipe 寫得進去就回 `Success`，等於假的成功）。
- **決策二（併入 Viewer）**：**傾向不做**。Executer 唯一且真正的價值不是通訊，是「Viewer 沒開時把它叫起來並補送」（醫師需求 3）。併進去之後 Viewer 一掛就沒有任何角色能救它——LinkClient 在 HIS 那台，叫不動對面的程式。要補就得再加看門狗，等於又變兩支。資源不是問題（登入畫面沒有 `LayoutControl`，30fps 計時器不存在；常駐約多 50–100 MB），問題是**當掉沒人接手**、**關閉行為要改成縮系統列**、以及**長期不重開會攤開原本靠冷啟動掩護的累積**。
- **效能備註**：協定本身佔比是雜訊（~1–2 ms）。真正的成本是 `LinkClientDesktop.exe` 冷啟動（300–800 ms）與 Viewer 冷啟動輪詢（最多 30 秒，`LaunchRetryIntervalMs = 1000` 可縮到 200ms）。而「拿掉 LinkClient 讓 HIS 直接打 HTTP」是唯一數量級的改善，**只有 REST 做得到**。
- **本輪已落地（未延後的部分）**：Kestrel 由 `localhost` 改綁 `0.0.0.0`（HIS 在別台時原本根本連不進來，且服務端沒有任何紀錄）；`AppSettingsManager.Save` 補齊缺漏節點避免 NRE；LinkClient 設計階段預留值 5001→5002。
- **配套已補齊**（2026-08-13，commit `f6347f6`）：看片端安裝程式新增「連動來源限制」頁 → 依填入的 HIS IP（留空=LocalSubnet）建立防火牆放行規則，埠號從 Executer 的 appsettings 讀、先刪再加、解除安裝時移除、填 `Any` 會先確認；連動用戶端安裝程式新增「連動服務位址」頁寫入 `ExecuterUrl`，更新時以前一版預填，指向 localhost 會再確認一次。**尚未實機試裝驗證。**

### REQ-012　看片端授權（註冊）機制
- **狀態**：**實作完成、端到端驗證通過**（2026-08-14）。正本 [viewer-license-design.md](viewer-license-design.md)
- **關鍵轉折——改成線上註冊**：原設計是純離線（帶 `.req` 回原廠簽、再帶授權檔回現場），但痛點不在簽章而是「**醫師的個人電腦我們連不到，拿檔案一定要跑現場**」。關鍵觀察：每間醫院一定有我們的主機，而**看片端本來就要連那台 PostgreSQL 才能看片＝能看片就一定連得到 DB**。所以**拿 `HD_DEVICE_LICENSE` 當信箱**：看片端寫申請、我們 VPN 進去簽、看片端下次啟動自己取回。不開埠、不加服務、不必在每間醫院部署主控台。傳輸改了但**私鑰仍只在原廠**——寫回去的必須是原廠簽的字串，自己塞的驗不過，那張表只是郵筒不是核准權。離線那條完整保留當備援，兩條路格式相同。
- **已完成**：`HD.Shared.Licensing`（格式／ES256 驗章／指紋四取二／**憑證鏈**，15 項機制測試）、migration `007`+`008`（已上 .191）、主控台 `/licenses`（待簽發清單＋一鍵簽發＋公鑰顯示，簽發服務 15 項測試）、看片端全套（指紋、驗簽、`%ProgramData%`、DB 信箱、閘門、`RegisterForm`）、`viewer.iss` 建授權目錄。主控台 `alpha.3` 已部署 .191。
- **⚠️ 目前是蒐集階段，`LicenseGate.Enforce = false`**：現場既有看片端全是「從來不必註冊」的狀態，一上版就擋等於自己把所有醫院鎖住。先出一版 `false` 讓清冊自動長出來 → 把在用的機器全簽掉 → 下一版才改 `true`，切換當下沒有人會被擋到。刻意是**編譯期常數**不是設定檔開關（設定檔裡放「把授權關掉」的開關比不做還糟）。
- **實作時發現的三個真問題**：①**`Win32_Processor.ProcessorId` 是型號層級的值**（實測 `178BFBFF00B60F00`），同型號機器全都一樣 → 複製到同型號的另一台會中一項而被判成「漂移→放行」，而同型號正是整批採購的常態 → 列為**弱識別**，只中它一項時當作不同機器。②主控台 `IssuedAt` 是非 nullable，pending 列一進來 Dapper 就在 materialization 炸掉，**整頁打不開**；`ORDER BY LAST_ISSUED_AT DESC` 也會把 NULL 排最前面。③換發判定原本看「這一列在不在」，但線上申請已先佔一列，第一次簽發會被記成換發 → 改看 `ISSUE_COUNT`。
- **先前實測補的三個防呆**（離線流程，仍有效）：①重複上傳同一份 `.req` 會開出多台 → 比對指紋後警告＋「改為換發這台」 ②撤銷被靜默解除 → 警告＋勾選確認 ③`existingDeviceId` 指向不存在的裝置時不能還顯示「換發」。
- **下一步**：出一版蒐集階段的看片端安裝包；把現場在用的機器簽掉之後再翻 `Enforce`。
- **系統**：HD.DicomImageViewer（客戶端）＋ HD.AdminConsole（簽發與裝置清冊）
- **要什麼**：離線、綁機器、簽章驗證的基本防護，擋「整包複製到別台就能跑」。新版 `RegisterForm` 目前是 stub（`DialogResult = Yes`），等於完全沒有保護。
- **為什麼現在做**：Keycloak／主控台尚未推到醫院端，短期內沒有其他把關手段。
- **決策**：按台授權、簽發留原廠（私鑰不進醫院、不進 repo）、預設永久、客戶端只驗簽（ECDSA P-256）、授權檔放 `%ProgramData%`（不能放版本目錄）、指紋四取二且只中一項仍放行。
- **舊版三個必修**（舊版在 `C:\Users\yang\source\repos\HD.Desktop`）：①RSA 私鑰寫死在客戶端＝可偽造 ②任一指紋變動即失效，實際發生過「韌體／OS 更新後突然不能用」 ③到期硬鎖，看片軟體不該如此。**新舊授權檔格式不相容**，換裝一律重新簽發。
- **分兩階段**：①現在＝人工帶檔案，主控台簽發＋裝置清冊 ②醫院端主控台就緒後＝內網自動收集與派發、即時撤銷；`deviceId` 沿用，現場機器不必重註冊。

### REQ-013　看片端安裝：從舊的手動安裝匯入設定
- **狀態**：**完成**（2026-08-14，實裝驗證通過）。正本 [viewer-install-design.md](viewer-install-design.md)
- **做法**：安裝精靈多一頁「沿用舊版設定」，預設帶入偵測到的舊路徑（舊 Executer 從開機自動啟動項回推，舊 Viewer 再從它設定裡的 `ViewerPath` 回推——比猜兄弟資料夾可靠，舊版是人工佈署的、位置沒規律）。舊版與現行的 `localconfig.json` **欄位結構相同**，所以整份複製比逐欄搬安全（螢幕配置那種巢狀陣列不適合字串手術），舊檔沒有的新欄位再從 `.sample` 補回去。連動服務端只搬**埠號**——`ViewerPath` 必須指向新的 `current\`，綁定位址也不能沿用舊版的 `localhost`。更新既有安裝時這一頁會跳過（設定本來就從前一版搬）。
- **順帶修掉的**：設定裡的 DISPLAY 編號在新機器上常對不上（換插孔／顯卡／擴充座都會變），原本那顆螢幕會被當成「沒有設定」→ 啟動時不開視窗、或在設定畫面被歸零，見 `MonitorPairing`。
- **要什麼**：安裝精靈多一頁，讓安裝同事指定「舊的 Viewer／Executer 資料夾」，把現場設定搬到新版。
- **為什麼**：現在只有三種情況會沿用設定——同版重跑、從本安裝程式裝的前一版升級、以及 `.sample` 預設值。**醫院現行那種「手動複製資料夾」的舊安裝不在其中**：安裝程式只會從開機自動啟動的登錄檔項目認出它在哪、移除自動啟動、停掉程序，然後告知位置請人自行刪除，**設定完全不搬**。等於每一台換過來的機器都要重打資料庫位址、DownloadIP、螢幕配置——那正是最容易打錯又最難查的幾項（打錯的症狀是「連不上」或「連到別家醫院的主機」）。
- **怎麼做**：預設帶入偵測到的舊路徑（從自動啟動那個值推回資料夾）供確認或修改；讀舊的 `localconfig.json` / `appsettings.json`，**只挑該挑的欄位**搬（資料庫位址、`DownloadHost`、螢幕配置）。**`ViewerPath` 絕對不能搬**——它必須指向新的 `current\`，搬過去會讓連動整條掛掉而且沒有錯誤訊息（2026-08-12 踩過）。舊版欄位名稱若與現行不同要做對照。
- **注意**：舊版是 .NET Framework 時代的設定格式，欄位不一定對得起來；搬不動的要明確跳過並在安裝紀錄留一行，不要靜默略過。

### REQ-014　看片端：登出回到登入畫面
- **狀態**：**完成**（2026-08-14）。影像與查詢兩個 Header 各一顆，排在「離開」左邊。
- **實作重點**：換人時不能沿用前一位的身分（會讓稽核記到錯的人）→ `LoginSession` 與 `AccessDefinition.Content` 清掉，**整顆 `ImageViewerManager` 重建**而不是逐一重設欄位（它持有十幾個子 Manager／Form，漏一個就留下殘留狀態）。`Shutdown()` 一開頭要立 `IsClosing`——`MainForm_FormClosing` 會回頭呼叫 `Exit()`，沒有旗標就會連登入視窗一起關掉、登出變成關程式。授權不隨換人重驗（綁機器不綁人）。
- **現況**：沒有「登出」。`ImageViewerManager.Exit()` 最後會 `loginForm.Close()`，而 `Application.Run(loginForm)` 是訊息迴圈的根——登入視窗一關行程就結束。所以「離開」＝關掉整個程式。
- **為什麼要做**：判讀室是共用工作站，醫師 A 看完換醫師 B 是常態，現在得整個程式重開（含重新載入設定、重建視窗、重連）。而且 `UserSettings` 會記住上一位的帳號，換人時反而容易誤用別人的身分登入——那會讓稽核紀錄記到錯的人身上。
- **要注意**：登出時要確實清掉 `LoginSession` / `AccessDefinition` / WebApi 的 cookie，否則新的人會沿用前一位的權限；已開啟的病人與影像要全部關閉；授權檢查一次就好（`LoginForm.licenseChecked`），不必每次換人重跑。

### REQ-015　授權簽發：醫院是封閉網路，簽發端與醫院 DB 碰不到彼此
- **狀態**：提出（2026-08-14，裝機前確認網路時發現）。相關 [viewer-license-design.md](viewer-license-design.md)
- **問題**：線上註冊把申請寫進**醫院自己的** `HD_DEVICE_LICENSE`，但簽發要私鑰、私鑰在 `.191`，而
  - `.191` 主控台**連不到**醫院 DB（10.10.1.148）
  - 醫院主機**不對外**（資安要求，大部分醫院都是封閉網路），連不到 `sso.ltcd.tw`
  - **只有工程師的筆電同時碰得到兩邊**（VPN 進醫院、公司網路到 .191）
- **⚠️ 連帶推翻一個既有假設**：設計文件原本寫「醫院端也會裝主控台，同一份程式碼沒有私鑰就只能檢視」。**行不通**——主控台的登入是 OIDC 導向 Keycloak，封閉網路根本走不到登入頁。要在醫院端跑，得另外給一組本機帳號（或別的離線驗證方式），那是獨立的一件事。
- **三個選項**：①主控台跑在筆電上（最快，現有程式不用改；但**私鑰要複製到筆電**，等於把簽發能力綁在個人機器上，先前已否決此性質）②**拉／簽／推**：筆電上的小工具讀醫院 DB 的待簽發產出一個檔 → 在 `.191` 主控台上傳簽發 → 把簽好的寫回醫院 DB（**私鑰始終在 .191、不綁人**，要做主控台的批次匯入匯出＋一支小工具）③純手工（測試時就是這樣做的，五到十台可行，四十台會很痛苦）
- **三個動作都不碰醫師的電腦**：拉與推都只對醫院主機的資料庫，簽在 `.191`。那台機器只在「醫師自己登入」時送出申請、「下次啟動」時取回授權——這正是當初選「DB 當信箱」的理由。
- **什麼時候要決定**：不急。蒐集階段（`Enforce = false`）不擋人，可以持續數週到數月。等清冊長出來就知道那家醫院實際幾台，**那個數字直接決定值不值得做 ②**。要簽發是「翻 Enforce 之前」的事。

### REQ-016　看片端紀錄檔：Linux 側調閱不到醫師機器的 log
- **狀態**：提出（2026-08-14）。相關 [viewer-install-design.md](viewer-install-design.md)
- **問題**：看片端的 log 只落在醫師自己的電腦上（`HDLogger` 只掛 `Serilog.Sinks.File`，安裝版寫 `{app}\logs`、Media 版寫 `%LocalAppData%`，**沒有任何網路 sink**）。要查問題得請人到那台去撈，而**我們連不到醫師的機器**（與授權那件事同一個限制）。現在連「是哪一台出問題」都不知道。
- **為什麼不能送 LoggingPlatform（.195）**：醫院是封閉網路（見 REQ-015），對外要走資安審查，每家都得談。**唯一保證連得到的是醫院自己的主機**。
- **另一個獨立理由（2026-08-17 討論）**：就算網路可通，**Debug 全量灌進 LoggingPlatform 也不該做**。兩者性質不同——伺服器 log 是**訊號**（每筆都可能要處理），看片端 Debug 是**軌跡**（一台一天數十 MB，99.9% 是一切正常的流水帳）。混在一起會同時毀掉三件事：查詢被雜訊淹沒、保留期被迫縮短、「排障第一站」的定位失效。
  → **分成兩條管道**：細流（Warning/Error＋少量關鍵事件）即時送；粗流（Debug 全文）留本機、出事才整包上傳。
- **🔑 傳輸通道定案（2026-08-17，取代原本的「寫進醫院 DB」）**：上傳到**院內 Linux 主機的 `ViewerWebApi`**（`HD.DicomImageViewer.Server`），工程師 VPN 進醫院看。
  理由：看片端的目標架構就是**只對 ViewerWebApi 與 DicomWeb 說話、不再直連 DB**（見 [systems/viewer.md](systems/viewer.md)），
  那支服務每間醫院本來就要裝（hdctl 獨立元件 `viewerapi`），所以診斷包不需要為自己另外爭取一條通道；
  而且服務端能直接把包寫成主機上的檔案，VPN 進去 `ls` 就看得到，不必從 bytea 撈出來。
- **不能只把等級調低**：使用者明確反對——現場出問題是**一次性事件**，事後才把等級調高請醫師重現，情況早就沒了，而且醫師也不會配合重跑。所以**本機維持 `Debug`**。
- **做法（環形緩衝 + 觸發式上傳）**：記憶體裡留最近 N 筆 Debug（約 2000 筆／2 MB），平常不外送；**一旦出現 Error，就把緩衝區那段連同錯誤一起寫進醫院 DB**，並讓接下來 60 秒的 Debug 也放行（事發之後的反應同樣有資訊）。結果：平常幾乎不送東西，出事時 Linux 側拿到的是**可以還原當時操作序列**的一段，而不只是一句「有錯」。
- **⚠️ 程式當掉怎麼辦（2026-08-17 定案）**：**不要在崩潰當下上傳**。程序正在死的時候能做的事極少，網路 IO 很可能來不及、或再炸一次把原始錯誤蓋掉。拆兩段：
  1. **當下只留記號**（要快、不能失敗）：掛 `Application.ThreadException` ＋ `AppDomain.UnhandledException`，只寫一個小的崩潰標記檔（例外內容、時間、當時的 log 檔名），然後讓它死。
  2. **下次啟動才上傳**：看到標記 → 打包那段時間的 log 送出 → 清掉標記。
  - 這樣還順便解掉更難抓的一種：**程序被砍／當機／斷電**——連 handler 都不會跑。作法是啟動寫「執行中」標記、正常關閉清掉；**下次啟動發現標記還在＝上次不是正常結束**，一樣打包上傳（dirty-shutdown 偵測）。
  - 合起來覆蓋：未處理例外 ✅ 程序被殺 ✅ 藍屏／斷電 ✅，且都不必在最脆弱的那一刻做複雜的事。
- **觸發方式**：①崩潰／不正常結束自動（上述）②醫師手動「回報問題」＋填一句描述——**那句描述最值錢**，現在最難的是知道發生了什麼事，不是拿到 log ③工程師遠端標記某台機器下次啟動上傳。
- **⚠️ 個資**：log 裡會有病人姓名／病歷號（查詢與開檢查的軌跡必然帶 PatientID／AccessionNumber）。**診斷包只停在醫院主機**＝資料沒出院，跟工程師到現場看是同一個層級，阻力最小；**若日後要自動傳回公司**那是資料外流，需要醫院同意、可能要去識別化，難度完全不同。schema 要不要留遮蔽欄位，取決於這個選擇。
- **要控三件事**：單包大小上限（超過就截斷最舊的）、保留期自動清、頻率限制（同一台一天最多幾包，防止壞掉的機器狂送）。
- **已先做的**：紀錄檔保留 90 天 → **30 天**（三支都改，`fa37978`）。90 個檔 × 49 MB 最壞 4.4 GB，醫師電腦不一定有那個空間。
- **✅ 第一階段完成（2026-08-17，趕在 8/18 裝機前）**：**先做「拿得到」、不做自動上傳**。理由是那天要裝的是已實機驗證過的 `2.4.0`，再往啟動路徑塞伺服器端相依等於把驗證作廢，而裝機當天出問題的代價遠大於少一套自動上傳。交付兩項，都**只寫本機檔案、不碰網路、不碰登入流程**：
  1. **「匯出診斷包」按鈕**（`Core/Diagnostics/DiagnosticPackage.cs`，掛在「關於」視窗）：logs＋事故記錄＋設定檔＋環境資訊＋使用者描述 → 一個 zip。環境資訊直接重用「關於」視窗已收集的那份（`BuildReport()`），不另寫一套會走樣的來源。
  2. **事故標記**（`Core/Diagnostics/SessionMarker.cs`＋`Program.HookCrashHandlers`）：未處理例外當下只寫記號；啟動寫「執行中」、正常關閉清掉，**下次啟動發現記號還在＝上次不正常結束**（涵蓋被砍／當機／斷電這種連 handler 都不會跑的情況）。
  - **意外的加分**：三支程式（Viewer／Executer／LinkClient）安裝時**共用同一個 log 目錄**，所以診斷包自動涵蓋 Executer 的紀錄——連動問題最關鍵的那份。
  - **實作要點**：①今天的 log 檔正被 Serilog 開著寫，必須明講 `FileShare.ReadWrite` 才讀得到（而它正是最需要收的一個）②`localconfig.json` 有**資料庫密碼**，用「欄位名看起來像密碼就遮」而非列舉已知欄位（設定檔會長出新欄位，漏一個就是把密碼寄出去）③紀錄檔總量上限 60 MB、由新到舊收 ④打包走背景執行緒（同步會凍住視窗）⑤掛上 `Application.ThreadException` 後 WinForms 就不再顯示內建錯誤對話框，所以自己叫出同一個 `ThreadExceptionDialog` 並照樣處理「結束」，**目的是多記一筆事故、不是改變使用者看到的行為**。
  - **驗證**：機制測試 21 項全過（含「正被寫入的 log 收得進去且內容完整」「密碼與巢狀 apiKey 都被遮蔽」）；「關於」視窗版面截圖確認三顆按鈕沒擠壞、既有按鈕位置未變；**用實際出貨的 binary 端到端跑過**「啟動→強制砍掉→再啟動」，正確產生不正常結束的事故記錄。
  - **打包**：`HD.DicomImageViewer_Setup_2.4.0.exe`／`2.4.0+20260817-121900+0800`（版本號不動，依規約靠 build 時間戳區分——2.4.0 尚未交付現場）。
- **第二階段（之後）**：上傳到院內 ViewerWebApi。收集與打包的邏輯**刻意跟出口分開**，屆時同一份包直接送上去，`DiagnosticPackage` 一行都不用改；而且「存成檔案」仍是必要退路（封閉網路、服務沒起來、版本對不上時總得有辦法把包弄出來）。環形緩衝＋Error 觸發那套設計也留到那時一起做。
- **參數什麼時候定**：8/18 那台裝上去之後會第一次拿到**真實的 log 量與錯誤樣態**，那時候再定「送什麼、留多久、緩衝多大」會準得多；現在定等於用猜的。

### REQ-017　NuGet 套件已知弱點（NU1903）
- **狀態**：**全部處理完畢（2026-08-18）**。八個 repo 掃下來零弱點，唯一例外是 `HD.Animal`（專案擱置、未來可能不再使用，故不動）。
- **怎麼發現的**：`HD.Export` 建置時的 `NU1903` 警告（`Microsoft.OpenApi 2.0.0` 高嚴重性）。**警告不會擋建置，所以很容易一直被忽略**——順手把所有 repo 掃了一遍才發現不只一處。
- **掃描方式**（值得定期跑，每個 repo）：
  ```
  dotnet list package --vulnerable --include-transitive
  ```
- **✅ 已修（都是「傳遞相依或純 pin」＝不動程式碼、風險低）**：
  | repo | 動作 |
  |---|---|
  | HD.Export | `Microsoft.AspNetCore.OpenApi` 10.0.7 → **10.0.11**（連帶解掉傳遞的 `Microsoft.OpenApi 2.0.0`） |
  | HD.Pacs.DicomWeb | 同上；`Microsoft.Data.Sqlite` 9.0.6 → **10.0.11**（解傳遞的 `SQLitePCLRaw`，順帶對齊 net10）；`System.Security.Cryptography.Xml` 10.0.6 → **10.0.11** |
  - `Cryptography.Xml` 那行**本來就是上一輪為修弱點而加的顯式 pin**（csproj 註解寫著 CVE-2026-33116 等），程式碼沒有用到它的 API（無 `SignedXml`／`EncryptedXml`），所以升 patch 沒有行為風險。
  - **驗證**：DicomWeb 單元 **87/87**、整合 **31/31**；Export 實跑 `/health` 與 `/openapi/v1.json` 確認 schema 未受影響。⚠️ 過程中整合測試一度 24 失敗，是**連不到 .191 的 DB**（逾時 15 秒→500），不是升版造成——DB 通了之後 31/31、18 秒跑完。判斷這類失敗要先看「失敗數與耗時的形狀」。
  - **尚未部署**：三支都還沒上生產，下次部署時一起帶上。
- **✅ SSH.NET（High）→ 移除，不是升版**（2026-08-18，HD.Net10 `80a0cee`）
  - 弱點 `GHSA-q939-rpr3-3284` 在 **`ScpClient.Download()`** 的遞迴目錄下載（不驗證伺服器回傳的檔名，惡意 SCP 伺服器可用 `../` 寫到目錄外）。**整個 codebase 沒有任何一處用 `ScpClient`**，實際暴露是零。
  - 更關鍵的是**先前的認定有誤**：這個套件在 `HD.Net10` 根本沒被使用。唯一引用是 `Tools/SftpClientExtension.cs` 的 `CreateDirectoryRecursively`，它**沒有任何呼叫點**；`GatewaySetting.cs` 的 `GatewaySftp` 也沒有讀取者。原記錄寫的「主 PACS 的 SFTP 傳輸／`DicomTransmitService`」不成立——`DicomTransmitService` 沒有碰 SSH.NET。
  - 所以處置是移除 `PackageReference` + 刪掉那支死碼。`HD.csproj` 被九支服務參考，一次清掉九支的 NU1903，且**零回歸風險**。`GatewaySetting.cs` 保留（純 POCO、不依賴該套件）。
- **✅ Magick.NET 14.14.0 → 14.16.0**（2026-08-18，同 repo）
  - 14.14.0 累積 **29 個 advisory**（11 中、18 低）。用途只有一處：`HD.DicomTransmit` 的 Encapsulated PDF 轉圖（`pdfToImage`），用到 `MagickReadSettings`／`Density`／`MagickImageCollection.Read`／`Scale`／`Alpha`／`Write(Jpg)`。
  - **回歸用實測而非推論排除**：①那組 API 在新版編譯無變動 ②兩版產生的 Ghostscript 命令列**逐字相同** ③以真實 CT 影像跑完整 `Scale`＋`Alpha`＋JPEG 編碼路徑，輸出**像素逐位元相同**。
  - 比對要比**解碼後的像素**：PNG 檔案位元組會因 ImageMagick 寫入時間戳而每次不同，直接比檔案 SHA 會誤判成「版本有差異」（我一開始就誤判了一次）。
  - **重要副產物**：ImageMagick 的 PDF 是**委派給外部 Ghostscript**（實測 `gswin64c.exe` exit 127 現形）。套件升版不改變這件事——**主機沒裝 gs，`pdfToImage` 本來就不會動**，與版本無關。要確認生產主機是否具備。
- **建議**：把上面那條 `dotnet list package --vulnerable` 納入發版前檢查（或 CI），否則 `NU1903` 這種「不擋建置的警告」會累積到沒人記得為什麼在那裡。

---

## 已完成（近期）
- **看片端 2.4.0 重打包**（2026-08-14，`0bd4c32` / `2.4.0+20260814-175614+0800`）——出貨用這一顆，先前 `c571782` 那顆作廢。**已在測試機實機安裝驗證通過**。
  - **設定頁在直式螢幕（醫院常見）沒鋪滿**，關閉鈕卡在半空中、右半邊按不到。三件互相獨立的事：①Designer 的 `WindowState=Maximized` 讓表單永遠停在主螢幕的最大化尺寸（`TopLevel=false` 重建 handle，底層仍帶 `WS_MAXIMIZE`，狀態被寫回 Maximized，而 Maximized 的表單設 `Size` 只會存進 restore bounds）②`AutoScroll` 不把停靠的子控制項算進捲動範圍，子頁 `Dock=Fill` 就永遠捲不動（加 `MinimumSize` 也沒用，三種寫法都實測過）③`Ctrl+滾輪` 用 `Control.Scale()`，會連表單自己的 Bounds 一起縮，嵌入式表單就縮成畫面一角。
  - 自動字體倍率原本用**螢幕高度**估像素密度，直立擺放的螢幕會被誤判成 1.78 倍；改取**短邊**（直放 FHD 仍是 1.0、4K 不論橫直都是 2.0）。`GetAutoScale` 也改由呼叫端傳 MainForm 進來——建構當下表單還沒掛進容器，一律問到主螢幕。
  - **UI**：設定頁頂部加上與查詢、影像同一條 `AppHeaderBar`，「關閉」做成它上面的功能鍵（三個畫面頂端一致）；導覽欄欄寬 330→365；工具列換行變寬時「版面調整」鍵跟著加寬（並限制 icon 上限，否則圖示會暴增到一百多 px）。
  - **新增「關於」視窗**（公司／軟體版本／授權開通／登入帳號權限／連線與環境），掛在兩個 header 的「設定」右邊。授權那段用掛勾由啟動專案餵進來，且**只讀本機檔案不連 DB**——這個視窗最常在網路不通時被打開。有「複製資訊」可整頁貼成純文字回報。操作手冊按鈕已預留（`AboutForm.ManualLocation` 有值才出現）。
  - **全新使用者的工具列**已用 `.163` 實測確認：沒有自己設定時 `get_user_config` 會退到群組再退到系統 DEFAULT，而現場 DEFAULT 是舊格式 → 走自動轉換拿到醫院那 36 個工具（不是內建的 21 個）；連 DEFAULT 都沒有才套內建預設。
- **看片端 2.4.0 出貨版就緒**（2026-08-14，`c571782` / `2.4.0+20260814-151024+0800`）。這一版動到登入路徑、啟動流程與三個設定頁，**第一台裝完要走完整圈冒煙測試**（登入→查詢→開片→登出→再登入）再裝其他台。
  - **可靠性**：授權檢查連例外都放行；連線層失敗自動重試一次（`SafePostgresConnection.RunRead`，只給讀取用）；登入失敗訊息分清「連不到主機」與「帳密錯」且改為 1.5 秒 TCP 探測（原本等 21 秒）；**移除直連資料庫的登入路徑**（⇒ `DownloadHost` 變必填）。
  - **升級相容**：安裝時匯入舊手動安裝的設定（REQ-013）；舊版分組工具列自動轉新格式；螢幕名稱變動不再毀掉配置（`MonitorPairing`）。
  - **功能**：登出（REQ-014）；紀錄檔保留 90→30 天。
  - **UI**：Header 分隔線；快捷工具設定三欄化；標題列設定去框中框；區塊樣式抽 `SettingsPanelTheme` 共用。
  - **順手修掉的既有地雷**（都不是這次改出來的，但都會在現場出事）：①改變視窗大小會把快捷工具已放好的工具清掉（`CreateGrid` 重建 Items，`OnResize` 會呼叫它）②`ApplyData` 對著空清單塞工具，靠「格數剛好不同」矇混 ③連不到主機時跳「使用者登入錯誤」④工具列與快捷工具各留一份樣式碼。
- **看片端安裝包實機試裝驗證通過**（2026-08-13，commit `aefee59`）：以 2.3.0→2.3.1 實際跑過安裝／更新／退版／解除安裝。通過項目：`current` 為真 junction、Run 項目指向 `current\`（更新退版都不必改）、防火牆規則（TCP 5002／LocalSubnet，埠號從 Executer 設定讀出而非寫死，先刪再加所以更新後仍只有一條）、`ViewerPath` 寫入與跳脫、**更新不掉設定**（三個設定檔的植入值全數搬移）、退版（`current` 與註冊表同步回退、讀到的是該版當時的設定）、重裝不覆蓋現場的 `ExecuterUrl`。**試裝中抓到兩個 bug 並修掉**：①Executer 的 `WebApplication.CreateBuilder()` 以工作目錄為 ContentRoot，開機自啟時工作目錄是 `C:\Windows\system32`，找不到 `appsettings.json` → 退回 `localhost:5000`／`ViewerPath` 為 null／完全沒有 log，且全部靜默——**等於開機自啟整個是壞的**；②解除安裝用 `uninsdeletevalue` 只刪值、留下空機碼。修後以「註冊表命令 + 工作目錄 system32」重測，正確綁 `0.0.0.0:5002` 且以一般使用者權限寫入 log（驗證 icacls 授權有效）。
- **三支的紀錄檔位置改由安裝時指定**（同上 commit）：預設 `{app}\logs`（在版本資料夾外，更新與清理舊版都不影響），記入註冊表供更新沿用，並以 icacls 授權 Users 寫入；Executer 因有執行期設定介面，只在設定為新建立時才寫。
- **看片端三支的 log 路徑不再是單點故障**（2026-08-13，commit `048b990` + `c2967e5`）：出貨設定的 log 路徑寫的是我們機器的磁碟（Executer `D:\HyperDigital\...`、Viewer 開發機的 `D:\Dev\logs\`），醫師與 HIS 的電腦不一定有 D 槽。三支的壞法各不相同且都沒有線索指向 log：Executer 例外被 `Form1_Load` 的 try 吞掉→「圖示在、服務死」；Viewer 走到 `HDLogger.Initialize(null)`→**完全不產生 log**；LinkClient 直接開不起來。改成建 logger 前先確認目錄寫得進去，寫不進去退到 exe 旁 `logs\`（只換目錄、保留檔名）。另修 `DicomQuery` 自開的查詢 sink：路徑 `..\logs\` 相對工作目錄、在版本化安裝下落在 `current\logs\` 會被清舊版刪掉，且 static 欄位初始化失敗會讓第一次查詢丟 `TypeInitializationException`；改為與主 log 同目錄（`HDLogger.LogDirectory`）+ 延後建立 + 失敗收斂成 `Logger.None`。
- **主 PACS A2 coerce（媒體出口）驗證通過**（.191，2026-08-04）：DB 校正疊進燒錄輸出、原檔不變。
- **主 PACS B 日誌驗證通過**（.191）：ClientIp/User 正確帶入。
- **LoggingPlatform ClefParser `@l` 缺漏誤判 Verbose bug 修正**（待部署 .195）。
- WADO-URI anonymize 改金鑰驅動、fail-safe 403（DicomWeb，commit 43426d5，已上 .199）。
- QIDO 效能索引 A（RC_STUDY STUDY_DATE，已建 .234）。

---

## 擱置 / 取消
- （無）

## 動物醫院總主機（2026-08-10 方向宣告，未排程）
.191 架設完成後複製 VM → 獸醫總主機；全院影像集中匯入；新版 DicomWebViewer 依 HospitalName 控管顯示（舊制一院一 DB → 集中單 DB）。開工前要定的六個設計決策見記憶 project_animal_central_host（院別歸屬正本＝上傳憑證非 InstitutionName、server 端強制過濾、穩定院別代碼、單 DB 取捨、VM 複製 checklist、存量匯入路徑）。
