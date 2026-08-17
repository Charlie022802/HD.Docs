# 進檔瘦身實作規劃（REQ-006 / 007 / 008）

> 承接 A3（REQ-001「原始檔不可變 + 出口疊合」）。目標:進檔階段拿掉已不需要的副產物與預轉流程。
> 狀態:**規劃（2026-08-04）**。部署照 [environments.md](environments.md):.191 測試、.234 暫緩。

## 決策紀錄（2026-08-04）
- **REQ-008**:~~保留 MPEG4 預轉~~ → **翻案:移除 DicomToVideo/MPEG4 預轉（2026-08-05）**。
  - **翻案理由**:當年做 DICOM_TO_VIDEO→dicomMpeg4 的唯一目的是「舊 DicomWebViewer 拿不到 frame」;經確認 **(a) 新 DicomWeb 的 frames 端點能逐格取真實多幀資料**（.191 實測 454 幀 instance,frames/1 裸像素 + 頭/中/尾 rendered 皆 200 JPEG）、**(b) dicomMpeg4 只有舊 viewer 用、無其他消費者**（使用者確認）。→ 保留的兩個殘留價值(frame 存取、外部消費者)都不成立。
  - **移除做法(同 REQ-007 route A,低風險)**:`insert_dicom_info` 讓 `mpeg4`/`dicomMpeg4` 一律標 `'N'`、不 enqueue DICOM_TO_VIDEO(video 分支比照 jpeg 分支處理);`check_nearline_cache` 的 `mpeg4 IS NULL OR dicomMpeg4 IS NULL` 因變 `'N'` 非 null 自然放行,gate 不用動;下架 `hd-dicom-to-video`(DicomToVideoService + VideoToDicomMpegService)、slnx 移除。`DicomPACSService` 的 MPEG4 傳輸語法支援保留(無害,只是不再有 dicomMpeg4 物件);`export.insert_package_job` 讀 `mpeg4='N'` 的過濾維持有效。邊路徑(resend/restore/archive_decompress 的 DICOM_TO_VIDEO/VIDEO_TO_DICOMMPEG4 enqueue)同法停用。
- **REQ-007**:**完整移除** DicomToImage。**JPEG 政策(2026-08-04 更新):今後取 JPEG 一律走新的 DicomWeb(WADO-RS rendered,即時 render),不再預生、不再各消費端吃預生檔。**
  - PACS/DB 端(本案範圍,先做):停止預生 JPEG + enqueue DICOM_TO_IMAGE、拆 3 處 jpeg gate、下架 `hd-dicom-to-image`、清死碼。
  - 消費端遷移(**脫鉤、日後各自做,不卡本案**):`HD.DicomImageViewer`(縮圖/預覽)、`HD.MediaPackage`(燒錄)、`viewer_station.*`/`wadouri_query` 的 `CacheJpegPath` 等,改為向 DicomWeb 取 JPEG。移除後、遷移前,這些消費端在該台會暫時拿不到預生 JPEG(.191 測試可接受;.234 正式暫緩)。
  - ⚠️ 連帶:JPEG 需求全導向 DicomWeb 後,**REQ-004(DicomWeb 縮圖無快取、每次即時 render)** 的重要性上升,宜一併排入。
- **動工順序**:REQ-006 ✅ → REQ-007 PACS/DB 端 ✅ → REQ-008 移除 video 預轉 ✅（2026-08-05，Database `2449d2a` + HD.Net10 `81d56a6`；待 .191 套 proc）。**進檔瘦身 REQ-006/007/008 全數完成。**

## 0. 共通原則

