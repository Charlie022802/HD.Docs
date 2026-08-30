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
- [x] **階段二（PACS 部分）：C-FIND／C-MOVE 出口過濾 —— 完成並實機驗證（2026-08-25）**。DB＝`db_update_v2.0.33.sql`（**已套用 .191，DB 版本 2.0.33**）：`site_query_scope`（可見範圍的唯一正本）＋`site_can_access_study`＋`site_can_access`（Study/Series/Image 三層級）＋修補 `query_dicom` 的 `prosrc` 加院區 WHERE。C#＝`DicomPACSService.cs` 在插 job 前呼叫 `site_can_access`（**已部署 .191 `pacs 2.0.13+20260825100752`**）。
  - **C-MOVE 是這次補起來的洞**：三個層級原本都是「UID → ref → 直接插 job」，沒有任何權限判斷。只過濾 C-FIND 的話，知道別院 StudyInstanceUID 的 AE 照樣搬得走——擋在「找得到」卻沒擋在「拿得到」。層級對應放在 DB（表在那裡）而不是 C#，呼叫端只有一個進入點，不會有人只擋 Study 忘了擋 Image。
  - **拒絕回一般的 `ProcessingFailure`**，不用專用拒絕碼，否則對方能靠回應碼試探 UID 存不存在。
  - 驗證：DB 層排練 34 項斷言（整份包在 tx 裡 ROLLBACK）＋**對 .191 發真的 DICOM 請求**——掛 BRANCH／未掛院區取 HQ 的 study 都**沒有建出 CMOVE job**，掛 HQ 才建得出來；C-FIND 為 HQ=2／BRANCH=0／未掛院區=62。**斷言看的是 job 有沒有被建立，不是回應碼**——回應碼可能因為目的地連不上而失敗，只有「沒有 job」能證明是院區過濾擋下的。
  - **注意：`.191` 的 `SITE` 表有 3 筆 fixture，所以那台的過濾現在是生效狀態**（沒掛院區的 AE 只看得到未歸戶）。要回到完全不過濾就把 `SITE` 清空。
- [x] **階段二（DicomWeb QIDO/WADO）—— 完成並實機驗證（2026-08-25）**。DB＝`db_update_v2.0.34.sql`（**已套用 .191，DB 2.0.34**）：規則引擎抽成 `site_scope_for_code(code, actor)`，`site_query_scope(calling_ae)` 改為薄殼，新增 `site_scope_for_user(user_id)` 讀 `HD_USER.OTHERS ->> 'siteCode'`（比照 AE 存在 `AE_CONFIG` 的 jsonb，零 schema 改動）。程式＝`SiteScopeProvider`（Infrastructure/MultiSite）＋ QIDO 四個查詢加 WHERE、WADO 七個入口加閘門（**已部署 .199 `dicomweb 1.0.0-alpha.4`**）。
  - **呼叫者身分兩條路**：API Key 走 `ae_title`（與 C-FIND/C-MOVE 同一支 `site_query_scope`）、Keycloak token 走 `site_scope_for_user`。**金鑰沒綁 AE ＝ 視為未歸戶**（使用者選定），不是放行——忘了設定不該變成後門。
  - **WADO 一定要自己擋**：全是「拿 UID 直接取」，沒有 WHERE 可加。只過濾 QIDO 的話知道 UID 就取得走。拒絕回 404 不是 403，否則能靠狀態碼試探某筆存不存在。
  - 驗證：DB 排練 16 項（含 `site_query_scope` 改寫後的回歸，拿改寫前的實際值比對）＋**對 .199 發真的 HTTP 請求** 10 項全過（QIDO study/series/instances、WADO metadata、無 AE 金鑰）。
  - **踩到兩顆**：①PL/pgSQL 的 `SELECT ... INTO` 查無資料時會把**所有**目標設成 NULL（不是維持原值），自己帶的 `v_found` 旗標永遠不會是 false → 查無使用者默默變成「未歸戶」而非拒絕；要用 `FOUND`。②金鑰身分的 `Identity.Name` 是**金鑰名稱**（`nameType: "api_key_name"`），拿它當使用者帳號查 `HD_USER` 必然查無此人 → 沒綁 AE 的金鑰什麼都看不到；要用 `actor_type` 判斷身分類別。
- [x] **匯出／燒錄（HD.Export）—— 完成並實機驗證（2026-08-25，`alpha.15`）**。`db_update_v2.0.37.sql`（**已套用 .191，DB 2.0.37**）：`site_scope_for_actor(actor_type, actor_id)` 依身分類別分派 ＋ `export.create_package_job` 在選件展開後檢查。
  - **擋在 proc 而不是 API**：選件有兩種模式（`studies[]` 的 UID、`patientId+accessionNumber` 的條件查詢），都在那支 proc 裡展開成 UID 清單——擋在展開之後兩種一次涵蓋，而且檢查與寫入同一個交易，沒有 TOCTOU。
  - **整批拒絕而不是靜靜略過**：產物會離開系統（燒成光碟交給病患），少幾張而呼叫端不知道是臨床問題。訊息也不區分「不存在」與「別院的」，免得能拿來試探。
  - 排練 14 項 ＋ 對 .199:5090 的實機 6 項。**排練第 0 項先量了「改造前 BRANCH 確實打包得到 HQ 的資料」**——洞是實證存在的，否則後面全部被拒也可能只是條件被寫死成 false。
- [ ] **階段二（其餘出口）**：Viewer（登入者帳號綁院區——DB 那半已經好了，`site_scope_for_user` 直接可用）、**RLS 第二道護欄**（RC_STUDY policy，同時是誤刪的第二道，pgbouncer 環境需 `SET LOCAL`）。規則沿用同一支 `site_scope_for_code`，不要各自實作。
- [ ] **其餘沒有院區概念的出口**（2026-08-25 盤點，實際查過）：
  - **hd-web-server** —— 看片端影像的**實際來源**（`/api/v2.0/wado-uri`），零院區概念，且**不是我們的 repo**（同事維護），要跨團隊協調。
  - **Viewer 直連 DB 的 56 處查詢** —— 完全繞過所有過濾，要等 ViewerWebApi 架構才有地方掛。
  - **ROUTE / C-STORE 轉送** —— 路由規則沒有院區概念，可能把 A 院的片自動送到 B 院登記的目的地。
  - **AdminConsole** —— 看得到全部。可能是刻意的（管理員本來就跨院區），但要確認而不是預設。
  - **`delete_site_studies` 只存在於註解裡，還沒實作** —— v2.0.31 引用它解釋「為什麼停用院區要拒收」，但函式本身不存在。整院匯出工具也還沒有。
- [x] **DicomWeb 其餘出口（DELETE / UPS / STOW）—— 完成並實機驗證（2026-08-25，`alpha.5`）**。DB＝`db_update_v2.0.35.sql`（`site_code_of_ae` / `site_code_of_user`，回答「我自己是哪一個院區」，蓋章用；**不能拿 scope 的 codes[0] 代替**，共用群組下那是亂選）＋ DicomWeb `db/migrations/007`（`UPS_WORKITEM.SITE_CODE`）。兩者**已套用 .191**（DB 2.0.35）。
  - `DELETE`：三個層級都在解析 ref 之前擋，回 404。
  - `UPS`：建立時蓋 `SITE_CODE`，搜尋加條件，其餘六個入口（取得/改狀態/修改/取消/訂閱/退訂）逐一擋。
  - `STOW`：**查證後確認本來就正確，未改動**——`insert_dicom_info` 是階段一蓋章的四個點之一，依 calling AE 解析 siteCode 並帶跨院區同 UID 護欄；STOW 傳的是 header AE 或金鑰綁的 AE，未登記的 AE 本來就被拒。
  - 驗證 13 項全過。**`DELETE` 只驗「被擋」不驗「放行」**——放行等於真的把 .191 的 study 排進刪除，而放行路徑與 QIDO/WADO 共用同一支 `CanAccessStudyAsync`，那輪已經驗過。斷言看的是「沒有排出 CACHE_DELETE job」＋「`IS_CACHED` 沒被動到」，不是只看回應碼。
