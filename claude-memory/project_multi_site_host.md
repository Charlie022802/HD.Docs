---
name: project_multi_site_host
description: 多院區主機:一台 PACS/一個 DB 承載多院區(SITE_CODE);涵蓋「多家動物醫院共用總機」與「一家醫院的多分院」兩種形狀,差別靠 PATIENT_ID_SHARED 設定
metadata: 
  node_type: memory
  type: project
  originSessionId: 13e6b6ed-984d-4c27-aed8-2170077bfa02
  modified: 2026-08-17T16:49:22.126Z
---

**🔑 階段一完成並套用(2026-08-18)。** `.191` DB 已是 **v2.0.31**(版本注記仍 2.0.30,因未結案)。

- **1a 承載結構**:`SITE` 表(`SITE_CODE`/`SITE_NAME`/`ENABLE`/`CUTOVER_DATE`/`PATIENT_ID_SHARED`)+ `RC_STUDY.SITE_CODE`(**帶外鍵**,只允許已登記代碼或 NULL)+ 索引。
- **1b 進檔蓋章**:四個 `RC_STUDY` INSERT 點全處理——`store_dicom`(C-STORE)、`insert_dicom_info`(**PROCEDURE 不是 FUNCTION**,腳本寫死 CREATE FUNCTION 被 42723 擋過)、`study_split`、`viewer_station.qc`(後兩者繼承來源 study)。
- **做法**:那四支共 1253 行,**用腳本從 dump 抽出後程式化套用 16 處修改**(scratchpad/gen31.py),每處 assert「只能匹配一次」,不手抄。日後 dump 更新重跑即知哪些錨點失效。
- **實測**:BEGIN…ROLLBACK 連兩次(物件與 proc 的 `prosrc` 0→4→4→0);套用後 STOW 三條路徑(全新 UID 200、既有 UID 409 是 DicomWeb 擋重複**走不到 proc 既存分支**、同 study 加新影像 200 才走得到)。

**進檔四種情況(定案)**:無 siteCode→收下留 NULL;啟用→蓋章;**停用→拒收**;查無此碼→收下+WARNING。
- **停用必須拒收**是關鍵:退場三段式第一段就是停用以「讓進檔停止」;若收下並當未歸戶,那些資料**不會被 `delete_site_studies` 掃到**(它按院區刪),退場後留下無主的該院影像。
- **既存 study 護欄不受 `allow_duplicate` 影響**——「屬於誰」與「要不要覆寫欄位」是兩件事。跨院區同 UID `RAISE EXCEPTION`,取代會弄壞 UID 解析的複合唯一鍵。

**院區只停用不刪除**:`SITE` 沒有刪除動作。DB 已擋一半(有 study 就刪不掉),縫在「還沒 study 但已被 AE 引用」(`siteCode` 在 jsonb 無外鍵)。**管理 UI = CRU 不含 D,且 AE 的 siteCode 必須下拉不可自由輸入**——這兩條是讓「代碼不存在」變罕見的前提。

**出口過濾(階段二,已定案)**:**`SITE` 表空的＝功能未啟用＝完全不過濾**(單一醫院零設定、行為與導入前逐字相同;用「資料存在」當開關才不會與旗標矛盾)。啟用後:有 siteCode=X 只看 `SITE_CODE = X`、**看不到未歸戶**(使用者確認導入方式是「先全部轉置完才開放給醫師」,故可選嚴格版);無 siteCode 只看未歸戶。實作要在連線/請求層取一次總開關,別每查詢都數 `SITE`。

**🔑 1b 全部完成並端到端實測(2026-08-19)。** `NetworkConfig` 加了 `siteCode`;用 fo-dicom 送**真的 C-STORE** 到 `.191:2020`(called `HDPACS`/calling `TESTSCU`)逐一驗五種情況,全部符合設計:未設定→NULL;`HQ`→蓋上;既存未歸戶→**補蓋**;`NOSUCH`→收下留 NULL;`OLDSITE`(停用)→**拒收**;`BRANCH` 重送 HQ 的 study→**拒收且物件數不變**。錯誤訊息在 `RC_ERROR_DATASET` 逐字可見。

