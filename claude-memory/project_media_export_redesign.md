---
name: project_media_export_redesign
description: "媒體匯出/燒錄重新設計—新四張表(PACKAGE_JOB/SELECTION/ITEM/DISC)+新proc,legacy完全不動;起因Viewer要用UID選影像+Kiosk要重構;archive流程淘汰"
metadata: 
  node_type: memory
  type: project
  originSessionId: ea8648ec-751b-449c-aab0-36db86e8c1e2
  modified: 2026-08-17T14:03:39.360Z
---

**🔑 打包進度回寫完成(REQ-018,pacs `2.0.11`,2026-08-18)。管線本來就通,缺的只有迴圈裡的呼叫點。**
三個取捨:節流每 5%(`UpdateJobStatus` 每次都 new 連線,744 張逐張寫=744 次連線)、兩種輸出**合併計算**(否則進度條跑兩次 0→100)、回寫**自己包 try**(那幾行在外層 catch 保護範圍內,不吞例外的話一次暫時性 DB 錯誤就讓整包標成 failed)。

**⚠️ 這次最該記的是驗證,不是功能。** 第一版**四項斷言全綠但功能實質沒達成目的**:同一方法裡有**兩條 JPEG 產出路徑**,不燒字那條(現場實際走的,因 HD_CONFIG 沒有燒字設定)存檔後直接 `continue`,**跳過迴圈尾巴的 `ReportProgress()`**。744 張 JPEG 全程零回報,之後 DICOM 才貢獻 744 單位→進度停在 50%。
- 壞版本一樣通過「有中間值/單調遞增/上限99/最終100」。**差別只在時間軸**:首個進度在第 63 秒(全程 72 秒),佔 88% 執行時間的 JPEG 完全沒有進度。
- 抓到靠「60 秒空白然後 8 秒衝完」的不合理感 + 比對 journalctl 時間戳。**追查中我推論錯兩次**(先猜 JPEG 本來就慢、再猜分母算錯),都靠加 log 拿實際數字排除→那兩行 log(`進度基準`/`進度回寫`)刻意保留。
- 修法用 **`finally`** 而非把呼叫搬到 `continue` 前:後者只補這一條路徑,日後再加一條 `continue` 又會漏。
- 驗證腳本已補**時序斷言**(首個進度不得晚於全程 35%、進度點不得少於 8)。

**`containViewer` 預設已在 Export API 翻成 false**(alpha.8):`.191` 補上 cd-viewer-win 後,預設 true 會讓每次下載多背 130MB。DB 端仍 true(kiosk/legacy 要的正是它)。744 張 DICOM+JPEG 的包實測 **228MB**(DICOM 166 + JPEG 62,JPEG 平均 85KB/張)。

**正本 = `docs/media-export-redesign.md`**(2026-08-17 起草)。起因:Viewer 要接燒錄,發現 job 只能用 `studyRef`(**HDPACS 內部自增代理鍵**,跨系統/重建 DB 就變)且只能整個 study;使用者指出 Viewer 手上有的是 UID 才合理。順著查發現 `EXPORT_JOB` 一張表服務六種用途,而 **Kiosk 之後也要重構 → 決定先把資料模型做對再往上接**。

**🔑 三個已決策(2026-08-17)**:①**`SELECTION`(使用者要求什麼)與 `ITEM`(實際打包了什麼)兩張都要**——沒有 ITEM 就回答不出「當初那片光碟燒了哪幾張」,而病歷爭議正是問這個;ITEM 一併取代 jsonb 裡的 `discInfo`(原本是 `Dictionary<string,BurnInfo>`),哪張光碟裝哪些改成 `DISC_NO` 一欄 ②**`archive` 流程淘汰**(功能要改版,不納入新設計、不遷移;`BurnInfo.archiveItems` 的 nearline 撈回一併退場) ③**新舊並行、legacy 完全不動**(`EXPORT_JOB` 與 `insert_package_job`/`get_job_package_info` 原封不動繼續服務桌面端/kiosk/rimage)。