- [x] **Worklist（MWL）讀取端過濾 —— 完成並實機驗證（2026-08-25）**。`db_update_v2.0.36.sql`（**已套用 .191，DB 2.0.36**）：`HDM_SERVICE_REQUEST` 加 `SITE_CODE`（＋外鍵＋索引）＋修補 `query_worklist` 的 `prosrc`。規則沿用同一支 `site_query_scope`；掛鉤本來就在（`WorklistDicomService` 已經傳 `{aeTitle: CallingAETitle}`）。**改動全在 DB，不需要重新部署 PACS。**
  - 驗證：排練 8 項（交易內 ROLLBACK）＋**對 .191 的 WorklistServer 發真的 MWL C-FIND** 5 項。
  - **測試素材是自己建的**：`.191` 的 worklist 本來是空的，不建測試單的話每一項都是 0、全綠但什麼都沒驗到。
  - **踩到一顆假綠燈**：第一次跑時 WorklistServer 回 `CallingAENotRecognized`（Worklist SCP 有自己的白名單 `HDM_AE_MAIN`，與 PACS 的 `AE_MAIN` 是兩張表，而 .191 上它是空的）。此時「BRANCH 應該看不到」那項回 0 而「通過」——但那是連線被拒，不是過濾生效。測試裡改成先登記測試 AE（`HOST='0.0.0.0'` 跳過 IP 比對）、測完移除。
- [ ] **⚠️ Worklist 寫入端蓋章（上線前必做）** —— 讀取端已是**嚴格模式**（AE 掛了 siteCode 就只看得到同院區），但 `insert_worklist` 還沒有蓋章，所以現有的單全是未歸戶。**在醫院／動物醫院啟用多院區之前，`SITE_CODE` 必須先寫得進去，否則儀器會查不到任何排程**（2026-08-25 使用者確認接受此順序，內部測試環境不受影響）。
  - `insert_worklist(template jsonb)` 不知道呼叫者是誰——worklist 走 HTTP 不走 DICOM association。三條寫入路徑的身分來源各不相同：動物醫院線（院區在 URL `/hcs/<院號>`，設計文件說靠 nginx 注入 header）、UPS 線（`GetOwnSiteCodeAsync` 拿得到）、既有 HIS 線（目前完全沒有身分）。要跟 WorklistInsert 那個案子一起定。
  - **已知的不對稱**：UPS 建立 workitem 會橋接進 `insert_worklist`，所以 `UPS_WORKITEM` 有蓋章、連帶產生的 `HDM_SERVICE_REQUEST` 沒有。
  - 既有 worklist 資料怎麼歸戶也要一併決定。
- [ ] 管理 UI 要能設定使用者的院區（`HD_USER.OTHERS.siteCode`），目前只能手改 DB。
  **⚠️ 2026-08-27 起 `HD_USER` 要退場（REQ-024）**，院區改成 Keycloak 的 user attribute（隨 token 帶進來）；
  `site_scope_for_user(user_id)` 這支 proc 屆時**不能再自己查 DB，要改成由 C# 把 siteCode 當參數傳進去**。
  **動工前先看 REQ-024 的執行順序**，免得做完又要重來。
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
- [x] **稽核頁下架，收斂到主控台（2026-08-26，`1.0.0-alpha.11`，已部署 .199）**：
  `HD_USER_AUDIT_LOG` 自 v2.0.27 起是全產品共用表（多了 `PRODUCT`／`CATEGORY`），
  但這裡的 `/admin/audit-logs` 只濾 `TENANT_ID`、頁面也沒有 `PRODUCT` 欄，
  等於把 export／admin-console 的事件混進來當成本站的顯示（表頭還寫「資源 UID」，
  是它只服務 DICOM 時的遺留）。**不是多一個入口，是會讀錯的入口。**
  這是 API Key 那次整併的遺漏，不是設計決定。
  拆掉：`AuditLogs.razor`＋NavMenu 連結＋`GET /api/v1/admin/audit-logs`＋
  `ApiClient.GetAuditLogsAsync`＋只剩它在用的 `_defaultTenantId`。
  **留下**：寫入管線（`ChannelAuditLogger`/`AuditChannel`/`AuditFlushBackgroundService`/`AuditSpool`）
  完全不動；對外契約 `GET /api/v1/audit/logs` 保留（有文件、有 conformance 宣告、
  且整合測試靠它驗證寫入）；`PageAdminAudit` policy 留著（`AccessLogs.razor` 也在用）。
  驗證：舊管理端點 404、對外契約 401（端點還在）、**並打一筆帶特徵字串的 QIDO 確認事件仍寫得進去**
  （`qido.query.studies`／`actor=hdtest`／`success`）——只看筆數沒有鑑別力，系統是活的、筆數本來就會長；
  拆壞寫入端的症狀是稽核靜默停止，不會有錯誤訊息。
- [ ] `GET /api/v1/audit/logs` 也沒有 `PRODUCT` 篩選、回應也不帶 `Product`/`Category`。
  對外契約所以沒跟著動，但同樣會讓呼叫端以為拿到的只有 dicomweb 的事件。
  加篩選參數與欄位是可加性的（不破壞契約），值得補。
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
- [x] **`burnTemp/package/` 的守門已驗證有效（2026-08-30 回頭確認，臨界日 8/28 已過）**。
      `CleanUpLegacyOutputs` 對容器目錄有 `continue`，但**失敗要滿 7 天才會現形**，
      2026-08-21 部署當天只做得到程式碼層面確認。三項證據：
      ①**結構**：`package/` 還在，而 `burnTemp/` 的 mtime 停在 8/27 ——
      若 `package/` 被刪後重建，父目錄 mtime 會是 8/28，所以它是連續存在的。
      ②**legacy 掃描的 log** 全部指向 `/burnTemp/<數字>` 這種舊產出（最後一次 8/21），
      **沒有一筆是 `/burnTemp/package`**。
      ③`package/` 的 mtime `8/28 16:04:25` 由**正常路徑**解釋 —— 同一秒的 log 是
      「產出過期，已刪除目錄 job=[128] [`/home/HD/data/burnTemp/package/128`]」。
      順帶確認 `expire_package_jobs` 新舊佈局都處理得了（8/27 刪 `burnTemp/125`、
      8/28 刪 `burnTemp/package/127`）。
      > **查法上的教訓**：這支服務**不寫 journald**，寫 Serilog 檔案
      > `/home/HD/service/hd-pacs/logs/hd-media-package_YYYYMMDD.log`。
      > 最初兩次 `journalctl | grep` 都是空的，而**空結果什麼都不代表** ——
      > 先放一條「grep 本來找得到東西嗎」的對照組，才發現前面白查。
- [ ] 長期：Export 整支取代 hd-media-package（燒錄佇列/取件號/費用/光碟 viewer 收進來）。
- [ ] 人用 Keycloak token 呼叫：ResolveScopes 已支援 ACCESS.export 區段（HD.Shared `f52b1fa`）；等 Export 接 MultiScheme+Keycloak 時啟用。

## Auth 收斂 / Keycloak — **定案：所有產品的「人」登入一律走 Keycloak（2026-08-06）**
稽核分層隨之定案：**登入事件正本＝Keycloak Events**（各產品不自記登入）；操作＋API Key＝共享事件表。
- [x] **Keycloak Events 已開**（2026-08-06 使用者自己開：User events + Admin events + 保留期）。註：原生 UI 的 User 欄只顯示 UUID，要點開才見帳號 → 主控台稽核頁（Admin API 拉 events、UUID→帳號人話呈現）解決。
- [x] **共享事件表落地（2026-08-06 程式面全完成）**：v2.0.27 migration（PRODUCT/CATEGORY 欄+索引，Database `e36249a`）；共用 `DbAuditLogger`（HD.Shared `69e08a2`）；DicomWeb 補欄+category 粗分（`a15cb65`）、Export（`ad734b3`）、主控台（`34ca38d`）皆改寫事件表。**全部完成（2026-08-06 晚）**：.191 已套 migration；DicomWeb（build 205757）/Export（205819）已重部署 .199（部署慣例改為 ~/deploy-dicomweb、~/deploy-export 分資料夾）；**三產品實測入表**：dicomweb/operation（qido）、export/audit（壞 key 攔截）、admin-console/audit（金鑰生命週期），SOURCE_IP 皆正確（VPN 來源 192.168.68.253／本機 ::1）。
- [x] **DicomWeb 切 Keycloak（2026-08-07/08，HD.Pacs.DicomWeb `4c9535b`→`ed4156b`、HD.Shared `79ee858`，部署 .199 驗證通過）**：Admin UI=OIDC 導頁（登入卡→SSO→後台→RP-initiated 登出）；API JWT=AddKeycloakJwtBearer（aud=hd-pacs 嚴格）+OnTokenValidated 查 HD_USER 補 scopes（無對應→401）；退役 JwtIssuer/DevSigningKeyProvider/dev-token/固定管理帳密/HD_USER.PASSWORD 驗證。新坑三枚：**登出需 id_token_hint→必須 SaveTokens=true**；**DefaultChallengeScheme 別設 OIDC**（未登入會跳過登入卡直彈 Keycloak）；**Valid post logout redirect URIs 用 `+`**。單元 87/87、整合 31/31 綠。
- [x] **看片端登入雙軌實作完成並部署 `.199`（2026-08-28，viewerapi `0.1.0-alpha.4`）**：
  `Auth:Provider` 切換（預設 `database`，走 `/etc/hd-viewer-api/keycloak.env`）；
  `ViewerAccessBuilder` 把 scope 展開成與 `get_access_definition` 逐鍵相同的 access 樹，
  **客戶端零改動**。端點開始實際檢查 scope（原本只有 `[Authorize]`，access 樹純粹是 UI 層）。
  實測：巢狀 composite 會展平（8→14／8→13）、`qc/config` 200 vs `qc/action` Delete 403、
  部署後真實帳號的帳密軌登入與端點皆正常。**`.199` 已於 2026-08-28 21:18 切成 SSO**（建 `/etc/hd-viewer-api/keycloak.env`）；
  驗收證據是「兩條軌的輸出逐字不同」與「同一 payload 換職務 403↔200」，不是「服務還活著」。
  退回只要 `rm` 那個 env 檔再重啟。**目前只有 `hdtest` 在 Keycloak 有 `viewer.*` 角色。**
  順手修掉一個會靜默毀資料的 bug，詳 [systems/identity.md](systems/identity.md)。
