---
name: project_req003_export_webapi
description: REQ-003 Export WebApi—定案改「獨立一支API」(不併DicomWeb);薄殼端點已寫在DicomWeb待搬出;worker保留
metadata: 
  node_type: memory
  type: project
  originSessionId: 913e10e5-5ad9-400e-82d5-b8e1163936aa
  modified: 2026-08-17T05:55:21.049Z
---

**🔑 現行 `.199:5090` `0.1.0-alpha.14`(2026-08-21)。五支端點:建立/清單/查單筆/取消/下載。**
清單 `GET /export/packages` 是 REQ-020 加的(游標分頁、狀態多選、日期區間),**歸屬一律由憑證決定、沒有指定 owner 的參數** —— 否則會從「只能看自己」退化成越權查詢工具。細節見 [[project_media_export_redesign]]。

**已接 Keycloak JWT + CORS,對 WebViewer 整條路實證完畢(2026-08-18)。**

同事端是**純前端、只有 token 沒有金鑰**,卡在**兩道各自獨立的牆**:①只註冊 ApiKey,任何 Bearer 都被拒 ②完全沒有 CORS,瀏覽器連 preflight 都過不了(連 401 都拿不到)。修法=MultiScheme(模式同 DicomWeb)+ CORS。
- **CORS 要 expose `Content-Disposition`**,否則前端讀不到下載檔名(瀏覽器預設不讓 JS 讀)。
- **部署踩兩顆**:`appsettings.json` 在 hdctl `preserve` 清單→**新增的設定區塊不會上機**;而選配認證缺 Authority 時 JwtBearer 首次解析 options 就丟例外,MultiScheme 是預設 scheme→**連 `/health` 都 500**→健檢自動退版。修法=條件式註冊(沒設就只收 API Key)+ 設定改走 `/etc/hd-export/keycloak.env`(比照 Database/LoggingPlatform)。規範已寫進 `docs/systems/deployment.md`「設定要放哪」。
- **`MapInboundClaims=false`** 共用套件已設,所以 `sub` 不會被改名成 nameidentifier(否則所有 JWT 使用者會共用同一身分,誰都能查別人的 job)。
- **歸屬看憑證不看人**:job 綁 `sub`(JWT=Keycloak UUID、金鑰=key id),同一個人用 token 建的與用金鑰建的**互不相通**(查別人回 404 不回 403)。已寫進 `/scalar`。
- **`hdserver` 已驗**:ACCESS 含 `export` 區段→`ResolveScopes` 給 export.read/write;token 取法=password grant client `hd-pacs-client`(見 identity.md)。
- 契約補齊:`claimed` 狀態、瀏覽器下載要 fetch+blob、英文 schema 欄位翻譯(key 用 `Schema.property` 不用中文原文,否則改中文英文會默默退回)。

**⚠️ 參數盤點:BURN_INFO 有一半欄位 net10 worker 根本不讀(2026-08-17 查證,查三層才確定)。** 鏈路=API `CreatePackageRequest` → proc `insert_package_job` 寫進 `BURN_INFO` → `get_job_package_info()`(HDPACS_20260811.sql:2498)把 **burn_info 整包**丟給 worker → 但 worker 反序列化的 `HD.Net10/HD.MediaPackage/Class/PackageJob.cs` 只有部分屬性,其餘**靜靜被丟掉**。**有效**=anonymous/containViewer/ignoreCompress/dicomStoragePath;**空頭**=packageSevenZip/packageSevenZipName/storageUserId/storagePassword/opticalDiskDrive(全 HD.Net10 搜 `SevenZip|7z|storagePassword|storageUserId` **零結果**)。→ **已把 packageSevenZip/packageSevenZipName 從 API 拿掉**(使用者確認 Export 還沒人用),**補上 dicomStoragePath**(proc+worker 都支援、獨漏沒開)。日後真要「Export 取代 hd-media-package」時,這些欄位得先決定實作還是廢掉。

**`ignoreMultiframe` 正在失去意義**:proc 內部用它篩 `CONVERT_STATUS->>'mpeg4'='N'`,但 REQ-008 後 `insert_dicom_info` 一律標 `mpeg4='N'` → 對新資料 true/false 結果相同,只有舊資料有差(第 16 行那條「測舊資料要送 false」的踩雷備忘,原因就是這個)。