**查證翻出來的四件事(都是實查 DB dump + 兩份 PackageJob.cs)**:
1. **`export.EXPORT_JOB` 是唯一 job 表,被六種 `PRODUCT_UUID` 共用**(`export`/`dicomweb`/`rimage`/`kioskExport`/`mms`/`archive`);kiosk 另三張表(CARD_EVENT/DISC_EVENT/DISC_TRANSFER)只存事件。`get_job_package_info` 用**排除法** `PRODUCT_UUID != 'mms' AND != 'kioskExport' AND != 'archive'` → 每加一種用途都得回來改別人的 WHERE(新設計改白名單 `PRODUCT =`)。
2. **同一個 `BURN_INFO` 有兩種互不相容結構**:net10 `HD.MediaPackage/Class/PackageJob.cs` 吃**扁平** `studyInfoList[{...fileList:[路徑]}]`;`HD.MediaExportSuite/Job/PackageJob.cs` 吃**階層** study→series→image。**切換條件是 `IF product_uuid='rimage' AND hd_user_uuid='76b856c5-05e8-44c5-b0f4-e5e7e5802060'`——一個硬編碼使用者 UUID 當功能開關**,而 series 層級篩選(`seriesInstanceUidList`)只活在這個分支裡。
3. **`HD.MediaExportSuite`(`C:\Users\yang\source\repos\HD\HD.MediaExportSuite`,.NET Framework WinForms,Program.cs 竟 329KB)的階層模型已經做對了我們要的事**:UID 三層識別、`ImageInfo.fileLength`(所以容量估算/`estDiscs` 分片成立)、`discInfo` 切多張光碟、`discFileId` 光碟上檔名。**新設計不是發明,是把它一般化+正規化。**
4. **併發是定時炸彈**:`get_job_package_info` 是 `SELECT ... STATUS='N' LIMIT 1` → 展開全部檔案路徑(慢) → `UPDATE STATUS='p'`,中間**沒有 `FOR UPDATE SKIP LOCKED`**。現在只一個 worker 所以沒事,**多開一個就重複打包**。新設計用 `claim_package_job` 標準 PG 佇列模式。

**新四張表**:`PACKAGE_JOB`(生命週期,`STATE` 有 CHECK、`CLAIMED_BY/AT` 支援多 worker)、`PACKAGE_JOB_SELECTION`(要求什麼,**存 UID 三層級不存路徑**,UID 全域唯一故混存無歧義)、`PACKAGE_JOB_ITEM`(實際打包快照:SOP/SERIES/STUDY UID+`FILE_BYTES`+`DISC_FILE_ID`+`DISC_NO`)、`PACKAGE_JOB_DISC`(kiosk/rimage 專屬:PICKUP_NO/FEE/PAY_*/DEVICE_UUID/EST_DISCS)。**憑證欄位一律不設**——現在 `BURN_INFO.storagePassword` 是**明文落庫**。

**存 UID 不存路徑是關鍵決定**:worker 領到才解析 → 歸檔搬移/W-L 校正/出口疊合自然吃到最新狀態(舊的 `fileList` 是路徑快照,檔案一搬 job 就失效)。

**EXPORT_JOB 其他問題(清單在正本第 3 節)**:狀態碼單字母且**大小寫有意義**(`p`=處理中/`P`=完成)無 CHECK、`m/M/b/B/Y/C` 連對照表都沒有(只有 `kiosk.convert_disc_transfer_status_display` 有 N/p/P/d/D/E);兩套時間記錄並存(`ACTIVITY_RECORDS` + `BURN_INFO.jobTimeRecord`);`ERROR_MSG` 用 jsonb;`PATIENT_ID` 平放但一 job 可多病患。

**Viewer API 規格(正本第 5 節)**:三個 UID 陣列(`studyInstanceUid`/`seriesInstanceUid`/`sopInstanceUid`)**可混用取聯集**;建立回 `imageCount`+`totalBytes`(讓 Viewer 顯示「248 張約 320MB」——`imageCount` 一直有算只是沒回);查狀態多回正規化 `state`(queued/processing/ready/failed),legacy `status` 保留供除錯。Export 這條路實際只出現 `N`/`p`/`P`/`E` 四個狀態。

