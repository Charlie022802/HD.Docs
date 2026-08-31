# 影像看片（HD.DicomImageViewer / HD.DicomImageViewer.Server）

桌面 DICOM 看片（WinForms）+ 進行中的 Server 化。

- **原始碼**：`D:\Dev\HyperDigital\HD.DicomImageViewer`（git）。net10-windows（WinForms）+ 共用 lib。
- 管線：fo-dicom 解碼 → System.Drawing (GDI+) 軟體繪製。核心 `HD.DicomImageViewer.Core`。

## 桌面看片現況
- **顯示管線優化**：8 點計畫，1/2/4/6/7/8 完成 + 3 部分（cine 預取；跨 instance CT/MR 待）。重繪快取、W/L 拖曳降解析度預覽、記憶體預算 LRU、GDI handle 洩漏修正、Timer 30fps。剩：跨 instance CT/MR 預取（需設計審查）。
- **MPR 3D**：2D + 3D 皆完成；3D 走 OpenTK.GLControl（GLSL raymarch）。
- 狀態列：ZoomFactor/PixelValue 等移到 StudyControl 底部。

## 影像實際是誰送的（現行架構，容易誤解）

看片端的資料流目前是**分開的兩條**，`localconfig.json` 裡是兩個獨立設定，可以指向不同主機：

| 用途 | 設定 | 對象 |
|---|---|---|
| 查詢清單、study tree、DICOM tag | `Database.Host` | PostgreSQL |
| **影像檔／JPEG／MP4** | `DownloadHost` | **`hd-web-server`** 的 `/api/v2.0/wado-uri` |

`hd-web-server` 是**同事維護的 Node 服務**，不是我們的 repo。
所以「清單查得到、影像調不出來」是正常的失敗形狀，兩邊要分開查 ——
排障方式、已知地雷、事件記錄見 [hd-web-server.md](hd-web-server.md)。

（下面的 Server 化目標架構會讓這條路改走 **ViewerWebApi 轉送**，後端可設成 hd-web-server
或 HD.DicomWeb，屆時 `DownloadHost` 退場。）

## Viewer Server / ViewerWebApi（進行中）
新專案 `HD.DicomImageViewer.Server`（ASP.NET Core net10，Blazor Server 管理 UI + Web API），部署為 Linux systemd。目的：把客戶端「直連 Postgres」收到伺服器後面（**DB 密碼只留伺服器**）+ 管理後台。

### 目標架構（2026-08-17 立案，2026-08-25 修訂為單一前門）
**看片端只跟 ViewerWebApi 說話**，不再直接碰資料庫，也不直接碰影像來源：

```
Viewer ──► ViewerWebApi ──┬─► [legacy]   hd-web-server（WADO-URI）
                          ├─► [dicomweb] HD.DicomWeb（WADO-RS）
                          └─► DB（清單 / QC / 設定 / KeyImage / hanging）
```

舊的 `DownloadHost` 退場，`localconfig.json` 從「DB 帳密 + DownloadHost」瘦成**一個網址**。

**為什麼影像也走 ViewerWebApi、而不是 Viewer 直連 DicomWeb**（2026-08-25 修訂）：

1. **相容性要住在伺服器，不住在客戶端。** 沒升級主系統的醫院只要把 ViewerWebApi 設成
   `legacy`，Viewer 出一版就好。切換若放在客戶端，等於每個現場都要管一份設定。
2. **登入搬到 ViewerWebApi 之後，Viewer 就沒有 hd-web-server 的 cookie 了。**
   現在取影像靠的正是登入時 hd-web-server 給的 cookie（見 `WebApiClient` 註解）。
   由 ViewerWebApi 持有憑證轉送，客戶端完全不用管認證。
3. 兩種後端的回應形狀不同（見下），在伺服器正規化成同一種，客戶端的下載／驗證／
   重試／限流一行都不用改。

**代價**：內網流量加倍、ViewerWebApi 成為吞吐點。要求**串流轉送、不緩衝、不解析 DICOM**
（`ReadAllBytes` 再吐出去會被一個 CT study 吃光記憶體）。日後量到瓶頸再換成 302 轉址
＋短效簽章 URL，客戶端不用改（`HttpClient` 自動跟隨轉址）。

