# 多院區主機設計(SITE_CODE)

狀態:**設計已完備,待開工**(2026-08-18)。開工前的設計決策全部定案:歸屬正本、server 端強制過濾、穩定代碼當 key、病歷號作用域、整個院區匯出／退場／誤刪防護、存量資料路徑。原「複製 .191 VM」已作廢,改以安裝檔全新裝。

Schema 基準:`Database/HDPACS_20260811.sql`(自 .191 拉,已核對 `store_dicom`/`get_ae_config`/`RC_STUDY` 與 20260720 版一致)。**注意:該 dump 之後 DB 已推進到 v2.0.30(export 四張表等),真正要寫 migration 前請重拉一份 dump 再核對這四個 INSERT 點的行號。**

## 這份設計在解什麼

**一台 PACS 主機、一個 HDPACS DB,承載多個彼此獨立的院區。** 資料進來蓋 `SITE_CODE`、出去依院區過濾。

「院區」是刻意選的中性詞,因為它要涵蓋兩種形狀不同的部署:

| 場景 | 一個院區是什麼 | 病歷號 | 隔離強度 |
|---|---|---|---|
| **多家動物醫院共用總機** | 一家診所 | 各家獨立編號,`003867` 在 A 院與 B 院是不同病患 | 嚴格——跨院區看到彼此的資料就是外洩 |
| **一家醫院的多個分院** | 一個分院 | **全院共用一套**,`003867` 在總院與分院是同一人 | 寬鬆——分院醫師看得到病患在總院拍的片,往往是臨床需要 |

這兩種對「出口要不要強制帶院區」的要求是**相反的**,所以那不是架構決定,而是部署設定(見「病歷號作用域」)。

至於**動物醫院**那條線的具體導入(Proxy 退役、儀器 C-STORE 直打、worklist 反代改指)寫在文件末的導入案例,不要跟通用機制混讀。

## 定案原則

1. **`STUDY_INSTANCE_UID` 的 UNIQUE 不動**(單欄、全域唯一)。院區不參與唯一性——UID 依 DICOM 標準本就全球唯一,複合 UNIQUE 反而弄壞 QIDO/WADO/C-MOVE 的 UID 解析。
2. **歸屬在進檔當下凍結成實體欄**,不靠 AE_REF join 推導——AE 日後改掛院區不追溯改寫歷史;RLS/查詢不用 join。
3. 病患無主表(病患欄位攤平在 RC_STUDY),**不動 PatientID 的約束**。病歷號是否跨院區共用由設定決定,見下節——約束層面兩種場景都不需要改。
4. 未歸戶(AE 未設院區)照收、SITE_CODE 留 NULL,管理 UI 認領。
5. 儲存路徑**不編院區目錄**,歸屬純靠 DB 欄位(免搬檔、改掛只改 DB)。

## DDL(migration 草案)

```sql
-- 院區登記表
CREATE TABLE public."SITE" (
    "SITE_CODE"          text PRIMARY KEY,
    "SITE_NAME"          text NOT NULL,
    "ENABLE"             boolean NOT NULL DEFAULT true,
    -- 分界日:此日之後的檢查直接進本機,之前的留在原系統按需重送(見「存量資料」)。
    -- per-site 而非全域,因為多個院區不會同一天切換。NULL = 尚未切換。
    "CUTOVER_DATE"       date,
    -- 病歷號是否跨院區共用(見「病歷號作用域」)。false=各院區獨立編號(預設,安全的那邊);
    -- true=全院共用一套,同一個號碼就是同一人,查詢可跨院區。只影響出口,不影響進檔。
    "PATIENT_ID_SHARED"  boolean NOT NULL DEFAULT false,
    "DATE_TIME_CREATED"  timestamptz NOT NULL DEFAULT now(),
    "DATE_TIME_MODIFIED" timestamptz NOT NULL DEFAULT now()
);

-- 歸屬欄(NULL=未歸戶)
ALTER TABLE public."RC_STUDY"
    ADD COLUMN "SITE_CODE" text REFERENCES public."SITE"("SITE_CODE");

CREATE INDEX rc_study_site_code_index
    ON public."RC_STUDY" ("SITE_CODE", "STUDY_REF");
```