**✅ 階段 1 完成(2026-08-17)**:`db_update_v2.0.28.sql`(四表+八 proc)+`v2.0.29.sql`(授權表歸位+補設定),**使用者已在 .191 依序執行 27→28→29**;DB版本.xlsx 也補了 2.0.28/29 分頁(用 copy_worksheet 從 2.0.27 複製保樣式)。**每個 migration 結尾必加「Update Database Version」DO block**——見 [[reference_pacs_db_schema]]。

**✅ 階段 2 完成(2026-08-17):Export API 改用新 proc**(`8d4cf9b`,未部署)。開放 `studyInstanceUid`/`seriesInstanceUid`/`sopInstanceUid` 三層級聯集;建立回 `imageCount`/`totalBytes`/`offlineCount`;狀態回正規化 `state`+`packagedCount`(legacy 單字母 status **不再回傳**,新表沒那欄);`jobRef` int→**long**(bigserial),路由改 `:long`;產出路徑改 `[JsonIgnore]` 不對外。**三個實作時才浮現的問題**:①`get_package_job` 只吃 jobId、**沒有舊 proc 的 productUUID+userUUID 比對** → 不補的話任何有 export.read 的金鑰都能查別人的 job;已在 `GetStatusAsync` 比對 product+requestedBy,不符回 **404 不是 403**(403 等於承認 job 存在) ②proc 用 `RAISE EXCEPTION` 表達業務拒絕 → 要 catch `PostgresErrorCodes.RaiseException`(P0001) 轉 400,否則變 500 ③移除 `ignoreMultiframe`(新 `package_job_objects` 無 mpeg4 篩選,本來就因 REQ-008 失去意義)。

**✅ 已部署 .199(2026-08-17):Export `0.1.0-alpha.3+20260817184305`**(hdctl install,健檢過)。同版加了 **`contents`(dicom/jpeg/兩者,Viewer 要三種組合;legacy 的 `onlyJpeg` 布林表達不出「兩者都要」)** 與 **DELETE 取消端點**(限 queued/claimed)。`contents` 值域錯回 400 列出錯值(不靜靜忽略);OPTIONS 一併寫 `onlyJpeg` 讓 legacy worker 至少純 JPEG 對。同批 DicomWeb 升 `1.0.0-alpha.2`(套件弱點修補,兩 unit+UPS 5081 皆 active)。**DB 那層使用者也已在 .191 跑完 27→28→29**,所以新模型從 DB 到 API 都在生產就位。

**⚠️ JPEG 現況(2026-08-17 查證)**:worker **有實作**(fo-dicom `DicomImage.RenderImage()` **打包時即時轉**,不吃預生檔 → REQ-007 停 DicomToImage 對它無影響),輸出 `JPG/{SOPInstanceUID}.jpg`。但**兩顆地雷**:①`job.burnInJpeg` **完全沒有 null 檢查**(PackageService 169/172-173/176/182 行)而它**沒有任何設定來源**(.191 的 `BURN_WORKSTATION/SYSTEM` 只有 burnTempPath/queryLimit/viewerPath/viewerSize 四個鍵)→「只要 JPEG 不要燒字」會直接 NRE,**燒字必須改成選配** ②`onlyJpeg` 只能二選一,要支援 DICOM+JPEG 得改讀 `contents`。另:燒字用 `System.Drawing`(4.7.3,Linux 靠 libgdiplus,離線包有含)但**這條路從未被啟用故從未在 Linux 跑過**;程式碼已在用 ImageSharp(`AsSharpImage`/`SaveAsBmp`)只是又轉回 Bitmap 燒字 → 改用 ImageSharp 繪字可拿掉 GDI+ 依賴。