### 新舊系統相容：唯一的差異是影像那一層（2026-08-25 定案）

需求是「同一版 Viewer 要能服務尚未升級主系統的醫院」。實查之後，新舊的差異**只有影像取得**：

| Viewer 要的 | 靠什麼 | 新舊有差嗎 |
|---|---|---|
| 檢查清單 | `viewer_station.search_study` | 兩邊都有 |
| study tree / dataset / hanging | `RC_*`＋`viewer_station.*` | 兩邊都有 |
| QC（9 個方法） | `viewer_qc` 等 | 兩邊都有 |
| 設定 / KeyImage | `get_user_config` 等 | 兩邊都有 |
| **影像取得** | WADO | **舊＝hd-web-server WADO-URI，新＝DicomWeb WADO-RS** |

所以只有影像需要「後端介面 + 兩個實作」，其餘 24 個方法是純搬遷、不分支。

**檢查清單不能改走 QIDO。** Viewer 的清單不是 DICOM 查詢——`QueryResult` 帶著
`StudyRef`（RC_STUDY 代理鍵，DicomWeb 刻意不對外露）、`Status`（流程狀態）、
`HasICad` / `ICadScore[]`（CAD 分數，DICOM 標準外）、`DateTimeCreated`。QIDO 表達不了，
硬換會讓清單少掉狀態與 iCAD。這也是舊站當初沒用 QIDO 的原因。

### 影像端點與兩種後端

ViewerWebApi 對客戶端只開一個穩定端點：

```
GET /api/v2.0/image/{studyUid}/{seriesUid}/{instanceUid}?type=dicom|jpeg
```

Viewer 實際只會要**兩種**（程式碼實查：`DownloadFileManager` 與 `PreviewJpegLoader` 各一處要 JPEG，其餘都要 DICOM）：

| type | legacy（hd-web-server） | dicomweb（WADO-RS） |
|---|---|---|
| `dicom` | `?contentType` 省略 | `GET .../instances/{uid}`＋`Accept: application/dicom` |
| `jpeg` | `?contentType=image/jpeg` | `GET .../instances/{uid}/rendered` |

**裸檔模式已經支援**：DicomWeb 的 `returnRaw = accept.Contains("application/dicom") && !accept.Contains("multipart")`，
所以 Viewer 「寫進檔案再用 fo-dicom 驗證」那段完全不用改。若送標準的
`multipart/related` 就要在伺服器拆封套，那是解 MIME 不是解 DICOM，成本可忽略。

**JPEG 的語意兩邊不同，這是唯一醫師看得到的差異：**

- 舊：回**進檔時預先轉好的 JPEG 檔**（DicomToImage 產生）
- 新：`/rendered` 是**即時渲染**，套 coerce 後的 W/L，有 REQ-004 的快取

外觀可能不同（W/L 來源不同），第一次取也較慢。方向是對的（REQ-007 本來就要停掉預轉 JPEG），
但**縮圖列是醫師每天看的東西**，切換前要在 .191 實測外觀與速度。

**視訊不是缺口**（2026-08-25 確認）：新系統不收 DicomMpeg4、轉檔功能也停用，舊版本來就不支援。
hd-web-server 的 `sendPartialMp4`（HTTP Range 分段）是網頁端用的，桌面 Viewer 沒有任何 mp4 相關程式碼。
日後若要支援，兩邊都要補。

**過濾行為兩邊不同**：DicomWeb 的 WADO 有院區過濾與匿名規則，hd-web-server 有 study-share 的
`filterCheck`。同一筆影像可能一個給一個不給——切換時要確認新後端不會擋掉現在拿得到的東西。

### 施工進度：① 影像端點 + legacy 後端（2026-08-25 完成，端到端驗證過）