- [ ] **`.163` 還停在 `alpha.3`**（2026-08-28 擱置）：那天連不到正確的那一台 ——
  `192.168.68.163` 在兩條 VPN 通道上指到不同機器，而兩台是複製 VM、主機名與 machine-id
  都一樣（見 [environments.md](environments.md)）。**兩台版本不一致中**，
  下次能連上正確的機器時補裝。裝之前先跑那份最小身分檢查。
- [ ] **Viewer 切 Keycloak — 雙軌（2026-08-17 決策）**：醫院封閉網路連不到 sso.hdtech.tw，**之後會在各醫院內部自建 Keycloak**（尚未架設）。→ 登入這塊**可提前實作**（Authority 指院內位址、由設定決定），**但不替換現行 WebApi 帳密登入**（`LoginForm.CheckUser` → `/api/v2.0/user/login`）；兩條路並存、設定切換，院內 SSO 到位才開。AuthZ 仍查 DB。詳 [systems/identity.md](systems/identity.md)。
  **⚠️ 2026-08-27 推翻「不替換」**：hd-web-server 確定淘汰，它就是那條帳密路的實作，
  沒有第二軌可留 → 看片端的 Keycloak 登入從「並存」變成**取代**，而且是 REQ-024 整條路的**瓶頸**
  （必須先於 hd-web-server 淘汰）。封閉網路根因與 OIDC 九坑仍然有效。
- [x] ApiTest / TestClient 工具更新（2026-08-08，`f033af4`）：登入改 Keycloak password grant 或直接貼 API Key（TestClient 帳號欄貼 `hdp_` 開頭免密碼）；金鑰管理頁/測試段移除（歸主控台）；ApiTest 加「dev-token 與 /api/v1/api-keys 應 404」防呆；Smoke 流程 Import 明帶 X-Calling-AE-Title。
- [x] 抽跨產品共用 Auth lib（2026-08-06 完成：HD.Shared.Auth＝Keycloak 取/驗 token＋API Key handler＋ScopeCatalog＋HdUserRepository；DicomWeb/Export 已用）。
- [x] Keycloak 驗證面全通：audience mapper（hd-api→hd-pacs）嚴格驗證、OIDC 授權碼登入（主控台整圈）。
- [x] DicomWeb 人類登入切 Keycloak（2026-08-07/08 完成，見上）。
- [x] ~~provisioning：使用方打 API 註冊（Keycloak Admin REST 契約待同事）~~ → **改成 JIT 佈建（2026-08-26）**。
  契約沒發生：同事的**前端訂閱制系統**先上線，使用者在那邊自行註冊、Keycloak 在他那端整合，於是
  `HD_USER` 永遠不會長出來 → 拿合法 token 打 DicomWeb/Export 一律 401。改成「Keycloak 認得但無對應
  `HD_USER` 就地建一筆零角色的」，`HD.Shared.Auth.HdUserRepository.ResolveByIdAsync`，三支服務共用。
  開關 `Keycloak__JitProvisionUsers=true`（**環境變數，不能放 appsettings**——preserve 會擋住），
  **預設 false**。兩種真實 schema 各 25 項斷言通過。詳 [systems/identity.md](systems/identity.md)。
- [x] **JIT 佈建已部署 `.199`（2026-08-26）**：dicomweb `1.0.0-alpha.10`＋export `0.1.0-alpha.16`，
  `/etc/hd-pacs-dicomweb/keycloak.env` 與 `/etc/hd-export/keycloak.env` 各加一行
  `Keycloak__JitProvisionUsers=true`。**env 目錄是 `hd-pacs-dicomweb` 不是 `hd-dicomweb`**
  （unit 名同）——加到不存在的路徑不會報錯，只會讓 JIT 靜默沒開啟，所以動之前一定要先 `ls`。
  兩個 unit（5080 主站＋5081 UPS）共用同一份 envFiles，加一次即可。
  順手補了 `HD.Export/deploy/pack-export.sh`（Export 原本是唯一沒有打包腳本的 hdctl 元件，
  等於少掉密碼檢查與設定檔可載入檢查兩道）。
  **主控台（`.191`）刻意不開**：它本來就不會 401（沒對應 `HD_USER` 也登得進、只是零 scope），
  而且三支共用同一張 `HD_USER`，人只要打過 `.199` 一次就已經在表裡了。
- [x] **JIT 端到端驗證通過（2026-08-26，`.199` 生產）**：`active`＋`/health` 200 只證明服務起得來、
  沒走到 JIT 分支，所以另外造了「Keycloak 有、`HD_USER` 沒有」的狀態實測 ——
  把 `.191` 的 `hdtest` 那列暫時改名 `hdtest_jitbak`，用 password grant 取 token 打 `.199`：

  | | `HD_USER` 有（基準） | 改名後（JIT 生效） | 還原後 |
  |---|---|---|---|
  | `/api/v1/auth/me` | 200、10 scopes | **200、`scopes:[]`** | 200、10 scopes |
  | QIDO | 200 | **403**（不是 401） | 200 |

  **401→403 是關鍵證據**：401＝不知道你是誰，403＝知道你是誰但沒權限，後者代表 `HD_USER`
  已建出來且 `ResolveScopes` 跑過。建出來的列：`ROLES=[]`、`GROUP_REF=2`、
  `OTHERS.keycloakSub` **等於 token 的 `sub`（`c23d9283-…`）** —— 那個 UUID 我們沒有別的管道拿得到，
  能對上才證明存的是真身分。還原用單一交易（先刪 JIT 列再改回名字，因為 `ID` 沒有唯一約束，
  順序反了會短暫出現兩列同 ID 而查詢是 `LIMIT 1`），原列 UUID `2836b334-…` 全程未被刪。
- [x] **`HD_IDENTITY_MIRROR` 落地 `.191`（2026-08-27，`db_update_v2.0.40`）**：表本來只寫了腳本沒套，
  等於投影表那段程式碼是「寫了但沒交付」。套完驗過的是**結構不是存在**：10 欄、`SCOPES` 的索引
  實際型別是 `gin`（不是被建成 btree）、`USERNAME` unique、`@> ARRAY[...]` 查詢可執行。
  `.191` 上跑的 `alpha.25` 已含讀這張表的程式碼（`ExistsAsync()` 每次開頁面檢查），不必重新部署。
- [x] **realm 設定變成版控產物（2026-08-27）**：[keycloak/](keycloak/) —— 整個 realm 原本只存在
  那台 Keycloak 裡，共用 realm 上任何人的誤觸我們都看不出來。腳本只抓 `hd-pacs*` 三個 client、
  `hd-pacs` 的角色（composite 展開）、群組、user profile；**不碰同事的 client**，也不含 secret。
  輸出穩定排序，所以有 diff 就代表真的有人改了設定。
- [ ] **權益等級仍未解**：JIT 讓人進得來，但權限要人工指派。方向＝訂閱方案對應 Keycloak group、
  我方做 group → `HD_ROLE` 映射（`groups` claim 已經在 token 裡）。**待與同事確認對照表。**