兩件先前只是假設、現已證實:**`siteCode` 取自 calling AE**(`aeRef: calling_ae_ref`)不是 called AE;**掛院區真的零 schema 變更**——`get_ae_config` 的 `includeMain` 只是把 `AE_MAIN` 五欄併進結果、**不是設定繼承**,且 `NetworkConfig` 在 C# 全程唯讀(只有 `GetConfig` 反序列化,沒有任何地方序列化寫回),所以不存在「C# 少一個屬性→存檔洗掉 siteCode」。

**⚠️ 驗證抓到的問題:政策性拒收回的是 `Warning B000 (Coercion of Data Elements)`,DICOM 語意屬警告而非失敗——儀器會認定已存檔而可能刪掉本機那份。** 成因是 `DicomStoreProcess.FileIO.cs` 的 `HandleStorageError` 把**任何**儲存例外一律映射成 B000(既有行為,非多院區引入)。影響最大的正是退場情境(停用院區以停止進檔,儀器卻以為送成功)。**尚未修**,因為會動到所有儲存錯誤的回報。列入待議。

**`.191` 遺留的驗證素材**:`SITE` 三筆(`HQ`/`BRANCH` 啟用、`OLDSITE` 停用)、study 67(未歸戶)/68/69(`HQ`)/70(未歸戶)。**AE 的 `siteCode` 已還原移除**,所以後續 C-STORE 測試不會被意外蓋章。注意 `SITE` 表有資料即代表「多院區功能啟用」(階段二出口過濾的總開關),要回到停用狀態得先清掉那三筆(需先處理 68/69 的外鍵)。

**DICOM 補位坑**:C-STORE 進來的 `PATIENT_ID` 會被補到偶數長度(`SITE-TEST-002 ` 尾有空格),用 `= 'SITE-TEST-002'` 查會落空;STOW(JSON)不補。查測試資料用 `btrim()`。

