---
name: project_dicomweb_features
description: HD.Pacs.DicomWeb 強化 — 稽核緩衝、Admin UI 登入、WADO 匿名、授權收斂 全部 DONE+已部署(commit 009b754)
metadata: 
  node_type: memory
  type: project
  originSessionId: 4955439c-e319-4882-9ff7-dc4be5c80843
  modified: 2026-08-02T17:49:59.161Z
---

HD.Pacs.DicomWeb 一批強化，2026-07-27 起。與 [[project_dicomweb_impl_split]]、[[project_shared_logging]] 同專案。

**① 稽核落地緩衝（B 級持久化，DONE，本機驗證）:** 原稽核子系統三個靜默遺失漏洞（channel DropOldest 溢位丟、DB flush 失敗整批丟、當機/重啟未 flush 丟）。修法：新增 `Infrastructure/Audit/AuditSpool.cs`（NDJSON 落地，先 .tmp 再 rename 原子寫）；`ChannelAuditLogger` 溢位改落地；`AuditFlushBackgroundService` flush 失敗先重試 FlushMaxRetries 次再落地，且每 SpoolReplayIntervalSeconds + 啟動時重送 spool 回 DB（成功才刪檔）；FullMode 預設改 `wait`（配合 TryWrite 溢位落地）。AuditOptions/appsettings 加 SpoolDirectory(`./data/audit-spool`)/SpoolReplayIntervalSeconds(30)/FlushMaxRetries(2)。仍會丟的極小視窗：事件僅在記憶體 channel 時硬當機（要 C 級入口同步落地才能消除）。

**② Admin UI 登入（DONE，本機驗證）:** 原 Admin UI 完全沒 gate（`AuthState.SetToken` 是死碼從沒被呼叫；`ApiClient` 打的 `/api/v1/admin/*` 是 AllowAnonymous）。新增 cookie 登入**只保護 Blazor Admin UI**（DICOMweb API 不碰）。
- `Services/Admin/AdminAuthentication.cs`：`AdminAuthCookie`(scheme "AdminCookie"/cookie "hdpacs_admin")、`AdminAuthOptions`(User/Password，預設 hdadmin/hd12!Qazxc，env `ADMIN_USER`/`ADMIN_PASSWORD` 覆寫)、`IAdminAuthenticator`+`FixedAdminAuthenticator`。**SSO 之後只換 IAdminAuthenticator 實作**，登入畫面/cookie/流程不動。
- Program.cs：**預設 scheme 改成 cookie**（`AddAuthentication(o=>o.DefaultScheme=AdminAuthCookie.Scheme)`+`AddCookie`）；**8 個 API policy 全部明確 `.AddAuthenticationSchemes("MultiScheme")`**（DicomWebRead/Write/Delete、ImportWrite、Admin*）+ AuthEndpoints `/me` 也釘 MultiScheme → API 行為不變、仍 JWT/API Key。`AddCascadingAuthenticationState()`。
- 登入/登出端點 **`/admin/auth/login`、`/admin/auth/logout`**（⚠️路徑不能用 `/admin/login`，會和 Login.razor 的 `@page` 撞成 AmbiguousMatch 500）+ `.DisableAntiforgery()`。
- Blazor：`AdminRoutes` 包 AuthorizeRouteView→NotAuthorized→`RedirectToLogin.razor`；6 個頁面（Status/AuditLogs/ApiKeys/AccessLogs/LogViewer/Settings）加 `@attribute [Authorize]`；新 `Pages/Login.razor`(@page "/admin/login" + EmptyLayout + [AllowAnonymous]，form post 到 /admin/auth/login)；NavMenu 加使用者名 + 登出。
- 已知限縮：`/api/v1/admin/*`（AdminEndpoints）仍 AllowAnonymous（UI 有 gate，但 API 可直接呼叫）；符合「只保護 Admin UI」範圍，日後可再收。

