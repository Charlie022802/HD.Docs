# DicomWeb

> 端點完整清單（含參數/認證/退役對照）：[dicomweb-endpoints.md](dicomweb-endpoints.md)（HD.Pacs.DicomWeb）

DICOMweb 對外 REST 服務（QIDO-RS / WADO-RS / WADO-URI / STOW-RS / DELETE / Import / UPS-RS）+ Blazor Admin UI。

- **原始碼**：`D:\Dev\HyperDigital\HD.Pacs.DicomWeb`（git，GitHub Charlie022802/HD.Pacs.DicomWeb，master）。需與 `HD.Shared` clone 到同層（ProjectReference 相對路徑）。
- **生產**：**192.168.68.199**（hostname 目前 newdicomweb；產品名定 `hd-dicomweb`），埠 **5080**，連 **192.168.68.191** 的 HDPACS DB。
  （~~連 .234~~ 是舊資訊：2026-08-05 已 repoint 到 .191，2026-08-10 再確認「DicomWeb 不上 .191、長留 .199」。
  同機的 Export API :5090 也是連 .191。**三支服務（DicomWeb／Export／.191 的主控台）共用同一張 `HD_USER`**。）
- **版本**：`Directory.Build.props`（`1.0.0-alpha.1` + 台灣時間 build 戳）。`/health` 與 `/dicomweb/conformance` 回 version+build（`Domain/AppVersion.cs`）。**安裝端不另寫版本檔**，靠 /health 查。

## 雙軌實作（重要）
每個服務有兩套：Application 層 EF Core 版、Infrastructure 層 Dapper 版（`HdPacsQidoService`/`HdPacsWadoService`/`HdPacsStowService`/`HdPacsUpsService`）。**生產（.199 接真 HDPACS）跑 HdPacs* 版**（`Infrastructure/ServiceCollectionExtensions.cs` 覆蓋 DI）。**改生產行為要改 HdPacs\* 版。**

## 認證 / 授權
`MultiScheme` = JWT + API Key 兩者皆可（`X-API-Key` 或 `Bearer hdp_...`→ApiKey；其他 Bearer→JWT）。對外資料/管理 API 皆雙支援；Admin 主控台 API 限 loopback+`X-Self-Call` 祕鑰；Admin UI 走 cookie。`anonymise` claim 只 API Key 會鑄。詳見記憶 reference_dicomweb_auth。

**API Key 管理已收斂（2026-08-06）**：scope 有單一正本 `Domain/ScopeCatalog.cs`（顯示名/分類/可否指派給 API Key/是否需綁 AE），REST 驗證、Admin UI 勾選框、badge 配色皆讀它（以前散四處漂移）。CRUD 收斂成單一 `Api/Services/ApiKeyService.cs`（EF 存 `HD_API_KEY`），REST 端點（`ApiKeysEndpoints`，補了 `PUT` 編輯 + `/scopes`、`/ae-titles` 目錄端點）與 Blazor `ApiKeys.razor` 都呼叫它，退掉原 raw-SQL 的 `ApiKeyAdminService`。`export.read/write` 現在可指派（原 REST/UI 白名單漏了）。驗進來的 key 仍走 `ApiKeyAuthenticationHandler`（EF，不變）。

**✅ auth 已切 Keycloak（2026-08-07/08，部署 .199 整圈驗證）**：AuthN=Keycloak（Admin UI 登入卡→OIDC 導頁；API Bearer 驗 JWKS+aud=hd-pacs）、AuthZ 查 DB（`OnTokenValidated` 以 `preferred_username` 查 `HD_USER`→`ResolveScopes` 補 scopes，**無對應 HD_USER 一律 401**）；自鑄 token 那串（`JwtIssuer`/`/api/v1/auth/dev-token`/`DevSigningKeyProvider`/`HD_USER.PASSWORD`/固定管理帳密）已退役；**金鑰管理端點+UI 同步下架**（搬 HD 後端管理主控台，本站只驗）。導頁登入的坑（SaveTokens/challenge/post-logout `+`/http 三坑）見 [identity.md](identity.md)。工具面：ApiTest/TestClient 的 dev-token 登入待改。

## 功能現況（皆已上生產）
- **QIDO**：study/series/instance；transfer syntax（0008,3002）；ModalitiesInStudy 陣列比對；通用 includefield；study 補生日/性別/年紀/description。
- **WADO-RS**：metadata / 影像 / frames / rendered / thumbnail；**出口疊合（coerce-on-retrieve）試點已上**（`HdPacsWadoService`：載入→ApplyCoercion→父表 UID→選擇性匿名→重序列化）；可重建疊合快取（CoercedInstanceCache）；lenient 解析（壞 tag 不害整份）。
- **WADO-URI**：舊版相容；**anonymize 改金鑰驅動、fail-safe 403**（commit 43426d5，已上 .199 build 20260803-013853）。
- **STOW**：入庫；file-meta transfer syntax 併入 DATASET。
- **DELETE**：委派 legacy `delete_dicom`（排 CACHE_DELETE job）。
- **UPS-RS**：工作清單（建/搜/取/改狀態/改屬性/取消/訂閱+WebSocket/filtered 訂閱）；獨立 `UPS_WORKITEM`/`UPS_SUBSCRIPTION` 表；橋接 HDM worklist（MWL 可見）。
- **強化**：稽核落地緩衝、Admin 登入、匿名綁金鑰、Rate limiting、IP 白名單、金鑰管理 UP、DB migration 版本化（`db/migrations`）。

## 部署
自有流程（非 podman）：`deploy/install.sh`（framework-dependent tgz、systemd、保留 data/logs、互動 DB）。打包 `publish/hd-pacs-linux.tgz`。部署到 hdadmin@.199：publish+打包開發端做、上傳/install.sh 使用者跑（ssh 需密碼）。DB 密碼externalize 到 `/etc/hd-pacs-dicomweb/database.env`。

## 待辦 / 未來
- HTTPS 上線（`deploy/https-setup.md`）、P2 角色、P5 Keycloak（見上「未來 auth 走 Keycloak」）。
- **REQ-003 Export API**：程式面三支端點已在（薄殼），但**定案改獨立成一支 API、不併 DicomWeb**（見 [backlog.md](../backlog.md) / 記憶 project_req003_export_webapi）。auth 沿用「先保留一條路、之後接 Keycloak」。
- 未來與主 PACS 統一部署（hdctl）時併為一個 component、位置與 .234 對齊。