SITE_CODE=穩定代碼(改名只動 SITE_NAME)。Series/Object 不加欄(跟著 study)。索引尾掛 STUDY_REF 對齊既有 `accession_number_index` 慣例;若 Viewer 清單以日期為主可改 `("SITE_CODE","STUDY_DATE")`,等查詢模式確定再調。

## 病歷號作用域(2026-08-18 定案:做成可設定)

`SITE.PATIENT_ID_SHARED`(見上方 DDL)決定**病歷號在院區之間是不是同一個人**:

- `false`(預設,動物醫院):各院區獨立編號。`003867` 在 A 院與 B 院是**不同**病患,出口一律強制 `WHERE "SITE_CODE" = …`。
- `true`(分院):全院共用一套病歷號。同一個 `003867` 就是同一人,查詢可跨院區,`SITE_CODE` 退為**標記與統計**用途。

**預設 false 是刻意的**:設錯方向的後果不對稱。該隔離卻共用=跨院區外洩(不可逆、可能要通報);該共用卻隔離=醫師看不到舊片(會被抱怨,但資料還在、改個設定就好)。所以預設取安全的那邊,要放寬得明確設定。

**這個旗標不影響進檔**——蓋章邏輯、跨院區同 UID 護欄、QC 複製繼承在兩種模式下完全一樣,差別只在出口。這樣切的好處是同一套程式碼兩種場景都能裝,而且日後一家醫院從「獨立」改成「共用」只是改設定,不必搬資料。

**混合部署要注意**:同一台主機上同時有「獨立編號的動物醫院」與「共用編號的分院群」時,旗標是 per-site 的,所以共用群組還需要一個群組概念(例如 `SITE.GROUP_CODE`,同組才互通)。目前沒有這種需求,先不做,但欄位命名時預留這個可能——這也是不把旗標塞進系統層 `HD_CONFIG` 的原因。

## AE 掛院區(零 schema 變更)

per-AE 設定正本=`AE_CONFIG`(SECTION='NETWORK', KEY='DICOM')的 VALUE jsonb → **加 key `"siteCode"`**。`get_ae_config` 原樣通吃(jsonb 透傳),DB proc 與 C# 兩邊自動拿得到:

- DB:`store_dicom`/`insert_dicom_info` 讀 `config ->> 'siteCode'`。
- C#:`NetworkConfig`(HD.Net10/HD/Configuration/NetworkConfig.cs)加 `public string siteCode { get; set; }`——進檔蓋章用不到(全在 DB),但出口過濾(C-FIND/C-MOVE 查詢組建)會用。

## 進檔蓋章(兩條進檔路 + QC 複製)

**RC_STUDY 共四個 INSERT 點(20260811 版行號)**:

| 位置 | 路徑 | 處理 |
|---|---|---|
| `store_dicom`(L20956,INSERT L21147) | C-STORE(DicomStoreProcess.InsertToDatabase) | 讀 config 蓋章+護欄 |
| `insert_dicom_info`(L11744,INSERT L11943) | DicomWeb STOW(HdPacs Infrastructure) | 同上(它同樣解析 calling_ae_ref) |
| `study_split`(L22187,INSERT L22233) | QC 拆單(SELECT 複製自來源 study) | 複製欄位清單**加 "SITE_CODE"**(繼承來源) |
| QC Split(study_qc 類,INSERT L27818) | 同上 | 同上 |

蓋章改法(以 store_dicom 為例,insert_dicom_info 同構):

```sql
-- DECLARE 加
hospital_code text;
existing_hospital_code text;

-- 讀 DICOM settings 那段(既有 get_ae_config('NETWORK','DICOM',aeRef))一起讀
--   config ->> 'siteCode' INTO hospital_code

-- Insert Study 分支:欄位清單加 "SITE_CODE"、VALUES 加 hospital_code

-- Study 已存在分支(進 update 前,無論 allow_duplicate):
IF hospital_code IS NOT NULL THEN
    SELECT "SITE_CODE" INTO existing_hospital_code
    FROM "RC_STUDY" WHERE "STUDY_REF" = study_ref;

    IF existing_hospital_code IS NULL THEN
        -- 先前未歸戶、AE 後來掛好院區 → 補蓋
        UPDATE "RC_STUDY" SET "SITE_CODE" = hospital_code WHERE "STUDY_REF" = study_ref;
    ELSIF existing_hospital_code != hospital_code THEN
        -- 跨院同 UID:不靜默合併(真正需要的唯一性保護,取代複合 UNIQUE)
        RAISE EXCEPTION 'Cross-hospital study conflict: % owned by %, incoming from %',
            study_instance_uid, existing_hospital_code, hospital_code;
    END IF;
END IF;
```

