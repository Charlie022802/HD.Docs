# 待辦（Todo）

可執行的事項，依系統分組。完成就打勾或移到各系統文件的歷史。

## 多院區主機（新主線，2026-08-10 立案；正本＝[multi-site-design.md](multi-site-design.md)）
**一台 PACS／一個 DB 承載多個院區**。兩種形狀共用同一套機制：多家動物醫院共用總機（各自獨立編號、嚴格隔離）、一家醫院的多分院（共用病歷號、可跨院區查）。差別靠 `SITE.PATIENT_ID_SHARED` 設定，不是兩套程式。動物醫院的具體導入見設計文件末的導入案例。
**架構重定（2026-08-11 三輪）：Proxy 整個退役**——儀器 --C-STORE--> 直打總機新版 PACS（開 port 對外）；STOW 轉發鏈（StowForwarder）與 UserUUID 歸屬設計一併作廢。WorklistInsert 擱置（同事討論中）。**本輪唯一核心＝SITE_CODE 設計**。
已定案：server 端強制過濾必做、安裝檔全新裝（不複製 VM）、單 HDPACS DB+SITE_CODE+RLS 雙護欄。
- [ ] **階段一：進檔開始歸戶**（設計已完備，見正本）：重拉 dump 核對四個 RC_STUDY INSERT 點行號 → migration（SITE 表含 CUTOVER_DATE/PATIENT_ID_SHARED ＋ RC_STUDY.SITE_CODE ＋索引）→ 改 `store_dicom`／`insert_dicom_info` 蓋章＋跨院區同 UID 護欄 → 兩處 QC 複製繼承 → NetworkConfig 加 `siteCode` → AE 設定匯入。舊盤點結論保留參考：Proxy 特殊流程 → 新 PACS 對照結論——AE 白名單/CalledAE 驗證/視訊 TS/健檢 AE＝新 PACS 現成（AE_MAIN 登記＋NetworkConfig per-AE：host 綁定、allowCStore/CFind/CMove）；進檔改寫＝proxy 的 DicomInputRuleList **從未實作**（只有 UI+設定），新 PACS 反而有真的（per-AE `dicomImportModified`＋`dicomTagFilter`，DicomStoreProcess 套用）；ServiceManager 重啟＝systemd 取代；物種中翻英（狗→Feline 對調）＝worklist 線，隨 WorklistInsert 案處理。**缺口只剩院區歸屬**：提案＝SITE 表＋AE_CONFIG jsonb 加 `siteCode`（NetworkConfig 加屬性，零 schema 改動）＋DicomStoreProcess 進檔蓋 SITE_CODE 實體欄（RC_STUDY 為主）＋病患複合身分（SITE_CODE+PATIENT_ID）＋未歸戶=NULL 收下待認領。對外 port 安全：NAT 下 host 綁定失效，靠 AE+防火牆/VPN，要議。
- [ ] 設計定案：存量匯入路徑（之後談）。**已定（2026-08-10 二輪）：現場 AE 一律不動（鐵則）→歸屬 key＝CallingAE 尾 6 碼 UserUUID 沿用舊慣例；對照表正本＝總機 DB（UserUUID→SITE_CODE），初始資料從現有 Proxy 設定檔一次性匯入，新院走管理 UI**。待定小點：未歸戶進檔處理（建議收下＋隔離＋UI 認領）。**worklist 已查明（2026-08-10）**：Proxy WorklistSCP＝純轉發（儀器 C-FIND→依 UserUUID 轉該院 PACS worklist SCP，保留原 CallingAE；proxy 不寫資料）→新制沿用轉發鏈、目標改總機單一 SCP＋總機端依 CallingAE 過濾；**動物醫院寫入鏈定案（2026-08-11 反代設定實證）**：NxVet→`www.horoview.vet/hcs/<院號>/mwl`（horoviewReverseProxy nginx，網際網路曝露、被掃描中）→各院 VM `:6060/Api/v2.0/MwlInsert`（hd-pacs-administration-tool Flask，**零認證+SQL 字串拼接注入洞**）→`CALL insert_worklist`→該院 DB→hd-worklist-server 供 C-FIND。（MSI 檔匯入=另一條平行路，動物醫院主用 MwlInsert。）**院區身分已在 URL 路徑→新制診所端零改動**：反代 `/hcs/<n>/mwl` 全改指總機相容端點＋nginx 注入院區 header＋內部金鑰（順治認證/注入洞）；院區對照雙 key：儀器線=UserUUID、worklist 線=hcs 院號，同表對 SITE_CODE。VetMwl 佇列僅 /hcs/1 一家特規。**反代 bug：/hcs/62/mwl 指 .62（=hcs/61 主機），62 號單進錯院**→待同事確認修正。另：物種改寫狗→Feline/貓→Canine 對調（正確版被註解），沿用前要確認。
- [x] **DicomWeb HTTPS（2026-08-10 完成，SSO 整圈驗證通過）**：nginx TLS 終結（443）＋自簽憑證（SAN 含 hddicomweb/IP）＋app ForwardedHeaders；Keycloak 加 https redirect URIs。踩掉兩顆 proxy buffer 雷（自家 nginx 的 SaveTokens cookie 502＋sso openresty，見 identity.md 坑⑨，皆已修）。設定=deploy/setup-https.sh＋nginx/hdpacs-tls.conf。後續選項：穩定後關 5080 對外、名稱 hddicomweb 上內部 DNS。
- [x] **Proxy STOW-RS 轉發模組（2026-08-10 建置完成＋本機 mock 驗證）**：新服務 HD.Animal.Proxy.StowForwarder（HD.Animal `7a2e53e`）——掃 CacheTemp（天然持久佇列）→STOW 上傳總機（X-API-Key＋X-Calling-AE-Title）→成功移 CacheSent（保留期自動清）／壞檔 CacheFailed／網路問題原地退避重試（驗證：斷線不丟、復線自動補送）。unit＋install.sh＋proxyConfig 樣板齊；**預設 Enabled=false**。待真機（.222→.199）試跑：需總機發金鑰（dicomweb.write）＋AE_MAIN 登記＋開啟設定；WebController 設定頁補 StowForwarder 區塊（followup）。
- [x] **WorklistSCP 轉發器優化（2026-08-10，HD.Animal `bdce2a7`，本機雙情境驗證）**：逐筆串流轉發（不再全收完才回）＋上游失敗/逾時回 ProcessingFailure（原本吞錯回空 Success，儀器分不出「失敗」與「沒單」）＋接上 Worklist.RequestTimeoutInMs（設定/WebController 有欄位但程式沒用）＋物種對照表驅動（行為不變；狗→Feline/貓→Canine 對調仍保留，待確認）。隨下次 .222 部署一起上。
- [ ] ~~院區歸屬鏈（UserUUID/StowForwarder 版）~~ → **作廢（2026-08-11 Proxy 退役）**；歸屬改為 PACS 進檔蓋章，見上方 SITE_CODE 設計。舊 Proxy 各院 AE 清單仍是初始登記資料來源（AE→院區 匯入 AE_MAIN）。
- [ ] 進檔蓋章：SITE_CODE＋病患複合身分（IssuerOfPatientID 概念；寫 DB 不改原始檔）。
- [ ] **階段二：出口過濾**（2026-08-21 會議再次確認要推進）：C-FIND／C-MOVE 依 calling AE 的 `siteCode` 限制可見範圍。規則已定案——**`SITE` 表沒有資料＝多院區功能整個關閉、完全不過濾**（單一醫院零設定），啟用後 AE 掛 `siteCode = X` 就**只看得到 `SITE_CODE = X`**（刻意不是 `X OR NULL`，因為會先全部轉置好才開放）。`.191` 上留了 `HQ`／`BRANCH`／`OLDSITE` 三筆院區與測試 study 當現成 fixture。
- [ ] Site 功能完善：管理 UI 的院區 CRU（**不含 D**——只停用不刪除，見設計正本「院區的生命週期」）、AE 掛院區的介面、未歸戶 study 的認領流程。
- [ ] QIDO/WADO 依呼叫者院區過濾＋PostgreSQL RLS 護欄。
- [ ] 新版 DicomWebViewer：院區顯示（順帶 Keycloak＋i18n 一起上）。

