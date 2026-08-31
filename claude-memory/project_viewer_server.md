---
name: project-viewer-server
description: "ViewerWebApi(HD.DicomImageViewer.Server)—看片端只對它+DicomWeb、不再直連DB;伺服器端與客戶端遷移都已寫完,2026-08-31 用真 Viewer 端到端跑通(374 張、12.5 秒、零錯誤);剩第4步拿掉DB連線,前置=授權機制還直連DB"
metadata: 
  node_type: memory
  type: project
  originSessionId: 67bc2ae6-64eb-431b-aeab-11935a1b18ab
  modified: 2026-08-17T03:51:23.064Z
---

新專案 **`src/HD.DicomImageViewer.Server`**（ASP.NET Core net10.0，Blazor Server 管理 UI + Web API），部署為 **Linux x64 systemd 服務**。目的：把客戶端「直連 Postgres」收到伺服器後面，讓 **DB 密碼只留在伺服器**（解決客戶端看得到密碼的問題，即前面 license 討論的 Level C）＋管理後台。已加入 sln。建立於 2026-07-06。

**重用**：參考 `HD.DicomImageViewer.Shared`（改成單一 `net10.0`——本身無 Windows 相依，net10.0-windows 的 WinForms 端仍可參照）取得 `SafePostgresConnection`/`PostgresSettings`/`HDUserRequest/Response`。曾短暫多標的但改回單一以免 VS 相依性顯示驚嘆號。

**與現有客戶端契約相容**（沿用不改客戶端）：
- `POST /api/v2.0/user/login` body `{id,pw}` → 成功設 Cookie + 回 `{access,userInfo}`。驗證走 DB `public.get_user_info` + `BCrypt.Verify(pw + "HyperD!git@l", hash)`（固定 salt 尾綴，與舊 SystemConfig 一致）。
- `GET /api/v2.0/config/section/{section}/key/{key}`（目前回 404 骨架）。
- login 的 `access` 已接：AccessService 對 stationViewer/mammoViewer/qualityControlViewer 各呼叫 DB `viewer_station.get_access_definition({userId,section})` 組成 access；userInfo 含 id/name/uuid/group/groupRef。與客戶端 AccessDefinition.SetContent(access[section]) / LoginSession 對齊。注意 get_user_info 的 includeField 只能放 HD_USER 真欄位(PASSWORD/GROUP_REF)，GROUP_NAME 會 42703。
- 認證 = Cookie(scheme HDViewerAuth)；/api 未授權回 401 不轉址。

**組成**：Program.cs(Serilog+Cookie+Blazor+controllers+API記錄中介層)、Services/UserService、Services/ApiCallLogStore(環形緩衝供監控頁)、Middleware/ApiCallLoggingMiddleware、Controllers/{Auth,Config}、Components/(Blazor: ApiMonitor=/、Users、Settings、Clients、Login[SSR表單post /account/login])。appsettings 的 Database 區段=伺服器端連線(密碼建議用環境變數 `Database__Password` 覆寫)。Kestrel 預設 0.0.0.0:8080。

**部署**：`deploy/hdviewer-server.service`(systemd) + `deploy/README.md`。發布 `dotnet publish -c Release -r linux-x64 --self-contained true`。已驗證發布到 D:\Dev\Publish\ViewerServer(353檔/108MB/含 libcoreclr.so)、smoke test 過(healthz 200 / login 頁 / 未授權 API 401)。

**Server 端 API 面已完成(2026-07-06)**，全部薄代理(收 JSON → 呼叫既有 stored proc → 原樣回傳、需登入 Cookie、用 Services/PgProxy)。已 push 到 master：
- Query: /api/v2.0/query/{studies,study-tree,hanging,dicom-info,cfind} → search_study/get_study_elements/query_study/get_dicom_info/query_dicom
- KeyImage: GET/POST/PUT /api/v2.0/keyimage → get/insert/update_key_image
- Config: POST /config/{user,common,user/update,common/update} + GET /config/import-folder-path → get_user_config/get_common_config/update_*/get_ae_config
- QC: GET/POST /qc/config、POST /qc/{tree,action,transmit-job}、GET /qc/{transmit-jobs,exist-data} → qc_get_config/update_qc_config/get_qc_tree/qc/get_qc_transmit_jobs/update_qc_transmit_job/exist_data

**🔑 架構定案(2026-08-17,使用者定調):看片端之後「只對 ViewerWebApi 跟 HD.DicomWeb 說話」,不再直接讀資料庫。** 舊 `DownloadHost`(DICOMServer)退場、影像改走 DicomWeb WADO-RS,`localconfig.json` 從「DB 帳密+DownloadHost」瘦成兩個網址。**部署走 hdctl(同 .191/.199),先獨立成自己一個元件 `viewerapi`,日後要跟別的整併再說**——每間醫院都會裝這一支。

