# 主 PACS（HD.Net10）

傳統 DICOM PACS，.NET 10 重寫版（前身 v4.8）。多專案 slnx，fo-dicom 5.2.5，Npgsql 8，PostgreSQL **HDPACS**（.234）。

- **原始碼**：`D:\Dev\HyperDigital\HD.Net10`（`HD.Net10.slnx`）。git repo。
- **版本**：`HD/HD.csproj` 等（目前 2.0.4 系列）。
- **部署**：規劃裝到 **.234**（與 DB、影像檔同機，worker 直接存取）；佈局 `/home/HD/service`，見 [deployment.md](deployment.md)。

## 服務組成（11 支，皆 systemd）
被動 SCP / 查詢：
- **hd-pacs** — DIMSE SCP：C-STORE / C-MOVE / C-FIND / C-ECHO（C-GET 停用）。埠 2020。
- **hd-worklist-server** — MWL C-FIND + MPPS。埠 3320。

主動 worker（讀 DB 佇列動作）：
- **hd-dicom-transmit** — C-STORE SCU（CSTORE/CMOVE/ROUTE 三型），對外送檔。
- **hd-workflow-manager** — STUDY_CLOSE 等；**已停止就地改寫 DICOM 檔（A3）**，只推進 job 狀態；校正走 DB overlay + 出口疊合。
- **hd-archive-manager** — 封存 / nearline / 上傳。
- **hd-cache-delete** — 依 CACHE_DELETE 佇列**刪除影像檔**。
- **hd-media-package** — CD/DVD 燒錄 / 媒體打包（讀 `export.EXPORT_JOB`）。
- **hd-dicom-to-image / hd-dicom-to-video** — 轉 JPEG / MP4 / DICOM-MPEG4。
- **hd-dicom-service-manager** — 服務協調（最後啟動）。

舊 web 元件（不在新 slnx）：
- **hd-web-server** — 原生執行檔（Node/sharp+libvips、port 80）＝**DB/PACS 控制網頁介面，營運需要、要裝**（沿用 legacy build，本身沒改）。裝法見 `install-web.sh`（setcap 綁 80 + libvips + SELinux .pp + unit）。網頁裡走 gRPC `dicomSCU:5002` 的 DICOM 功能需 hd-web-dicom-scu，已停用（見下）故那些不動。
- **hd-web-dicom-scu** — 舊的 dicom-web（fo-dicom 4）＝**已被 .199 新 DicomWeb 取代，不裝**。

## 關鍵架構
- 全系統實體檔路徑走 `get_next_map_job` → `MapJobInfoData.filePath`；`includeDataset=true` 時 `.dataset` 是 DB 校正後的 DICOM-JSON。
- 共用 lib 在 `HD/` 專案（namespace `HD`）：`HD.Database.PostgresConnection`、`HD.DicomCore`（含 `DicomDatasetExtension.ToDicomDataset()`）、`HD.Json.DicomJsonConverter`、`HD.Job.MapJobManager`、`HD.Configuration`。
- DB 存取：raw Npgsql + jsonb 參數，呼叫 stored procedure。

## 進行中改造

### 出口疊合 + 停止改檔（REQ-001）
目標：進檔後檔案唯讀不可變；校正只寫 DB（RC_STUDY/RC_SERIES/RC_OBJECT.DATASET）；**每個對外出口送出前把 DB 校正疊到記憶體 dataset 再吐**（coerce-on-retrieve）。與 DicomWeb WADO 已上線的試點一致。疊合 idempotent，可與現有改檔並存 → 漸進安全。

- **A0（DONE, build 過）** `HD/DicomCore/CoercionService.cs`：`ApplyCoercion(target,overlay,studyUid,seriesUid)`（逐 tag、跳 PixelData/group0002、父表 UID 強蓋、每 tag 寬鬆 try/catch）+ `CoerceBySopUid(target,sopUid)`（DB 撈 RC_OBJECT.DATASET+父表 UID）。
- **A1（DONE, build 過, 未部署）** `HD.DicomTransmit/Service/DicomTransmitService.cs`：C-STORE/CMOVE/ROUTE 送出前疊合（優先 job.dataset，無則 CoerceBySopUid）。
- **A2（DONE, build 過, 未部署）** 對外出口：`HD.MediaPackage/PackageService.cs`（媒體匯出/封面）、`HD.CallBack`（StudyCallbackService + ChangGungHorizonHandler）。**VideoToDicomMpeg 跳過**（內部衍生，真正出去時才疊）；archive/nearline/純像素不疊。
- **A3（DONE + .191 驗證通過, commit `68b33e1`）** 移除 `StudyClosedService.UpdateDicomFileSafe` + 2 呼叫點 + 孤兒 `DatasetsAreEqual` + 死掉的 tempInfo/TempPath/usings；保留 STUDY_CLOSE 迴圈 + DB reconcile（get_next_map_job→update_study_info，DB 端，不在 C#）。STUDY_CLOSE 現在只推進狀態、不碰原檔。**驗證（2026-08-04）**：部署 hd-workflow-manager 到 .191（先前 6 支子集沒裝此支），設 `RC_STUDY.INSTITUTION_NAME` 標記→觸發 STUDY_CLOSE→檔案 md5 before==after 一字不差、DATASET 疊上標記但磁碟原檔沒有、STATUS→X。前置需 `skipWorklistVerified=true` + `toJpeg=false`（.191 無 hd-dicom-to-image）。

### 接入共用日誌（REQ-002）
- **DONE（build 過, 未部署）**：`HD/Log/LoggingPlatformSetup.cs`（`ConfigureLoggingPlatform` 讀 GetSection+env `LOGPLATFORM_URL`/`LOGPLATFORM_API_KEY`；`LogScope.Dimse` 綁 ClientIp/User）。HD.PACS + WorklistServer 的 Program.cs UseSerilog 接上；DIMSE handler 用 `using var LogScope.Dimse(RemoteHost, CallingAE)`。
- Serilog 4.0.1→4.3.1（HD.csproj，隨 HD.Shared.Logging 參考升）。
- **部署要點**：unit 需 `EnvironmentFile=/etc/hd/logplatform.env` 才會送（留空=no-op）。
- 詳見 [shared-logging.md](shared-logging.md)。

## 待辦
見 [todo.md](todo.md)「主 PACS」。核心：A0–A3 + B 皆已寫+build 過；A3 已完成（停止改檔）。核心待辦：正式部署 + A3 上線後驗證（STUDY_CLOSE 後原檔未動、出口疊合仍正確）。