## 主 PACS（HD.Net10）
狀態（2026-08-04）：A0/A1/A2/B + REQ-005 已 commit+push（HD.Net10 `eb7f932`）。.191 測試機驗證：A2 媒體 coerce ✅、B 日誌 ClientIp/User ✅。
- [x] A0 CoercionService、A1 DicomTransmit、A2 MediaPackage/CallBack、B 日誌 — 完成+commit+push
- [x] **A3**：移除 `StudyClosedService.UpdateDicomFileSafe`（停止改檔）+ 2 呼叫點 + 孤兒 `DatasetsAreEqual` + 死掉的 tempInfo/TempPath/usings；保留 job 迴圈與 DB reconcile。commit+push `68b33e1`。**.191 驗證通過（2026-08-04）**：部署 hd-workflow-manager（先前 6 支沒裝此支），觸發 STUDY_CLOSE→檔案 md5 before==after 一字不差、DATASET 有校正標記但檔案沒有、STATUS→X。詳 [main-pacs.md](systems/main-pacs.md) / 記憶 project_main_pacs_coerce_logging。
- [ ] A1 / CallBack 的 runtime 補測（選配，高信心；A2 已證機制）。
- [~] 主 PACS 正式部署 — **暫緩（2026-08-04 決策：.234 先不動、保留舊版）**。新版續留 .191 測試。日後要上正式再處理 .234 建 hdadmin + 舊 CentOS/runtime，見 [environments.md](environments.md)。
- [ ] **REQ-022 Nearline 沿用舊版 NFS 檔案複製**（2026-08-21 會議定案）：機制與 `Insert Job` 都不改，唯一差別是**進檔只需做一次**——原始檔不可變之後，校正不再產生新檔，所以不必「改檔後重插 job」。要逐一確認舊的重插觸發點是否還在，並保留 QC 拆單／合併這類**真的會產生新檔**的插 job 路徑。詳 [backlog REQ-022](backlog.md)。
- [ ] **REQ-023 Archive 帶 metadata**（2026-08-21 會議定案）：**上傳前給一次、打包前再跟 PACS 要一次**，目的是「來源 DB 整個消失時，光靠 Archive 也能還原完整資料」。對接目標＝同事的 **HD-Archive**（`Others/archiveServer`，S3 相容 CAS＋WORM），之後我們這邊改接過去。待確認 metadata 形狀與失敗時的行為。詳 [backlog REQ-023](backlog.md)。
- [ ] 清理：PACS `PostgresConnection` 帳密硬編碼 → 改讀 hd_conf.json/env。

## 儲存層 / 資料補回（正本＝[systems/storage-tiers.md](systems/storage-tiers.md)）
2026-08-24 若瑟資料流失事件的後續。工具＝`HD.Net10/tools/HD.StorageAudit/`（hd-storage-audit + purge-for-resend.sh）。
- [x] **若瑟資料補回（2026-08-24 完成）**：受損 122 筆 / 748 張 → **復原 79 筆 1066 個檔案零缺漏**（NONDICOM 重送），43 筆 449 張不可復原。同批補完 8089 筆 NEARLINE_BACKUP、126 筆分散兩層的 study 補齊校準（871 檔 1754 MB）。**全庫「線上有檔但無 nearline」已歸零**。
- [ ] **若瑟升版到 v2.0.27 以上**（唯一能防復發的）：`get_next_delete_study` 在 v2.0.27 才加入「沒有 nearline 副本就不清」的守門，v2.0.22 會把唯一一份刪掉留下空殼——**這就是這次事件的成因，不升就會再發生**。
- [ ] 若瑟 nearline 空間：VOL 3 已 94.6%（R）、VOL 7 85.9%（Y）。線上 89.9%，且 ARCHIVE 與 ONLINE 是同一個檔案系統（歸檔不會釋放線上空間）。
- [ ] 若瑟 43 筆不可復原的明細送醫院（`/tmp/studies-nondicom-missing.csv`）。送之前值得查兩件事：有沒有被 ROUTE/CSTORE 到別的 AE、modality 分布（部分 CR 可能能從 AGFA PACS 撈回）。
- [ ] 清若瑟的 285 個 nearline 孤兒檔（`/tmp/orphan-nearline.txt`）——CACHE_DELETE 只刪 online 檔，nearline 實體檔會失去所有指向。建議放一天再刪。
- [ ] 定期稽核：把「線上有檔但無 nearline」與「三層都沒位置」納入例行檢查（兩者應長期為 0）。
- [ ] 若瑟 study 1667133 的 1 張影像補 nearline（已排 job 50250589，待確認）。