- **ViewerWebApi**：`ImageController`（`api/v2.0/image/{study}/{series}/{instance}?type=dicom|jpeg`）
  ＋`IImageBackend` / `LegacyWadoUriBackend` / `ImageBackendOptions`。設定在 `appsettings` 的
  `ImageBackend` 區段。串流轉出（`ResponseHeadersRead` + `File(stream)`），不緩衝、不解析 DICOM。
- **客戶端**：`ViewerWebApiClient` 加 `useViewerApiImage` 旗標，`BuildWadoUrl` 依此組不同位址；
  `InitializeWebApiClient` 在 `ApiBaseUrl` 有設時把影像也導向 ViewerWebApi。
  **下載本身（重試、限流、fo-dicom 驗證、快取）一行都沒改。**
- **驗證**（本機跑 ViewerWebApi 對 `.221`）：登入 200、DICOM 527264 bytes、JPEG 26150 bytes，
  且**與直接跟 hd-web-server 取的位元組 sha256 完全相同**——轉送沒有動到任何內容。
  第二次請求 121ms（cookie 重用，沒有重登）。

### 施工進度：② dicomweb 後端（2026-08-25 完成，含效能實測）

`DicomWebRsBackend`：`dicom` → `/instances/{uid}`（`Accept: application/dicom` 裸檔模式）、
`jpeg` → `/rendered`、**`thumbnail` → `/thumbnail`**。三種都對 `.199` 實測過，
`DICM` 與 `ffd8` 檔頭正確、裸檔模式生效（不是 multipart）。

**縮圖改對到 `/thumbnail` 而不是 `/rendered`**：實測 4.5KB vs 134KB（小 30 倍），
而縮圖列本來就只要小圖。客戶端由 `PreviewJpegLoader` 傳 `thumbnail: true` 區分；
舊後端沒有縮圖概念，兩者都回同一張預轉檔，**行為不變**。

#### 效能實測（每組 20 張冷啟、同一 study、各組不同 instance）

| 並行度 | 舊：預轉 JPEG（45KB） | 新：`/thumbnail`（4.5KB） |
|---|---|---|
| 1 | 0.099s | 0.212s |
| 4 | 0.029s | 0.074s |
| 8 | 0.033s | 0.065s |
| 16 | 0.025s | 0.055s |

換算 300 張的縮圖列：

| | 時間 |
|---|---|
| 舊：預轉 JPEG @4 | **8.8s**（每次都一樣） |
| 新：冷啟 @4 / @8 / @16 | 22.1s / 19.4s / 16.4s |
| **新：快取命中 @4** | **1.6s** |

**結論：第一次慢 2.5 倍，之後快 5.5 倍。** 慢的是 CPU（解碼＋縮放＋編碼），不是網路
——新的傳輸量只有舊的十分之一。加上 Viewer 本機還有磁碟快取，同一台 PC 只有第一次會慢。

`PreviewJpegLoader.MaxParallel` **4 → 8**（+12%）。不用 16：客戶端並行度會乘上醫師人數
壓到伺服器，20 位醫師同時開檢查就是 320 個併發渲染，收益遞減而風險是乘出來的。
**真正的槓桿是快取命中率，不是這個常數。**

**注意 `RenderedImageCache` 是 DicomWeb 行程內的記憶體快取，每次部署更新就會清空**
——所以每次更新後第一批開檢查的醫師都會遇到冷啟。要避免得做成落地快取或預熱（見待辦）。

**踩到的坑：hd-web-server 未登入回的是 400 不是 401。**
它有全域 preHandler（`src/index.ts` 的 `authMiddleware`），非 app 路由的驗證失敗走
`rep.badRequest()`。route 內的 `filterCheck` 只是額外的資源過濾，**不是驗證**——
只看那一段會誤以為 wado-uri 不需要登入（我一度就是這樣判斷錯的）。
排障時看到 400 要先想到「沒登入」，不要去查參數格式。

因此 `LegacyWadoUriBackend` 自己用服務帳號登入 hd-web-server（`POST /api/v2.0/user/login`，
body `{id, pw}`，與 ViewerWebApi 同形狀），cookie 存在 Singleton 的 `CookieContainer`；
上游回 400/401/403 就重登一次再試。`CookieContainer` 要自己給——`AddHttpClient` 的 handler
預設每 2 分鐘輪替，cookie 掛在 handler 上會跟著沒，變成每兩分鐘白登一次。