- [ ] **AdminConsole 使用者管理頁**：JIT 佈建出來的人要有地方指派角色。順帶補掉
  「`HD_USER.ROLES` 全 DB 沒有任何寫入路徑」這個洞（現在只能手動改資料庫）。
- [x] **帳密（人）路打通（2026-08-09）**：`HD_USER` 補 `ID=hdtest`（ROLES=[1] admin、email=hdtest@hyperdigital.biz 與 Keycloak 一致）→ password grant 取 token 打 `/me` **200 整圈通**（scopes 由角色 1 解析：dicomweb.read/export.*/report.*/admin.*；無 stow/import 子區段故無 write）。正軌仍是 provisioning 雙寫。
- [x] **groups claim（2026-08-09，同事需求）**：Keycloak `hd-api` scope 加 Group Membership mapper（claim=groups、Full path Off、access+ID token）→ 掛 `hd-api` 的 client 全部帶 groups；DicomWeb `/api/v1/auth/me` 回傳 groups（`782ed6f`，部署 .199 驗證：`["hyperdigital"]`）。提醒：groups 僅供顯示/分流，**授權仍查 DB**；若要群組→權限映射另議。

## HD 後端管理主控台（HD.AdminConsole）— 集中管理平面
- [x] **`/users` 標成「舊」（2026-08-27，`0.1.0-alpha.26`）**：三支服務都改讀 token 之後，
  `HD_USER.ROLES` 只剩 hd-web-server 會讀，但那頁與側欄註解還寫著「目前實際生效的授權來源」。
  改成頁面上一條明說「這一頁已經不是權限的正本了」並連到 `/identity`，側欄加「舊」徽章。
  **還不能整頁移除**：看片端的帳密登入仍走 hd-web-server。等它淘汰再拿掉。
- [x] **系統資訊視窗（2026-08-26/27）**：右上角 info，三組（程式／執行時期／連線）。
  排障第一句話——現場截這張圖就知道版本／環境／連到哪個 DB／SSO 指哪。**DICOMweb Manager 同步加上**
  （`1.0.0-alpha.12`），那邊多「啟用模組」與「JIT 佈建」兩項：前者因為同一份程式碼會以不同模組
  組合起多個 unit（5080=dicomweb+admin、5081=ups），後者只存在機器的 env 檔裡、畫面上原本看不出來。
- [x] **互動渲染統一到 router 層（2026-08-26，`0.1.0-alpha.9`）**：原本四個頁面各自標 `@rendermode`，
  MainLayout 留在靜態渲染——掛在它上面的 `@onclick` 不會執行、`@ref` 也跨不過邊界，於是同一個功能
  得寫兩種版本。改成 `<Routes @rendermode="InteractiveServer" />` 後，`DotNetObjectReference` +
  `show.bs.modal` 那整套繞法拆掉。**必要的連帶修正**：互動路由會攔截同源連結去比對路由，
  指向非 Blazor 端點的連結要 `data-enhance-nav="false"`——`/logout` 與語言切換本來就有，
  `LoginPrompt` 的 `/login` 沒有（靜態時不需要），不補的話按登入變 NotFound。
- [x] **翻譯補齊（2026-08-26，`0.1.0-alpha.11` / DicomWeb `1.0.0-alpha.13`）**：裝置授權頁 60 個 key
  從沒進過 resx、API 金鑰的權限名稱根本沒經過 localizer、Export 狀態的「錯誤」卡在另一本 resx。
  **查法的教訓寫在 [i18n-plan.md](i18n-plan.md)「漏譯怎麼查」** —— 掃 `L["字面量"]` 只找得到一半，
  動態查表點要另外枚舉；漏譯是靜默失敗（localizer 找不到就回傳 key，而 key 就是中文）。

- [x] **第一鏟：骨架 + Keycloak SSO 登入整圈驗證（2026-08-06）**：Blazor Server + OIDC 授權碼導頁（定案：保持導頁、美化走 Keycloak theme）；登入卡/身分頁/RP-initiated 登出全通；鯨魚 logo。repo GitHub Charlie022802/HD.AdminConsole。
- [ ] 請同事做 Keycloak login theme（HD 風格登入頁，全產品受益）。
- [x] **API Key 管理搬入（2026-08-06，`f8533af`，對 .191 DB 實測）**：/apikeys 清單/建立/編輯/撤銷；Npgsql 直連 HD_API_KEY（與各服務驗證同表）；badge 產品配色+目錄排序+去黑話用語。授權 v1=登入即可管（scope 檢查待補）。
- [x] DicomWeb 側金鑰管理 UI/REST 下架（2026-08-07/08，隨 Keycloak 切換一起；`/api/v1/api-keys` 404、驗證留 HD.Shared handler；測試改 TestApiKeySeeder 直接種表）。
- [x] **授權細化（2026-08-10 上線，主控台+DicomWeb 同步）**：OIDC OnTokenValidated 查 `HD_USER`→`ResolveScopes` 蓋進 cookie claims（無對應=零 scopes；異動需重登）。主控台：/apikeys=`admin.api_keys`、/audit=`admin.audit`、/exports=`export.read`；首頁「我的權限」badges。DicomWeb 管理頁：狀態/系統日誌/設定=`admin.settings`、稽核/存取紀錄=`admin.audit`（Page* policy 走 cookie，勿綁 MultiScheme）。側欄按權限顯示＋已登入無權限顯示 Forbidden（不導登入頁防迴圈）。角色 1 補 `dicomWeb.manageApiKeys`（jsonb_set）。hdtest 正向驗證通過（AdminConsole `90ba655`、DicomWeb `c712aa1`）；負向（無 HD_USER 帳號全擋）待同事帳號順測。
- [x] **稽核紀錄頁 + 匯出紀錄頁（2026-08-06 晚，`99b385e`→`dec5fef`，本機對 .191 實測）**：/audit 全欄位過濾（產品/分類/結果/操作者(類型)/動作/對象(類型/ID)/IP/自訂時間）＋keyset 分頁；/exports 唯讀管理視圖（狀態人話/進度條/錯誤展開）。寬表格水平捲動＋首欄 sticky。主控台三大功能到齊（金鑰/匯出/稽核）。
- [x] **部署 .191:5200（2026-08-07 驗證通過，`77e0640`→`087f7ed`）**：self-contained + install.sh（/opt/hd-admin-console、systemd、SELinux usr_t、自動防火牆）；Keycloak redirect URI 加 `http://192.168.68.191:5200/*`。修 http 站台 OIDC 三坑：cookie SameAsRequest+Lax、回跳改 query（form_post 被 Chrome 攔+cookie 不帶）、關 PAR（sso.hdtech.tw 該路徑 502）。另：SSO 節點死掉時帶舊 cookie 穩定 502（無痕正常）→ 清 sso.hdtech.tw cookie 解，**症狀待回報同事**。詳 [admin-console.md](systems/admin-console.md)。
- [ ] 稽核頁併入 Keycloak 登入事件（Admin API 拉 events、UUID→帳號）。
- [~] **DICOM 連線紀錄**：P2 已實現於 **LoggingPlatform**（連線紀錄籤，排障第一站）；主 PACS 未寫共享事件表 → 主控台稽核頁的 connection 分類目前無來源，若日後要「管理視圖」再議（可能收斂掉該分類）。
  - [x] 存法定案＝A 單一共用表（HD_USER_AUDIT_LOG + PRODUCT/CATEGORY，2026-08-06 落地）。
  - [x] 分工定案：LoggingPlatform＝排障（技術 log）；主控台＝管理視圖（事件表）。
  - [x] DicomWeb/Export/主控台已經共用模型寫同一套事件（主 PACS 連線事件＝LoggingPlatform P2）。
  - [ ] 主控台「稽核查詢頁」：讀事件表（product/category 過濾）＋ Keycloak Admin API 拉登入事件。