## 進檔瘦身（REQ-006/007/008，設計見 [intake-slimming-design.md](intake-slimming-design.md)）
- [x] **REQ-006** 進檔不再存 `.meta` — 完成、.191 驗過、commit（HD.Net10 `17de498` + HD.Pacs.DicomWeb `8fb0562`）。
- [x] **REQ-007（PACS/DB 端）** 移除 DicomToImage — route A 完成、.191 驗過。C# `HD.Net10 86ef7bd`（下架 HD.DicomToImage + 清死碼）+ DB migration 併入開著未結案的 `Database/HDPACS/db_update_sql/db_update_v2.0.27.sql`（insert_dicom_info 一律 jpeg='N'、不 enqueue、gate 不動）+ `DB版本.xlsx` 2.0.27 分頁加列。
- [ ] **REQ-007（消費端，2026-08-04 釐清=併入更大取代，非原地修補）**：
  - HD.DicomImageViewer 線上版**不可動**→JPEG 改接 DicomWeb 在**新專案**做（未來軌）。
  - HD.MediaPackage **整支待淘汰→改 Export WebApi**（見 REQ-003），JPEG 隨整支取代。
  - viewer_station.*/wadouri_query 的 CacheJpegPath 由**舊版 WebApi** 消費（待汰），隨新 WebApi/DicomWeb 取代時一併改。
- [x] **REQ-008** DicomToVideo 移除 MPEG4 預轉（2026-08-05 完成）：insert_dicom_info 一律標 mpeg4/dicomMpeg4='N'、不 enqueue DICOM_TO_VIDEO（Database `2449d2a`，併入 v2.0.27）+ 下架 HD.DicomToVideo（HD.Net10 `81d56a6`，slnx 移除+刪專案，build 過）。理由：DicomWeb frames 端點能逐格取多幀（.191 實測 454 幀 OK）+ dicomMpeg4 只有舊 viewer 用、無其他消費者。.191 已套 req008_insert_dicom_info.sql（2026-08-09 以 prosrc 指紋驗證確認）。

## LoggingPlatform（.195）— 大改：產品分區（排障第一站）
- [x] **P1 產品總覽+專區上線（2026-08-06，commit `8d2e315` 部署驗證）**：首頁=產品卡（24h 錯誤/量/最近錯誤/無日誌偵測）、`/product/{App}` 專區（摘要+spark+錯誤/警告/全部籤+進階查詢連結）、登入導首頁。產品識別定案 HDPacs/HDDicomWeb/HDExport/HDDicomViewerStation（DicomWeb 原誤送 HDPacs 已改）。
- [x] **P2 連線紀錄（2026-08-08/09 上線驗證通過）**：慣例＝結構化屬性 `Category=connection` + `CommType`（ASSOCIATE-OPEN/CLOSE/REJECT/ABORT、C-ECHO/C-STORE/C-FIND/C-MOVE/MWL-FIND/MPPS）+ `Outcome`(success/failure) + `ClientIp`/`User`/`CallingAET`/`CalledAET`；共用發送器 `HD.Shared.Logging.ConnectionLog`（HD.Shared `d95400b`→`fbcc59d`）；主 PACS 兩支 SCP 全生命週期掛事件、**C-STORE 成功彙總進 CLOSE 不逐筆**（HD.Net10 `8c2aa45`）；Web 產品專區加「連線紀錄」籤（props `@>` GIN 過濾，Query 零改動，HD.LoggingPlatform `b728293`）。部署：.191 兩服務＋.195 web（2026-08-08 23:17）；驗證：TESTSCU C-ECHO 整圈（OPEN→ECHO→CLOSE，AET/IP/結果齊）。註：DicomWeb/Export 的 HTTP 面走既有 access log，不另發 connection 事件（定位=儀器 DICOM 連線）。訊息去引號小修（`fbcc59d`）隨下次重佈生效。
- [x] **P3 治理（2026-08-10 完成＋部署驗收）**：①**服務維度**——共用包自動附 `properties.Service`（進入點組件名），產品專區「服務」下拉＋服務欄（`/api/services`；歷史資料無此欄位僅新資料可篩）②**per-app 保留期**——設定頁產品列「保留(日)」（retention_per_app，Archive 每輪清 hot/std，warn/audit 不動）③**RBAC**——app_scope 進 claims，產品卡按人過濾＋專區守門④**金鑰治理**——四把綁產品正式金鑰上崗（HDPacs/.191、HDDicomWeb+HDExport/.199、ViewerStation 待站台側），ApiKeys 頁改彈窗＋複製鈕 http fallback（原 clipboard API 炸電路已修）。
- [ ] P3 收尾：ViewerStation 站台側換裝金鑰後**停用 ingest 的 INGEST_API_KEY fallback**；各來源 log 收斂（量的治理）續觀察。
- [x] **追 HDPacs ExecuteStore Critical Error（2026-08-09 結案，用新匯出功能撈 CSV 分析）**：30 筆分三群——20 筆 `server_login_retry`（8/6 測試期 DB/pgbouncer 重啟，環境性）、6 筆 HTTP 500（DicomWeb 改名前誤掛 HDPacs 的殘留）、**1 筆真 bug**：`HandleStorageError(dynamic info)` 對 ValueTuple 取 `info.PatientID` 必炸（tuple 欄位名只存在編譯期）→ 底層 deadlock 該進錯誤處理卻整包炸掉、錯誤資料集沒寫 DB。修＝參數改具名 tuple（HD.Net10 `e3cb1ef`），**已部署 .191（2026-08-09 23:48，hd-pacs active）**。底層 deadlock 本身＝併發 C-STORE 撞 `insert_dicom_info`，暫時性，先觀察。
- [x] **ClefParser fix 已部署 .195 + 驗證通過（2026-08-04）**：只重 build Ingest（ClefParser 在 Shared，但等級在 ingest 解析時決定）→ `podman load` 覆蓋 `hdlog-ingest:v1.0.0` → `podman compose up -d --no-deps --force-recreate ingest`。驗證：C-Echo(TESTSCU) 新 log 正確標 Information（不再 Verbose），且帶 User/ClientIp 標籤。commit `8915f84`。