- **部署＝hdctl，跟 .191/.199 同一套**。**先獨立成自己一個元件**（`viewerapi`），日後要不要跟別的元件整併再說。
  每間醫院都會裝這一支——這點反過來讓「診斷包上傳」有地方落腳（見下）。

### 現況盤點（2026-08-25 重查，修正先前的計數）
- **Server 端 API 已完成**（薄代理既有 stored proc）：`Auth` / `Query` / `KeyImage` / `Config` / `QC`
  五個 controller、約 20 個端點。與現有客戶端契約相容（login cookie、access）。
- **客戶端只接了 1 處**：`ViewerApiGateway.Enabled` 在整個 codebase 只出現在
  `DicomQuery.QueryStudies`，而 `ViewerWebApiClient` 也只實作了 `SearchStudies`。
- **「56 處／86 處」的計數要修正**：那是 `CreateCommand` 的呼叫次數，不是要接的 API 數量。
  實際是 **26 個公開方法**，已接 1 個、**剩 25 個**：

  | 類別 | 方法數 | 內容 |
  |---|---|---|
  | `DicomQuery` | 12 | study tree／dataset／查詢／CFind／hanging／KeyImage 讀寫 |
  | `QualityControl` | 9 | QC 設定、三層樹、動作、轉送 job |
  | `SystemConfig` | 5 | 使用者與共用設定讀寫、匯入路徑 |

- **登入已經沒有直連 DB 的路**：`CheckUser` 一律走 WebApi，原本「`DownloadHost` 是 localhost
  就直連 DB 在客戶端比對密碼雜湊」那條已移除。
- `DicomQuery.CFind` **名不副實**：它不是 DICOM C-FIND，是呼叫 `query_dicom`。
  ViewerWebApi 的 `query/cfind` 端點沿用了這個名字，日後真要接 C-FIND 會混淆。
- Blazor Users/Clients/Settings 頁、`/account/login` CSRF 待補。

### 施工順序（2026-08-25）
把「轉送」與「換協定」拆開，因為兩者的風險完全不同：

1. **影像端點 + legacy 後端** —— 行為與現在完全相同（後面還是 hd-web-server），只是多一跳。
   Viewer 改 `BuildWadoUrl` 一處。**單獨驗證串流轉送不會變慢、不會壞**，把傳輸風險與協定風險分開。
2. **加 dicomweb 後端** —— 在 .191 實測，重點是 JPEG 縮圖的外觀與速度。
3. **接其餘 24 個方法** —— 最大宗但最單純，端點大多已存在，缺的是 `ViewerWebApiClient` 的方法
   與各 `Database/*.cs` 的分支。
4. **拿掉 Viewer 的 DB 連線能力** —— 移除 `SafePostgresConnection` 與設定檔的 `Database` 區塊。
   **這一步才算真的達成「不再直連 DB」**；只要那條路還在，它就會被用。

**診斷包上傳（REQ-016）先做、不排在遷移後面。** 它是這支服務上最獨立的一塊——不碰既有查詢、
不改 stored proc、失敗了也只是少一份診斷資料。拿它當第一個真正上線的功能，先把
「進到每間醫院、hdctl 部署與更新」這條路走通；之後遷移就是往一台已經在跑的服務上加端點。

### 端到端實測：第一次真的用 Viewer 跑完整條路（2026-08-31）

在此之前全部是 curl 與測試程式驗契約。這次拿 `ReleaseEnforce` 組建對 `.199:5100`
（`hd-viewer-api 0.1.0-alpha.4`，DB 指 `.191`）實跑，一筆 374 張的檢查，清空本機快取冷啟。

**結果：整條路都通，零錯誤。** 一輪的請求分佈：