**✅ 階段 3 完成+實機驗證(2026-08-17,已部署 .191 `pacs 2.0.6`)**:worker 改領新表。**關鍵決定=讓 DB 組出與 legacy 同形的 payload**(`claim_package_job_payload`),所以 worker 700 多行產出流程**一行沒動**,只改四接縫(取 job 先問新表→沒有才 legacy／回寫依 `jobSource` 分流／寫 `ITEM` 快照／`contents` 把 onlyJpeg 的 if-else 拆成兩個獨立 if)。實機三種組合皆 ready:純 DICOM 6 筆快照、純 JPEG 6 筆 `JPG/{SOP}.jpg`、DICOM+JPEG 6 筆記 DICOM 那份。

**⚠️⚠️ 部署後才現形的兩個問題(都已修,是這輪最有價值的發現)**:
1. **JPEG 每張都 NRE**(`PackageService.cs:213` 的 `AsSharpImage`)。`new DicomImage(file)` **直接 new 不經 DI**,靠 fo-dicom **靜態 ServiceProvider** 找 ImageManager;`ConfigureServices` 的 `AddImageManager<ImageSharpImageManager>()` 只設定 host DI,**Generic Host 這條路沒接上** → fallback 到 `RawImageManager` → 回的 IImage 不是 ImageSharpImage → `AsSharpImage()` 回 null → NRE。**對照:Viewer/TestClient 都有 `new DicomSetupBuilder().RegisterServices(...).Build()`,DicomWeb 走 ASP.NET Core 也沒事,只有 MediaPackage 沒接。** 這是**既有缺陷**(JPEG 路徑從未啟用+DICOM 不 render,所以一直沒發現)。修=Program.cs 補 DicomSetupBuilder，並讓 AsSharpImage 回 null 時丟出帶「實際 IImage 型別」的錯誤(原本無頭 NRE 指不出原因)。
2. **JPEG 全失敗卻標 `ready`**(交空包顯示成功)。逐檔 try/catch 只記 log 不中斷 → 六張全炸也走到標 ready。修=累計成功/失敗數,全失敗丟例外標 failed;部分失敗仍交包但把「N 張失敗」寫進 ERROR_TEXT。

**教訓:API 層與 DB 層都能在本機驗,但 worker 的影像轉檔依賴 ImageManager 的執行期初始化——那種東西只有真的部署跑起來才會現形。**:`hd-media-package` worker 還在讀舊 `EXPORT_JOB`(`get_job_package_info`)。已寫進 `ExportService` 類別註解免得被當 bug。worker 要改的接縫:領 job(`claim_package_job`)、解析檔案(`resolve_package_job_files` 回**階層**、worker 的 `PackageJob` 是**扁平 fileList** → 要轉換)、回寫(`update_package_job`)、寫快照(`record_package_job_items`)。

**驗證方法(兩次都靠它抓到問題)**:①SQL 層用 Npgsql 把 migration+冒煙測試包在 `BEGIN…ROLLBACK` 對 .191 實跑 ②API 層直接 `new ExportService(dataSource, logger)` 繞過 HTTP 測 service 邏輯(用 `product='apitest'` 建 job、跑完 DELETE 清乾淨)。**⚠️ 素材一定要挑「多 series 多影像」的 study**——兩次第一輪都抓到只有 1 張的 study,導致 study/series/instance/聯集四個數字全是 1、**等於什麼都沒驗到**;改用 744 張/9 series 才真正驗到(study=744 / series=2 / instance=1 / series 2張+別series一張=3)。

**⏳ 待決**:`PRODUCT` 值域要不要 enum;取消能否中斷 `processing` 中的 job;`worklistStudyInstanceUid` 要不要保留(MediaExportSuite 的 study 去重鍵是 `worklistStudyInstanceUid ?? studyInstanceUid`);**`ITEM` 保留期**——若是稽核快照就不該跟 job 一起 `ON DELETE CASCADE`(與病歷保存年限有關)。

相關:[[project_req003_export_webapi]]、[[project_studyclose_flow]]、[[reference_pacs_db_schema]]。