## DicomWeb（HD.Pacs.DicomWeb）
- [x] **API Key 管理收斂（2026-08-06，已 commit `f64704b` + 隨重構部署 .199）**：scope 單一正本 `Domain/ScopeCatalog.cs` + CRUD 單一正本 `Api/Services/ApiKeyService.cs`（EF）；REST（`ApiKeysEndpoints` 補 `PUT`＋`/scopes`、`/ae-titles`）與 Blazor `ApiKeys.razor`（改強型別）共用；退掉 raw-SQL `ApiKeyAdminService`。順手修：`export.read/write` 原本 REST/UI 白名單漏了、無法建 export 金鑰，現可指派（解 REQ-003 測試前置③）。build 0 err、單元測試 87/87 綠。**待 commit + 部署驗**。
- [x] HTTPS 上線（2026-08-10 完成，詳上方動物總主機區）。
- [ ] 其他出口疊合的 DicomWeb 側收尾（WADO 已做；視需要）。
- [ ] P2 角色細化 / P5 Keycloak SSO（待 SSO 主機）。
- [ ] UPS 延後項：Progress Report 事件、suspend、deletion lock、WS 瀏覽器 `?apikey=`。

## DicomWeb 縮圖效能（REQ-004）— ✅ 完成收案（2026-08-06）
- [x] 記憶體 render 快取 `RenderedImageCache`（128MB/LRU/30分；key=`sopUid|frame|format|maxDim`、version=DATE_TIME_MODIFIED）。**已 commit（`9dfa1ff`，todo 原「未 commit」為過時資訊）並隨 2026-08-06 部署上 .199**。
- [x] **整合驗證通過（.199 生產實測）**：同一縮圖三連打 1.164s → 0.073s → 0.043s（16~27×，快取命中）。
- [x] 「選項2 吃 hd-dicom-to-image 的 .jpg」確認已死（REQ-007 服務已移除）。
- [ ] （未做）render 套 coerce W/L：等 W/L 校正工作流出現再補（架構已留 version 失效路）。
- [ ] （選）第二階段：pre-gen 改 legacy 相容磁碟快取（冷啟動/跨程序持久）。

## 燒錄 / Export WebApi（REQ-003）— 定位提升：全面取代 HD.MediaPackage
- [x] **獨立 HD.Export 上線+驗證全通（2026-08-06）**：`D:\Dev\HyperDigital\HD.Export`（local git），部署 **.199:5090**（與 DicomWeb 同機、DB 連 .191 HDPACS）。三支端點+共用 HD.Shared.Auth（v1 僅 API Key）；PRODUCT_UUID="export" worker 正常接手；下載走 NAS `/home/HD/data/burnTemp`。驗收：建立→P→下載 200 合法 DICOM 包。install.sh 新慣例=自動放行防火牆（DicomWeb 的也加了）。
- [x] 端到端前置全解：export scope 可指派、`insert_package_job` 兩 bug 修（v2.0.27）、burnTemp 搬 NAS。
- [x] **DicomWeb 側 export 端點下架**（2026-08-06，`fcf7d6d` 部署 .199 驗證：5080 /export 回 404、5090 照常）。
- [x] HD.Export GitHub remote：Charlie022802/HD.Export（2026-08-06 已推）。
- [x] **REQ-020 歷史清單＋過期標記（2026-08-21 三層全部上線驗證）**：DB `v2.0.32`（.191）＋pacs `2.0.12`（.191 worker）＋Export `0.1.0-alpha.14`（.199）。新增 `GET /export/packages`（游標分頁、狀態多選、`CREATED_AT` 區間），單筆端點不動只多回 `createdAt`／`modifiedAt`。清理改由 DB 主導：`expire_package_jobs` 標記 `expired`＋清 `RESULT_PATH`，worker 拿回路徑才刪檔，所以 `downloadReady` 不會再騙人。保留天數改設定（`packageRetainDays`，預設 7，原本寫死 2）。順帶修掉撞號（新表產出移到 `burnTemp/package/`）與版本雙來源（hdpack 加護欄）。設計正本＝[media-export-redesign.md](media-export-redesign.md) 第 8 節。
- [ ] **⏰ 2026-08-28 要回頭確認：`burnTemp/package/` 沒有被 legacy 的時間掃描誤刪**。
      `CleanUpLegacyOutputs` 有跳過這個容器目錄的判斷，但**它的失敗要滿 7 天才會現形**——
      `package/` 只會被建立一次，建立時間一旦超過保留天數，掃到就會把裡面**所有還沒過期的產出
      一起刪光，而且 DB 完全不知情**，正好製造出 REQ-020 要消滅的那種「說謊的 ready」。
      2026-08-21 部署當天 `package/` 才 0 天大，測不出來，只有程式碼層面確認過。
      **怎麼確認**：`ls /home/HD/data/burnTemp/package/` 還在，且裡面沒過期的 job 仍能下載；
      或在 worker log 搜 `Delete directory` 看有沒有出現 `.../burnTemp/package`（出現就是漏了）。