**實查現況(2026-08-17)——⚠️ 已被 08-25／08-31 的紀錄取代,下面那個「剩 56 處」的數字現在是錯的:** Server 端五個 controller 都在(Auth/Query/KeyImage/Config/QC);**客戶端側幾乎還沒接——`ViewerApiGateway` 開關做好了,但只有 `DicomQuery` 裡 1 處真的走 API,其餘 56 處仍直連 DB**(DicomQuery 26/QualityControl 17/SystemConfig 11/AccessDefinition 2)。→ 工作量全在客戶端這 56 處。

**施工順序定案:診斷包上傳(REQ-016)先做,刻意排在 56 處遷移之前。** 它是這支服務上最獨立的一塊(不碰既有查詢、不改 stored proc、失敗只是少一份診斷資料),拿它當第一個真正上線的功能,先把「進每間醫院+hdctl 部署更新」走通;之後遷移就是往一台已在跑的服務加端點。詳 [[project_viewer_diagnostics]]。

**WADO 不做**(屬 DICOMServer)。**尚未做=客戶端側**：客戶端要連兩個後端(app-server 走登入/查詢=新增 ApiBaseUrl；DICOMServer 走 WADO=現有 DownloadHost)→ 拆兩個 ViewerWebApiClient 實例；DicomQuery/SystemConfig/QualityControl 各方法改走 API(靜態 gateway 判斷 ApiBaseUrl 有設才啟用、否則維持直連 DB)。Blazor Users/Clients/Settings 頁、/config section-key、/account/login CSRF 待補。相關：[[project-license-mechanism]] [[project-versioning]]

**2026-08-25 大幅推進(詳見 docs/systems/viewer.md,那是正本)：**

- **需求定案**:同一版 Viewer 要能服務尚未升級主系統的醫院。實查後**新舊唯一的差異是影像取得**
  (舊=hd-web-server WADO-URI、新=DicomWeb WADO-RS),其餘 24 個方法都是同一組 proc。
  **相容性住在 ViewerWebApi**,不住在客戶端。
- **計數修正**:先前寫的「56 處/86 處」是 CreateCommand 次數,不是 API 數量。實際是
  **26 個公開方法**(DicomQuery 12/QualityControl 9/SystemConfig 5)。
- **①②③ 已完成並 push**(HD.DicomImageViewer `480cc3f`):影像端點+legacy 後端、
  加 dicomweb 後端(縮圖對到 /thumbnail)、其餘 25 個方法全部接上 ViewerApiGateway 分支。
  ApiBaseUrl 留空仍走直連 DB,非破壞。
- **④ 未做**:移除 SafePostgresConnection 與設定的 Database 區塊。**要等 ViewerWebApi
  真的部署驗證過再做**,否則所有現場立刻不能用。
- **檢查清單不能改走 QIDO**:viewer_station.search_study 回的 QueryResult 帶 StudyRef／
  Status／HasICad／ICadScore,全是 DICOM 標準外的東西。這也是舊站當初沒用 QIDO 的原因。
- **效能實測**:300 張縮圖列,舊系統每次 8.8s、新系統冷啟 22.1s、**快取命中 1.6s**。
  第一次慢 2.5 倍、之後快 5.5 倍。MaxParallel 4→8。縮圖預熱已記待辦。
- **順手修掉伺服器端既有 bug**:get_qc_tree／query_dicom 是 SETOF jsonb,controller 用
  SelectJson(ExecuteScalar)**只拿第一列**。加了 PgProxy.SelectJsonRows。
- ~~**正在進行**:把 viewerapi 佈到 `.163`~~ hdctl 的坑已全修(見 [[project_hdctl_hospital_host]])。

**✅ 端到端實測完成(2026-08-31):第一次真的用 Viewer 跑完整條路,整條都通、零錯誤。**
`ReleaseEnforce` 組建對 `.199:5100`(`hd-viewer-api alpha.4`,DB 指 `.191`),
一筆 **374 張**的檢查、清空本機快取冷啟。請求分佈:image?type=dicom **374**(= 張數)
/jpeg 27/thumbnail 5、dicom-info 374、studies+study-tree+keyimage+config 各 1、
**wado-uri 0**。開啟檢查→最後一張 **12.5 秒**;dicom-info 與下載幾乎同時起跑(差 34ms),
中繼資料查詢沒有卡在下載前面。

**⚠️ 客戶端遷移其實 08-25 就寫完了**(`480cc3f`,分支數 DicomQuery 20/QualityControl 18/
SystemConfig 10),`docs/systems/viewer.md` 的待辦到 08-31 都還寫著「剩下 25 個方法」,
害我一度以為要重寫。`AccessDefinition.GetValue()` 那兩處是**死碼**(全專案無呼叫端)。