- [x] **使用者管理頁（2026-08-26，`0.1.0-alpha.13`）**：`/users`，policy `AdminUsers`
  （那個 scope 一直在 `ScopeCatalog` 與 `ResolveScopes` 裡，但從來沒有 policy 用它——
  在這一頁出現之前沒有任何頁面需要把關）。
  **補掉的是結構性的洞**：`HD_USER.ROLES` 全系統原本沒有任何寫入路徑（DB proc 只讀不寫、
  hd-web-server 只有 SELECT），指派角色只能手動改資料庫；JIT 讓使用者會自己長出來且是零角色，
  這個洞就從「不方便」變成「功能不完整」。
  定位＝**管授權不管身分**：不建立、不刪除、不碰密碼。只寫 `ROLES`/`GROUP_REF`/`DATE_TIME_MODIFIED`
  三欄（`ENABLE`/`EXPIRE_DATE` 舊站台沒有且沒人讀；`OTHERS` 帶著 `siteCode` 與 `keycloakSub`，
  整欄覆寫會抹掉）。清單把未指派角色的排最前面＝JIT 之後的待辦；角色旁邊顯示它實際解析出的
  scope（角色名稱本身回答不了「他到底能做什麼」），用的是各服務驗權限的同一份實作
  （`ScopeResolver`，從 `HdUserRepository.ResolveScopes` 抽出來成靜態）。
  稽核 `auth.user.permission_update` 記 before/after——只記結果的話看不出是誰把權限加上去的。
  **已實測（`.191`，2026-08-26）**：塞一列 `provisionedBy:"jit"` 的測試資料 → 畫面上排最前面／
  黃底／「自動註冊」→ 用 UI 指派角色 → `ROLES` 變 `[2]`、**`OTHERS` 的 `keycloakSub` 原封不動**、
  稽核留下 `rolesBefore:[] → rolesAfter:[2]`。第二項是「不覆寫 OTHERS」那個宣稱的證據——
  抹掉的話是靜默破壞：畫面一切正常，只有多院區的出口過濾之後莫名失效。
- [x] **表格可用性（`0.1.0-alpha.14`）**：明確欄寬、列多時表格內捲動＋表頭 sticky、
  過長內容在格內捲動而非撐寬整表、**可拖曳調整欄寬**（`hdResizableTable`，通用，
  寬度存 localStorage；把手要在每次資料重繪後重掛，Blazor 換資料會重建 thead 的 DOM）。
- [x] **預先建立＋停用（2026-08-26，主控台 `alpha.16`／DicomWeb `alpha.14`／Export `alpha.17`）**：
  - **預先建立**：建的是「授權」不是「身分」——不碰 Keycloak，只先放好一列帶角色的 `HD_USER`，
    JIT 之後不會重複建，那個人第一次登入就能用。**打錯帳號是主要失敗模式**（角色會變孤兒且無錯誤訊息），
    無法事前驗證（沒有 Keycloak Admin API），改成事後看得出來：登入時回填 `keycloakSub`，
    「有沒有 sub」＝「有沒有真的登入過」→ 清單顯示「尚未登入」。
  - **停用取代刪除**（使用者決定不做刪除）。`ENABLE` 由 **v2.0.39** 補進更新鏈（第 4、5 個分岔項）。
    讀用 `COALESCE((to_jsonb(u.*) ->> 'ENABLE')::boolean, true)`——同一句 SQL 在有沒有那一欄的站台
    都跑得動，且不必在驗 token 的熱路徑多打一次 `information_schema`；寫之前先探測，沒有就不提供選項。
  - 實測：主控台停用 → `.199` 的 `/me` **401** → 啟用 → **同一顆 token** `/me` **200**。
    用同一顆 token 才排除得掉「其實只是 token 過期」。
  **停用的涵蓋範圍是三個入口**（主控台／DicomWeb／Export）。看片端的帳密登入不受影響，
  且 **hd-web-server 不會為此修改**（2026-08-26 決定）——看片端切到院內 Keycloak 之後那條路退場，
  限制自然消失。在那之前要完全停掉一個人，得在 SSO 也停用。**UI 與交接文件都據實寫明**，
  不寫成「尚未支援」——那個字會讓人以為系統之後會自己補上。
  （曾評估「停用時抽換密碼 hash、啟用時放回」讓它對看片端也生效，不採用：那讓停用變成一個
  有隱藏副作用的操作，且賭在暫存值不會遺失上，而問題本身會隨 Keycloak 切換消失。）
- [ ] 使用者管理後續：`OTHERS.siteCode` 的編輯（多院區）、`EXPIRE_DATE` 的實際攔截
  （欄位已隨 v2.0.39 補上，但還沒有人讀）、`name`／`email` 是否要每次登入從 token 同步。
- [ ] **角色本身的 CRUD 介面**：現在只能指派既有角色，建立／編輯角色仍得直接打 DB。
  那六支 `HD_ROLE_RBAC_functions.sql`（在 HD.Pacs.DicomWeb repo 的 `db/functions/`）
  **不在更新鏈裡** —— `.191` 有、2026-07-20 的 dump 與若瑟都沒有，是**第六個分岔項**。
  差別是這支至少檔案在版控裡，補一支 migration 直接抄即可。動的是 `HD_ROLE`（主 PACS 的表），
  放在 DicomWeb repo 本來就錯位，跟 `HD_USER_AUDIT_LOG` 是同一種洩漏。
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
- [ ] **Viewer 去 DB 化 + 新舊系統相容（設計定案 2026-08-25，正本＝[systems/viewer.md](systems/viewer.md)）**。
  需求：同一版 Viewer 要能服務**尚未升級主系統**的醫院。實查後結論——**新舊唯一的差異是影像取得**
  （舊＝hd-web-server WADO-URI，新＝DicomWeb WADO-RS），其餘 24 個方法都是同一組 proc、純搬遷不分支。
  **相容性住在 ViewerWebApi**，Viewer 只認一個位址、一套認證。
  - **計數修正**：先前寫的「56 處／86 處」是 `CreateCommand` 呼叫次數，不是 API 數量。實際是
    **26 個公開方法**（`DicomQuery` 12／`QualityControl` 9／`SystemConfig` 5），已接 1、剩 25。
  - **檢查清單不能改走 QIDO**：`viewer_station.search_study` 回的 `QueryResult` 帶 `StudyRef`／
    `Status`／`HasICad`／`ICadScore[]`，QIDO 表達不了。這也是舊站當初沒用 QIDO 的原因。
  - **影像走 ViewerWebApi 轉送而不是直連**：登入搬走之後 Viewer 就沒有 hd-web-server 的 cookie 了
    （現在取影像靠的正是它）。要求串流、不緩衝、不解析 DICOM。
  - 施工順序：① 影像端點＋legacy 後端（行為不變，只驗轉送）② 加 dicomweb 後端（.191 實測
    **JPEG 縮圖外觀與速度**，預轉檔→即時渲染是唯一醫師看得到的差異）③ 接其餘 24 個方法
    ④ 移除 `SafePostgresConnection` 與設定的 `Database` 區塊——**這步才算真的達成不再直連 DB**。
  - 視訊已確認**不是缺口**：兩邊都不支援 DicomMpeg4（新系統不收、轉檔停用；舊版本來就沒有）。
- [ ] **⏸ 進行中：`viewerapi` 已佈上兩台，待設定與端到端驗證** —— 2026-08-25。
  Viewer 的 ①②③ 已完成並 push，但**第一次真的 Viewer 走這條路還沒發生過**，
  到目前為止全是 curl 與測試程式驗契約。④（移除 `SafePostgresConnection`）**要等端到端
  驗證過再做**，否則所有現場立刻不能用。
  - 現況：`.163`（**CentOS 8 / glibc 2.28**，內網測試機）與 `.199`（AlmaLinux，newdicomweb）都跑
    `hd-viewerapi-0.1.0-alpha.3`，聽 **5100**，`/healthz` 正常。設定仍是 `CHANGE_ME`。
  - ~~已驗到 self-contained 的 .NET 10 在 CentOS 7 的 glibc 上跑得起來~~
    **⚠️ 2026-08-26 更正：`.163` 其實是 CentOS 8 / glibc 2.28，不是 CentOS 7**
    （我從「Python 3.6」推論成 CentOS 7，但 RHEL 8 家族的 platform-python 也是 3.6）。
    **不影響結論**：若瑟正式機（`10.10.1.148`）實測是 **RHEL 9.2 / glibc 2.34**，比 `.163` 還新，
    self-contained 沒有相容性疑慮。真正沒驗過的是 CentOS 7 那種老環境，而目前沒有已知醫院是那個版本。
  - **監聽埠 8080 → 5100**：8080 是醫院既有的 hd-web-server 在用，viewerapi 要同機共存
    就不能搶。5100 與 DicomWeb 5080、Export 5090、AdminConsole 5200 同一段。
  - **2026-08-25 兩條路都已在真機端到端驗過（伺服器端）**：同一支 viewerapi、同一組 API，
    只有設定不同——這正是「兼容新舊系統」要的形狀。
    | | `.163`（舊系統） | `.199`（新系統） |
    |---|---|---|
    | DB | 本機 `127.0.0.1` | `.191` |
    | 影像 | `legacy` → hd-web-server **:80** | `dicomweb` → `:5080` |
    | 縮圖實測 | 512×512 / 27KB | 128×96 / 2.3KB |
    - `legacy` 那條路**兩個從沒驗過的假設同時成立**：服務帳號登入只發生一次（cookie 有黏住，
      自帶 `CookieContainer` 是對的）、wado-uri 直接 200 沒走到「400 當未登入」的重試分支。
    - **`type=thumbnail` 在 legacy 回的是全尺寸預轉 JPEG**（舊系統沒有縮圖端點，Jpeg 與
      Thumbnail 同一張），這是刻意的、行為與改造前一致。也解釋了縮圖列的效能數字：
      舊系統那 8.8s 是在搬 300 張全尺寸 JPEG。
    - `.163` 的 hd-web-server 在 **port 80**，不是 8080。「8080 被 hd-web-server 佔著」
      這個當初改埠的理由在 .163 不成立（改 5100 本身仍然對）——**若別處記得是 8080，
      要確認是不是不同版本或前面掛了 nginx**，別把錯的認知帶去下一間醫院。
  - **還沒發生的事：真的 Viewer 走一次。** 到目前為止全是 curl。
    在一台 Windows 的 `localconfig.json` 加 `"ApiBaseUrl": "http://<主機>:5100"`，
    跑完整一輪：登入→查詢→開片→縮圖列→QC→登出。有值＝走 API，留空＝維持直連 DB，
    **這個開關就是新舊並存機制本身**，所以同時也在驗「沒設的機器完全不受影響」。