- [ ] 長期：Export 整支取代 hd-media-package（燒錄佇列/取件號/費用/光碟 viewer 收進來）。
- [ ] 人用 Keycloak token 呼叫：ResolveScopes 已支援 ACCESS.export 區段（HD.Shared `f52b1fa`）；等 Export 接 MultiScheme+Keycloak 時啟用。

## Auth 收斂 / Keycloak — **定案：所有產品的「人」登入一律走 Keycloak（2026-08-06）**
稽核分層隨之定案：**登入事件正本＝Keycloak Events**（各產品不自記登入）；操作＋API Key＝共享事件表。
- [x] **Keycloak Events 已開**（2026-08-06 使用者自己開：User events + Admin events + 保留期）。註：原生 UI 的 User 欄只顯示 UUID，要點開才見帳號 → 主控台稽核頁（Admin API 拉 events、UUID→帳號人話呈現）解決。
- [x] **共享事件表落地（2026-08-06 程式面全完成）**：v2.0.27 migration（PRODUCT/CATEGORY 欄+索引，Database `e36249a`）；共用 `DbAuditLogger`（HD.Shared `69e08a2`）；DicomWeb 補欄+category 粗分（`a15cb65`）、Export（`ad734b3`）、主控台（`34ca38d`）皆改寫事件表。**全部完成（2026-08-06 晚）**：.191 已套 migration；DicomWeb（build 205757）/Export（205819）已重部署 .199（部署慣例改為 ~/deploy-dicomweb、~/deploy-export 分資料夾）；**三產品實測入表**：dicomweb/operation（qido）、export/audit（壞 key 攔截）、admin-console/audit（金鑰生命週期），SOURCE_IP 皆正確（VPN 來源 192.168.68.253／本機 ::1）。
- [x] **DicomWeb 切 Keycloak（2026-08-07/08，HD.Pacs.DicomWeb `4c9535b`→`ed4156b`、HD.Shared `79ee858`，部署 .199 驗證通過）**：Admin UI=OIDC 導頁（登入卡→SSO→後台→RP-initiated 登出）；API JWT=AddKeycloakJwtBearer（aud=hd-pacs 嚴格）+OnTokenValidated 查 HD_USER 補 scopes（無對應→401）；退役 JwtIssuer/DevSigningKeyProvider/dev-token/固定管理帳密/HD_USER.PASSWORD 驗證。新坑三枚：**登出需 id_token_hint→必須 SaveTokens=true**；**DefaultChallengeScheme 別設 OIDC**（未登入會跳過登入卡直彈 Keycloak）；**Valid post logout redirect URIs 用 `+`**。單元 87/87、整合 31/31 綠。
- [ ] **Viewer 切 Keycloak — 雙軌（2026-08-17 決策）**：醫院封閉網路連不到 sso.ltcd.tw，**之後會在各醫院內部自建 Keycloak**（尚未架設）。→ 登入這塊**可提前實作**（Authority 指院內位址、由設定決定），**但不替換現行 WebApi 帳密登入**（`LoginForm.CheckUser` → `/api/v2.0/user/login`）；兩條路並存、設定切換，院內 SSO 到位才開。AuthZ 仍查 DB。詳 [systems/identity.md](systems/identity.md)。
- [x] ApiTest / TestClient 工具更新（2026-08-08，`f033af4`）：登入改 Keycloak password grant 或直接貼 API Key（TestClient 帳號欄貼 `hdp_` 開頭免密碼）；金鑰管理頁/測試段移除（歸主控台）；ApiTest 加「dev-token 與 /api/v1/api-keys 應 404」防呆；Smoke 流程 Import 明帶 X-Calling-AE-Title。
- [x] 抽跨產品共用 Auth lib（2026-08-06 完成：HD.Shared.Auth＝Keycloak 取/驗 token＋API Key handler＋ScopeCatalog＋HdUserRepository；DicomWeb/Export 已用）。
- [x] Keycloak 驗證面全通：audience mapper（hd-api→hd-pacs）嚴格驗證、OIDC 授權碼登入（主控台整圈）。
- [x] DicomWeb 人類登入切 Keycloak（2026-08-07/08 完成，見上）。
- [ ] provisioning：使用方打 API 註冊（Keycloak Admin REST 契約待同事）。詳 [systems/identity.md](systems/identity.md)。
- [x] **帳密（人）路打通（2026-08-09）**：`HD_USER` 補 `ID=hdtest`（ROLES=[1] admin、email=hdtest@hyperdigital.biz 與 Keycloak 一致）→ password grant 取 token 打 `/me` **200 整圈通**（scopes 由角色 1 解析：dicomweb.read/export.*/report.*/admin.*；無 stow/import 子區段故無 write）。正軌仍是 provisioning 雙寫。
- [x] **groups claim（2026-08-09，同事需求）**：Keycloak `hd-api` scope 加 Group Membership mapper（claim=groups、Full path Off、access+ID token）→ 掛 `hd-api` 的 client 全部帶 groups；DicomWeb `/api/v1/auth/me` 回傳 groups（`782ed6f`，部署 .199 驗證：`["hyperdigital"]`）。提醒：groups 僅供顯示/分流，**授權仍查 DB**；若要群組→權限映射另議。