**③ WADO-RS 取回匿名 + 授權整頓（設計定案 2026-07-28，未實作）:** 完整設計文件 = `HD.Pacs.DicomWeb/docs/authz-anonymise-design.md`（實作以此為準）。演進：原本想「BasicProfile/依 key-role 觸發」，討論後**推翻**——因同事 WebViewer 分享功能:醫生看片(醫生金鑰,正常) vs 分享(SharedServer 自有金鑰,匿名),是**不同金鑰**,所以匿名**綁金鑰、DB 設定直接套**,不用 BasicProfile、不用每請求參數。定案:
- 匿名綁 API Key（`HD_API_KEY` 加「匿名規則名」欄,可空;空=正常）;規則**共用舊版 `ROUTING_ANONYMISE`**（NAME+RULE jsonb,規則建立走舊版 UI,DicomWeb 只依名稱讀套）;用**名稱**參照非 REF（跨 DB/Keycloak 友善,不下硬 FK）。
- 作用範圍:DICOM Part10 **+ 全部 metadata**（QIDO 三層 + WADO metadata 三層都遮 PII）。UID 重生用**確定性衍生**（舊 UID→固定新 UID,因 WADO 無狀態）;未知規則名 **fail-safe 拒絕**。引擎移植 HD.Net10 `HD.DicomTransmit`（Remove/Clear/ReplaceAll/Replace/ReplaceDate/ReplaceUid）。
- 顆粒度:一把匿名金鑰=全流量匿名;要分匿名/正常給 SharedServer **兩把金鑰**選用。SharedServer 金鑰縮到只 `dicomweb.read`。
- **AE_TITLE 與匿名/取回無關**（只 STOW 用,驗 AE_MAIN 啟用）;維持字串不改 AE_REF。

③ **已全部實作 + commit `009b754` + 部署 .199**（build 20260729-031936）。實作細節與**對設計文件的偏離**：

**授權 P1（乙案，但改 A 法實作）:** 移除匿名 `/api/v1/admin/api-keys`(list/create/revoke)。金鑰管理**不走 HTTP 自呼叫**——原設計 §4.4「Blazor ApiClient 自呼叫帶 cookie」在 **InteractiveServer 電路行不通**（互動事件裡 `IHttpContextAccessor.HttpContext` 為 null，拿不到 cookie 轉送）。改為 **in-process 直呼**：新增 `Services/Admin/ApiKeyAdminService.cs`（NpgsqlDataSource 直接 CRUD HD_API_KEY），`ApiKeys.razor` 注入它、頁面加 `[Authorize(Roles="system_admin")]`。受保護的 `/api/v1/api-keys`(ApiKeysEndpoints, EF, JWT+admin.api_keys) 保留給程式化呼叫。
- **§4.2 admin console 端點加鎖（已補，改用自呼叫祕鑰）**：`/api/v1/admin/status|settings|logs|access-logs|audit-logs` 原僅 loopback+AllowAnonymous。因 Blazor 電路無法帶 cookie，改用 **per-process 隨機祕鑰** `SelfCallToken`（`Services/Admin/SelfCallToken.cs`，256-bit，只在記憶體）：`ApiClient` 自呼叫附 `X-Self-Call` header，admin group endpoint filter 驗祕鑰（外加 loopback）→ SSRF 觸及 localhost 也偽造不出。另 5 個 admin console 頁面 `[Authorize]` 升為 `[Authorize(Roles="system_admin")]`（為未來 SSO 非管理者防護；現在只有 hdadmin 能登入故無影響）。
- **金鑰 UI 稽核（已補）**：`ApiKeyAdminService` 建/改/撤金鑰後寫 audit（`IAuditLogger`，actor 取自 `AuthenticationStateProvider`；電路無 HttpContext 故 SourceIp 從缺）。新增動作 `auth.api_key.update`。編輯功能：UI 每列「編輯」鈕→同彈窗帶入現有內容改 name/scopes/AE/匿名/到期（金鑰 hash 不可改），`UpdateAsync` 重名擋排除自己。
- hdadmin 角色 claim 由 `admin` 改為 **`system_admin`**（FixedAdminAuthenticator）。
- **`admin.api_keys` 授予改由 `HD_ROLE.ACCESS` 的 `dicomWeb.manageApiKeys` 鍵**（`HdUserRepository.ResolveScopes`），**不再搭 `admin.pacsSetup`**。即 `{"dicomWeb":{"manageApiKeys":{}}}`→admin.api_keys。CLI 建 key 流程：dev-token(具此鍵的 HD_USER)→JWT→`POST /api/v1/api-keys`。

**匿名 P3/P4（DONE）:** 如上 ③ 設計，全部照做。`HD_API_KEY.ANONYMISE_NAME`(text 欄，**手動 ALTER 加的，schema dump 沒有**)。引擎 `Infrastructure/Anonymisation/DicomAnonymiser.cs` + `RoutingAnonymiseRuleProvider`(讀 ROUTING_ANONYMISE，IMemoryCache 5min)；認證鑄 `anonymise` claim；WADO/QIDO 套用(HdPacs*Service)。fail-safe 未知規則回 409。Conformance 加 `extensions.anonymisation`。