| 端點 | 次數 |
|---|---|
| `/api/v2.0/image/…?type=dicom` | 374（＝該檢查的張數） |
| `…?type=jpeg` / `…?type=thumbnail` | 27／5 |
| `/api/v2.0/query/dicom-info` | 374 |
| `/api/v2.0/query/studies`／`study-tree`／`keyimage` | 各 1 |
| `/api/v2.0/config/user`／`config/common` | 各 1 |
| `/api/v2.0/wado-uri`（舊端點） | **0** |

時間：開啟檢查 → 最後一張 **12.5 秒**。`dicom-info` 與影像下載幾乎同時起跑
（相差 34ms），那 374 次中繼資料查詢**沒有卡在下載前面**。

#### 抓到並修掉：每次登入送兩次請求（`7b35c41`）

`InitializeWebApiClient` 建兩個 `ViewerWebApiClient`——`apiClient`（查詢）與
`webApiClient`（影像）。**遷移前兩者指向不同主機**（影像走 `DownloadHost` 上的
hd-web-server），各自登入取得各自的 cookie 是對的；影像改走 ViewerWebApi 之後
兩者指向同一台，第二次登入純屬重複。

**代價不是慢，是密碼打錯一次會在伺服器上留下兩筆失敗紀錄。** 醫院若設了
「連續 N 次失敗鎖帳號」，實際門檻直接砍半，而畫面上完全看不出來。

改法是共用同一個實例（cookie 自然共用），`CheckUser` 以 `ReferenceEquals` 判斷。
**但 `apiClient` 必須改成 `useViewerApiImage: true`** —— 它原本用預設值 `false` 建立，
直接把 `webApiClient` 指過去會讓影像悄悄退回 `/api/v2.0/wado-uri`：不報錯、影像照樣顯示，
只是繞過整個 ViewerWebApi 影像層。所以驗證要看兩件事，只數登入次數會漏掉這個。

#### 觀察到但沒改：`dicom-info` 是每張一次

374 張 → 374 次 `{"type":"objectDataset","objectRef":N}`。**這不是遷移造成的**——
直連 DB 那條分支做的是同一件事、同樣 374 次，差別只在往返從本機資料庫變成 HTTP。
實測 5.9 秒（每次約 16ms）且與下載並行，目前不是瓶頸。要不要開批次端點，
等有更大的檢查（上千張）實測過再決定。

### 授權改走 ViewerWebApi（2026-08-31，viewerapi `alpha.5`）

`/api/v2.0/license` 四個端點：`device`／`by-fingerprint`／`request`／`seen`，
對應客戶端 `LicenseRepository` 的四個方法。`ApiBaseUrl` 留空仍走直連分支。

**回應協定刻意分三種，客戶端靠它決定要不要記住：**

| 回應 | 意思 | 客戶端 |
|---|---|---|
| `200` ＋ 物件／陣列 | 找到了 | 用 |
| `200` ＋ `null` | 沒有那一列（正常結果） | 當作沒有 |
| `404` | 這台伺服器不支援授權 | **記住，不再問** |
| `5xx` | 暫時故障 | 這次放棄，**不記住** |

混在一起就沒得選：把暫時故障記成「不支援」，資料庫抖一下就停掉整個行程的授權；
反過來則是每次啟動都白等一輪重試。**「表在不在」交給 PostgreSQL 的 `42P01` 回答，
不自己先探測**——探測失敗跟表不存在長得一樣。

**三個配套**：

1. `SendRequestAsync` 加 `maxRetries` 覆寫。預設 5 次、每次隔 2 秒，一支打不通要 8 秒；
   授權一次判定打三支 ＝ **24 秒卡在登入按鈕上**，而使用者只看到「按了沒反應」。
2. 例外帶上 HTTP 狀態碼。原本只有訊息字串，要分辨 404 就得比對字串——
   那種判斷會在改一句 log 的時候安靜地失效。
3. `APP_VERSION` 的截斷移到伺服器，寬度用 `information_schema` **量**而不是用資料庫
   版本號推（更新鏈與實際結構會分岔）。