- **兩軸改動**:C#（`HD.Net10`,git repo 在 `HD.Net10/`）+ DB（HDPACS,SQL 正本 `D:\Dev\HyperDigital\Database\`、發布走環境包 `D:\HD-Release\environment\sql\`）。
- **DB 改動一律 append-only**:新增 `db_update_v2.0.(N+1).sql`,內容用 `CREATE OR REPLACE FUNCTION` 重定義要改的 proc;**永不編輯已發布的舊 db_update 檔**(否則已套用的 DB 會漂移)。既有 DB 只補跑新增檔。
- **驗證環境**:.191(本機 DB、可全測)。每項改完先在 .191 驗,再視情況上正式。

---

## REQ-006　進檔不再存 `.meta` — ✅ 完成（2026-08-04，.191 驗證通過）
> HD.Net10 `17de498` + HD.Pacs.DicomWeb `8fb0562`。.191 C-STORE 新影像不再產 .meta（總數不變）。

### 現況
- `.meta` = C-STORE / STOW 進檔時,在 DICOM 主檔旁寫的「去掉 PixelData + private tags 的純 metadata DICOM 副本」。
- **產生點(2 處)**:
  - `HD/DicomCore/DicomStoreProcess.cs:120` → `SaveMetaFile`(路徑定義 `DicomStoreProcess.FileIO.cs:23`、內容處理 `Validation.cs:50 GetMetaInfo`)。
  - `HD.Pacs.DicomWeb` `HdPacsStowService.cs:203-207`（`BuildMetaFile`）— DICOMweb STOW 進檔。
- **讀取點:0 處**。全 solution + DB 無任何流程解析 `.meta` 還原 metadata（DICOMweb metadata 走 DB `MetadataJson` 欄位;PACS 走進檔時的 `InsertToDatabase`）。DB 對 `.meta` 零依賴（SQL 全檔 0 命中）。→ **純「只寫不讀」保險副本,可安全停產**。

### 改動清單（純 C#,無 DB）
1. **停止產生**:
   - `DicomStoreProcess.cs:120` 移除 `SaveMetaFile(...)` 呼叫(及 `FileIO.cs:28 SaveMetaFile`、`FileIO.cs:23` Meta 路徑、`Validation.cs GetMetaInfo` 若無他用一併清)。
   - `HdPacsStowService.cs:203-207` 移除 `.meta` 寫出(及 `BuildMetaFile`)。
2. **修下游「沒有 `.Exists` 保護」的消費點**（停產後對新進物件會丟 `FileNotFoundException`）:
   - `HD.ArchiveManager` `Blob.cs:81`（`ArchiveCompressService` 打包時 `File.ReadAllBytes`,無檢查）→ 改成不再把 `.meta` 加入待壓縮清單（`ArchiveCompressService.cs:241`）。
   - `HD.ArchiveManager` `ArchiveUploadService.cs BackupFile:100`（`File.Copy` 無檢查）→ 停止複製 `.meta`（呼叫點 `:68`）。
3. **已有 `.Exists` 保護、可不動**（缺檔自動略過）:NearlineBackup、CacheDelete、Compress 的 size 計算/刪除、進檔 error 回滾（`FileIO.cs:128 SafeDelete`）、STOW 回滾（`HdPacsStowService.cs:267`）。

### 風險 / 驗證
- 舊資料既存的 `.meta`:留著無害(沒人讀),不必回頭清;要清可另開一次性工具。
- **archive decompress 從 blob 還原 `.meta`**（`ArchiveDecompressService.cs:108`）:舊 blob 內含 `.meta` → 解壓照樣還原,不影響;新 blob 不再含 `.meta`（因 #2 改動）→ 也沒問題。
- 驗證:.191 進一批新影像 → 確認磁碟旁**不再產生** `.meta`、DB metadata 正常、archive compress/upload 該批不報缺檔。

---