**金鑰管理 UI 強化（DONE）:** AE Title 改 **AE_MAIN 下拉**（`ListAeTitlesAsync`：ENABLE=true 且 **AE_REF<>1**（排本機 PACS AE）；**上傳類 scope(dicomweb.write/import.write)→AE 必填**（import 無 DICOM 原生 AE 可退回；STOW 為一致也要）。**有效金鑰名稱不可重複**（大小寫不敏感，服務+端點兩路都擋）。列表加建立時間欄。複製鈕在**純 HTTP**（非安全上下文，clipboard API 無）**fallback `document.execCommand`**（`hdCopyText` in AdminApp.razor）。

**中文化（DONE）:** NavMenu、ApiKeys、AccessLogs 標題/表頭/狀態值全中文。

**生產 DB / 密碼外部化（已補）:** DicomWeb 生產機 .199（實際 hostname 目前 `newdicomweb`；產品/對外名定為 **`hd-dicomweb`**，未來改 hostname/DNS 別名時三者[hostname/反代 server_name/憑證 CN]要一致），連 **192.168.68.234** HDPACS（獨立於既有傳統 PACS 產品 HDPACS）。**DB 密碼已移出 appsettings**：repo `appsettings.json` 的 ConnectionString 清空、`appsettings.Development.json`（本機 dev、gitignore）排除出 publish（csproj `CopyToPublishDirectory=Never`）；正式站由 `install.sh` 互動填 → `/etc/hd-pacs-dicomweb/database.env`（root 600），systemd `EnvironmentFile` 注入 `Database__ConnectionString`。install.sh 首次遷移會偵測舊 appsettings 連線問「沿用? [Y]」、既有則問「覆蓋? [y/N]」。**部署時新 install.sh 要一起 scp。** git 歷史仍有舊密碼（未清）。ANONYMISE_NAME 欄已在 .234。HTTPS 未上（deploy/https-setup.md 有 Caddy/nginx 反代做法，屬 ops 待辦）。

**功能補齊批（commit `041b884`，已部署 .199 build 20260729-134315；DELETE 404/conformance 已驗）:**
- **Rate limiting**：`AddRateLimiter`（Program.cs）——全域每來源 IP 限額（預設 1200/min，資料端點寬鬆免壞 WebViewer 爆量）、認證端點 policy `auth`（15/min，防暴力，套在 dev-token）、**loopback 豁免**（Admin 自呼叫）；限額 appsettings `RateLimit:GeneralPerMinute/AuthPerMinute` 可調；超限 429。
- **IP 白名單生效**：`Infrastructure/Auth/IpWhitelist.cs`（單 IP + CIDR，IPv4/6），`ApiKeyAuthenticationHandler` 補上檢查（原本略過）。用**連線 IP**（RemoteIpAddress）判定不用 XFF；設定壞掉不鎖死合法金鑰（fail-open on parse error）。設定 IP_WHITELIST 目前走 SQL（UI 未加）。
- **DB migration 版本化**：`Database/migrations/`（README + 冪等 SQL `001_..ae_title`/`002_..anonymise_name` + `apply.sh`）。因 HDPACS DB 與傳統 PACS 共用、用 SQL dump 管理，故用**冪等 SQL** 而非 EF migration（避免打架）。解決 ANONYMISE_NAME 手動 ALTER 漂移問題。
- **DELETE 端點**：`DELETE /dicomweb/studies/{uid}[/series/{uid}[/instances/{uid}]]`，需 `dicomweb.delete` scope。**關鍵：委派 legacy `public.delete_dicom(jsonb)`**（不手寫 DELETE）——由 UID 解析內部 REF（RC_STUDY.STUDY_REF 等），呼叫函式排 `CACHE_DELETE` job（非同步，PACS worker 處理實際刪檔+下游）。函式內建保護：受保護/已封存(不可刪DB)/未關閉STATUS='N'/無近線備份→回 false=Refused(409)。`?deleteDatabase=false` 僅清快取(預設 true 連 DB)。`skipNewStudy=true` 不刪接收中研究。`IDicomDeleteService`/`HdPacsDeleteService`；有稽核(`dicom.delete`)。Conformance 加 delete/rateLimit 聲明。