**🔑 重新定框(2026-08-18 使用者更正):這不是「動物醫院總主機」,是「多院區主機」。** 動物醫院只是剛好形狀類似——**同一家醫院的不同分院也是同樣需求**。正本改名 `docs/multi-site-design.md`,識別字 `SITE_CODE` → **`SITE_CODE`**(表 `SITE`、C# `siteCode`、proc `delete_site_studies`/`create_site_export_jobs`),「院別」一律稱「院區」。

這個定框揭露一項**會因場景反轉的實質決策**:**病歷號作用域**。原本寫「跨院病歷號相撞不動約束,靠查詢紀律必帶院區範圍」——動物醫院成立(各診所獨立編號,`003867` 在 A 院與 B 院是不同病患),但**分院通常共用一套病歷號**,同號就是同一人,而且分院醫師看得到病患在總院拍的片往往是臨床需要。同一條規則兩種場景要求相反。

**定案:`SITE.PATIENT_ID_SHARED` 設定,預設 `false`。** 預設取安全那邊是刻意的——設錯方向後果不對稱:該隔離卻共用=跨院區外洩(不可逆、可能要通報);該共用卻隔離=醫師看不到舊片(會被抱怨但資料還在,改設定就好)。**旗標只影響出口**,進檔蓋章/跨院區同 UID 護欄/QC 複製繼承兩種模式完全一樣→一套程式碼兩種場景都能裝,日後改變也只是改設定不必搬資料。混合部署(同機同時有獨立與共用院區群)需要 `SITE.GROUP_CODE` 群組概念,目前無需求先不做。

文件已拆兩層:通用機制在前,**動物醫院特有的(Proxy 退役、CallingAE 尾 6 碼 UserUUID 當歸屬 key、`hcs/<院號>` worklist 反代、50+ 台舊 VM)集中在文末「導入案例」**。存量資料那節的前提是「資料分散在多台舊主機」,分院情境往往本來就在同一套系統裡、只需回填 SITE_CODE。

**🔑 設計已完備、待開工(2026-08-18):六項開工前決策全部定案。** 正本 `docs/multi-site-design.md` 狀態已改。最後兩項的定案:

- **決策4 整院匯出／單院退場／誤刪防護 → 階段二就做成正式工具**(不留到需要時寫一次性腳本;真正需要的時機有時間壓力,那時對承載 50 家的共用 DB 現寫破壞性 SQL 最危險)。現況盤點:**目前完全沒有機制**——`get_next_delete_study` 是快取清理(`HD.CacheDelete`)不是退場,`RC_STUDY` 外鍵**沒有 CASCADE**。三個非顯而易見點:①**不從 Export 公開 API 開 `siteCode`**(否則任何 `export.write` 金鑰能一次拉走全院)→走管理主控台+專用 proc ②**必須依 `STUDY_DATE` 按月分片**(`PACKAGE_JOB_DISC` 是 kiosk 專屬 1:1 表、只放 `EST_DISCS`/取件/付費,**不是分片機制**,而且新 proc 還沒人寫它)③驗證是匯出的一部分。退場三段式不可換序:`ENABLE=false`→匯出+驗證→刪除;**刪除只允許經 `delete_hospital_studies(hospital_code, expected_study_count)`**,帶預期筆數當二次確認、不符就整批不動。RLS 同時是誤刪第二道,故與出口過濾同階段。
- **決策6 存量資料 → 分界日+按需重送**。`HOSPITAL` 加 per-hospital `CUTOVER_DATE`(50+ 家不會同天切)。之後進總機;之前留舊院 VM 唯讀,病患回診才用 C-STORE 重送單筆。避開 50+ 台大遷移,且重送自動走 `store_dicom` 蓋章、與「歸屬在進檔當下凍結」一致(DB 層搬遷會繞過蓋章,風險最高故不採)。**可行前提=重送兩次不會產生重複資料**(同院同 UID 走既存分支、跨院由護欄擋)——改 `store_dicom` 時不能破壞這點。舊 VM 退役條件:重送需求趨近零+已完成整院匯出並驗證。
- **注意 dump 已落後**:設計基準是 `HDPACS_20260811`,但 DB 已推進到 v2.0.30,**寫 migration 前要重拉 dump 再核對那四個 INSERT 點的行號**。

**架構重定(2026-08-11 三輪,最新有效):Proxy 整個退役**——儀器 C-STORE **直打總機新版 PACS**(開 port 對外),STOW 轉發鏈(StowForwarder `7a2e53e`)與 UserUUID 歸屬設計**作廢**(WorklistSCP 優化 `bdce2a7` 也隨 proxy 退役,但物種改寫邏輯 worklist 案要接手)。WorklistInsert 擱置(同事討論中)。**使用者本輪唯一核心=SITE_CODE 設計**。盤點結論:proxy 特殊流程幾乎全由新 PACS 現成覆蓋(AE_MAIN 登記+NetworkConfig per-AE 權限/host 綁定/視訊 TS/健檢 AE;進檔改寫=proxy DicomInputRuleList 從未實作,新 PACS 有真的 per-AE dicomImportModified+dicomTagFilter 於 DicomStoreProcess);缺口只剩院別歸屬。**SITE_CODE 設計正本=docs/multi-site-design.md**(2026-08-11 依 HDPACS_20260811 schema 出完整草案):HOSPITAL 表+RC_STUDY 加 SITE_CODE 欄(UID UNIQUE 不動、不做複合)+AE_CONFIG NETWORK/DICOM jsonb 加 siteCode(get_ae_config 透傳,零 schema 改動)+**兩條進檔路蓋章**(store_dicom=C-STORE、insert_dicom_info=STOW,各自已解析 calling_ae_ref)+QC split 兩處複製繼承欄位+**跨院同 UID 護欄=RAISE EXCEPTION 不靜默合併**(未歸戶 NULL 補蓋例外)+三階段施工(蓋章→出口過濾+RLS→管理 UI)。跨院病歷號=查詢紀律非約束(無病患主表)。待議:對外 port 網路安全(NAT 下 host 綁定失效→防火牆/VPN)。**慣例:schema 正本=Database/ 最新日期 dump(現 20260811,自 .191 拉),要動 DB 前過時就請使用者重拉**。

---(以下為歷史脈絡,拓撲已被上方取代)---

**動物醫院總主機計畫(2026-08-10 使用者宣告方向):**

- **.191 架設完成後複製這台 VM → 動物醫院總主機**;之後**所有動物醫院的影像都匯入這台**。
- **新版 DicomWebViewer 依 HospitalName 做控管顯示**(各院只看得到自己的)。
- **舊制=一家動物醫院一個 DB;新制=集中單 DB 靠院別區隔**。
- 相關既有件:[[project_hd_animal_proxy]](各院端的上傳代理,.222 已穩定)、DicomWeb Domain 層已有 TenantId/ICurrentTenant/ApiKey.TenantId 骨架——但**生產查詢走 HdPacs*(RC_* 表)那條,RC_* 無租戶欄位**,見 [[project_dicomweb_impl_split]]。

**Proxy STOW-RS 轉發模組建置完成(2026-08-10,HD.Animal `7a2e53e`,本機 mock+斷線補送驗證通過)**:新服務 `HD.Animal.Proxy.StowForwarder`(Worker 模式同 CStoreSCP;proxyConfig.json 的 StowForwarder 區塊,預設 Enabled=false)。機制:掃 `{CacheLocation}/CacheTemp`(CStoreSCP 落地目錄=**天然持久佇列**,檔案按 UserUUID 分桶——AE 尾 6 碼,未來院別歸屬現成鉤子)→DICM 前導檢查→單檔 STOW `POST {TargetUrl}/dicomweb/studies`(multipart/related+X-API-Key+X-Calling-AE-Title)→2xx 移 CacheSent(SentRetentionDays 自動清)/永久 4xx 移 CacheFailed/網路/5xx/401/403 原地退避重試(2^n 上限 300s)。AllowUntrustedTls 供自簽過渡。**待真機試跑**:總機發金鑰(dicomweb.write)+AE_MAIN 登記+Enabled=true;WebController 設定頁補區塊(followup)。**拓撲修正(2026-08-10 使用者澄清):Proxy=總機側集中接收器,全部動物醫院的儀器都打進這一台**(「一院一台」指舊制 PACS DB,不是 proxy)。因此**院別歸屬不能靠一院一金鑰**(單 proxy 單金鑰)→歸屬正本=**每檔的 CallingAE 尾 6 碼 UserUUID**(落地已按它分桶)。轉發模組待補:**逐檔依 UserUUID 桶帶識別**(如 X-Calling-AE-Title=該 UserUUID 對應 AE,總機 AE_MAIN 逐院登記;目錄第一層即 UserUUID,小改)。設計決策①的核心=**UserUUID→院別代碼對照表放哪/誰維護**。

**前置②HTTPS 已完成(2026-08-10,SSO 整圈驗證)**:.199 nginx TLS 終結(443)+自簽憑證(SAN 含 hddicomweb/IP,setup-https.sh 一鍵)+app UseForwardedHeaders(X-Forwarded-Proto,OIDC redirect_uri 才正確);**兩顆 proxy buffer 雷**:自家 nginx 4k 撐不住 SaveTokens 登入 cookie(~10KB)→回呼 502(直連正常/走反代必死=特徵),sso openresty 同款(PAR 502 同根因)——皆已加大(詳 docs/systems/identity.md 坑⑨)。名稱=hddicomweb(hosts/未來內部 DNS)。

**端到端流程定調(2026-08-10):** 儀器--C-STORE-->院內 HD.Animal.Proxy--STOW-RS(HTTPS+X-API-Key,一院一金鑰)-->總機 DicomWeb-->HDPACS DB/NAS;Viewer 依登入者院別過濾查詢。**要補的工**:①Proxy 的 STOW-RS 轉發模組(帶 X-Calling-AE-Title,含離線緩衝+復線重送)②**DicomWeb HTTPS 變前置必做**③金鑰綁院別代碼+AE_MAIN 登記各院 AE ④STOW 進檔依金鑰院別寫 SITE_CODE+病患複合身分(寫 DB 不改原始檔,合「原始檔不可變」)⑤QIDO/WADO 強制過濾+RLS ⑥新版 Viewer 院別顯示。

**討論進度(2026-08-10 首輪):** ②server 端強制過濾=**定案必做**;⑤定案**用安裝檔全新裝、不複製 VM**(hdctl+環境包一條龍);④DB 架構使用者傾向集中單 DB(多 DB 維護/更新麻煩、設定串接有問題),我方建議=**單 HDPACS DB+SITE_CODE 欄位+雙護欄(應用層 WHERE+PostgreSQL RLS)**,關鍵坑=跨院病歷號會撞→IssuerOfPatientID(0010,0021)=院別代碼複合身分、儲存路徑把院別編進目錄層(單院匯出/退場容易);①③⑥續議。

**決策①定案(2026-08-10 二輪討論):使用者鐵則=現場 AE Title 一律不動**(改 AE 要跑現場)。因此:**歸屬 key = CallingAE 尾 6 碼 UserUUID(沿用舊制慣例,不改完整 AE)**;正本=總機 HDPACS DB 新對照表(UserUUID→SITE_CODE),**初始資料=從現有 Proxy 設定檔(AE+UUidList)一次性匯入**,日後新院走管理 UI 登記;Proxy 本身不需要對照表(逐檔帶 CallingAE,歸屬判定在總機 STOW 進檔端查表蓋 SITE_CODE)。表建議:新增 HOSPITAL 表(CODE+顯示名+狀態)、AE 登記沿用 AE_MAIN+加 SITE_CODE 欄(實體欄位才好索引/RLS,不塞 AE_CONFIG jsonb)。**未定小點**:未歸戶進檔處理(建議收下+隔離+UI 認領,不拒收)。**worklist 全鏈查明(2026-08-11 反代設定實證定案)**:讀=儀器 C-FIND→AnimalDicomProxy WorklistSCP(純轉發依 UserUUID、保留 CallingAE;**已優化 HD.Animal `bdce2a7`**:串流+上游失敗回 ProcessingFailure+接上逾時;物種狗→Feline/貓→Canine 對調待確認)→各院 hd-worklist-server。寫=**NxVet→www.horoview.vet/hcs/<院號>/mwl(horoviewReverseProxy nginx,網際網路曝露、被 bot 掃描)→各院 VM :6060/Api/v2.0/MwlInsert(hd-pacs-administration-tool,Python3.7 Flask 管理 API,源碼 C:\Users\yang\Downloads\hd-pacs-administration-tool;零認證+CORS *+SQL 字串拼接注入洞+postgres 密碼硬編碼)→`CALL insert_worklist`→該院 DB**。舊制規模=一院一 VM 50+ 台(192.168.68.x),/hcs/<n>/dcmweb→各院 :9000 Viewer。MSI 檔匯入(horoview6804 有跑)=另一條平行路,最終同歸 insert_worklist;動物醫院主流=MwlInsert。VetMwl 拉取佇列僅 /hcs/1 一家特規(proc 只在舊院 DB)。**新制接法定調:診所端零改動**——院別身分本來就在 URL,反代 /hcs/<n>/mwl 全改指總機相容端點+nginx 注入院別 header+內部金鑰(順補認證/注入洞);院別對照雙 key(儀器線=UserUUID、worklist 線=hcs 院號)同表對 SITE_CODE;新版 DB 已有 insert_worklist proc 家族(insert_worklist/from_msi/from_dicomdataset——後者吃 ae_title=歸屬蓋章先例)。**反代 bug:/hcs/62/mwl 指 .62(=hcs/61 主機),62 號單進錯院→待同事確認修**。院機 web-server(Node)只做 Viewer 後端,與 worklist 無關。

**開工前要定的設計決策(2026-08-10 初步評估):**
1. ~~院別歸屬正本~~ → **已定案,見上**。
2. **控管做在 server 端**:QIDO/WADO/全出口強制 WHERE 院別(由金鑰/登入者解析),Viewer 只是呈現——純 UI 過濾=跨院外洩。
3. HospitalName 用**穩定代碼**當 key、顯示名另掛(改名不動歷史)。
4. 一院一 DB→單 DB 的取捨:失去硬隔離,要想好「單院退場/整院匯出/誤刪範圍」。
5. VM 複製 checklist:IP/hostname/AE Title/金鑰/Keycloak redirect URIs/logplatform Source 等機器身分要改;hdctl 佈局會整套帶過去(這正是 hdctl 的紅利)。
6. 舊各院 DB 的**存量資料匯入**路徑(migration 工具/走 Proxy 重送?)。