**API 文件(2026-08-17)**:預設值+「留空=不送該欄位、由 proc 套預設」寫進 `///` XML 註解並開 `GenerateDocumentationFile`,/scalar 直接看得到;**預設值正本仍在 proc**(C# 刻意不給預設值,免得兩份定義漂移)。**兩個坑**:①`<remarks>` **不會**進 OpenAPI description,只有 `<summary>` 會 ②多行 summary 會把 XML 檔縮排帶進去,4 空格開頭在 markdown 變程式碼區塊 → 寫單行。驗證方式=實際跑起來抓 `/openapi/v1.json` 看 schema(兩個坑都是這樣抓到的,不是靠推測)。

**本機跑 HD.Export.Api**:唯一硬性門檻是 `Database:ConnectionString`(Program.cs:52 沒有就 throw),正式機來自 `/etc/hd-export/database.env`,開發機要自建 `appsettings.Development.json`(已在 .gitignore);預設值抄 install.sh=192.168.68.191/HDPACS/postgres。LoggingPlatform 留空就不啟用(Program.cs:42),不會把開發機雜訊送進 .195。launchSettings 已補 `launchUrl: scalar`。

**端到端測試全通過(2026-08-06,.199 生產 live,整條一條龍)。** 部署含 export 的新 build 到 .199(build 20260806-145834,順帶把整輪 auth/audit 重構上生產、runtime 正常)。用 export scope 的 key(`hdp_***...`,建立時預設也帶 dicomweb.read)實測:**POST 建立→201**;**.191 worker 打包→status `P`**;**GET 查狀態→通**;**GET 下載→200,3.5MB 合法 DICOM 包(DICOMDIR + 3 .dcm)**。job 7 的 packageDir=`/home/HD/data/burnTemp/7`(NAS)。

**過程修的三件:**
- **兩個 proc bug(已修 + 寫進 v2.0.27,.191 DB 已套):** legacy `export.insert_package_job` —— ①PATIENT_ID 的 CASE 誤用 `study_refs` 判斷長度(改 `patient_ids`);②accession/patientId 為 DICOM 偶數長度補位(奇數尾空格,如 `'A26R1302506 '`),原 `= ANY` 精確比對對不上 REST 無空格值 → 改**兩邊 TRIM**(桌面帶空格/REST 無空格皆相容,回歸測過)。proc TRIM 當防呆保留;進檔正規化(root fix)記 backlog **REQ-009**。
- **burnTemp 搬 NAS(download 缺口):** `HD_CONFIG` BURN_WORKSTATION/SYSTEM 的 `CONFIG_VALUE`(型別是 **`json` 非 jsonb**,jsonb_set 要 `::jsonb ... ::json`)的 `burnTempPath` 改 `/home/HD/data/burnTemp`;.191+.199 都掛 NFS4 `192.168.68.229:/HDPACS`→`/home/HD/data`(777、hdadmin 可寫,**NAS 上 chown 會 EPERM 屬正常、不需要**);重啟 hd-media-package worker(.191)。viewerPath 未搬(cd-viewer-win 未安裝,留本機;測用 containViewer:false)。
- **踩雷備忘:** `ignoreMultiframe` 預設 true 要求 `CONVERT_STATUS.mpeg4='N'`,REQ-008 前舊 study 沒有會被濾掉 → 測舊資料要送 `ignoreMultiframe:false`。

**REQ-003 薄層 API(建立/查狀態/下載)驗證完成。**

**獨立專案已建+部署+驗證全通(2026-08-06,`D:\Dev\HyperDigital\HD.Export`,GitHub Charlie022802/HD.Export,master):** 單專案 `HD.Export.Api`(slnx),ref 共用 HD.Shared.Auth/Events;三支端點+`ExportService`(自 DicomWeb HdPacsExportService 搬,邏輯同);**PRODUCT_UUID=`"export"`(worker 實測正常接手)**;**v1 僅 API Key**(單 scheme+ExportRead/Write policy;Keycloak 之後加 AddKeycloakJwtBearer+MultiScheme 即可);audit v1 落 ILogger(product=export,待共享事件表)。**部署 .199:5090(與 DicomWeb 同機,原定 .191 改掉)**,systemd `hd-export`,`/home/HD/service/hd-export`,DB env `/etc/hd-export/database.env`→**連 .191 那顆 HDPACS**(install.sh 預設值)。install.sh **自動放行防火牆**(firewalld/ufw 偵測,新慣例,DicomWeb install.sh 也加了 `b3a96c5`)。**驗收:health OK、無 key 401、建立 jobRef 8→worker P→NAS `/home/HD/data/burnTemp/8`→下載 200 合法 DICOM 包。**剩:DicomWeb 側 export 端點下架(待安排,再部署一次 DicomWeb);HD.Export 建 GitHub remote(選)。

**已接共用日誌(2026-08-06,commit `a2a9402`,部署+驗證):** Serilog+`HD.Shared.Logging`(App=`HDExport`),env `/etc/hd-export/logplatform.env`(URL .195:5101+ingest key,抄自 DicomWeb 同把);.195 可見 HDExport log → 排障第一站成立。DicomWeb 側 export 端點也已下架+部署(.199 5080 回 404,`fcf7d6d`)。Source=機器 hostname(=newdicomweb)。

**人用 token 的權限地基已鋪(HD.Shared `f52b1fa`):** 舊版 RBAC `HD_ROLE.ACCESS` 本就有頂層 `export` 區段(kiosk/燒錄工作站;.191 admin、.234 All/Charlie 有)→ `ResolveScopes` 已加對應 → `export.read`+`export.write`(payment/mediaType/kioskDiscImport 細項暫不映射)。

**放哪定案改了(2026-08-06,使用者確認):Export 改「獨立成一支 API」,不併 DicomWeb。** 理由:Export 未來會長大(燒錄佇列/取件號/費用/光碟 viewer),寄生在 DicomWeb 進程會綁死故障域與部署節奏;而現在只有三支薄殼端點,切成獨立成本最低。→ 下面「放 DicomWeb」的舊決策作廢;`fc2c662` 那三支端點(`IExportService`/`HdPacsExportService`/`ExportEndpoints`)要**搬到獨立專案**,worker `hd-media-package` 仍保留。認證面:先用現有 API Key 機制(`export.read/write` 現已可從 UI/REST 指派,見 [[project_dicomweb_apikey_consolidation]])把端到端測通,auth 之後隨 Keycloak 一起換(見 [[project_auth_keycloak_plan]])。

**程式面完成(2026-08-05,commit HD.Pacs.DicomWeb `fc2c662`,build 過,未部署未測):** 三端點 `IExportService`(Application `Services/IExportService.cs`)+ `HdPacsExportService`(Infrastructure `DicomWeb/`,Dapper 打 export.* proc,下載讀 PACKAGE_DIR:File.Exists 直串 / Directory.Exists 即時 ZipFile 到 temp DeleteOnClose)+ `ExportEndpoints`(Api,`/export/packages` POST 建立[export.write]、GET {jobRef} 查狀態[export.read]、GET {jobRef}/download 下載[export.read])。新 scope `export.read`/`export.write`(Domain Constants + Program.cs policy)、DI 註冊 ServiceCollectionExtensions。productUUID 固定 `"dicomweb"`、userUUID=認證 sub(fallback tenantId)一致做歸屬。

**端到端測試前置(待做):** ①部署新 DicomWeb build 到 .199(有 export 端點);②**burnTemp 搬 NAS** —— 現 `/home/HD/extend/burnSource/burnTemp`(.191 本機),要改 DB `HD_CONFIG` BURN_WORKSTATION.burnTempPath=`/home/HD/data/burnTemp`(+mkdir),.199 才讀得到 worker 產出;③**API key 加 export scope** —— 現有 key 只有 dicomweb.read,測試需 `UPDATE HD_API_KEY SET SCOPES='["dicomweb.read","export.read","export.write"]'::json WHERE NAME='DicomWebViewer'`(或鑄新 key);④確認 hd-media-package worker 在 .191 running;⑤測 POST 建立→worker 打包→GET 狀態→GET 下載 zip。

REQ-003:把 HD.MediaPackage 的燒錄/媒體打包開成 **Export WebApi**(建立打包 / 查狀態 / 下載三支端點)。原目標,環境已備好([[project_new_version_testbed_191]] 的 .191 新版 + .199 DicomWeb + 資料齊),**待實作**。承接 [[project_intake_slimming]](REQ-006/007/008 已完成)。

**架構決策(使用者確認):薄層 API + 保留 worker。** API 只負責建立工作/查進度/下載;實際打包仍由獨立 worker `hd-media-package` 吃佇列執行。放 **DicomWeb(.199)**(有現成認證/授權/稽核/部署;下載讓 .199 讀 NAS 上的 PACKAGE_DIR,PACS 端零新增)。「MediaPackage 整支淘汰」=長期目標,但這輪只做薄層 API 前置,worker 保留。

**HD.MediaPackage 盤點(D:\Dev\HyperDigital\HD.Net10\HD.MediaPackage):**
- `Service\PackageService.cs`(~815 行,核心):BackgroundService 輪詢(Task.Delay 2s)。`export.get_job_package_info()` 撈 N job(展開實體檔清單、轉 job→'p')→ 產出 → `export.update_job({jobRef,status,packageDir,errorMessage})`(成功 'P'、失敗 'E'+errMsg)。
- **產出=一個資料夾或 zip**(`burnTempPath/{jobRef}/`):DICOM 檔(出口疊合 CoercionService+選匿名+改 tag)+ DICOMDIR + cover CSV(.merge)+ 選配光碟 viewer(rules.enc 白名單 AES/RSA + study_elements.json)。或 onlyJpeg 模式(GDI+ 燒字)。ignoreCompress=false 才壓 zip。**不產 ISO、不碰燒錄硬體**(那是下游 BURN_WORKSTATION)。
- 與佇列耦合**很薄**:只有「get_job_package_info 取 job」+「update_job 回寫狀態/packageDir」兩接縫,主體是純檔案產出邏輯(可搬)。技術債:ViewerWebApiHelper 硬編碼帳密、StudyRulesManager 硬編碼 RSA 私鑰、System.Drawing(GDI+ 跨平台風險)。

**export.* DB 契約(三端點對應):**
- **建立打包** → `export.insert_package_job(jsonb)`(REST 友善:patientId[]+accessionNumber[] 或 studyRef[];選項 anonymous/containViewer/ignoreMultiframe(預設true)/ignoreCompress/dicomStoragePath/mediaType/productUUID/userUUID;回 `{"jobRef":N}`,狀態 'N')→ 既有 worker 自然接手。進階(外部 AE retrieve/kiosk 取件號)才用 `export.insert_update_export_job(jsonb)`。
- **查狀態** → `export.get_package_job_status({jobRef,productUUID,userUUID})`(單筆)或 `export.get_job(jsonb)`(豐富查詢,回人類可讀 status/progress/packageDir/errorMsg/fee/pickupNo)。
- **下載** → 讀 `EXPORT_JOB.PACKAGE_DIR`(worker 由 update_job 寫入)→ WebApi 到該目錄串檔;無專用 proc。檔名由 BURN_INFO(packageSevenZipName/dicomStoragePath)決定。
- **EXPORT_JOB 表**(export schema,dump ~33929):JOB_REF PK、PRODUCT_UUID(來源過濾)、HD_USER_UUID、BURN_INFO jsonb(studyInfoList+選項)、PROGRESS、PACKAGE_DIR、STATUS、ERROR_MSG、DISC_INFO、PICKUP_NO、FEE 等。狀態機:N→d/D→p/P→m/M→b/B→Y;E=err、C=cancel。**綁 HD_USER_UUID+PRODUCT_UUID(非 AE),建立不需指定 AE。**
- ⚠️ `get_job_package_info` / `get_next_package_upload_job` 是 **worker 專用(會改 STATUS)**,WebApi **不可**呼叫;查狀態只用 get_job*/get_package_job_status。

**待決/下一步:** ①端點路由設計(沿用 DicomWeb API Key/JWT 認證);②下載檔案存取(.199 經 NAS 掛載讀 PACKAGE_DIR,路徑要兩機一致);③實作。可在 .191/.199 測試環境開發(hd-media-package 已裝 .191、burnTemp 目前在 .191 本機 `/home/HD/extend/burnSource/burnTemp`,要 .199 下載得到需搬到 NAS `/home/HD/data`)。

**金鑰明文刻意不記在這裡**（2026-08-20 移除，為了讓 memory 能納入版控）：內部測試金鑰查主控台的金鑰管理頁。
