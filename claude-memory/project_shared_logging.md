---
name: project_shared_logging
description: HD.Shared.Logging 共用包 — Serilog 直送 HawkLog（CLEF+durable+自製 NDJSON formatter）；第一層已建好並測過
metadata: 
  node_type: memory
  type: project
  originSessionId: 4955439c-e319-4882-9ff7-dc4be5c80843
  modified: 2026-08-10T02:00:55.184Z
---

目標:讓所有產品的「運作 log」統一送進 HawkLog（[[project_hd_animal_proxy]] 的日誌平台 HD.LoggingPlatform，Ingest 端點 `POST /ingest`，吃 NDJSON/CLEF + `X-Api-Key`）。

**分兩軌**（討論後定案）:
- 軌道 A 運作/診斷 log → 走 HawkLog（本包負責）。重複無所謂。
- 軌道 B 稽核「誰做了什麼」→ 以各服務自己的 DB 為正本（DicomWeb 已有 `HD_USER_AUDIT_LOG` 表），**不**拿 HawkLog 當正本，因為 HawkLog Ingest **不做去重**（`@i` 被忽略、COPY 直插）。要集中看才選配鏡射一份帶 `Audit:true`。

**已建好:** `D:\Dev\HyperDigital\HD.Shared\src\HD.Shared.Logging\`（net10，葉子包,只依賴 Serilog / Serilog.Sinks.Http 9.0.0 / Serilog.Formatting.Compact 3.0.0）。API:`.WriteToHawkLog(HawkLogOptions)` 一行接上(enrich App/Source + durable HTTP sink)。已端對端測過:輸出正確 NDJSON、帶 X-Api-Key、避開陣列坑。

**關鍵坑 2(2026-08-10):** `BufferBaseFileName` 原預設相對 CWD——**多服務共用 WorkingDirectory(hdctl current/ 佈局)時七個行程共寫同一緩衝檔、各自拿書籤補送→同一事件送七次**(.191 實案,LoggingPlatform 一次 C-ECHO 出現 7×OPEN/ECHO/CLOSE)。已改預設錨 `AppContext.BaseDirectory`;凡 appsettings 覆寫相對路徑的都要拿掉(DicomWeb 已拿)。

**關鍵坑:** Serilog.Sinks.Http **v9 內建只剩 `ArrayBatchFormatter`**（包成 `[...]`），HawkLog 逐行解析會整批丟（accepted:0）。故自製 `NdjsonBatchFormatter`（一行一筆）。HawkLog 自己的 `PlatformLogging.cs` 用預設 formatter,其 self-log 很可能一直在被丟。用 `DurableHttpUsingFileSizeRolledBuffers` 取得斷線落地/恢復補送。

**共用方式:** 專案參考（非 NuGet）— 使用者選的,單人+同資料夾開發最省事。各產品 csproj 加 ProjectReference + 給 `HAWKLOG_URL` / `INGEST_API_KEY`。

**部署規劃:** 四類產品全是 Serilog（傳統 PACS [[project... HD.Net10]] 共用 `HD/LoggerManager.cs` 且已裝 Compact；DicomWeb；Animal.Proxy；WinForms 看片）→ 全部「直送」。第一階段不做站點中繼；只有「診間看片電腦很多／不想把金鑰發到客戶端」才在站點現有機器上加 Fluent Bit。

**Pilot 已完成（2026-07-27）:** DicomWeb → HawkLog 端到端驗證通過（received/written 隨 DicomWeb 啟動+request log 上升、0 丟棄）。
- HawkLog ingest 在 .195 原本只綁 127.0.0.1:5101 且 firewalld 未開 5101 → 已開放內網（compose 綁 0.0.0.0:5101 + firewall-cmd 開 5101）。
- .199 DicomWeb 用 `systemctl edit --full` 加 `HAWKLOG_URL=http://192.168.68.195:5101` + `INGEST_API_KEY`（金鑰值即 ingest 容器的 INGEST_API_KEY）。
- **持久化已做（含 SELinux 坑）**:install.sh 改成寫 unit `EnvironmentFile=-/etc/hd-pacs-dicomweb/hawklog.env`（金鑰放 /etc、root:600、restorecon → etc_t）。
  - ⚠️ **SELinux 坑**:一開始放 `/home/HD/service/.../data/hawklog.env`（user_home_t），SELinux Enforcing 下 systemd(init_t) 讀 EnvironmentFile 被 AVC denied,加上 `EnvironmentFile=-` 的 `-` 靜默略過 → env 沒載入、無錯誤、log 靜默不送。查法:`ausearch -m avc | grep hawklog`、`ls -Z`。解法:放 **/etc**（etc_t,systemd 讀得到,且跨部署保留）。install.sh 會自動從舊 data/ 位置遷移。