- [x] **hdctl／hdpack：self-contained 元件踩出的四顆坑（2026-08-25 全修完）** ——
  `viewerapi` 是**第一個 self-contained 元件**（exec 是二進位本身，不是 `dotnet app/xxx.dll`），
  而既有機制全是為後者寫的，所以四顆坑其實是同一個根源。真醫院主機才會暴露：
  `.191`/`.199` 是我們自己養的機器，帳號早就有、Python 也新。
  | 坑 | 症狀 | 為什麼半年來沒暴露 | 修在哪 |
  |---|---|---|---|
  | Python 3.6 | `add_subparsers(required=)` TypeError | 我們的機器 Python 都夠新 | hdctl 0.2.2 |
  | `hdadmin` 不存在 | `217/USER`，unit 一直 activating、**表面看不出跟使用者有關** | 全新主機才沒有 | hdctl 0.2.2（自動建系統帳號） |
  | 沒有執行位元 | `203/EXEC`（Windows 打的 tar 沒有 POSIX mode） | 被執行的是 dotnet，dll 不需要 x | hdctl 0.2.2（`ensure_exec_bits`） |
  | SELinux `user_home_t` | `203/EXEC`，`avc: denied { execute } init_t → user_home_t` | dotnet 在 `/opt`（型別本來就對），`/home` 下的 dll 只被**讀取**——讀允許、執行不允許 | hdctl 0.2.3/0.2.4（`label_exec_selinux`） |
  - **SELinux 那顆修法有兩個容易寫錯的地方**：①必須排在 `restorecon(comp_dir)` **之後**，
    先 `chcon` 會被它洗掉；②要標 **`rel_dir`（新 release）而不是 `current`**——這個函式跑在
    `flip_current` 之前，標 `current` 等於標了舊版、新版一個字都沒動（0.2.3 就是這樣白做一次）。
    用 `semanage fcontext` 登記一條涵蓋所有版本的正規式規則（持久、全機 relabel 也還在），
    再 `restorecon` 去套；`semanage` 不在才退用 `chcon`。
  - 另外兩顆不是 hdctl 而是打包／版號：
    - **hdpack 的「manifest 與組件版號一致」護欄對 self-contained 靜默失效**——它只認 exec
      裡的 `.dll`，認不到就 `return`。已改成取 argv[0] 的檔名。
    - **`InformationalVersion` 讓 `/healthz` 說謊**：`Directory.Build.props` 比 csproj 早匯入，
      算 `InformationalVersion` 時 `$(Version)` 還是共用的 2.4.0，專案自己覆寫的 alpha 版號
      還沒生效 → `/healthz` 回報看片端的 `2.4.0`。搬到 `Directory.Build.targets` 就對了。
  - 教訓（**下次加任何元件層級的機制都要問一次**）：這些機制的隱含前提都是
    「exec = `dotnet <dll>`」。護欄本身也會有這種前提，而護欄失效是**靜默的**。
- [x] **`pack-viewerapi.sh`（2026-08-25）** —— `dotnet publish` 會把開發機的
  `appsettings.json`（**含本機 DB 密碼**）一起帶進包裡。先前是手工洗掉的，這種步驟下次一定忘。
  腳本改成自動用 `appsettings.template.json` 覆蓋，並回頭驗包裡確實是 `CHANGE_ME`，不是就中止。
- [ ] **`insert_study_job` 的 NEARLINE_BACKUP gate 也信 `IS_NEARLINE_CACHED`（併下次正式更新）** ——
  2026-08-25 由使用者發現。
  ```sql
  ELSEIF job_type = 'NEARLINE_BACKUP' THEN
      ...
      IF (SELECT "IS_NEARLINE_CACHED" FROM public."RC_STUDY" WHERE "STUDY_REF" = study_ref) THEN
          RAISE NOTICE 'Already backup to nearline!';
          RETURN;        -- 旗標錯了就不會排備份
      END IF;
  ```
  - **跟 2026-08 若瑟掉資料是同一個根源**：舊的 `get_next_delete_study` 也信這個旗標。
    一個負責「不備份」、一個負責「刪掉」，兩者共用同一個競態窗口。
  - **但嚴重度差一個量級**，別混為一談：

    | | 窗口內發生什麼 | 後果 |
    |---|---|---|
    | 舊 `get_next_delete_study`（已修） | 刪掉沒備份的物件 | **不可逆，資料沒了** |
    | `insert_study_job` 的 gate | 跳過這次備份排程 | 可回復（重算成 false 後下次觸發會補排） |

  - **旗標本身是重算出來的**，不是長期漂移：`update_study_statistical_info` 直接數
    `RC_OBJECT JOIN RC_LOCATION WHERE NEARLINE_VOLUME_REF IS NOT NULL` 來設 true/false。
    所以靜止狀態是準的——2026-08-25 在若瑟實測「旗標說有、實際沒有」的檢查數是 **0**。
    真正的失效是**競態**：新物件進來之後、重算跑之前那段窗口，旗標還是舊的 true。
    若瑟那次正是 NONDICOM 重送把物件加進既有檢查，窗口內自動刪除跑了。
  - **這個 gate 從 2.0.1 就存在**，`insert_study_job` 改過六次（2.0.1/8/12/14/15/20）
    都沒碰它；`.191` 的 2.0.37 也一字不差。所以**不是版本落差，是從沒被回頭看過的原始設計**。
    旁邊的 `ARCHIVE_UPLOAD` 信 `IS_ARCHIVE_CACHED` 是同一個形狀，一起看。
  - **刻意不單獨 hotfix**：`get_next_delete_study` 是刪除的最後一道關卡、單獨補風險可控；
    `insert_study_job` 是進檔流程主幹（STUDY_CLOSE / ROUTE / ARCHIVE 全走它），
    在生產醫院單獨換掉的回報小於風險。併進下一次正式版本更新一起評估。
