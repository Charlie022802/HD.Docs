# LoggingPlatform（HD.LoggingPlatform）

集中式日誌平台（前身 HawkLog）。收各產品的 log、可查詢。

- **原始碼**：`D:\Dev\HyperDigital\HD.LoggingPlatform`（git，Charlie022802，master）。
- **生產**：**192.168.68.195**，ingest 埠 **5101**（吃 NDJSON/CLEF + `X-Api-Key`）。podman compose 部署（具名卷 pgdata/dpkeys/archive）。
- **組成**：Ingest / Query / Alerting / Archive / Web（Blazor）+ PostgreSQL。

## 接收契約
- Ingest `POST /ingest`，NDJSON/CLEF，`X-Api-Key`。**不做去重**（`@i` 忽略、COPY 直插）→ 稽核正本別放這。
- 通用欄位 `ClientIp` / `User`（大小寫需一致）在查詢頁可篩選 + inline tag。DICOM 專屬欄位（CallingAET/CalledAET/CommType）另外拉。

## 現況
- 生產 .195 已部署；DicomWeb 端到端驗證通過（received/written 上升、0 丟棄）。
- ingest 綁 0.0.0.0:5101 + firewall 開放內網。
- **產品分區（排障第一站）**：P1 產品總覽 `/` ＋專區 `/product/{App}`（2026-08-06）；**P2 連線紀錄籤（2026-08-08/09）**。P3 治理待做。

## 連線事件慣例（P2，2026-08-08 定案）
發送端用 `HD.Shared.Logging.ConnectionLog.Emit(...)`，本質是一般 log ＋結構化屬性：
- `Category="connection"`（固定小寫；`@>` containment 大小寫敏感）
- `CommType`：ASSOCIATE-OPEN / ASSOCIATE-CLOSE / ASSOCIATE-REJECT / ABORT / C-ECHO / C-STORE / C-FIND / C-MOVE / MWL-FIND / MPPS
- `Outcome`：success（Information）/ failure（Warning，會同時進「警告以上」籤）
- `ClientIp` / `User`（平台契約名）＋ `CallingAET` / `CalledAET`（進階查詢 DICOM 過濾欄位）
- **音量約定**：C-STORE 成功不逐筆，彙總進 ASSOCIATE-CLOSE 的 detail（`C-STORE n ok / m fail`）；失敗才逐筆。
- 呈現：專區「連線紀錄」籤（只在 `dicom_apps` 清單的產品顯示），查詢走既有 `props` 參數（GIN jsonb_path_ops），Query 服務零改動。
- 發送端現況：主 PACS DicomPACSService＋WorklistDicomService（.191 已部署）。定位＝**儀器 DICOM 連線**；DicomWeb/Export 的 HTTP 面走既有 access log，不另發。

## 已修 / 已部署
- **ClefParser `@l` 缺漏誤判等級（2026-08-04 修 + 已部署 .195）**：CLEF 規範 Information 省略 `@l`，但 `ClefParser` 缺 `@l` 時 `evt.Level` 停在 short 預設 0=Verbose → **所有 Information log 被誤標 Verbose**（影響全部產品）。已修 `ClefParser.cs`（缺 `@l` 預設 Information，commit `8915f84`）。**部署方式**：ClefParser 在 `HD.LoggingPlatform.Shared`，但等級是 ingest 解析 CLEF 時決定→**只需重 build Ingest**：`build-deploy.ps1` 邏輯手動跑 Ingest（dotnet publish→podman build `hdlog-ingest:v1.0.0`→save）→ .195 `podman load` → `podman compose up -d --no-deps --force-recreate ingest`（db/其他服務不動、卷保留）。只影響之後進來的 log。

## 已知小缺口
- Web 專案沒 map `/health`（Ingest/Query/Alerting/Archive 才有）→ 監控 Web 活著不好探。
- `App.razor` 的 `<link href="app.css">` 無版本指紋 → 換版後要 Ctrl+Shift+R。

## 部署注意
- 同版本重裝**別直接跑 install.sh**（會誤判全新安裝）；改手動 `podman compose down`（不加 -v）→ `podman load` → 解壓 → `up -d`。資料靠具名卷保留。
