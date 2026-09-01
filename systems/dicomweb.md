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
| 視訊（MPEG-2／MPEG-4 AVC／HEVC） | `video/mpeg`／`video/mp4`／`video/H265` | Video 類，標準行為 | ✅ `alpha.24` |
| Waveform（ECG） | `image/png`（看）／`application/pdf`（印）／`image/svg+xml`（嵌） | **標準沒有定義**，屬我們的擴充 | ✅ `alpha.20`／PDF `alpha.25`／SVG `alpha.26` |

**PDF 不是渲染，是取出**——它本來就完整躺在 `EncapsulatedDocument` 欄位裡。
**SR 才是真正的渲染**，而且做壞比不做糟，理由見 `SrHtmlRenderer` 的類別註解
（同一個射出分率會出現多次，哪個是代表值只能靠修飾語分辨）。

**波形另外宣告在 `extensions.waveformRendering`**，含 `standard: "none — DICOM PS3.18 does not
define a rendered representation for waveforms"`。不混在標準行為裡講，是為了讓別人照標準寫的
客戶端對不上時，查得到這是誰的決定。渲染本體在 [`HD.Ecg`](https://forgejo.hdtech.tw/charlie/HD.Ecg)。

**波形 PNG 與 PDF 都有（PDF 於 alpha.25 開通）。** PDF 曾經因為體積關掉：上游會把整套 CJK 字型嵌進去——實測 13.9 MB，其中
13,929,598 bytes 是單一個 `/FontFile2`，真正的圖形內容只有 38 KB。
解法不是子集化（SkiaSharp 不做），是**把文字轉成向量路徑**：PDF 裡沒有任何字型，
但仍然是向量——96 KB，145 倍小。而向量正是 ECG 要 PDF 的唯一理由：心臟科醫師拿卡尺量
紙本上的間期，25 mm/s 必須是紙上真實的 25 毫米，PNG 列印出來的尺寸不保證。
**代價：PDF 裡的文字不能選取或搜尋。** PNG 不走這條（點陣不需要，小字級下字型渲染比路徑填色清楚）。

分流順序上，**波形要排在封裝 PDF 前面**：兩者都吃 `application/pdf`，但意思完全不同
（封裝 PDF 是「把躺在那裡的 PDF 取出來」，波形是「把訊號畫成 PDF」）。順序反了的話，
對波形要 `application/pdf` 會得到「此 instance 不是封裝 PDF」——訊息正確但完全幫不上忙。

**SVG（alpha.26，老闆要求）是三種輸出裡唯一不依賴伺服器字型的。** 它的文字是 `<text>` 元素，
由瀏覽器用自己的字型畫——「病人姓名變豆腐」那個無聲的失敗在這條路上不存在（改由客戶端負責，
而客戶端幾乎都有 CJK 字型）。文字也可以選取與搜尋（PDF 那條是向量路徑，不行），
前端還可以直接進 DOM 套 CSS。我們產出的 SVG 不含 `script` 與 `foreignObject`。

順帶修掉上游一個坑：`RenderSvg` 失敗時回的是**一張寫著錯誤訊息的 SVG**——對人友善，
對呼叫端是災難，因為它跟成功長得一模一樣（同樣是合法的 SVG），服務層照樣回 HTTP 200。
現在多一個 `RenderSvg(source, options, out error)` 多載，失敗回 null，DicomWeb 走那條。

### ⚠️ 部署前提：主機要有 fontconfig 與 CJK 字型

波形繪製走 SkiaSharp，需要系統的 `libfontconfig` 與 `libfreetype`；而**病人姓名要靠 CJK 字型**。

```bash
# RHEL 9/10
sudo dnf install -y google-noto-sans-cjk-vf-fonts
sudo systemctl restart hd-dicomweb      # 字型偵測結果有快取
```

**這個缺失是完全無聲的。** 少了 CJK 字型時波形照樣畫得出來、HTTP 照樣 200、日誌一句話都不會說
——標籤會自動退回英文（良性降級），但**病人姓名沒有英文可退**，會變成一排豆腐。而且
**只有全新環境會踩到**，既有機器裝過就不會再犯。

所以不要只靠這份文件：**`/health` 有 `ecgFontCoverage` 欄位**（`None`／`Latin`／`Cjk`），
部署後看一眼就知道，而 hdctl 的健檢本來就會打 `/health`。

> 實測：`.199` 初次部署時是 `Latin`——37 個字型、`fc-list :lang=zh-tw` 為 0。
> 裝了 `google-noto-sans-cjk-vf-fonts`（12 個 CJK 字型）並重啟後變成 `Cjk`，中文標籤回來。
> 這個差異是靠「本機 266 KB vs 伺服器 282 KB」的 6% 檔案大小差追出來的——
> 只看「有沒有回 200」會完全錯過。

四種型別對錯配一律回 415 並說明下一步（對 SR 要 jpeg、對影像要 pdf、對 PDF 要縮圖或影格…）。

**視訊多一道容器檢查（alpha.24）。** transfer syntax 說的是「怎麼編碼」，沒說「裝在什麼容器裡」——
同樣是 MPEG-4 AVC（`.102`），有的產生端封的是 MP4（開頭有 `ftyp` box），有的封的是 H.264 Annex-B
裸位元流，兩者都合法，但**只有前者瀏覽器的 `<video>` 播得動**。所以送出前會看實際位元組：
要 `video/mp4` 卻是裸流就回 415 並要對方取整份 DICOM，不做 remux（那要背 ffmpeg，是部署前提，
等真的遇到再說）。不檢查的話得到的是「HTTP 200、檔案有大小、就是不會動」——比明確的錯誤糟得多。
實測手上那份 `.102` 的檔案是 MP4 容器（`00 00 00 20 66 74 79 70 69 73 6f 6d`），可以直送。

**沒有像素的型別問 `/frames` 也要回 415** —— 不擋的話是 500 加空的 body，
而 500 在現場會被判斷成「這個檔案壞了」。

### 匿名規則與 rendered 的非影像路徑（alpha.27 修）

**到 alpha.26 為止，rendered 的四條非影像路徑完全沒有套匿名規則。** 而其中三條會把病人資訊送出去：

| 路徑 | 資訊從哪來 | 修法 |
|---|---|---|
| ECG | **我們自己畫進圖裡**（姓名／病歷號）| `EcgViewOptions.Anonymize`，真的遮掉 |
| SR HTML | **我們自己印的表頭**（`SrHtmlRenderer.cs`）| 先把規則套在 dataset 上再渲染 |
| 封裝 PDF | 原始文件原樣送出 | **改不了** → 403 `anonymisation_not_possible` |
| 視訊 | 像素燒錄（超音波常見）| 不處理——既有的影像 rendered 本來就這樣，不是這幾條引入的 |

對外的承諾是「所有 WADO 取得＋QIDO 結果自動去識別，client 無法選退」，這三條把那個承諾破掉了。
發現的過程是去查「能不能開排版參數給客戶端選」，看到 `EcgViewOptions` 有個 `Anonymize` 才回頭問
「那我們現在有在用嗎」——**答案是沒有**。

**快取鍵也要帶匿名旗標**（`{uid}|ecg|{format}|anon|raw`）。不帶的話兩種請求共用同一格：
一般金鑰先取過的那份會被匿名金鑰拿到——**那是把可識別資料送給不該看到的人，而且完全無聲**。

封裝 PDF 那條回 403 而不是靜默送出，跟 WADO-URI `anonymize=yes` 沒綁規則時回 403 是同一個原則：
**寧可拒絕，也不要回可識別資料**。一般金鑰不受影響，照常拿得到。

驗收腳本 `tests/manual/Verify-AnonymisedRendered.ps1`（兩把金鑰對打同一份資料）。
**SVG 讓 ECG 這條第一次可以自動檢查**——文字是 `<text>` 元素，病歷號在不在 grep 一下就知道；
PNG 與 PDF 要 OCR 才驗得了，腳本只能存檔讓人看一眼。

### Keycloak 未設定的站台（alpha.23 修）

`Keycloak__Authority` 留空是**文件宣稱支援**的設定（新醫院還沒自建院內 Keycloak 時，先只收 API Key）。
實際上到 alpha.22 為止它會讓**整台服務每個請求都 500，包括 `/health`**：
OIDC handler 是 `IAuthenticationRequestHandler`（要攔回跳路徑），`AuthenticationMiddleware`
每個請求都會把它建出來一次，而空字串過不了 options 驗證。JWT 那邊是同一個病，
空 Authority 在 `PostConfigure` 就丟「must use HTTPS」，讓帶保護的端點回 500 而不是 401。

現在兩個 scheme 都只在 Authority 有值時才註冊；沒有 SSO 時 `MultiScheme` 一律轉給 API Key，
`/admin/auth/login` 回 503 並說明設定檔位置（而不是 Challenge 一個不存在的 scheme）。

**既有站台全都有設 Authority，所以這個坑只有全新醫院會踩到**，
而且它踩到的樣子是「服務 active、hdctl 說安裝成功，然後每一支 API 都 500」。
順帶一提，整包整合測試（34 條）從 Keycloak 切換後就是全紅的，正是同一個原因——
沒人跑它，所以沒人看到它在喊。

### 客戶端怎麼知道「這份 DICOM 可以轉成什麼」（alpha.22）

**標準沒有這個機制。** 沒有 `OPTIONS`、沒有回應標頭、QIDO 也沒有這個欄位——
PS3.18 假設客戶端自己認得 SOP Class。所以我們補了兩條，一條事先查、一條試了就知道。

**① `/dicomweb/conformance` 的 `renderedMediaTypes`（機器可讀）**

原本三種型別的宣告方式不一致：波形（唯一的擴充）有 `mediaTypes` 與 `sopClasses` 陣列，
而封裝 PDF 與 SR 這兩個**標準行為**只寫在 WADO-RS 的 note 字串裡——一句英文散文，程式剖析不了。
那是因為做波形時特地想過「別人怎麼知道這是擴充」，做前兩個時沒想到這一層。
現在四類（image／document／report／waveform）都是同一種形狀，各帶 `mediaTypes`、`standard`，
以及 `sopClasses` 或 `sopClassPrefix`；拿 metadata 的 `(0008,0016)` 一比即可。

**② 415 回應的 `supportedMediaTypes`（RFC 9110 對 406 本來就這樣要求）**

```json
{
  "title": "Instance not renderable in the requested media type",
  "status": 415,
  "detail": "此為 Structured Report，沒有影像資料，無法輸出靜圖。請改以 Accept: text/html 取回報告。",
  "supportedMediaTypes": ["text/html"]
}
```

**這條比較重要**，因為它是唯一「一定會被走到」的發現路徑——只要有人 `Accept` 寫錯就會遇到。
`detail` 人看得懂，但程式得剖析字串。錯誤本身就該是答案，而且要機器讀得懂。

順帶修掉的假資訊：三處 415 的稽核 `reason` 一律寫著 `video_not_renderable`（視訊那一輪留下的，
現在同一條路徑要服務四種型別），WADO-URI 那條連 `title` 都還寫著 `Video instance…`
且完全沒帶清單。**稽核裡的錯誤分類寫錯，比沒有分類更糟**——查的人會被帶往錯的方向。
現在一律 `media_type_not_supported`，兩條路（WADO-RS／WADO-URI）共用同一個 helper。

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