## HD 後端管理主控台（HD.AdminConsole）— 集中管理平面
- [x] **第一鏟：骨架 + Keycloak SSO 登入整圈驗證（2026-08-06）**：Blazor Server + OIDC 授權碼導頁（定案：保持導頁、美化走 Keycloak theme）；登入卡/身分頁/RP-initiated 登出全通；鯨魚 logo。repo GitHub Charlie022802/HD.AdminConsole。
- [ ] 請同事做 Keycloak login theme（HD 風格登入頁，全產品受益）。
- [x] **API Key 管理搬入（2026-08-06，`f8533af`，對 .191 DB 實測）**：/apikeys 清單/建立/編輯/撤銷；Npgsql 直連 HD_API_KEY（與各服務驗證同表）；badge 產品配色+目錄排序+去黑話用語。授權 v1=登入即可管（scope 檢查待補）。
- [x] DicomWeb 側金鑰管理 UI/REST 下架（2026-08-07/08，隨 Keycloak 切換一起；`/api/v1/api-keys` 404、驗證留 HD.Shared handler；測試改 TestApiKeySeeder 直接種表）。
- [x] **授權細化（2026-08-10 上線，主控台+DicomWeb 同步）**：OIDC OnTokenValidated 查 `HD_USER`→`ResolveScopes` 蓋進 cookie claims（無對應=零 scopes；異動需重登）。主控台：/apikeys=`admin.api_keys`、/audit=`admin.audit`、/exports=`export.read`；首頁「我的權限」badges。DicomWeb 管理頁：狀態/系統日誌/設定=`admin.settings`、稽核/存取紀錄=`admin.audit`（Page* policy 走 cookie，勿綁 MultiScheme）。側欄按權限顯示＋已登入無權限顯示 Forbidden（不導登入頁防迴圈）。角色 1 補 `dicomWeb.manageApiKeys`（jsonb_set）。hdtest 正向驗證通過（AdminConsole `90ba655`、DicomWeb `c712aa1`）；負向（無 HD_USER 帳號全擋）待同事帳號順測。
- [x] **稽核紀錄頁 + 匯出紀錄頁（2026-08-06 晚，`99b385e`→`dec5fef`，本機對 .191 實測）**：/audit 全欄位過濾（產品/分類/結果/操作者(類型)/動作/對象(類型/ID)/IP/自訂時間）＋keyset 分頁；/exports 唯讀管理視圖（狀態人話/進度條/錯誤展開）。寬表格水平捲動＋首欄 sticky。主控台三大功能到齊（金鑰/匯出/稽核）。
- [x] **部署 .191:5200（2026-08-07 驗證通過，`77e0640`→`087f7ed`）**：self-contained + install.sh（/opt/hd-admin-console、systemd、SELinux usr_t、自動防火牆）；Keycloak redirect URI 加 `http://192.168.68.191:5200/*`。修 http 站台 OIDC 三坑：cookie SameAsRequest+Lax、回跳改 query（form_post 被 Chrome 攔+cookie 不帶）、關 PAR（sso.ltcd.tw 該路徑 502）。另：SSO 節點死掉時帶舊 cookie 穩定 502（無痕正常）→ 清 sso.ltcd.tw cookie 解，**症狀待回報同事**。詳 [admin-console.md](systems/admin-console.md)。
- [ ] 稽核頁併入 Keycloak 登入事件（Admin API 拉 events、UUID→帳號）。
- [~] **DICOM 連線紀錄**：P2 已實現於 **LoggingPlatform**（連線紀錄籤，排障第一站）；主 PACS 未寫共享事件表 → 主控台稽核頁的 connection 分類目前無來源，若日後要「管理視圖」再議（可能收斂掉該分類）。
  - [x] 存法定案＝A 單一共用表（HD_USER_AUDIT_LOG + PRODUCT/CATEGORY，2026-08-06 落地）。
  - [x] 分工定案：LoggingPlatform＝排障（技術 log）；主控台＝管理視圖（事件表）。
  - [x] DicomWeb/Export/主控台已經共用模型寫同一套事件（主 PACS 連線事件＝LoggingPlatform P2）。
  - [ ] 主控台「稽核查詢頁」：讀事件表（product/category 過濾）＋ Keycloak Admin API 拉登入事件。
- [ ] （未來 P2）使用者 provisioning / 稽核查詢。詳 [systems/admin-console.md](systems/admin-console.md)。

## 共用日誌
- [x] **HD.Export 接 HD.Shared.Logging → LoggingPlatform**（2026-08-06 完成+部署+驗證：.195 可見 App=HDExport；commit `a2a9402`。定位決策：**排障第一站＝LoggingPlatform**，主控台的 job/紀錄檢視是管理視圖非排障入口）。註：Source=機器名（hostname），.199 叫 `newdicomweb` 故兩服務 Source 相同；要更貼切可改 hostname。
- [ ] 確認 hd-media-package worker 的 log 有送 LoggingPlatform（燒錄失敗的關鍵訊息在 worker）。
- [ ] 推 ClientIp/User 到其他產品：Animal.Proxy、Viewer.Server、WinForms 看片（主 PACS 已寫）。
- [ ] LoggingPlatform 小缺口：Web `/health`、app.css 版本指紋。

## 影像看片 / Viewer.Server
### ViewerWebApi 架構定案（2026-08-17）
目標：**看片端只跟 ViewerWebApi ＋ HD.DicomWeb 說話，不再直連 DB**；舊 `DownloadHost`（DICOMServer）退場。
部署走 **hdctl**（同 .191/.199），**先獨立成自己一個元件 `viewerapi`**，日後要整併再說。
實查現況：Server 端五個 controller（Auth/Query/KeyImage/Config/QC）已完成；**客戶端只有 1 處走 API、其餘 56 處仍直連 DB**（DicomQuery 26／QualityControl 17／SystemConfig 11／AccessDefinition 2）。詳 [systems/viewer.md](systems/viewer.md)。
- [x] **看片端診斷包 — 本機版完成（2026-08-17，趕在 8/18 裝機前）**：「匯出診斷包」按鈕（關於視窗）＋事故標記（未處理例外／不正常結束偵測）。**只寫本機檔案、不碰網路、不碰登入流程**，所以不必重跑 2.4.0 的完整驗證。三支共用 log 目錄 ⇒ 自動涵蓋 Executer 紀錄。已重新打包 `2.4.0+20260817-121900+0800`。詳 [backlog.md](backlog.md) REQ-016。
- [ ] **第一鏟＝診斷包上傳端點（REQ-016 第二階段）＋ hdctl `viewerapi` 元件**。刻意排在 56 處遷移**之前**：它不碰既有查詢、不改 stored proc、失敗只是少一份診斷資料，適合拿來把「進每間醫院＋hdctl 部署更新」這條路走通。打包邏輯已就緒，屆時只是多一個出口。
- [ ] 客戶端側 56 處改走 API（登入/查詢/設定/QC）；影像改走 DicomWeb WADO-RS。
- [ ] **看片端安裝與更新統一（Inno Setup）**：設計正本＝`docs/viewer-install-design.md`（2026-08-13 討論中）。過去都用「直接複製過去」佈署→路徑混亂、無安裝紀錄、不能退版。**前置整備已完成並 push**（版本 2.3.0＋build 時間戳、LinkClient 可出 x86、程式對安裝位置零假設、升版不再遺失使用者設定）。**待決定四件事**：退版機制（junction 切換 vs 備份搬回）／self-contained 與否／安裝根目錄（Program Files vs C:\HyperDigital）／包怎麼切。⚠️ 關鍵限制：.NET 使用者設定路徑含「安裝路徑雜湊」，版本化目錄若直接當執行路徑，每次更新都會掉登入帳號與面板狀態且 `Settings.Upgrade()` 救不回——必須有固定不變的 `current` 指標當啟動路徑。