RAISE EXCEPTION 的行為:C-STORE 端由 `DicomStoreProcess.HandleStorageError` 接手(檔案進 error 路徑+回非零狀態),不會靜默把 B 院資料併進 A 院;STOW 端回 HTTP 錯誤。

## 出口過濾(第二階段)

過濾條件取決於該院區的 `PATIENT_ID_SHARED`(見上節):`false` → 限本院區;`true` → 限同一共用範圍。

- 儀器 C-FIND/C-MOVE:院區=CallingAE 的 `NetworkConfig.siteCode` → 查詢加 `WHERE "SITE_CODE" = ...`。
- DicomWeb QIDO/WADO(生產走 HdPacs* Dapper 版):依呼叫者(金鑰/登入者)院區過濾。
- Viewer:登入者帳號綁院區。
- **RLS 第二道護欄**:RC_STUDY 上 policy(pgbouncer 環境需 `SET LOCAL`,既知)。細節此階段再展開。

## 整院匯出／單院退場／誤刪防護(2026-08-18 定案)

單一 DB 換來維護與設定串接的簡化,代價是**失去硬隔離**——原本「一院一 DB」時,交還一家醫院的資料就是 dump 一個 DB、清空一家就是 drop 一個 DB,而現在這兩件事都得自己建。現況盤點:`get_next_delete_study` 是**快取清理**(歸檔後釋放磁碟,`HD.CacheDelete` 在跑),不是退場;`RC_STUDY` 的外鍵**沒有 CASCADE**,逐層刪一直由應用層負責。也就是說整院匯出與退場目前**完全沒有機制**。

**決策:在階段二就把它做成正式工具,不留到需要時寫一次性腳本。** 真正需要的時機(醫院解約、要求交還資料)是有時間壓力的,那時對一個承載 50 家醫院的共用 DB 現寫破壞性 SQL,是最不該發生的組合。

**整院匯出** 接剛完成的 `export.PACKAGE_JOB`(選片機制已現成,見 `media-export-redesign.md`),但有三點必須另外處理:

1. **不從 Export 公開 API 開 `siteCode` 條件**。那是管理動作,開在公開契約上等於讓任何持 `export.write` 的金鑰一次拉走全院影像。走管理主控台 + 專用 proc `export.create_site_export_jobs(hospital_code, ...)`。
2. **必須分片**。`PACKAGE_JOB_DISC` 是 kiosk／rimage 專屬(1:1 於 job,只放 `EST_DISCS`／取件／付費),**不是分片機制**,而且新的 proc 還沒有人寫它。整院動輒 TB、`PACKAGE_JOB_ITEM` 會到百萬列等級,單一 job 不可行 → **依 `STUDY_DATE` 按月切成多個 job**,每個 job 可獨立重跑,失敗只需重跑那一片。
3. **驗證是匯出的一部分**。逐 job 比對 `imageCount` 與 `PACKAGE_JOB_ITEM` 的快照筆數,不一致就不算完成。沒有驗證的匯出在退場情境下等於沒有匯出。

**對帳必須是雙向的。** 2026-08-18 的實例顯示 DB 與磁碟會往兩個方向脫節,而且都不會有人察覺:

| 方向 | 實例 | 症狀 |
|---|---|---|
| DB 有列、磁碟沒檔 | 6 筆匯入測試資料 | WADO metadata 回 200 但取原始檔 404 |
| 磁碟有目錄、DB 沒列 | burnTemp 的 44-49 | 佔用空間,沒有任何機制會回收 |

第二種是 `PACKAGE_JOB` 重建時 DB 列消失、產出目錄留在 NAS 上造成的。退場流程若只檢查
「DB 說該有的東西是否都在磁碟上」,就只擋得住第一種;第二種會在整院退場後留下無主的
產出目錄,而那些目錄裡是**該院的病患影像**——退場的目的正是要把它清乾淨。
所以退場的第三段(刪除)完成後,要再對一次「磁碟上是否還有屬於該院的殘留」。

