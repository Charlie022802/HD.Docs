# DicomWeb

> 端點完整清單（含參數/認證/退役對照）：[dicomweb-endpoints.md](dicomweb-endpoints.md)（HD.Pacs.DicomWeb）

DICOMweb 對外 REST 服務（QIDO-RS / WADO-RS / WADO-URI / STOW-RS / DELETE / Import / UPS-RS）+ Blazor Admin UI。

- **原始碼**：`D:\Dev\HyperDigital\HD.Pacs.DicomWeb`（git，GitHub Charlie022802/HD.Pacs.DicomWeb，master）。需與 `HD.Shared` clone 到同層（ProjectReference 相對路徑）。
- **生產**：**192.168.68.199**（hostname 目前 newdicomweb；產品名定 `hd-dicomweb`），埠 **5080**，連 **192.168.68.191** 的 HDPACS DB。
  （~~連 .234~~ 是舊資訊：2026-08-05 已 repoint 到 .191，2026-08-10 再確認「DicomWeb 不上 .191、長留 .199」。
  同機的 Export API :5090 也是連 .191。**三支服務（DicomWeb／Export／.191 的主控台）共用同一張 `HD_USER`**。）
- **版本**：`Directory.Build.props`（`1.0.0-alpha.1` + 台灣時間 build 戳）。`/health` 與 `/dicomweb/conformance` 回 version+build（`Domain/AppVersion.cs`）。**安裝端不另寫版本檔**，靠 /health 查。

## 實作只有一份（2026-09-01 起）
QIDO／WADO／STOW／UPS 的實作在 `Infrastructure` 的 `HdPacs*`（Dapper 直接打 HDPACS 的 `RC_*` 表）。

**先前 Application 層另有一份對著 EF 模型寫的實作，已刪除（928 行）。** 那三支從來沒有被
建構過——同一個介面兩個註冊，誰贏完全由 `Program.cs` 裡 `AddDicomWebApplication()` 與
`AddDicomWebInfrastructure()` 的**先後順序**決定，後註冊的 Infrastructure 永遠贏。

留著的代價不是佔空間，是它**看起來完全是活的**：實作同一個介面、有一樣的短路邏輯與註解。
視訊短路曾經被補進那份永遠不會執行的檔案（白工），而每次有人要動 WADO，都得重新判斷一次
「這兩份哪一份是真的」。刪除的來由寫在 `Application/ServiceCollectionExtensions.cs` 的註冊點。

## 認證 / 授權
`MultiScheme` = JWT + API Key 兩者皆可（`X-API-Key` 或 `Bearer hdp_...`→ApiKey；其他 Bearer→JWT）。對外資料/管理 API 皆雙支援；Admin 主控台 API 限 loopback+`X-Self-Call` 祕鑰；Admin UI 走 cookie。`anonymise` claim 只 API Key 會鑄。詳見記憶 reference_dicomweb_auth。

**API Key 管理已收斂（2026-08-06）**：scope 有單一正本 `Domain/ScopeCatalog.cs`（顯示名/分類/可否指派給 API Key/是否需綁 AE），REST 驗證、Admin UI 勾選框、badge 配色皆讀它（以前散四處漂移）。CRUD 收斂成單一 `Api/Services/ApiKeyService.cs`（EF 存 `HD_API_KEY`），REST 端點（`ApiKeysEndpoints`，補了 `PUT` 編輯 + `/scopes`、`/ae-titles` 目錄端點）與 Blazor `ApiKeys.razor` 都呼叫它，退掉原 raw-SQL 的 `ApiKeyAdminService`。`export.read/write` 現在可指派（原 REST/UI 白名單漏了）。驗進來的 key 仍走 `ApiKeyAuthenticationHandler`（EF，不變）。

**✅ auth 已切 Keycloak（2026-08-07/08，部署 .199 整圈驗證）**：AuthN=Keycloak（Admin UI 登入卡→OIDC 導頁；API Bearer 驗 JWKS+aud=hd-pacs）、AuthZ 查 DB（`OnTokenValidated` 以 `preferred_username` 查 `HD_USER`→`ResolveScopes` 補 scopes，**無對應 HD_USER 一律 401**）；自鑄 token 那串（`JwtIssuer`/`/api/v1/auth/dev-token`/`DevSigningKeyProvider`/`HD_USER.PASSWORD`/固定管理帳密）已退役；**金鑰管理端點+UI 同步下架**（搬 HD 後端管理主控台，本站只驗）。導頁登入的坑（SaveTokens/challenge/post-logout `+`/http 三坑）見 [identity.md](identity.md)。工具面：ApiTest/TestClient 的 dev-token 登入待改。