### 若瑟醫院 陳醫師需求（2026-08-11 記錄，優先於多院區主機；SITE_CODE 設計已出正本暫停）
- [x] (1) **HU 即時量測（2026-08-11 建置完成，`15d9509`，待實機驗收）**：新工具「HU 即時量測」（HU_PROBE）——啟用後滑鼠移動即時在**游標旁**顯示該點 HU/像素值（樣式沿用「像素偵測」標註設定，字型可調大）；MouseLeave 清除、右鍵退回預設工具；工具面板/快捷鍵已註冊（工具列要從設定加入）。順手：ObjectElement 快取 rescale 後 IPixelData（hover 與標註拖曳逐點取值不再每次重建）。追加（`1c2c40b`）：專屬圖示 annotation_hu_probe（十字準星＋HU）＋作用中游標改十字準星（不疊工具圖示，免擋讀值）。追加（`226d7bd`）：單位規則統一＝有明確單位顯示單位（CT=HU），其餘（無 rescale／未宣告／Rescale Type="US" 未指定）一律 px。**HU 量測本體＋圖示＋單位已使用者驗收 OK**。
- [x] (2) **縮圖列寬度可設定（2026-08-11 完成，`7fbd453`＋`4879fd2`，待實機驗收）**：ViewerLayout.ImagebarWidth（預設 140＝原硬編碼值，per-modality）；設定位置＝**設定→預設格式→「影像列位置」下拉旁的「影像列寬(px)」**（80–1000）；作用於 Left/Right（含 Hidden）停靠，Top/Bottom 高度仍自動。順手整組移除無作用的 Dock Panel Portion UI（原意統一控各面板停靠尺寸、因各面板需求不同棄置；資料模型保留）。
- [x] (3) **連動冷啟動修正（`15d9509`）＋開發機端到端驗證通過（2026-08-12），現場尚未測**：鏈路=HIS→LinkClientDesktop(gRPC :5002)→Executer(tray)→NamedPipe→Viewer。查出三個問題：①Executer 冷啟動只 Process.Start、**不補送訊息**（調閱內容被丟棄）→已改輪詢 pipe 就緒補送（30s 上限）＋ViewerPath 驗證回明確錯誤；②Viewer 登入視窗顯示中收到 pipe 訊息**直接丟棄**→已改排隊＋前置登入視窗、登入成功補處理；③部署的 Executer appsettings.json 的 ViewerPath 指舊開發機路徑——**使用者確認現場這條設定正常**（現場一直在看片），純粹是這台開發測試機的 appsettings.json 沒跟上 net10 遷移路徑，已修正（機器層級設定，不 push）。2026-08-12 用 `LinkClientDesktop.exe` 在開發機完整跑過一輪（Viewer 未開→送 OPEN_STUDY→Executer 自動叫起→登入視窗跳出→登入成功→pending 訊息 flush→開檢查），log 全程正常，①②修正證實有效。另註：ViewerLinkerService.cs 原為 Big5 已轉 UTF-8；順手修一個測試時發現的登入失敗提示視窗被 TopMost 蓋住點不到的問題（`MessageBox.Show` 補 owner，`da8b6c7`）。**現場那台部署機是否已是含 `15d9509` 的版本、「Viewer 未開時連動不跳登入視窗」這個現場場景是否已解決，還沒有人實測**——Executer 跟 Viewer 兩邊都要更新到含這次修正的版本才會生效。
- [x] (4) **關閉歷史影像不再重舖版面（2026-08-12 完成＋已合併 master 並 push，`25604f5`；單/雙螢幕實機驗證通過，待現場驗收）**：設計正本＝`docs/viewer-layout-state-design.md`。根因是版面狀態存在控制項身上、而控制項會被重用，任何變動都得先備份才能還原；解法是把狀態搬進「每個 study 格一本、按檢查分頁的冊子」。
  - 階段 0（`fc4ee7d`）：連動開歷史只佔一格；單螢幕自動擴充成兩格。**順帶解掉「寬螢幕／單螢幕醫師完全無法並排比對歷史」**（開歷史整個畫面被接管）。
  - 階段 1（`b61d60a`）：建立 `StudyCellState`/`CellSnapshot`/`SeriesSlotSnapshot` 冊子＋拍快照。
  - 階段 3（`724b4bc`）：**改造 `REFRESH_STUDY` 而非新增指令**——HIS 沒有「關閉某筆歷史」的概念，回到原本要打的那筆＝視同不看歷史了，所以 HIS 端不用改。擴充出來的格收回、被佔用的既有格用冊子還原、已在顯示目標檢查的格完全不碰。順修 `studyDisplayMode` 指到沒有 Viewer 視窗的螢幕時歷史悄悄不見的靜默失敗。
  - 階段 2（控制項改看冊子）**刻意跳過**：階段 1 完成後 `ApplyCell` 已具備還原能力，不是交付前置條件；風險最集中，留待日後有完整時間再單獨處理。