## REQ-007　移除 DicomToImage（進檔預轉 JPEG）— ✅ PACS/DB 端完成（2026-08-04，.191 驗證通過）
> route A。C# `HD.Net10 86ef7bd`（下架 HD.DicomToImage + 清死碼）+ DB（insert_dicom_info 一律 jpeg='N'、不 enqueue DICOM_TO_IMAGE，gate 不動）。
> .191 驗證：migration 已套 + toJpeg=true 下 C-STORE 新影像 → jpeg='N'、零 DICOM_TO_IMAGE job。
> **消費端（2026-08-04 釐清 — 併入更大範圍取代，非原地修補）**：
> - `HD.DicomImageViewer`：**線上版不可動**，JPEG 改接 DicomWeb 要在**另開的新專案**（平行版）做 → 獨立/未來軌。
> - `HD.MediaPackage`：**整支待淘汰**，全面改成 **Export WebApi**（= backlog REQ-003）；JPEG 消費隨整支被取代，不單獨遷移。
> - `viewer_station.*` / `wadouri_query` 的 `CacheJpegPath`：現行 JPEG 由 **`hd-web-server`（legacy Node web）** 讀預生 `.jpg` 供給。方向=**全面改去 HDDicomWeb**（即時 render）。
> - **REQ-004 DicomWeb 縮圖快取**：JPEG 全導 DicomWeb 後重要性上升；且原「選項2 吃 hd-dicom-to-image 的 .jpg」**已死**（該服務已移除），只剩「選項1 加縮圖快取」。
>
> ### ⚠️ 硬相依（新版 rollout 前提）
> REQ-007 停掉預生 JPEG 後，`hd-web-server` 對**新資料無 `.jpg` 可讀** → 「新版 HD.Net10（含 REQ-006/007）上線」必須與「影像供給改由 HDDicomWeb」**同步**，否則舊 web 縮圖/預覽開天窗。生產 `.234` 保留舊版故**暫無影響**；正式 rollout 時務必一併切換影像來源到 DicomWeb（並先做 REQ-004 快取讓 DicomWeb 供圖夠快）。
> **migration 位置**：併入**開著未結案**的本地 canonical `Database/HDPACS/db_update_sql/db_update_v2.0.27.sql`（2.0.27 為當前開放版本桶，累積多筆帶日期變更；REQ-007 加在尾）。`DB版本.xlsx` 2.0.27 分頁同步加一列。環境包 `HD-Release/environment/sql/` 仍停在 26，需另行同步至 canonical。
> **待辦**：resend_convert_dicom_job / restore / archive_decompress 的 DICOM_TO_IMAGE enqueue 為邊路徑（archive 場景才觸發），日後同法停用。

### 現況（重要:分實際生效 vs 死碼）
- **實際生效**:進檔 `insert_dicom_info` 在 DB 內 enqueue `DICOM_TO_IMAGE` map job → 獨立服務 `HD.DicomToImage` 消費、寫出 `cacheLocation/JPEG/…jpg` → job 完成時 `update_map_job_status` 呼叫 `update_object_convert_status('DICOM_TO_IMAGE',…,'Y')` 把 `CONVERT_STATUS->>'jpeg'` 設 `'Y'`。
- **死碼**:`DicomStoreProcess.cs:289 ImageProcess()` + 整個 `HD/ImageConvert.cs`（進檔端同步產 JPEG）**全 repo 從未被呼叫**,但屬移除範圍。

### ⚠️ 與 A3 的核心相依 — jpeg gate（必改,否則 STUDY_CLOSE 卡死）
移除預轉後,`jpeg` 這個 key 不會再有人設成 `'Y'`、會永遠停在 `null`。所有「`jpeg IS NULL` → 擋」的地方都要改:
| 位置 | 現行邏輯 | 改法 |
|---|---|---|
| `get_next_map_job` `12756-12765` | STUDY_CLOSE:該 study 有任一 `jpeg IS NULL` 就不放行 | **移除整段 `AND (...)` 條件**（就是 .191 靠 `toJpeg=false` 繞過的那關） |
| `check_map_job_enable` `10255-10265` | STUDY_CLOSE 分支需 `jpeg IS NULL` count=0 | 移除 jpeg 條件（或該分支直接回 TRUE） |
| `check_nearline_cache` `10329-10334` | `jpeg IS NULL OR mpeg4 IS NULL OR dicomMpeg4 IS NULL` | **只移除 `jpeg IS NULL`**,保留 mpeg4/dicomMpeg4（REQ-008） |