- build 戳記用**台灣時間 UTC+8 標 +0800**（`UtcNow.AddHours(8)...+0800`）,見 [[feedback_versioning_convention]]。

**IP/使用者顯示（2026-07-27 完成 LoggingPlatform 側）:** 查詢頁本來只把 DICOM 專屬欄位（CallingAET/CalledAET/CommType）拉成 inline tag，通用 web 欄位沒拉出來。已改 `Logs.razor` + `app.css`：①新增「來源 IP」「使用者」兩個**通用**篩選欄（不綁產品）②`BuildProps` 改成 IP/使用者對所有產品生效、DICOM 三欄僅 DICOM 產品加③結果列把 IP/使用者拉成 inline tag（藍=IP 紫=使用者）。後端本來就支援（ClefParser 存全部非 `@` 欄位進 properties jsonb、Query 已有 `properties @> {...}` containment），缺口只在前端。
- **欄位命名契約（重要）:** 平台認的名字是 **`ClientIp`** 和 **`User`**（大小寫需完全一致），tag 顯示與精準篩選才生效。各使用方送 log 時必須用這組名字。
- **.195 已部署此版（2026-07-27）:** 同版本重裝進同一個 `~/hdlog-v1.0.0/`（project=hdlog-v100 → 具名卷 pgdata/dpkeys/archive 前綴不變 → 資料保留）。⚠️ **同版本重裝別直接跑 install.sh**（它偵測舊部署會排除自己所在目錄 → 誤判全新安裝、`up -d` 不保證換映像）；改手動 `podman compose down`（不加 -v）→ `podman load` → `tar -xzf … -C hdlog-v1.0.0` → `podman compose up -d`。驗證：ingest/query `/health`、資料保留、6 服務 Up。
- **小缺口:** ①Web 專案沒 map `/health`（Ingest/Query/Alerting/Archive 才有）→ 監控探 Web 活著沒不好探。②`App.razor` 的 `<link href="app.css">` **無版本指紋** → 換版後瀏覽器抓舊 CSS，使用者需 Ctrl+Shift+R 才看到新畫面（換 Web UI 版面時已中招一次）。兩者待補（建議 app.css 加 `?v=` 版本查詢字串或用 Blazor 靜態資源指紋）。
- **IP tag 顯示 bug（2026-07-27 修）:** Query API 回的 `properties` 是「內含 JSON 的字串」（JsonElement.ValueKind=String），非物件。Logs.razor 的 `Prop()` 要求 Object → tag（含既有 DICOM tag）全抽不出、不顯示。修法：結果列先用既有 `PropsElement()` parse 成物件再抽。同時把顯示改成「訊息在上、下方一條 `.log-meta` 淡色膠囊列（使用者/IP/通訊類型/AET，帶標籤 ::before）」，版面較清爽（使用者原嫌 tag 擠成一團）。