- [x] (5) **設定視窗字體隨解析度補正（2026-08-12 完成＋100%已驗收＋已 push，`d1ddd99`）**：Utilities/ResolutionFontScale——（螢幕實體高/1080）÷（DeviceDpi/96）=Windows 沒補足的倍率（>1.05 才動、上限 2×）。初版只放大 Form.Font，導致高解析＋100%縮放的機器字變大但控制項 Size/Padding 沒跟上→版面重疊裁切；改用 `Control.Scale(SizeF)`（WinForms AutoScaleMode.Font 做 DPI 縮放的同一套機制）一次縮放 Bounds＋Padding＋Margin＋字體，且會遞迴套到以 Controls 掛入的嵌入子設定頁，SettingsForm 呼叫點精簡為對自身呼叫一次即可。**只動設定頁**，100% 已使用者驗收正常。同批曾嘗試改行程 DPI awareness 修 MPR 3D 在 150% 填不滿右下象限的問題，多輪排查未解且引發新迴歸，已整批還原（MPR 3D 恢復原本行為，100%/150% 皆確認無問題）。
  - [x] **Ctrl+滾輪微調（2026-08-12 完成＋已驗收，`b4d5163`）**：自動倍率只能抓個大概（同解析度在 14吋筆電與 24吋桌機上密度差很多，純靠解析度換算不出「多大」；曾試過用真實 PPI＋LocalConfig.ScreenDiagonalInches，放棄），所以改成**混用**：自動顧開箱預設，Ctrl+滾輪讓醫師調到舒服為止，值存本機設定 `Settings.settingsFontScale`（顯示偏好不進 DB UserConfig，否則會被設定頁的變更偵測判成「設定已修改」）。倍率＝自動 × 使用者（0.7~2.5，每格 ±10%）。**關鍵坑：`Control.Scale()` 只縮放 Bounds/Padding/Margin、不動字體**——這就是先前「版面正常但字仍太小」的原因；只改 Font 又會因顯式設 Font 的控制項不吃 ambient 繼承而字大框沒跟上。正解是兩件事都自己做（關 AutoScaleMode →遞迴縮放字體→Scale() 排版面→還原）。另：`GetAutoScale` 依表單所在螢幕計算，建構當下表單還沒掛進 MainForm 會取到主螢幕，之後顯示在別顆螢幕就會回不同值、增量 delta 全錯，故自動倍率須在建構時定案不再重算。

## 統一部署框架（hdctl）
- [x] 階段一 MVP（2026-08-10）：`hdctl/` repo——hdctl.py（install/rollback/list/prune、sha256 驗證、symlink flip、健檢失敗自動退回）+ hdpack.py 打包 + manifest（範例 HD.Export/deploy/hdctl-manifest.json）；WSL 全流程自測通過。
- [x] .191 試裝 hd-export 驗證（2026-08-10）：install/更新/rollback 全過（HTTP 200）；踩到 init_t 讀 user_home_t symlink 被 SELinux 擋 → hdctl flip 後自動標 usr_t（已修）。/etc/hd/db.env 已建於 .191。
- [x] 階段二主體（2026-08-10）：hdctl 0.2.0（apply 協調包/links/start·stop·restart·status/migrate 登記；WSL 驗過 apply 全驗擋竄改）；**pacs 元件（7 服務）已遷 .191** 並修三顆 CWD 雷（LoggingPlatform 緩衝七倍事件=已修+重佈、CacheControl/History 錨 BaseDirectory=下次發版帶上）；adminconsole 包已備（hd-adminconsole-0.1.0-alpha.1+20260810092901.tgz）。
- [x] adminconsole 遷入 hdctl .191（HTTP 200；舊 /opt/hd-admin-console 留作備份，穩定後清）。hdctl 0.2.1：unit 自動塞 CONTENTROOT（共用 CWD 下 appsettings 沒載到的修正）。
- [ ] 簽章要不要做；`hdctl uninstall` 指令（目前手動移除）；穩定後清 /opt/hd-admin-console 與 service-backup/pre-hdctl。（DicomWeb 定案續留 .199 連 .191 DB，不上 .191；**Export 定案只裝 .199**，.191 試裝品已移除 2026-08-10）
- [x] **.199 的 DicomWeb＋Export 遷入 hdctl（2026-08-10 完成，四健檢全綠）**：dicomweb 元件=兩 unit（主 5080＋UPS 5081，模組設定由 manifest 接管、舊 drop-in 已清）＋`links: data→元件層`（access.db 等本機檔在 releases 外；NAS 掛載在 service 外不受影響）；export manifest 改雙主機 envFiles。之後更新＝hdpack＋`hdctl install`，install.sh 退役為全新環境用。舊資料夾備份在 service-backup/pre-hdctl。
- [x] CacheControl Temp／service-manager History 錨 BaseDirectory（`85bdb08`）——已隨 pacs 2.0.5～2.0.7 佈到 .191（2026-08-18 確認）。
- [ ] 階段三：.234 舊換新正式部署。

## Animal Proxy
- [ ] WebController Phase 7（config 版本歷史）redeploy 到 .222（已建未部署）。

## 多語系（i18n）
- [x] P0（2026-08-10）：HD.Shared.Localization＋共通詞彙 resx＋**管理主控台全站四語**（超出原定一頁示範；116 keys＋切換器，本機驗證通過；規劃見 [i18n-plan.md](i18n-plan.md)）。待 .191 部署驗收。
- [x] DicomWeb 管理端全站四語（2026-08-10）：139 處、108 keys＋切換器，本機驗證通過；待 .199 部署驗收。
- [ ] P2：舊頁面逐 repo 搬遷（Viewer/主控台 → DicomWeb → LoggingPlatform）。