### DB 改動清單（新 `db_update`,`CREATE OR REPLACE`）
| # | proc（行號） | 動作 |
|---|---|---|
| 1 | `insert_dicom_info` 16027-16036（讀 toJpeg 15755） | 移除 `DICOM_TO_IMAGE` enqueue 分支;**保留 video 分支**（見 REQ-008） |
| 2 | `insert_dicom_info` 15962-15963 / 15981-15985 | `CONVERT_STATUS` 初始化移除 `'jpeg'` key（或保留但不再當 gate;建議直接不 init jpeg） |
| 3 | `update_object_convert_status` 27262（27269-27276） | 移除 `DICOM_TO_IMAGE` / `jpeg` 分支 |
| 4 | `get_next_map_job` 12756-12765 | **必改**（見上表） |
| 5 | `get_next_map_job` 12962 / 13134-13143 | 清 `DICOM_TO_IMAGE` 前置條件與 pdfToImage options |
| 6 | `check_map_job_enable` 10255-10265 | **必改**（見上表） |
| 7 | `check_nearline_cache` 10329-10334 | **必改**:只拿掉 jpeg 分支 |
| 8 | `admin.resend_convert_dicom_job` 4034/4050、restore 分支 9720-9744、`archive_decompress` 9730-9745 | 移除 `DICOM_TO_IMAGE` enqueue（保留 video） |
| 9 | `insert_job_queue` 16302-16305、`get_next_map_job` 12711（maxJobCount） | 可選:清 `DICOM_TO_IMAGE` 佇列路由 |
| 10 | config 模板 `insert_update_ae_main` 17256 / remote 33271 | 移除 `toJpeg` 欄位（或留 no-op） |

### C# 改動
1. **下架整個 `HD.DicomToImage` 專案**（`HD.Net10.slnx` 移除;部署服務清單本就不含它,install 腳本確認無 `hd-dicom-to-image`)。
2. **刪死碼**:`DicomStoreProcess.cs:289 ImageProcess()`、`HD/ImageConvert.cs`、`DicomStoreProcess.Database.cs:112 UpdateObjectConvertStatus`（若僅死碼用）、`FileIO.cs:21` Jpeg 路徑。
3. **⚠️ 預生 JPEG 消費端改成容忍缺檔 / 改走即時**（見下「決策點」）。

### ⚠️ 決策點 — 預生 JPEG 的消費者不只舊 HDWeb
盤點發現靠 `cacheLocation/JPEG/*.jpg`（`get_object_path(...,'Jpeg')`）的還有**現役產品**:
- **DB 入口**:`wadouri_query`（WADO-URI 回 JPG,28399-28401）、`viewer_station.get_study_elements` / `_v1` / `get_tree`（回 `CacheJpegPath`,31168/31421/31749）。
- **桌面 viewer `HD.DicomImageViewer`（現役）**:`ObjectElement.cs:47 LocalJpegPath`——`CacheJpegPath` 為 null 就回 null;`PreviewJpegLoader`/`PreviewForm`/`DownloadFileManager` 下載伺服器預生 JPEG 當預覽/縮圖快取。
- **`HD.MediaPackage`（現役）**:`PackageService.cs:696/731` 燒錄時帶 `CacheJpegPath`。
- **不受影響**:`HD.Pacs.DicomWeb` rendered WADO-RS、`HD.PACS` rendered——都是即時從 DICOM 算 image/jpeg,不吃預生檔。