- [ ] **⏸ 暫停（2026-08-26 使用者決定）：若瑟（`10.10.1.148`）DB 升級 —— 準備工作已全部完成**
  **要重啟時直接排維護時段執行即可，沒有未解項。** 完整評估在
  [josef-db-upgrade-plan.md](josef-db-upgrade-plan.md)。重點：
  - **腳本已備妥並驗證**：若瑟原始 dump、零手動修改，`2.0.23 → 2.0.38` 全綠。
  - **執行前必做**：完整備份（含資料）—— 若瑟的 DB **自 2026-04-02 起沒有備份**，
    這件事的優先級可能比升級本身還高。
  - **升完的驗證重點**：進檔（C-STORE）、MWL 查詢、報告格式清單。
  - 本次**不含服務更新**（若瑟是 net6 + fo-dicom 4，現行原始碼是 net10 + fo-dicom 5，
    跨兩個世代，另案處理）。
  - 預演容器 `josef-rehearsal` 留著（`podman start josef-rehearsal`），
    下次改任何 DB 腳本都可以直接重跑整條鏈。
  **完整評估在 [josef-db-upgrade-plan.md](josef-db-upgrade-plan.md)。**
  - **預演方式**：取若瑟的 schema dump ＋ `HD_CONFIG` 實際資料，還原進 podman 的
    `postgres:16` 容器（若瑟是 16.0），確認基準與實機一致後用 `-v ON_ERROR_STOP=1`
    依序跑 23→27。**完全不碰生產機，失敗零成本。**
  - **結果：整條鏈通過，版本到 2.0.27。** 三個推測的阻擋項實跑後只剩一個。
  - **✅ 已修（`21b6b7f`）**：2.0.27 的 `ALTER TABLE public."HD_USER_AUDIT_LOG"` 加了
    `to_regclass` 判斷。那張表**只有 DicomWeb 的 `init_dicomweb.sql` 會建**，
    **任何沒裝 DicomWeb 的醫院都會卡在 2.0.27** —— 連帶拿不到同一支腳本裡的
    nearline 刪除保護。長遠仍該把那段搬回 DicomWeb 自己的 migration（跨產品相依洩漏）。
  - **❌ 誤判更正**：我原本說 2.0.26 的 `DROP VIEW VIEW_MWL` 會中止 —— **不會**。
    2.0.26 自己在第 1123 行就先建了那個 view。**錯在拿每支腳本去對「起始基準」做靜態分析，
    但更新鏈是累積的、單一腳本內部也有順序。** 這就是預演的價值。
  - **✅ 已解決（不必動 hd-web-server）**：2.0.27 把 `report.get_report_format_list`
    的參數加上 **`DEFAULT NULL`**，無參數呼叫恢復可用且語意完全等價（本體對 NULL 安全）。
    舊的無參數版仍必須 DROP —— `f()` 與 `f(json DEFAULT NULL)` 並存會 `function is not unique`。
    已經跑過舊版 2.0.27 的站台（`.191`）由 `2.0.38` 用既有 `prosrc` 就地補上。
  - **整條鏈已補完**：若瑟原始 dump、零手動修改，`2.0.23 → 2.0.38` 全綠。
  - **升級前務必先做完整備份（含資料）**：若瑟的 DB **自 2026-04-02 起沒有備份**。
    這件事本身的優先級可能比升級還高。
  - 本次**不含服務更新**：若瑟是 net6 + fo-dicom 4，現行原始碼是 net10 + fo-dicom 5，
    跨兩個世代，應該是獨立工程。
  - **日後其他醫院升級前照同一套流程走一遍** —— 每間缺的物件不一樣，靜態分析猜不準。
- [x] **Keycloak domain 搬遷 sso.ltcd.tw → sso.hdtech.tw（2026-08-25 完成並驗證）**
  - repo：HD.AdminConsole `760c633`、HD.Pacs.DicomWeb `bfcab68`、HD.Shared `2c383ba`、HD.Docs。
  - 機器：`.191` 主控台、`.199` DicomWeb 的 `appsettings.json`（**current 與舊 release 都改**）、
    `.199` 的 `/etc/hd-export/keycloak.env`；三支都重啟。`.163` 無關（只有 viewerapi）。
  - **舊 release 的設定也要改**，否則 `hdctl rollback` 會退回舊 domain、登入立刻壞掉，
    而症狀看起來像「退版沒解決問題」。`preserve` 只保護 current 那份往新版帶，
    不會回頭更新舊 release 目錄——這是它的盲點。
  - `data/access.db`（DicomWeb 的存取記錄 SQLite）裡也有舊 domain，**刻意不動**：
    那是歷史紀錄不是設定，改了等於竄改稽核；而且對 SQLite 檔跑 sed 會直接毀掉它。
  - 驗證（缺一不可）：`.well-known/openid-configuration` 200 只代表 realm 在；
    真正有鑑別力的是**拿 token 看 `iss` 與 `aud`**——`aud` 必須含 `hd-pacs`，
    因為 `Keycloak__ValidateAudience=true`，mapper 沒跟著搬的話 token 拿得到但 API 一律 401，
    而錯誤訊息不會說是 audience 的問題。實測 `iss` 新 domain、`aud=['hd-pacs','account']`，
    DicomWeb QIDO 與 Export `/export/packages` 都 200。**瀏覽器 OIDC 導頁也驗過**
    （`http://192.168.68.191:5200/` 登入正常）——那條驗的是 redirect URI，token 測試碰不到。
  - UI 字串裡的 domain **直接拿掉**（→「將導向 SSO 進行驗證」）：resx 的 key 本身含 domain，
    換一次要動三個語系的 key 與 value，而介面文字寫死基礎設施主機名注定會再爛一次。
- [x] **待部署的一批全部佈完並驗證（2026-08-26）** —— hdctl 0.2.6、AdminConsole alpha.5、
  DicomWeb alpha.6，`.191`／`.199` 兩台。順手補上 `pack-adminconsole.sh`／`pack-dicomweb.sh`
  （publish → 密碼檢查 → hdpack；明確標 `--self-contained false`，因為 manifest 的 exec 是
  `dotnet app/xxx.dll`）。
  - **驗「Authority 真的從 env 讀」要有鑑別力**：裝完之後 `preserve` 會把**舊的** appsettings
    蓋回去（裡面 Authority 有值），所以「服務起得來」什麼都證明不了——兩邊都有值，分不出讀哪個。
    要把已部署的 appsettings 的 Authority **清空**再重啟才算數：`.191` 仍 active（守衛沒觸發
    → 值只能來自 env）、`.199` 的 JWT 仍可驗（QIDO 200 → JWT 沒被停用）。
  - **`preserve` 的第二個性質**（第一個是退版那個）：**新版隨包附上的 appsettings 永遠不會
    抵達既有安裝**。設定檔一旦被 preserve，就只能靠人工改。
- [x] **hdctl 0.2.6：退版時目標版 envFiles 比現行版少就警告（2026-08-26，`5a94b66`）**
  0.2.5 的「退版帶設定」有個沒說出口的前提——**「設定是機器狀態、跟版本無關」，在設定的
  來源本身跨版本改變時就不成立**。
  - 實測踩到：alpha.5 把 Authority 從 appsettings 搬到 env（appsettings 留空），退到 alpha.4
    時空的 appsettings 被帶過去，但 **unit 是照目標版 manifest 重寫的**，alpha.4 沒有那個
    env 檔 → Authority 兩邊都沒有 → **服務 active 但每個請求都 500**。
  - `envFiles` 的差集是唯一的可觀察訊號。只警告不擋（退版是逃生路徑），但把修法一起印出來，
    因為「active + 5xx」這個症狀看起來完全不像設定問題。
  - **`.pre-rollback` 逃生門同一輪實測過**：換回正本重啟即恢復。
  - 教訓：這個前提**只有真的退一次版才會發現**。留到現場出事時才踩到，代價完全不同。
- [x] **AdminConsole／DicomWeb 的 `Keycloak:Authority` 改從 env 讀（2026-08-25 完成，待部署）**
  起因：換 domain 時 **HD.Export 的 repo 一個字都不用改**，因為它當初就把 Authority 當
  「機器相關設定」放進 `/etc/hd-export/keycloak.env`。這兩支寫死在 `appsettings.json`，
  結果要改程式碼＋改 current＋改舊 release，UI 字串還要重新部署才跟得上。
  而各醫院自建院內 Keycloak 已定案，到時每間的 Authority 都不一樣，寫死行不通。
  - HD.AdminConsole `227771b`（alpha.5）、HD.Pacs.DicomWeb `620605e`（alpha.6）。
  - **兩支的處理刻意不同**：DicomWeb 與 Export 同性質，留空＝不啟用 JWT、只收 API Key，
    服務照常跑；**AdminConsole 的唯一入口就是 OIDC**，留空等於沒人進得來，所以加了守衛讓它
    **啟動就失敗**。不擋的話症狀是「服務 active、健檢過、但一按登入就 500」——
    `AddOpenIdConnect` 會把 MetadataAddress 組成 `/.well-known/openid-configuration`
    （不是合法 URL），首次解析 options 才丟例外。啟動就死掉好排查得多。
  - **部署前提已備妥**：`.191` 的 `/etc/hd-admin-console/keycloak.env`、
    `.199` 的 `/etc/hd-pacs-dicomweb/keycloak.env` 都已建立（640）。
    **但現在跑著的 unit 還沒引用它們**——unit 的 `EnvironmentFile` 是 install 時照 manifest
    寫進去的，要等下次部署新版才生效。所以現在零風險，機器照舊跑。
  - 還沒搬的：`ClientId` / `Audience` 仍在 appsettings（值是對的）。要一併搬就照 Export
    那份 env 的格式。