**WADO-URI 匿名改金鑰驅動(2026-08-03,commit `43426d5`,已部署 .199 build 20260803-013853,生產實測全通過):** 原 `WadoUriEndpoints.cs` 遇 `anonymize=yes` 直接回 **501**。改為對齊 WADO-RS 的金鑰驅動:URI 本來就轉發 `IWadoService`(有匿名金鑰即自動去識別),只是端點在呼叫前把 anonymize 擋掉。修法=移除 501,`anonymize=yes` 時檢查 `ctx.User.FindFirst("anonymise")`——金鑰有綁規則→交 service 依規則去識別;**沒綁規則→403 fail-safe**(不靜默回可識別資料,稽核記 `anonymize_requested_but_key_not_anonymising`);非 "yes" 值仍 400。沒另做 per-request 匿名引擎(維持匿名綁金鑰設計)。rendered(jpeg/png)無 metadata 不漏 PII 維持原樣。認證機制對照見 [[reference_dicomweb_auth]]。

**狀態:**
- 匿名/授權/AE/重名/中文化/複製 fallback = commit **`009b754`**，已部署 .199（build 20260729-031936）。
- 金鑰**編輯 UI** + AE 改 AE_MAIN 下拉 + **DB 密碼外部化** + 金鑰**稽核** + admin **自呼叫祕鑰加鎖** + HTTPS 文件 = commit **`5211a9b`**。
- Rate limiting + IP 白名單 + DB migration 版本化(`db/migrations/`) + DELETE 端點 = commit **`041b884`**。
- **IP 白名單 UI**(建立/編輯表單 textarea 每行一筆 IP/CIDR、存前驗證防鎖死、`IpWhitelist.IsValidEntry`) = commit **`25d5065`**，已部署 .199（build 20260729-143404）。IP_WHITELIST 欄使用者已手動加。
- 5211a9b + 041b884 **已一起部署 .199**（build 20260729-134315；install.sh 首次互動 DB「沿用舊設定」成功、密碼externalize 生效；DELETE 404 + conformance delete/rateLimit 已驗）。DB 三個增量欄由使用者在 pgAdmin 手動下(AE_TITLE/ANONYMISE_NAME/IP_WHITELIST，對應 db/migrations 001-003)。
- 剩未做：HTTPS 上線（ops，deploy/https-setup.md）、P2 角色細化、P5 Keycloak；install.sh 目前不自動跑 DB migration（部署與加欄解耦，加欄用 db/migrations/apply.sh 或手動 SQL）。
- 部署走 `deploy/install.sh`（framework-dependent tgz；本機 `dotnet publish -r linux-x64 --no-self-contained` 打包 `hd-pacs-linux.tgz`，gitignore）。**下次部署 install.sh 有改（互動問 DB），要一起 scp**；首次會問「沿用舊連線 [Y]」。

**視訊 rendered（alpha.24，2026-09-01）：** `Accept: video/mp4`（或 video/mpeg／video/H265）直接回封裝的串流，**這是標準行為**（PS3.18 表 8.7.4-1 的 Video 類），跟波形不同。教訓：**transfer syntax 不等於容器格式**——同樣是 `.102`（MPEG-4 AVC），有的產生端封 MP4（`ftyp` box）、有的封 H.264 Annex-B 裸流，兩者都合法，但只有前者瀏覽器播得動；所以送出前看實際位元組（`DetectContainer`），要 mp4 卻是裸流就 415，不做 remux（會多背 ffmpeg）。手上那份 `D: 038b2.dcm` 是 MP4 容器，實測 STOW 進去再 `video/mp4` 取回 **sha256 完全相同**。順帶：視訊 UID 清單原本服務層與 Domain 各一份（只有服務層那份認得 Fragmentable 的 `.1` 變體），已合併；WADO-URI 的 406 原本 body 全空，現在帶 `supportedMediaTypes`。

**波形加開 PDF（alpha.25，2026-09-01）：** `Accept: application/pdf` 出向量 PDF（實測 72 KB，比 PNG 的 291 KB 還小，`/FontFile` 零個）。當初關掉的理由（嵌整套 CJK 字型 13.9 MB）已被「文字轉向量路徑」解掉。**代價：PDF 文字不能選取或搜尋**（寫在 conformance 的 `pdfNote`）。兩個實作重點：①**波形的分流要排在封裝 PDF 前面**——兩者都吃 `application/pdf` 但意思不同（取出 vs 畫出來），順序反了會回「此 instance 不是封裝 PDF」，訊息正確卻幫不上忙；②快取鍵要帶型別（原本 `{uid}|ecgpng`），否則先 PNG 後 PDF 會拿到 PNG 位元組配 PDF 的 Content-Type——200 但打不開。