→ 因此「移除 DicomToImage」不是只切舊 HDWeb,而是要讓 **桌面 viewer 預覽/縮圖 + 媒體燒錄**改走「即時 render 產 JPEG」或「無 JPEG 時 fallback」。**動工前必做**:確認並實作這兩者的 fallback（viewer 少了 `LocalJpegPath` 是否自動改本地 render 縮圖;MediaPackage 少了 `CacheJpegPath` 燒錄是否可即時產或略過）。這是 REQ-007 的最大工作量與風險,不在原始「舊 web 不需要」的認知內。

### 不動（重要澄清）
- **`deleteOriginDcm`**（`get_multiframe_delete_list` 12405 / `update_multiframe_delete_job` 27209）:是**多幀原檔清理**機制,受 system config `deleteMultiFrameSource`（預設 **off**）控管,配合 MPEG4 轉檔、**與 jpeg 無關**。移除 DicomToImage **不會刪任何原始 DICOM**。（若要「原檔絕對不可變」,可另案確認各佈署 `deleteMultiFrameSource.enable=false`。）

---

## REQ-008　DicomToVideo（MPEG4）去留 — 待討論

### 現況
- `DicomToVideoService`（消費 `DICOM_TO_VIDEO`,多幀 DICOM → `MPEG4/{name}.mp4`）→ `VideoToDicomMpegService`（消費 `VIDEO_TO_DICOMMPEG4`,`.mp4` → DICOM 封裝 MPEG4,即 `dicomMpeg4` 產物）。
- **`dicomMpeg4` 被檢索直接消費**:`HD.PACS DicomPACSService.cs:54-55` 對外 C-STORE/C-MOVE 的支援語法含 `MPEG4AVCH264HighProfileLevel41` → 外部 viewer/PACS 直接吃這個**預轉**檔。nearline/archive/媒體燒錄也消費。

### 建議:**保留預轉**
- 檢索（C-MOVE 送檔）當下要能回 MPEG4;即時轉大檔多幀會拖垮回應。dicomMpeg4 是被動消費的預轉產物,傾向保留。若日後要改即時,需另設計檢索時同步轉的機制(風險高)。

### 拆 REQ-007（jpeg）時「保護 video」的具體位置
- DB:`check_nearline_cache` 10332-10334（只動 jpeg 那行）、`insert_dicom_info` 16027-16053 的 if/else（拆 image 分支、留 video 分支）、`get_next_map_job` 12766-12767（video gate,**保留**）、`export.insert_package_job` 6693（讀 `mpeg4='N'`,**不要誤動**）。
- C#:`DicomStoreProcess.cs:298-299 & 319-335`、`DicomToImageService.cs:118-120`——當物件已是 MPEG4 時,舊 jpeg 流程會用 ffmpeg 抽首幀產 jpg（jpeg 縮圖依賴 video 資料）。這段在被移除的 jpeg 流程內,移除即消失,不影響 video 本身產出。

### 待確認
- 到底哪個 viewer / 流程在吃 MP4（裸 mp4 vs dicomMpeg4）→ 決定是否真的必須保留、或部分可即時。

---

## 相依與建議順序

1. **REQ-006 先做**——最獨立、純 C#、無 DB、無讀取風險。快速見效。
2. **REQ-008 先拍板（建議保留預轉)**——因為 REQ-007 拆 jpeg 的多處 DB/C# 與 video 交纏,得先確定 video 保留,才能安全地「只拆 jpeg」。
3. **REQ-007 最後、且分兩半**:
   - (a) **消費端 fallback**（桌面 viewer 縮圖 + MediaPackage 改即時/容忍缺檔)——**這是前置,先做並驗證**,否則移除伺服器端 JPEG 會弄壞現役 viewer/燒錄。
   - (b) DB gate 移除 + `DICOM_TO_IMAGE` enqueue 移除 + `HD.DicomToImage` 下架 + 死碼清除。

## 待辦入口
見 [todo.md](todo.md) 與 backlog REQ-006/007/008、記憶 `project_intake_slimming`。