**單院退場三段式**,順序不可換:

| 段 | 動作 | 用意 |
|---|---|---|
| ① | `SITE.ENABLE = false` | 先讓進檔停止,否則邊刪邊進 |
| ② | 整院匯出 + 逐 job 驗證 | 資料先離開,且證明離開得完整 |
| ③ | `delete_site_studies(hospital_code, expected_study_count)` | 才刪 |

**刪除鐵則**:批次刪 `RC_STUDY` **只允許經由 `delete_site_studies`** 這一個入口,而它強制要求傳入**預期筆數**當二次確認——數字與實際不符就 `RAISE EXCEPTION` 全數不動,不做部分刪除。逐層順序 OBJECT → SERIES → STUDY(外鍵無 CASCADE,proc 自己負責);檔案刪除不放在同一交易內(交易裡做檔案 I/O 一旦回滾就對不起來),沿用既有 CacheDelete 的兩段式慣例。

> **這個缺口當天就踩到了（2026-08-18）**：`.191` 有 6 筆匯入冒煙測試資料處於「DB 有列、
> 實體檔案已被清掉、又沒有 nearline 備份」的狀態，`delete_dicom` 的 `deleteDatabase=true`
> 分支因為要求 `IS_NEARLINE_CACHED` 而拒絕它們 —— 完全就是上面說的沒有入口。
> 最後寫在 `db_update_v2.0.30.sql` 的一次性清理段落，而**那段可以直接當
> `delete_site_studies` 的骨架**：逐層刪除順序、「先算預期筆數再比對、不符就整批不動」
> 的護欄都已具備，並在真實資料上驗過（BEGIN…ROLLBACK 先確認六層各 6 列才 COMMIT，
> 事後 DB 14 項＋API 3 項檢查全過）。
>
> 那次也證實**刪除順序不能憑印象**：指向 `RC_STUDY`/`RC_SERIES`/`RC_OBJECT` 的 13 條外鍵
> 裡只有 `RC_OBJECT_HASH` 是 CASCADE，而 `RC_OBJECT_CONVERT` 有資料且是 NO ACTION ——
> 只照 CASCADE 判斷就會漏掉它、刪 `RC_OBJECT` 時撞外鍵。真正實作時要用
> `information_schema` 掃過所有帶 `*_REF` 欄位的表，不要看 dump 猜。

**誤刪範圍**的第二道是階段二的 RLS:管理連線改用非 superuser 角色,policy 限定 `SITE_CODE`,如此連手寫 SQL 漏掉 WHERE 也打不到別院。這正是「單 DB 也能安全」的關鍵——它不只是給出口過濾用的。

## 存量資料:分界日 + 按需重送(2026-08-18 定案)

**這一節的決策取決於既有資料放在哪裡**,兩種場景差很多:多家動物醫院是「一院一 VM、50+ 台」各自獨立;一家醫院的分院則往往**本來就在同一套系統裡**,那樣只需要回填 `SITE_CODE`,不需要下面這套。以下是前者(分散在多台舊主機)的決策。

**決策:不做全量遷移,也不是完全不匯入,而是混合。**

- **分界日**(`SITE.CUTOVER_DATE`,per-hospital):之後的新檢查儀器直打總機。
- **分界日之前**:留在該院舊 VM 唯讀保存。**病患回診需要調閱舊片時,才從舊 VM 以 C-STORE 把那一筆重送進總機。**

選這條路的理由是它避開了「50+ 台大遷移」這個獨立專案級別的工程,而且重送**自動走 `store_dicom`**——歸屬在進檔當下蓋章,與定案原則 2 完全一致,不需要任何額外的補欄邏輯。相對地,DB 層搬遷工具會繞過蓋章、`SITE_CODE` 得自己補,一致性也得自己保證,風險最高。

**按需重送可行的前提是「重送兩次不會產生重複資料」**,這點靠既有行為成立:同院重送同一個 UID 會走 `store_dicom` 的 study 已存在分支(走 update,不會重複建 study);跨院同 UID 則由本設計的護欄 `RAISE EXCEPTION` 擋住。這是這個決策的支撐點,改動 `store_dicom` 時不能破壞它。