**DicomWeb 送 ClientIp/User + 訊息渲染修復（2026-07-27 完成並部署 .199 生產驗證）:**
- **IP/User 補值（DicomWeb Api Program.cs）:** .199 前**無反向代理**（`ss -tlnp` 只有 5080/22/9090-cockpit，無 80/443；反代檢查空）→ 直接用 `ctx.Connection.RemoteIpAddress`（IPv4-mapped 正規化為純 IPv4），**不需** ForwardedHeaders。兩處：①`UseSerilogRequestLogging` 的 `EnrichDiagnosticContext` 給「請求完成」那條加 ClientIp/User/UserAgent（此事件在 pipeline 尾端寫出，在 LogContext push 範圍外，故直接自 HttpContext 取）；②認證後加 `LogContext.PushProperty` 中介層，讓請求內其餘 log（如 WADO instance）也帶 ClientIp/User。helper `RequestLogEnrichment`（Program.cs 底部）。
- **訊息渲染修復（HD.Shared.Logging，影響所有使用方）:** 原 `HawkLogConfigurationExtensions.cs` 用 `CompactJsonFormatter` 只送 `@mt`（模板 `HTTP {RequestMethod} …`）不送 `@m` → 平台 ClefParser 取不到 @m 退存模板 → 訊息顯示未填值佔位符。改用 **`RenderedCompactJsonFormatter`**（送已渲染 `@m`），結構化屬性（含 ClientIp/User）不受影響。副作用：不再送 @mt（Template 欄變 null，可接受，平台以 message FTS 為主）。渲染出的字串屬性會帶引號（`"GET"`）純美觀。
- **部署驗證:** .199 `install.sh` 更新（保留 data/logs、/etc env），/health build=20260727-1632；.195 DB 查得 app=HDPacs 新 log：訊息已填值、ClientIp 有值、User 匿名空值。

**全部已 commit+push（2026-07-27）:** HD.Shared `4e80753`、HD.Pacs.DicomWeb `e81eb4f`、HD.LoggingPlatform `c71ad66`（三 repo 皆 github.com/Charlie022802/*，master）。

**待辦:** ①推到其他產品送 `ClientIp`/`User`（DicomWeb 已完成；剩傳統 PACS HD.Net10 改一處 LoggerManager 涵蓋十幾支、Animal.Proxy、Viewer.Server、WinForms）— 各使用方對齊平台契約欄位名 `ClientIp`/`User`，並改用 `LoggingPlatformOptions`/`WriteToLoggingPlatform()` + env `LOGPLATFORM_URL`／`LOGPLATFORM_API_KEY`②稽核持久化弱點（見下）。

**HawkLog → LoggingPlatform 全面改名（2026-07-27，使用者選「全部改新名不留後備」）:**
- HD.Shared.Logging：`HawkLogOptions`→`LoggingPlatformOptions`、`HawkLogConfigurationExtensions`→`LoggingPlatformConfigurationExtensions`、`WriteToHawkLog()`→`WriteToLoggingPlatform()`、sink `.HawkLog()`→`.LoggingPlatform()`；檔案同步改名；buffer 路徑 `logplatform-buffer`。
- **env 變數改名（重要）:** `HAWKLOG_URL`→**`LOGPLATFORM_URL`**、`HAWKLOG_API_KEY`→**`LOGPLATFORM_API_KEY`**（api key 仍保留 `INGEST_API_KEY` 後備，非 HawkLog 專屬名）。
- DicomWeb：Program.cs 讀 `GetSection("LoggingPlatform")` + `LOGPLATFORM_URL`；appsettings 區塊 `HawkLog`→`LoggingPlatform`。
- **DicomWeb install.sh：env 檔 `/etc/hd-pacs-dicomweb/hawklog.env`→`logplatform.env`**，且加**自動遷移**：偵測舊 `hawklog.env`（/etc 或 data/）→ `sed` 翻譯 `HAWKLOG_URL=`→`LOGPLATFORM_URL=` 寫入新檔、刪舊檔。故 **.199 下次部署 DicomWeb 會無縫遷移、log 不斷**（現在不部署也不影響，舊版仍讀 HAWKLOG_URL）。
- **已部署+驗證（2026-07-27）:** .199 重新部署，install.sh 自動遷移 `hawklog.env`→`logplatform.env`（sed 翻譯 `HAWKLOG_URL=`→`LOGPLATFORM_URL=`、刪舊檔），log 無縫不斷（.195 續收 HDPacs log）。.199 build 20260727-1913、.195 build 20260727-1917。

**DicomWeb 稽核子系統既有弱點**（與 HawkLog 無關,但重要）:in-memory channel `drop_oldest` + flush 失敗整批丟（`AuditFlushBackgroundService.cs:145`）→ 會靜默遺失；ActorId 存 GUID 非帳號名；SourceIp 信任 XFF 可偽造；QIDO 稽核無獨立 PatientID 欄位。