## 功能現況（皆已上生產）
- **QIDO**：study/series/instance；transfer syntax（0008,3002）；ModalitiesInStudy 陣列比對；通用 includefield；study 補生日/性別/年紀/description。
- **WADO-RS**：metadata / 影像 / frames / rendered / thumbnail；**非影像型別的 rendered（見下節）**；**出口疊合（coerce-on-retrieve）試點已上**（`HdPacsWadoService`：載入→ApplyCoercion→父表 UID→選擇性匿名→重序列化）；可重建疊合快取（CoercedInstanceCache）；lenient 解析（壞 tag 不害整份）。
- **WADO-URI**：舊版相容；**anonymize 改金鑰驅動、fail-safe 403**（commit 43426d5，已上 .199 build 20260803-013853）。
- **STOW**：入庫；file-meta transfer syntax 併入 DATASET。
- **DELETE**：委派 legacy `delete_dicom`（排 CACHE_DELETE job）。
- **UPS-RS**：工作清單（建/搜/取/改狀態/改屬性/取消/訂閱+WebSocket/filtered 訂閱）；獨立 `UPS_WORKITEM`/`UPS_SUBSCRIPTION` 表；橋接 HDM worklist（MWL 可見）。
- **強化**：稽核落地緩衝、Admin 登入、匿名綁金鑰、Rate limiting、IP 白名單、金鑰管理 UP、DB migration 版本化（`db/migrations`）。

## 非影像型別的 rendered（PDF / SR / 波形）

同一個 `/rendered` 端點依 **SOP Class** 分流，用 `Accept`（WADO-RS）或 `contentType`（WADO-URI）
決定輸出。標準依據是 PS3.18 表 8.7.4-1，它把可渲染的 instance 分成四類：
Single Frame Image／Multi-frame Image／Video／**Text**。

| 型別 | 輸出 | 標準怎麼說 | 狀態 |
|---|---|---|---|
| Encapsulated PDF | `application/pdf` | Text 類，標準行為 | ✅ `alpha.17` |
| Structured Report | `text/html` | Text 類，標準行為 | ✅ `alpha.18` |
| Waveform（ECG） | 未定 | **標準沒有定義**，屬我們的擴充 | 未做 |

**PDF 不是渲染，是取出**——它本來就完整躺在 `EncapsulatedDocument` 欄位裡。
**SR 才是真正的渲染**，而且做壞比不做糟，理由見 `SrHtmlRenderer` 的類別註解
（同一個射出分率會出現多次，哪個是代表值只能靠修飾語分辨）。

**波形要另外宣告。** 標準的 rendered 類別裡沒有它，所以那會是 `extensions` 區塊裡的擴充，
不能混在標準行為裡講——否則將來別人照標準寫的客戶端對不上時，沒有地方查得到這是誰的決定。

三種型別對錯配一律回 415 並說明下一步（對 SR 要 jpeg、對影像要 pdf、對 PDF 要縮圖或影格…）。
**沒有像素的型別問 `/frames` 也要回 415** —— 不擋的話是 500 加空的 body，
而 500 在現場會被判斷成「這個檔案壞了」。

### WebViewer 要怎麼顯示

**限制先講**：WADO 端點要帶憑證標頭，而 `<img src>`／`<iframe src>` 這類標籤**沒辦法帶標頭**。
所以不能把網址直接填進去，必須「先抓、再顯示」：前端自己 `fetch`（這時可以帶 token），
拿到內容後轉成 blob，再交給 `<iframe>`／`<img>`。CORS 已設定好（會回應 Origin、允許
credentials），回應也沒有 `X-Frame-Options` 或 CSP，所以嵌得進去。

**憑證用 Keycloak 的 JWT，不要用 API 金鑰**——金鑰放進前端等於公開。

**SR 與 PDF 都放進 `<iframe>`，不要塞進 `innerHTML`。** 我們回的 SR 是一整份 HTML 文件、
自帶樣式，塞進頁面會汙染 WebViewer 本身的版面，也等於直接信任伺服器來的標記。
iframe 給的是隔離，而且可以再加 `sandbox`（那份 HTML 不需要執行任何 script）。

**取捨要先知道：iframe 是個密封盒子。** 它顯示得出來，但 WebViewer 對裡面沒有控制權——
不能跟著主題切深色、不能摺疊章節或搜尋，而且 **SR 裡的 `IMAGE` 參照點不進去**
（現在渲染成「（參照其他 DICOM 物件）」）。

最後那項最可能變成需求。**真的要能點的時候，就不能用 iframe**，而要讓前端拿 `/metadata`
的 JSON 自己畫——等於把 `SrHtmlRenderer` 那套關係型別分工邏輯在前端重寫一次，兩邊之後會漂移。

**建議先用 iframe**：現在就能動、前端幾乎零成本，而且它是**任何 DICOMweb 客戶端**都拿得到的
東西，不是為 WebViewer 特製的。等「影像參照要能點」真的出現，那才是搬到前端的時機，
而伺服器這份仍然留著給其他客戶端。

## 部署
自有流程（非 podman）：`deploy/install.sh`（framework-dependent tgz、systemd、保留 data/logs、互動 DB）。打包 `publish/hd-pacs-linux.tgz`。部署到 hdadmin@.199：publish+打包開發端做、上傳/install.sh 使用者跑（ssh 需密碼）。DB 密碼externalize 到 `/etc/hd-pacs-dicomweb/database.env`。

## 待辦 / 未來
- HTTPS 上線（`deploy/https-setup.md`）、P2 角色、P5 Keycloak（見上「未來 auth 走 Keycloak」）。
- **REQ-003 Export API**：程式面三支端點已在（薄殼），但**定案改獨立成一支 API、不併 DicomWeb**（見 [backlog.md](../backlog.md) / 記憶 project_req003_export_webapi）。auth 沿用「先保留一條路、之後接 Keycloak」。
- 未來與主 PACS 統一部署（hdctl）時併為一個 component、位置與 .234 對齊。