**舊 VM 的退役條件**(兩者皆須成立):該院重送需求趨近零,且已完成一次整院匯出並驗證。在那之前舊 VM 不關機——它是分界日之前資料的唯一線上副本。

## 初始資料與管理

- 舊 Proxy 設定檔的各院 AE 清單=現成「AE→院區」登記來源:一次性匯入 AE_MAIN+AE_CONFIG(NETWORK/DICOM 含 siteCode)。
- 管理 UI(後續):SITE CRUD、AE 掛院區欄位、未歸戶清單+認領(認領=UPDATE 歷史 RC_STUDY.SITE_CODE)。

## 施工順序

1. **階段一(進檔就開始歸戶)**:migration(SITE 含 CUTOVER_DATE + RC_STUDY 欄 + 索引)→ 改 `store_dicom`+`insert_dicom_info`+兩處 QC 複製 → NetworkConfig 加屬性 → AE 設定匯入。
2. **階段二**:出口過濾(C-FIND/C-MOVE/QIDO/WADO/Viewer)+RLS + **整院匯出／退場工具**(RLS 同時是誤刪的第二道,所以與出口過濾同階段做)。
3. **階段三**:管理 UI(SITE/掛院區/認領/分界日/退場流程)。

存量資料不佔階段:分界日之後自然發生,分界日之前的重送是營運動作而非開發項目(需要的是舊 VM 上已有的 C-STORE 能力)。

## 待議

- **對外 port 網路安全**:DICOM 無認證,防線=AE 白名單+來源 IP 綁定;院區在 NAT/浮動 IP 下 host 只能 0.0.0.0 → 需防火牆限源/VPN/固定出口 IP,與網路規劃一起定。**這條在動物醫院場景特別關鍵**(儀器在各家診所、走網際網路);分院多半在同一內網,壓力小很多。
- 病患複合顯示:`PATIENT_ID_SHARED=false` 時,Viewer 顯示 PatientID 要不要帶院區前綴(同號不同人的視覺區辨),UI 階段再議。
- 混合部署(同一台同時有獨立編號與共用編號的院區群)需要 `SITE.GROUP_CODE` 之類的群組概念,目前無此需求,先不做。
- Worklist 線(擱置中)回來後:HDM 表是否也加 SITE_CODE、物種中翻英(狗→Feline 對調)一併處理。

---

## 導入案例:多家動物醫院共用總機

上面全部是通用機制。**這一節是動物醫院這條線特有的**,讀通用設計時可以略過。

- **拓撲**:Proxy 整個退役,儀器 C-STORE **直打總機**(對外開 port)。原本規劃的 STOW 轉發鏈(`StowForwarder`)與 UserUUID 歸屬設計一併作廢。
- **歸屬 key**:使用者鐵則是**現場 AE Title 一律不動**(改 AE 要跑現場),所以院區歸屬沿用舊慣例的 **CallingAE 尾 6 碼 UserUUID**,對照表(UserUUID → SITE_CODE)放總機 DB,初始資料從現有 Proxy 設定檔一次性匯入。
- **Proxy 特殊流程盤點結論**:AE 白名單/CalledAE 驗證/視訊 TS/健檢 AE 都是新 PACS 現成的;進檔改寫在 proxy 端**從未實作**(只有 UI 與設定),新 PACS 反而有真的(per-AE `dicomImportModified` + `dicomTagFilter`);ServiceManager 重啟由 systemd 取代。**缺口只剩院區歸屬**,也就是本設計。
- **Worklist 線**:診所端 NxVet → `www.horoview.vet/hcs/<院號>/mwl`(反代)→ 各院 VM `:6060/Api/v2.0/MwlInsert`。**院區身分本來就在 URL 裡**,所以新制診所端零改動:反代改指總機相容端點 + nginx 注入院區 header + 內部金鑰(順便補掉那支 Flask 的零認證與 SQL 注入洞)。院區對照是**雙 key**:儀器線用 UserUUID、worklist 線用 hcs 院號,同表對到 SITE_CODE。
- **存量**:一院一 VM、50+ 台,適用「分界日 + 按需重送」(見上)。
- **`PATIENT_ID_SHARED` = `false`**:各家診所獨立編號,嚴格隔離。