- [x] **hdctl 0.2.5：退版時把現行設定帶到目標版（2026-08-25，`afa431b`）**
  `do_rollback` 原本完全沒碰 `preserve`，目標 release 用的是它**當初被安裝時**那份設定。
  設定是**機器狀態**不是版本狀態——DB 密碼、SSO 位址、影像後端屬於這台機器，跟跑哪一版無關。
  - 實案：換 domain 改了 current 的 appsettings，舊 release 裡還是舊 domain。那時若退版，
    登入會立刻壞掉，而症狀看起來像「退版沒解決問題」——最不該在退版當下遇到的那種誤導。
  - 目標版原本那份留成 `.pre-rollback`。`preserve` 清單取兩版聯集（新版可能多列了目標版
    不知道的檔案）。**這版還沒佈到機器上**，三台目前是 0.2.4。
- [ ] **Viewer QC 的定位待重新釐清（先擱著，不要往任何方向推進）** —— 2026-08-25。
  Viewer 內建的 QC 是**單機 Viewer 時代的產物**，現在只有少數幾間醫院還在用；
  大部分 QC 是去 AdminTool 網頁做的。使用者要的是**重新整理這塊的定位**——
  **不是要退場**，所以現在既不要主動補功能、也不要規劃退役。
  - 已驗（2026-08-25 實測）：`qc/tree` 的 Study／Series／Image 三層、Study 修改
    （`CALL viewer_station.qc`）。三層都有資料回來，順帶證實 `SelectJsonRows` 的修正是對的
    （`get_qc_tree` 回 SETOF jsonb，原本用 `SelectJson` 只會拿到第一列）。
  - 還沒驗：`qc/config`、`qc/transmit-jobs`、`qc/transmit-job`、`qc/exist-data`
    ——其中「影像傳送」那兩支最值得補。
  - **與 ④ 的相依仍在**：④（移除客戶端 `SafePostgresConnection`）一旦做了，QC 就只剩
    API 這條路。定位沒定案之前，④ 不能把 QC 當成「反正要退役」而略過。
- [x] **查詢分頁被 header 蓋住（2026-08-25 修掉）** —— `queryHeader.BringToFront()` 讓 header
  反而蓋掉分頁列。WinForms 停靠照 z-order 由後往前處理（索引最大的先停靠），`BringToFront`
  把 header 移到索引 0 變成最後才停靠，而 `Dock=Fill` 的 `tableLayoutQuery` 已經先把整個區域
  吃光，header 只好疊上去。四個分頁（檢查查詢／查詢取回／影像傳送／品質管制）一直都有被建出來、
  `Visible=true`、尺寸也正常——**只是整個被蓋住**，所以先前一直以為是改版時漏了 QC 頁面沒加回來。
  教訓：「功能不見了」先量座標再下結論；`pages=4` 與螢幕座標重疊這兩個數字一出來就結案了。
- [ ] **MR 動態指示（DynamicView）改用 DICOM 標籤判斷，不要只看幾何** —— 2026-08-25 討論。
  現況（`ImageControl.cs` 的 `backgroundWorkerUpdateDynimacView_DoWork`）：只對 `Modality == "MR"`，
  等整個序列下載完，拿目前這張的 `ImagePlane` 掃過全序列，**平行（0.5 度容差）且
  `PositionPatientCenterOfImage` 相同**就算同一位置；符合的張數＝重複次數，
  自己在其中的序號＝第幾次（靠 SOP UID 比對）。`> 1` 才畫指示點。
  觸發點是 `LoadImage`，不是點擊——按左右鍵換影像時跟著重算，所以看起來像按鍵觸發。
  - **弱點①：分不出維度是什麼。** 雙回波（in/opposed phase、Dixon）、動態分期、真的重複掃，
    在畫面上長得一模一樣都是「2 個點」，但臨床意義完全不同。
    2026-08-25 現場遇到「Instance 1,2 同平面、3,4 同平面」，那個形狀比較像**雙回波**而不是重複。
  - **弱點②：張數不一致時指示點整個消失。** 計數是「目前這張所在的切面被掃過幾次」，
    不是整個序列的次數。第一輪 10 張、第二輪 8 張的話，只有第一輪才有的那 2 張算出來是 1，
    因為 `> 1` 才畫，所以捲到那裡指示點會不見（而不是顯示「這裡只有一次」）。
  - **弱點③：位置比對幾乎沒有容差。** 平行判斷有 0.5 度容差，但位置走 `Vector3D` 的 `==`
    → `ValueComparer.AreEqual` 是 **ULP 容差**，等同於「幾乎完全相等」。第二輪的
    `ImagePositionPatient` 只要有一點點差（病人動了、機器重算定位），整組就配不起來。
  - **改法**：先看標籤、沒有才退回幾何——`TemporalPositionIdentifier (0020,0100)`（動態第幾期）
    → `EchoNumbers (0018,0086)`（第幾個回波）→ `AcquisitionNumber (0020,0012)` → 幾何。
    這樣不只序號正確，畫面還能標出「第 2 期」或「第 2 回波」；用標籤分組也沒有「張數不一致
    就消失」的問題。**動工前要先撈一批現場 MR 看這幾個標籤實際填了什麼**（有些機器不填）。
  - 排序不是問題：`ObjectElements` 照 `get_study_elements` 的 `ORDER BY instance_number` 排，
    「先掃完一輪再第二輪」與「同位置連續兩張」兩種排列，算出來的序號都有意義。
    DICOM 本來就沒規定 Instance Number 的排列語意，兩種都合標準。
- [ ] **`backgroundWorkerUpdateDynimacView_DoWork` 的 `while (true)` 是空轉忙碌等待** ——
  等 `DownloadCount == ObjectElements.Count` 的迴圈裡沒有任何 sleep，序列下載完成前
  整條執行緒 100% 吃一顆核心。更糟的是**下載永遠完不成就無限空轉**（失敗、或使用者換序列
  讓條件不再成立），而外層有 `if (!IsBusy)` 守衛，那個 ImageControl 之後就再也不會更新。
  巢狀 if 內也沒有出口，`seriesElement`／`objectElement` 變 null 一樣停不下來。
  快網路 + 小序列看不出來，**慢網路 + 大序列 MR 正是最容易發作的組合**。
- [ ] **`HD.WebApi` 的重試策略對 4xx/5xx 也照重試 5 次** —— `MaxRetryCount = 5`、
  `RetryDelaySec = 2`，而 `!IsSuccessStatusCode` 是直接丟例外進重試迴圈。所以一個
  伺服器端 30ms 就失敗的請求，客戶端要耗掉約 8 秒（5 次嘗試、4 段等待）。
  2026-08-25 .163 實測：Mammo 的 hanging 查詢失敗時，切過去整個卡住好幾秒，
  **現場會被感知成「系統很慢」而不是「有錯誤」，反而更難排查**。
  合理的分法：連線層失敗（連不上／逾時）才重試；4xx 完全不重試；5xx 最多一次。
  **這會動到 `HD.WebApi` 的共用行為，舊系統那條路也吃得到**，所以要一起評估。
- [ ] **縮圖預熱（Viewer 換 DicomWeb 後端之後的冷啟成本）** —— 2026-08-25 實測：300 張的縮圖列，
  舊系統（預轉 JPEG）每次都是 8.8s，新系統冷啟 22.1s、**快取命中只要 1.6s**。也就是
  「第一次慢 2.5 倍、之後快 5.5 倍」。已把 `PreviewJpegLoader.MaxParallel` 4→8（+12%），
  但**並行度不是主要槓桿**（客戶端並行會乘上醫師人數壓到伺服器），真正的槓桿是快取命中。
  - 要壓下冷啟只能靠**預熱**：進檔或 STUDY_CLOSE 時先渲染一批縮圖。這與 REQ-007
    「停掉進檔預轉 JPEG」方向相反，要一起想——差別在於預熱的是**小縮圖**（4.5KB）
    而不是整張 JPEG（45KB），成本低兩個數量級。
  - **`RenderedImageCache` 是行程內記憶體快取，每次部署更新就清空**，所以每次更新後
    第一批開檢查的醫師都會遇到冷啟。要根治得做成落地快取。
- [ ] **`viewer_station.search_study` 沒有院區過濾**（2026-08-25 發現）：`query_dicom`／C-MOVE／
  QIDO/WADO/DELETE/UPS／MWL／匯出都補上了，但**醫師在 Viewer 上看到的檢查清單走這支、完全繞過**。
  它已經收到 `AETitle`，掛鉤與 `query_worklist` 一樣現成，可獨立於 Viewer 主線隨時做。
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
