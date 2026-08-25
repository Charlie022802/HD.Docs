---
name: project-viewer-server
description: "ViewerWebApi(HD.DicomImageViewer.Server)—看片端只對它+DicomWeb、不再直連DB;Server端API做完、客戶端只接了1處剩56處;hdctl獨立元件;第一鏟=診斷包上傳"
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

**實查現況(2026-08-17,比下方 2026-07 舊敘述新):** Server 端五個 controller 都在(Auth/Query/KeyImage/Config/QC);**客戶端側幾乎還沒接——`ViewerApiGateway` 開關做好了,但只有 `DicomQuery` 裡 1 處真的走 API,其餘 56 處仍直連 DB**(DicomQuery 26/QualityControl 17/SystemConfig 11/AccessDefinition 2)。→ 工作量全在客戶端這 56 處。

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
- **正在進行**:把 viewerapi 佈到 `.163`(醫院形態主機),卡在 hdctl 的三顆坑,見
  [[project_hdctl_hospital_host]]。**第一次真的 Viewer 跑這條路還沒發生過**——
  到目前為止全是 curl 與測試程式驗契約。
