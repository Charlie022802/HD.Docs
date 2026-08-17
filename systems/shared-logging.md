# 共用日誌套件（HD.Shared.Logging）

讓所有產品的「運作 log」統一送進 **LoggingPlatform**（.195）。Serilog 直送（CLEF+durable+自製 NDJSON formatter）。

- **原始碼**：`D:\Dev\HyperDigital\HD.Shared\src\HD.Shared.Logging`（git，Charlie022802/HD.Shared，master）。net10，葉子包。
- **共用方式**：ProjectReference（非 NuGet）；各產品 csproj 加參考 + 給 env。

## API
- `LoggingPlatformOptions`：App / Source / IngestUrl / ApiKey / BufferBaseFileName / MinimumLevel；`FromEnvironment(app)` 讀 `LOGPLATFORM_URL`(後備 SELF_LOG_URL) / `LOGPLATFORM_API_KEY`(後備 INGEST_API_KEY)。
- `WriteToLoggingPlatform(options)`（高階，enrich App/Source + durable HTTP sink）。
- sink 用 `RenderedCompactJsonFormatter`（送已渲染 `@m`）+ `NdjsonBatchFormatter`（一行一筆，避開 Sinks.Http v9 陣列坑）+ `DurableHttpUsingFileSizeRolledBuffers`（斷線落地補送）。

## 平台契約欄位（重要）
送 log 時欄位名必須是 **`ClientIp`** 和 **`User`**（大小寫完全一致），tag/篩選才生效。

## 兩軌
- 軌道 A 運作/診斷 log → 走本套件送 LoggingPlatform（重複無所謂）。
- 軌道 B 稽核「誰做了什麼」→ 各服務自己 DB 為正本（LoggingPlatform ingest **不去重**）。

## 接入現況
- **DicomWeb**：已完成並部署 .199（送 ClientIp/User、訊息渲染修復）。
- **主 PACS（HD.Net10）**：HD.PACS + WorklistServer 已寫（DIMSE 用 RemoteHost/CallingAE 映射），待部署。見 [main-pacs.md](main-pacs.md)。
- **待接**：Animal.Proxy、Viewer.Server、WinForms 看片。

## 部署要點
各服務 systemd unit 需 `EnvironmentFile` 指向 `/etc/hd/logplatform.env`（/etc、600、restorecon → etc_t）。**env 放 /home 會被 SELinux 擋且 `EnvironmentFile=-` 靜默略過**（踩過雷）。留空=不送。
