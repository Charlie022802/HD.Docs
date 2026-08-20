---
name: project_ups_rs
description: UPS-RS(DICOMweb 工作清單)實作—放在 HD.Pacs.DicomWeb、獨立 UPS_WORKITEM 表、phase 1 已建
metadata: 
  node_type: memory
  type: project
  originSessionId: 4955439c-e319-4882-9ff7-dc4be5c80843
  modified: 2026-07-31T04:05:49.343Z
---

決策(2026-07-30):在 **HD.Pacs.DicomWeb** 內實作 UPS-RS(Unified Procedure Step, PS3.18),不另開專案、共用授權/admin/部署/docs。UPS = MWL C-FIND(查)+ MPPS(改狀態)+ 建立/取消/訂閱 的統一 REST 超集。既有 **HD.WorklistServer**(HD.Net10 主程式,DIMSE SCP:C-FIND `query_worklist` + MPPS `update_procedure_step_status`)角色不變。

**目標=同一份 worklist(UPS 建的單 modality 要能用 MWL C-FIND 抓到)**,但**橋接延後**;phase 1 先做 UPS 服務本體。資料走 **獨立 `UPS_WORKITEM` 表**(不硬塞 HDM;HDM 是 Visit→ServiceRequest→Procedure→ProcedureStep 正規化階層,UPS 狀態機/transaction UID 塞不進去)。schema 留 `public`(DicomWeb 自己的 HD_API_KEY/HD_USER_AUDIT_LOG 也在 public,前綴區分)。

**Phase 1 已完成(2026-07-30:實作+部署.199+生產實測全通過+commit `a6fe2bc`)**。實測:建立→取回SCHEDULED→IN PROGRESS(帶txn)200→驗證state=IN PROGRESS且不外洩00081195→錯txn完成400→對txn完成200→非法轉換COMPLETED→IN PROGRESS 409。細節:
- DB:`db/migrations/004_create_ups_workitem.sql`(UPS_WORKITEM:SOP_INSTANCE_UID/STATE/TRANSACTION_UID/PATIENT_*/SCHEDULED_*/SERVICE_REQUEST_REF預留/DATASET jsonb)。**使用者自己在 pgAdmin(.234)跑**(慣例:DB 變更我只給 SQL、不執行)。
- Domain:`Ups/UpsWorkitem.cs`(UpsStates 狀態機 SCHEDULED→IN PROGRESS→COMPLETED/CANCELED + UpsTags);Constants 加 Scopes.WorkitemRead/Write、AuditActions.Ups*、AuditResources.Workitem。
- Application:`Services/IUpsService.cs`(+ UpsOutcome/UpsResult)。
- Infrastructure:`DicomWeb/HdPacsUpsService.cs`(Dapper;STATE 為狀態真相並同步進 DATASET;TRANSACTION_UID 只存欄不進 DATASET;改狀態/修改用 FOR UPDATE+交易)。註冊在 Infrastructure/ServiceCollectionExtensions。
- Api:`Endpoints/UpsEndpoints.cs`,group `/workitems`:POST(建)、GET(搜)、GET/{uid}(取)、PUT/{uid}/state(改狀態)、POST/{uid}(改屬性)、POST/{uid}/cancelrequest。授權 WorkitemRead/WorkitemWrite(Program.cs 加政策 + MapUpsEndpoints)。
- UI:ApiKeys.razor scope 清單加 workitem.read/write(工作清單查詢/寫入,write 走綠 badge)。

**模組開關(降風險,2026-07-30)**:為避免 UPS 跟取像同 process 連坐(部署重啟/崩潰/資源),Program.cs 加 `Modules` config(GetSection("Modules").Get<string[]>();未設/空=全開,向後相容)。值:dicomweb(QIDO/WADO/STOW/Import/Delete)、ups(/workitems)、admin(管理端點+Blazor UI+登入);health/conformance 一律掛。可拆兩個 systemd unit 跑同一份 binary:取像+admin(5080, Modules__0=dicomweb Modules__1=admin)、UPS(5081, Modules__0=ups),獨立重啟互不連坐。說明在 `deploy/modules-split.md`;appsettings.json 有 Modules 註解。

**Phase 2a 完成(2026-07-30,commit `2ea0543`,生產實測過)**:UPS 建單時同一交易映射屬性 → `CALL public.insert_worklist(template)` 建 HDM 訂單(SERVICE_REQUEST→PROCEDURE→PROCEDURE_STEP),modality MWL C-FIND 就抓得到(query_worklist 不動)。回填 UPS_WORKITEM.SERVICE_REQUEST_REF。踩雷:①此庫 search_path 為空、insert_worklist 內部有 unqualified 參照 → 交易內 `SET LOCAL search_path TO public`;②`AUTO_ACCESSION_NUMBER_COUNTER` 生產庫沒有(且 .234 一度是舊版 dump,後由使用者更新;該序列是 auto-worklist 功能殘留)→ 改用 UPS 自有序列 `UPS_WORKITEM_WORKITEM_REF_seq` 產 accession(UPS+序號)。映射照 DICOM 慣例(Modality 0008,0060 無則 OT;procedureCode/desc 取 Scheduled Workitem Code Seq 0040,4018);橋接失敗整筆回滾。**注意:每建一個 UPS 單就會在正式 HDM worklist 產一筆訂單、modality 會看到,測試後要清。**