**四取二的指紋判定沒有搬到伺服器。** 那個規則寫成 SQL 就變成第二份正本，兩邊遲早不一致。
SQL 只做粗篩（任一項相同就回），認不認是客戶端 `FingerprintMatcher` 的事。

#### 實測（Viewer 對 `.199`，DB 是 `.191`）

| # | 情境 | 結果 |
|---|---|---|
| A | 直接登入 | `seen` 走 API，`LAST_SEEN_AT` 與 `APP_VERSION` 都更新；判定 28ms |
| B | 刪掉 `license.lic` | 取回落地，檔案與原始備份**逐位元相同**（794 bytes） |
| C | `license.lic` 與 `device.json` 都刪 | `by-fingerprint` 認回**同一個** `DEVICE_ID`，**清冊維持 1 列** |

**C 是最重要的一項**，它等於模擬醫師的電腦重灌：不知道自己是誰、只憑四項指紋，
把身分與授權都認回來。失敗的話會多出一列重複的機器——不報錯、不影響使用，
只有對帳時才發現。**B 證明那 794 個位元組（含換行與跳脫字元）經過
`jsonb_build_object` → HTTP → `JsonDocument` 一整趟沒被動到一個位元**，否則簽章驗不過。

#### 在舊站台上再驗一次（`.163`，DB `v2.0.26`，`APP_VERSION` 欄寬 **32**）

`.191` 的欄寬已經是 64，所以「量寬度再截斷」那段在那裡根本沒被考驗過。`.163` 才是它的目標環境。

| 驗到的 | 結果 |
|---|---|
| 版本字串截斷 | 34 字元的 `…+0800.ENFORCE` → 寫入 **32 字元**的 `…+0800.ENFOR`，沒有 `22001` |
| 暫用期以誰為準 | 本機 `device.json` 寫 17:56、畫面算出的到期時間對應 09:48 ⇒ **用資料庫的 `REQUESTED_AT`**（記本機的話重灌就能刷新＝無限試用） |
| 過期 ＋ 強制模式 | `Missing（擋下）`，78ms，跳註冊視窗並顯示裝置代碼 |

**截斷失敗的表現是「什麼都沒發生」**——`22001` 會變成 500，客戶端安靜退回離線流程，
使用者兩週後才被擋。所以判準是**去資料庫看那個字串到底變成幾個字**，不是看畫面有沒有錯誤。

### 待補：多院區過濾繞過（2026-08-25 發現）
`viewer_station.search_study` **沒有院區過濾**。2026-08-25 已把 `query_dicom`、C-MOVE、
QIDO/WADO/DELETE/UPS、MWL、匯出全部補上，但**醫師在 Viewer 上看到的檢查清單走的是這支，
完全繞過**。它已經收到 `AETitle`，掛鉤與 `query_worklist` 一樣現成。
見 [multi-site-design.md](../multi-site-design.md)。

## 待辦
- 診斷包上傳端點（REQ-016）＋ hdctl `viewerapi` 元件（第一鏟）。
- ~~客戶端側剩下 25 個方法改走 API~~ **已完成（`480cc3f`）**。實查分支數：
  `DicomQuery` 20／`QualityControl` 18／`SystemConfig` 10。
  `AccessDefinition.GetValue()` 那兩處是**死碼**（全專案無呼叫端，登入回應已帶 access），
  隨第 4 步一起刪。
- ~~**第 4 步的前置：授權機制直連 DB**~~ **已完成（2026-08-31，`9e20c00`／viewerapi `alpha.5`）**，
  見下方「授權改走 ViewerWebApi」。
- **⚠️ 第 4 步還不能做，卡在部署面而不是程式面。** 拿掉 `Database` 區塊之後，
  **沒有裝 ViewerWebApi 的站台會整個不能用**。目前 `.199` 與 `.163` 都是 `alpha.5`，
  但**若瑟現在的看片端仍是直連資料庫**。第 4 步的前置條件是
  「所有在跑的站台都已經裝上 viewerapi 並驗過」，不是「程式碼寫好了」。
- 跨 instance CT/MR 預取（顯示管線最後一項）。
- 接入共用日誌。