**抓到並修掉:每次登入送兩次請求(`7b35c41`)。** `InitializeWebApiClient` 建兩個
`ViewerWebApiClient`(查詢用 `apiClient`、影像用 `webApiClient`)。**遷移前兩者指向不同主機**
(影像走 `DownloadHost` 的 hd-web-server),各自登入是對的;影像改走 ViewerWebApi 之後
兩者同一台,第二次純屬重複。**代價不是慢,是密碼打錯一次會在伺服器留兩筆失敗紀錄**——
醫院若設「連續 N 次失敗鎖帳號」門檻直接砍半,而畫面上看不出來。改成共用同一個實例
(cookie 自然共用)+`ReferenceEquals` 判斷。**但 `apiClient` 必須同時改成
`useViewerApiImage: true`**——它原本是預設 `false`,直接指過去會讓影像悄悄退回
`/api/v2.0/wado-uri`:不報錯、影像照樣顯示,只是繞過整個 ViewerWebApi 影像層。
**所以驗證要看兩件事(登入次數 + 影像端點),只數登入次數正好會漏掉自己剛弄壞的那個。**

**觀察到沒改:`dicom-info` 每張一次**(374 張→374 次)。**不是遷移造成的**,直連 DB 那條
分支同樣 374 次,差別只在往返從本機 DB 變成 HTTP。5.9 秒且與下載並行,目前不是瓶頸;
要不要開批次端點等上千張的檢查實測過再說。

**✅ 授權改走 ViewerWebApi 完成(2026-08-31,`9e20c00`／viewerapi `alpha.5` 已佈 .199)。**
起因:第 4 步(拿掉 DB 連線能力)的唯一障礙就是它——`LicenseRepository` 四個方法直連 DB、
零 gateway 分支;它是 08-14 之後長出來的,寫在施工順序之後,兩邊沒互相看過。
**而且它踩到授權設計的核心前提**(「能看片就一定連得到 DB」),第 4 步正是把那個前提拆掉;
直接做下去的失效鏈與 [[project_viewer_license]] 一模一樣:查不到→離線→14 天暫用→期滿被擋,
**而「怎麼註冊」那條路根本不存在**,症狀是「裝上去兩週後醫師突然登不進去」。

新增 `/api/v2.0/license` 四端點(device/by-fingerprint/request/seen)。**回應協定刻意分三種**,
客戶端靠它決定要不要記住:`200`+物件=找到、`200`+`null`=沒那一列(正常結果)、
`404`=這台不支援(**記住不再問**)、`5xx`=暫時故障(**不記住**)。混在一起就沒得選——
把暫時故障記成不支援,資料庫抖一下就停掉整個行程的授權;反過來則是每次啟動白等一輪。
**「表在不在」交給 PostgreSQL 的 `42P01`,不自己先探測**(探測失敗跟表不存在長得一樣)。

**三個配套**:①`SendRequestAsync` 加 `maxRetries` 覆寫——預設 5 次×2 秒,一支打不通 8 秒,
授權一次判定打三支=**24 秒卡在登入按鈕上**而使用者只看到「按了沒反應」;②例外帶上 HTTP
狀態碼(原本只有訊息字串,要分辨 404 就得比對字串,那種判斷會在改一句 log 時安靜失效);
③`APP_VERSION` 截斷移到伺服器,寬度用 `information_schema` **量**不是用版本號推。
**四取二的指紋判定沒有搬到伺服器**——寫成 SQL 就變第二份正本,SQL 只做粗篩。

**實測三項(Viewer 對 .199,DB .191)**:A 直接登入→`seen` 走 API、`LAST_SEEN_AT`+`APP_VERSION`
都更新;B 刪 `license.lic`→取回落地、**與原始備份逐位元相同**(794 bytes,證明含換行與跳脫
字元的字串經過 jsonb→HTTP→JsonDocument 沒被動到一個位元,否則簽章驗不過);
C **兩個檔都刪**→`by-fingerprint` 認回**同一個 DEVICE_ID**、**清冊維持 1 列**
(等於模擬醫師電腦重灌;失敗會多出一列重複機器,不報錯不影響使用,只有對帳才發現)。

**四支端點全部實打過(2026-08-31)。** 最後一支 `request` 是靠「刪掉 DB 那一列 + 本機兩個檔」
模擬全新機器才走到的——這台在兩個資料庫上早就註冊過,不清乾淨永遠走 by-fingerprint 那條。
完整生命週期:`by-fingerprint`(沒註冊過)→`request`(已送出申請,`Missing` 放行/暫用期)
→主控台簽發→`seen`(取回落地,`Valid` 49ms)。**全程沒有人碰過那台電腦的檔案。**
順序也對:**先確認真的沒註冊過才開新的一台**;`ISSUE_COUNT=1`(線上申請已先佔一列,
第一次簽發不算換發)。

**⚠️ 第 4 步還不能做,卡在部署面不是程式面。** 拿掉 `Database` 區塊之後,
**沒裝 ViewerWebApi 的站台會整個不能用**——目前只有 `.199` 有,若瑟的看片端仍是直連 DB。
前置條件是「所有在跑的站台都已裝上 viewerapi 並驗過」,不是「程式碼寫好了」。