**Phase 2b(A)完成(2026-07-30,commit `8ce96e3`,實測過)**:UPS ChangeState/cancelrequest 於同一交易鏡像狀態進關聯 HDM_PROCEDURE_STEP(靠 SERVICE_REQUEST_REF)。對映 IN PROGRESS→IN PROGRESS、COMPLETED→COMPLETED、CANCELED→DISCONTINUED(取消另標 HDM_SERVICE_REQUEST.STUDY_STATUS_ID=CANCELED);IN PROGRESS/COMPLETED 不動 STUDY_STATUS_ID。全 public. 全限定、不碰 MPPS 路徑。實測 UPS→COMPLETED,HDM step 同步 COMPLETED。

**2b(B) MPPS→UPS:決定不做(2026-07-30)**。原因:完成回報一律走 UPS ChangeState(方向 A 已把狀態鏡像進 HDM),modality/client 走 UPS-RS 不走 MPPS,所以沒有「外部改 HDM」需要反映回 UPS。MPPS 走 HD.WorklistServer(DIMSE，`update_procedure_step_status`)目前無人在用。→ phase 2 視為完成。單一狀態真相在 UPS 側、單向橋到 HDM。若未來 modality 改走 MPPS 回報,再重啟 2b(B)(候選 B2 讀取衍生零風險 / B1 trigger)。

**Update 病患鏡像到 HDM(2026-07-31,commit `45c8add`,實測過)**:UPS Update(POST /workitems/{uid})成功後把病患基本資訊鏡像到關聯 HDM 訂單(靠 SERVICE_REQUEST_REF),讓 modality MWL C-FIND 看到修正 —— 用途:worklist 病患打錯的修正,不動影像。欄位:PatientID(00100020)→PATIENT_ID、PatientName(00100010)→PATIENT_NAME、生日/性別/其他病歷號/發證單位(00100030/0040/1000/0021)→OTHERS jsonb(PATIENT_BIRTH_DATE/PATIENT_SEX/OTHER_PATIENT_IDS/ISSUER_OF_PATIENT_ID);null 不覆蓋、不動 Accession。`MirrorPatientToHdmAsync`。註:UPS Update 只改 workitem/worklist,不動已擷取影像(那是 PACS coerce 的事,見 [[project_immutable_original_coerce]])。

**Phase 3a 完成(2026-07-31,commit `7327bee`,生產實測過)**:UPS 訂閱 + WebSocket 事件。端點 POST/DELETE `/workitems/{uid}/subscribers/{ae}`(uid 可為特定或 worklist 通用 UID `1.2.840.10008.5.1.4.34.5`=訂全部),訂閱回 websocketUrl;WS 通道 GET `/workitems/subscribers/{ae}`(需 workitem.read)。in-process `UpsEventHub`(Api 層,實作 Application 的 `IUpsEventPublisher`)持連線扇出;建/改/取消時發 UPS State Report(DICOM JSON:0008,0018 + 00001002 EventType=1 + 00741000)。依賴 UPS 單一 process,多副本再上 LISTEN/NOTIFY。新表 UPS_SUBSCRIPTION。Program.cs 加 `UseWebSockets()`。實測(server 無 pip,用 Python 標準庫手寫 WS client):訂 worklist-wide→WS 101→建單→收到 State Report。WS 認證目前只 X-API-Key header(瀏覽器 client ?apikey= 待補)。

**Phase 3b 完成(2026-07-31,commit `c69491b`,生產實測過)**:①**Filtered 訂閱**:訂 filtered worklist 通用 UID `1.2.840.10008.5.1.4.34.5.1` + query 帶比對條件(keyword 或 8 碼 hex),只收符合的 workitem 事件。支援 key:ProcedureStepState(00741000)/ScheduledStationAETitle(00400001)/Modality(00080060)/PatientID(00100020)/ScheduledProcedureStepStartDateTime(00404005 可範圍),未支援 key 不擋;比對在 publish 時 C# 做(載 workitem 屬性比 MATCH_KEYS)。新欄位 UPS_SUBSCRIPTION.MATCH_KEYS jsonb(migration 006)。②**Cancel Requested 事件(Event Type 2)**:IN PROGRESS 的單 cancelrequest→發事件通知 performer(不強制改狀態)。事件推送重構為 PublishEventAsync(eventType,state?)+ResolveSubscribersAsync(直接訂+worklist-wide+filtered符合者)。實測:filtered Modality=CT→建CT收到/建MR不收;IN PROGRESS cancelrequest→收到 type 2。**延後**:Progress Report 事件、suspend、deletion lock 強制(無刪除端點無對象)。

**DB 檔整理(2026-07-31)**:新增 `db/init_dicomweb.sql`(一鍵建四表 + 種既有金鑰 SHA-256 hash,idempotent);刪 hd-pacs_data.sql(921MB)/hd-pacs_schema.sql/create_hd_user_audit.sql/dicomweb_app_tables.sql/files.zip。db/ 現 = init_dicomweb.sql + migrations/(001-005)+ functions/。全新環境跑 init 即可。金鑰 KEY_HASH 是 SHA-256(非明文)故可入 git。

**仍待辦**:phase 3b(上述);[[project_immutable_original_coerce]] 的 WADO 其他出口疊合。相關:[[project_dicomweb_impl_split]] [[project_dicomweb_deploy]] [[project_immutable_original_coerce]]
