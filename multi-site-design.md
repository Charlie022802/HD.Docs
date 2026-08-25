# 多院區主機設計(SITE_CODE)

狀態:**設計已完備,待開工**(2026-08-18)。開工前的設計決策全部定案:歸屬正本、server 端強制過濾、穩定代碼當 key、病歷號作用域、整個院區匯出／退場／誤刪防護、存量資料路徑。原「複製 .191 VM」已作廢,改以安裝檔全新裝。

Schema 基準:**`Database/HDPACS_20260818.sql`**(2026-08-18 自 .191 重拉,含 v2.0.30;schema-only 無資料段)。四個 `RC_STUDY` INSERT 點的行號已重新核對,且確認全庫**只有這四處**。

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

## 院區的生命週期:只停用、不刪除(2026-08-18 定案)

**`SITE` 沒有「刪除」這個動作。** 生命週期是 建立 → 停用 → (完成退場三段式後才談清理),
`ENABLE` 就是為此存在的。

DB 已經擋掉一半:`RC_STUDY.SITE_CODE` 的外鍵是 NO ACTION,所以**只要該院區有任何一筆
study,刪那列就會外鍵違反**。漏掉的縫是「院區還沒有 study、但已被 AE 設定引用」——
`siteCode` 塞在 `AE_CONFIG` 的 jsonb 裡,**沒有外鍵保護**,刪掉之後那台儀器下次送片就進不來。

**兩條前端規範是讓這個縫收斂的前提**,不是可有可無的 UI 細節:

1. **管理 UI 不提供刪除院區,只提供停用。** 真要刪除也只在退場三段式全部完成之後。
2. **AE 設定的 `siteCode` 用下拉選單(取自 `SITE`),不是自由輸入。** 打字錯誤這個來源直接消失。

做到這兩條之後,「AE 指到不存在的院區代碼」就只剩兩條路徑:從舊系統一次性匯入時來源
沒對上、以及有人直接下 SQL 改。都是低頻且屬於我們自己造成的。

### 進檔時的四種情況

| AE 設定 | `SITE` 狀態 | 處置 |
|---|---|---|
| 沒有 `siteCode` | — | 收下,`SITE_CODE = NULL`(未歸戶,管理 UI 認領) |
| 有,`ENABLE = true` | 正常 | 蓋章 |
| 有,`ENABLE = false` | **退場中** | **拒收**(`RAISE EXCEPTION`,訊息要指出是退場中) |
| 有,但 `SITE` 查無此碼 | 設定錯誤 | 收下 + `RAISE WARNING`(進集中日誌) |

**`ENABLE = false` 必須拒收,這是該旗標存在的唯一理由。** 退場三段式的第一段就是
`ENABLE = false`「先讓進檔停止,否則邊刪邊進」——若停用中仍照收,那一段等於沒有作用。

更嚴重的是:如果停用中收下但當成未歸戶(`SITE_CODE = NULL`),那些資料**不會被
`delete_site_studies` 掃到**(它按院區刪),退場完成後會留下一批無主的該院影像——
正是本文件「對帳必須是雙向的」那一節說的第二種脫節。

相對地,「代碼不存在」選擇收下而非拒收,理由是代價不對稱:影像是不可重來的臨床資料,
設定打錯事後可以修;為了一個設定錯誤讓儀器停止送片,代價落在錯的地方。而且它與定案
原則 4(未歸戶照收)方向一致,兩種「沒歸到戶」的情況處置相同,語意也單純。

## 進檔蓋章(兩條進檔路 + QC 複製)

**RC_STUDY 共四個 INSERT 點(20260811 版行號)**:

行號依 `HDPACS_20260818.sql`。**全庫只有這四處 INSERT `RC_STUDY`**(已用 script 掃過確認)。

| 位置 | 路徑 | 處理 |
|---|---|---|
| `public.store_dicom`(宣告 L21512,INSERT L21703) | C-STORE(DicomStoreProcess.InsertToDatabase) | 讀 config 蓋章+護欄 |
| `public.insert_dicom_info`(宣告 L12300,INSERT L12499) | DicomWeb STOW(HdPacs Infrastructure) | 同上(它同樣解析 calling_ae_ref) |
| `public.study_split`(宣告 L22743,INSERT L22789) | QC 拆單(SELECT 複製自來源 study) | 複製欄位清單**加 "SITE_CODE"**(繼承來源) |
| **`viewer_station.qc`**(宣告 L28110,INSERT L28374) | QC Split | 同上 |

(第四支先前記為「`study_qc` 類」,實際函式名是 `viewer_station.qc`,2026-08-18 更正。)

**掛設定的鉤子已存在,確認過不必改 schema**:兩條進檔路本來就在讀
`get_ae_config('NETWORK','DICOM', {aeRef: calling_ae_ref})`——`store_dicom` 在 L21623、
`insert_dicom_info` 在 L12417,兩邊都已解析出 `calling_ae_ref`。所以 `siteCode` 加進那個
jsonb 就會被兩邊自動拿到。

> **為什麼不直接用現成的 `RC_STUDY.INSTITUTION_NAME`?** 那一欄確實已經存在、也已經在填
> (store_dicom L21706 從 DICOM 表頭的 `InstitutionName` 帶入),但它是**儀器自己報的字串**:
> 各院區設定不一致、可能空白、可能被改機打錯、也不是穩定代碼。歸屬必須是**我們這邊認定的**
> (由 AE 設定決定),而不是相信來源填了什麼。兩者並存:`INSTITUTION_NAME` 保留原樣當參考,
> `SITE_CODE` 才是權威。

蓋章改法(以 store_dicom 為例,insert_dicom_info 同構):

```sql
-- DECLARE 加
hospital_code text;
existing_hospital_code text;

-- 讀 DICOM settings 那段(既有 get_ae_config('NETWORK','DICOM',aeRef))一起讀
--   config ->> 'siteCode' INTO hospital_code

-- Insert Study 分支:欄位清單加 "SITE_CODE"、VALUES 加 hospital_code

-- Study 已存在分支:護欄要放在 ELSE 一進去、**allow_duplicate 判斷之前**。
-- 原因(2026-08-18 讀 store_dicom L21717-21744 確認):allow_duplicate=false 只是
-- 「跳過更新 study」,後面的 series/object 仍然會用同一個 study_ref 掛上去——
-- 也就是 B 院區的影像會靜靜掛進 A 院區的 study。所以不能只在 update 分支裡擋。
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

### 總開關:`SITE` 表有沒有資料(2026-08-18 定案)

**`SITE` 表是空的 → 多院區功能整個未啟用,所有出口完全不過濾,行為與導入前逐字相同。**
表裡一有資料,過濾就自動生效。

用「資料的存在」當開關而不是另設一個旗標,理由是**不可能設錯**:

- **單一醫院部署完全不必做任何事**——不建 SITE、不設 AE,C-FIND/C-MOVE 就跟今天一樣全查。
  絕大多數既有安裝屬於這種,它們不該為了一個用不到的功能去記得「把某個開關關掉」。
- 旗標與資料會出現矛盾狀態(旗標關著但資料已分院區、或反過來),而「有沒有 SITE 資料」
  本身就是唯一事實,不會自相矛盾。

### 啟用之後的過濾規則

| 呼叫端 | 看得到 |
|---|---|
| 有 `siteCode` = X | **只有 `SITE_CODE = X`** |
| 沒有 `siteCode` | 只有 `SITE_CODE IS NULL`(未歸戶) |

**有 siteCode 者看不到未歸戶資料**(2026-08-18 定案)。這代表遷移期間尚未認領的舊資料
對醫師是不可見的——**可接受,因為導入方式是「先全部轉置完成,才開放給醫師」**
(使用者確認)。若改成 `SITE_CODE = X OR SITE_CODE IS NULL` 會好用,但 B 院未認領的
資料 A 院也看得到,在嚴格隔離的場景是外洩。

`PATIENT_ID_SHARED = true` 時,「本院區」的範圍擴大為同一共用群組(見「病歷號作用域」)。

### 各出口

- 儀器 C-FIND/C-MOVE:院區=CallingAE 的 `NetworkConfig.siteCode` → 查詢加 `WHERE "SITE_CODE" = ...`。
- DicomWeb QIDO/WADO(生產走 HdPacs* Dapper 版):依呼叫者(金鑰/登入者)院區過濾。
- Viewer:登入者帳號綁院區。
- **RLS 第二道護欄**:RC_STUDY 上 policy(pgbouncer 環境需 `SET LOCAL`,既知)。細節此階段再展開。

> **實作注意**:總開關要避免每次查詢都去數一次 `SITE`。建議在連線/請求層取一次
> (例如啟動時讀 + 管理 UI 異動時失效),而不是塞進每個查詢的 WHERE 裡。

### 實作結果(2026-08-25,`db_update_v2.0.33.sql` + `DicomPACSService.cs`,已上 .191)

**PACS 的 C-FIND／C-MOVE 已完成並實機驗證。** 三支 DB 函式:

| 函式 | 用途 |
|---|---|
| `site_query_scope(calling_ae)` | 可見範圍的**唯一正本**,回 jsonb(`enabled` / `mode` / `codes`) |
| `site_can_access_study(calling_ae, study_ref)` | 單筆判定 |
| `site_can_access(calling_ae, info_type, info_ref)` | Study/Series/Image 三層級,C-MOVE 實際呼叫這支 |

C-FIND 走 `query_dicom`(migration 修補 `prosrc`,在 `LOCKED = false` 那行之後接院區條件,
冪等且找不到錨點就中止)。C-MOVE 走 `DicomPACSService.cs`,在 `insert_job_queue` 之前擋。

**上面那條「連線層取一次快取」的建議,實作時刻意沒有採納。** 快取失效的後果是
**跨院區外洩**(旗標還說未啟用但資料已分院區),而 `SITE` 是一張幾十列的小表,
`EXISTS` 的成本相對於後面的 study 查詢可以忽略。這個量級下正確性優先。
日後若真的量到瓶頸再處理,屆時要一併想清楚失效路徑。

**C-MOVE 原本完全沒有權限判斷**——三個層級都是「UID → ref → 直接插 job」。
只過濾 C-FIND 的話,知道別院 StudyInstanceUID 的 AE 照樣搬得走。層級對應放在 DB
而不是 C#,因為表在那裡,而且呼叫端只有一個進入點,不會有人只擋 Study 忘了擋 Image
(那層最少用、最容易漏)。拒絕時回一般的 `ProcessingFailure`,不用專用拒絕碼,
否則對方能靠回應碼試探 UID 存不存在。

驗證方式見 [todo.md](todo.md) 的多院區章節:**斷言看的是 `MAP_JOB` 有沒有多出 CMOVE job,
不是回應碼**——回應碼可能因為目的地連不上而失敗,只有「沒有 job」能證明是院區過濾擋下的。

### DicomWeb QIDO/WADO(2026-08-25,`db_update_v2.0.34.sql` + `SiteScopeProvider`,已上 .199)

DicomWeb 的呼叫端有兩種身分,所以 v2.0.34 把規則引擎抽出來,兩條路共用同一顆:

| 函式 | 用途 |
|---|---|
| `site_scope_for_code(site_code, actor)` | **規則引擎(唯一正本)**,吃已解析出來的院區代碼 |
| `site_query_scope(calling_ae)` | AE 這條路,改成薄殼(行為與 v2.0.33 逐字相同) |
| `site_scope_for_user(user_id)` | 使用者這條路,讀 `HD_USER.OTHERS ->> 'siteCode'` |

**使用者的院區存在 `HD_USER.OTHERS` 的 jsonb 裡**,比照 AE 存在 `AE_CONFIG` 的 jsonb,
零 schema 改動。`user_id` 對應 `HD_USER."ID"`(＝Keycloak 的 `preferred_username`,
各產品都用它查 HD_USER 補 scopes)。

**身分判斷要用 `actor_type` claim,不能用「有沒有名字」**:金鑰身分的 `ClaimsIdentity`
建構時 `nameType: "api_key_name"`,所以 `Identity.Name` 是**金鑰名稱**;拿它當使用者帳號
去查 HD_USER 必然查無此人,結果是沒綁 AE 的金鑰什麼都看不到。同一個 `Name` 屬性在兩種
身分下語意完全不同。

**金鑰沒綁 AE ＝ 視為未歸戶**(2026-08-25 定案),與「AE 沒掛 siteCode」同一條規則。

**WADO 的每個入口都要自己擋**,因為全是「拿 UID 直接取」、沒有 WHERE 可加——
只過濾 QIDO 等於擋在「找得到」卻沒擋在「拿得到」。拒絕時回 404 不是 403,
否則對方能靠狀態碼試探某筆存不存在。QIDO 則是四個查詢(study/count/series/instances)
都要加條件,漏一個就是一條繞道。

### DicomWeb 的 DELETE / UPS / STOW(2026-08-25,alpha.5)

`DELETE` 與 `UPS` 已補上,`STOW` 查證後確認本來就正確(`insert_dicom_info` 依 calling AE
蓋章,STOW 傳的是 header AE 或金鑰綁的 AE)。

v2.0.35 另外加了兩支「**我自己是哪一個院區**」的查找,給建立資料時蓋章用:

| 函式 | 回答 |
|---|---|
| `site_scope_for_*` | 看得到**哪些**(共用病歷號時是一群) |
| `site_code_of_ae` / `site_code_of_user` | 我**是哪一個**(蓋章只能蓋一個) |

**不能拿 scope 的 `codes[0]` 代替**——共用群組下 `codes` 有多筆,選第一個就是亂蓋。

### Worklist(MWL):讀取端已做,寫入端待 WorklistInsert 案(2026-08-25,v2.0.36)

`HDM_SERVICE_REQUEST` 加了 `SITE_CODE`,`query_worklist` 依 calling AE 的可見範圍過濾
(規則同一支 `site_query_scope`;掛鉤本來就在——`WorklistDicomService` 已經傳
`{aeTitle: CallingAETitle}`)。**改動全在 DB proc,不需要重新部署 PACS。**

**⚠️ 讀取端是嚴格模式,而寫入端還沒蓋章。** `insert_worklist` 不知道呼叫者是誰
(worklist 走 HTTP 不走 DICOM association),所以現有的單全是未歸戶:

| 呼叫端 | 看得到 |
|---|---|
| AE 沒掛 siteCode | 未歸戶 → 與導入前相同 |
| AE 掛了 siteCode | 同院區 → **目前等於什麼都看不到** |

**在醫院／動物醫院啟用多院區之前,`SITE_CODE` 必須先寫得進去**,否則儀器拿不到排程。
2026-08-25 確認接受這個順序(內部測試環境不受影響)。

寫入端的三條路徑身分來源各不相同(動物醫院線在 URL `/hcs/<院號>`、UPS 線是呼叫者的
院區、既有 HIS 線沒有身分),要跟 WorklistInsert 那個案子一起定。

### 匯出／燒錄(HD.Export,2026-08-25,v2.0.37 + alpha.15)

`export.create_package_job` 在選件展開成 UID 清單之後檢查,含跨院區就**整批拒絕**。

擋在 proc 而不是 API:選件有兩種模式(`studies[]` 的 UID、`patientId+accessionNumber`
的條件查詢),都在那支 proc 裡展開,擋在展開之後兩種一次涵蓋,而且檢查與寫入同一個
交易、沒有 TOCTOU。

**整批拒絕而不是靜靜略過**:匯出的產物會離開系統——燒成光碟交給病患。少了幾張而
呼叫端不知道是臨床問題,寧可整批失敗讓人重來。訊息也不區分「不存在」與「別院的」。

`public.site_scope_for_actor(actor_type, actor_id)` 依身分類別分派(`user` 走
`site_scope_for_user`,其餘走 `site_query_scope` 並把 actor_id 當 AE Title),
規則本體仍在 `site_scope_for_code`。各產品的呼叫端身分不同,但規則只能有一套。

### 注意:Worklist SCP 有自己的 AE 白名單

**`HDM_AE_MAIN`**,與 PACS 的 `AE_MAIN` 是兩張表。
`.191` 上它是空的,所以 MWL 目前拒絕所有連線——測試時要先登記(`HOST='0.0.0.0'`
可跳過來源 IP 比對)。不知道這件事的話,「查不到」會被誤讀成過濾生效。

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

- 舊系統的各院 AE 清單=現成「AE→院區」登記來源:一次性匯入 AE_MAIN+AE_CONFIG(NETWORK/DICOM 含 siteCode)。
  **這是「代碼不存在」最可能的來源**——來源資料只要有一筆對不上,那家的所有 AE 都會落入該情況,
  所以匯入前應先比對「來源用到的代碼」與 `SITE` 表,差集要先補齊或明確排除。
- 管理 UI(後續)。注意是 **CRU 不含 D**——院區只停用不刪除,理由見「院區的生命週期」:
  | 功能 | 要點 |
  |---|---|
  | 院區維護 | 建立／改名／**停用**(不提供刪除) |
  | AE 掛院區 | `siteCode` **下拉選單取自 `SITE`**,不可自由輸入 |
  | 未歸戶清單 | 列出 `SITE_CODE IS NULL` 的 study + 認領(認領=UPDATE 歷史 `RC_STUDY.SITE_CODE`) |
  | 分界日／病歷號作用域 | `CUTOVER_DATE`、`PATIENT_ID_SHARED` 的維護 |
  | 退場 | 三段式的操作介面(停用→匯出驗證→刪除),見「整院匯出／單院退場」 |

## 施工順序

1. **階段一(進檔就開始歸戶)**——拆成兩步,承載結構先獨立驗證:
   - **1a ✅ 已完成(2026-08-18,`db_update_v2.0.31.sql`)**:SITE 表(含 CUTOVER_DATE／PATIENT_ID_SHARED)+ RC_STUDY.SITE_CODE + 索引 + 外鍵。純新增、零行為變更。已套用 .191。
   - **1b ✅ 已完成(2026-08-19)**:`store_dicom`／`insert_dicom_info` 蓋章 + 跨院區同 UID 護欄 → `study_split`／`viewer_station.qc` 複製欄位帶 SITE_CODE → `NetworkConfig` 加 `siteCode`。**已用真的 C-STORE 對 .191 端到端驗過五種情況**,見下方「1b 驗證結果」。剩「AE 設定匯入」歸到階段三的管理 UI。

### 1b 驗證結果(2026-08-19,.191,真 C-STORE 送檔)

用 fo-dicom 送真的 C-STORE 到 `.191:2020`(called `HDPACS` / calling `TESTSCU`),逐一驗五種情況:

| # | 情況 | AE 的 siteCode | 預期 | 實際 |
|---|---|---|---|---|
| T1 | 未設定 | (無) | 收下、未歸戶 | STUDY_REF 68 建立,SITE_CODE NULL ✅ |
| T2 | 正常歸戶 | `HQ` | 蓋上 HQ | STUDY_REF 69 SITE_CODE=`HQ` ✅ |
| T3 | 補蓋 | `HQ` | 既存未歸戶的補蓋上 | STUDY_REF 68 由 NULL → `HQ` ✅ |
| T4 | 查無此碼 | `NOSUCH` | 收下當未歸戶 + WARNING | STUDY_REF 70 建立,SITE_CODE NULL ✅ |
| T5 | 停用院區 | `OLDSITE` | 拒收 | 無 RC_STUDY 列;RC_ERROR_DATASET 記下 `Site [OLDSITE] is disabled (retirement in progress)` ✅ |
| T6 | 跨院區同 UID | `BRANCH` | 拒收,不併入 | study 仍屬 `HQ` 且物件數不變;錯誤訊息 `Cross-site study conflict: [...] owned by [HQ], incoming from [BRANCH]` ✅ |

順帶驗證了兩件先前只是假設的事:

- **`siteCode` 取自 calling AE**(`get_ae_config('NETWORK','DICOM',{aeRef: calling_ae_ref})`),不是 called AE。
- **掛院區確實零 schema 變更**:`get_ae_config` 的 `includeMain` 只是把 `AE_MAIN` 的五個欄位併進結果,不是設定繼承;每個 AE 的 `AE_CONFIG.VALUE` 各自獨立,加 `siteCode` 就是 jsonb 多一個 key。C# 這端 `NetworkConfig` 全程唯讀(只有 `GetConfig` 反序列化,沒有任何地方序列化寫回),所以不存在「C# 少一個屬性 → 存檔時把 siteCode 洗掉」的風險。

### ⚠️ 1b 驗證抓到的問題:拒收被回報成「成功」

T5／T6 在 DB 端擋得乾淨,**但送檔端收到的 DICOM 狀態是 `Warning B000 (Coercion of Data Elements)`**。B000 在 DICOM 語意上屬於**警告而非失敗**——儀器會認定影像已經存檔,可能就把本機那份刪掉。

成因不在多院區:`DicomStoreProcess.FileIO.cs` 的 `HandleStorageError` 把**任何**儲存例外一律映射成 `DicomStatus.StorageCoercionOfDataElements`,這是既有行為,多院區的 `RAISE EXCEPTION` 只是流進了同一條路。

影響最大的正是退場情境——「停用院區以停止進檔」時,儀器會以為送成功了。資料本身沒有遺失(檔案落在 `Error/` 目錄 + `RC_ERROR_DATASET` 有記錄),但**送檔端不知道要重送或告警**。

尚未修改,因為改 `HandleStorageError` 會影響所有儲存錯誤的回報(有些站台可能靠 B000 避免儀器不斷重試),不宜在多院區這條線上順手改掉。要修的話正確方向是讓政策性拒收走**失敗**狀態(例如 `0xC000`),與「處理失敗」區分開。列入待議。
2. **階段二**:出口過濾(C-FIND/C-MOVE/QIDO/WADO/Viewer)+RLS + **整院匯出／退場工具**(RLS 同時是誤刪的第二道,所以與出口過濾同階段做)。
3. **階段三**:管理 UI(SITE/掛院區/認領/分界日/退場流程)。

存量資料不佔階段:分界日之後自然發生,分界日之前的重送是營運動作而非開發項目(需要的是舊 VM 上已有的 C-STORE 能力)。

## 待議

- **對外 port 網路安全**:DICOM 無認證,防線=AE 白名單+來源 IP 綁定;院區在 NAT/浮動 IP 下 host 只能 0.0.0.0 → 需防火牆限源/VPN/固定出口 IP,與網路規劃一起定。**這條在動物醫院場景特別關鍵**(儀器在各家診所、走網際網路);分院多半在同一內網,壓力小很多。
- 病患複合顯示:`PATIENT_ID_SHARED=false` 時,Viewer 顯示 PatientID 要不要帶院區前綴(同號不同人的視覺區辨),UI 階段再議。
- 混合部署(同一台同時有獨立編號與共用編號的院區群)需要 `SITE.GROUP_CODE` 之類的群組概念,目前無此需求,先不做。
- Worklist 線(擱置中)回來後:HDM 表是否也加 SITE_CODE、物種中翻英(狗→Feline 對調)一併處理。
- **拒收的 DICOM 狀態碼**:政策性拒收(停用院區、跨院區衝突)目前回 `Warning B000`,儀器會誤判為成功。要不要讓它回失敗狀態、以及是否只針對政策性拒收而不動其他儲存錯誤,待定。見上方「1b 驗證抓到的問題」。

---

## 導入案例:多家動物醫院共用總機

上面全部是通用機制。**這一節是動物醫院這條線特有的**,讀通用設計時可以略過。

- **拓撲**:Proxy 整個退役,儀器 C-STORE **直打總機**(對外開 port)。原本規劃的 STOW 轉發鏈(`StowForwarder`)與 UserUUID 歸屬設計一併作廢。
- **歸屬 key**:使用者鐵則是**現場 AE Title 一律不動**(改 AE 要跑現場),所以院區歸屬沿用舊慣例的 **CallingAE 尾 6 碼 UserUUID**,對照表(UserUUID → SITE_CODE)放總機 DB,初始資料從現有 Proxy 設定檔一次性匯入。
- **Proxy 特殊流程盤點結論**:AE 白名單/CalledAE 驗證/視訊 TS/健檢 AE 都是新 PACS 現成的;進檔改寫在 proxy 端**從未實作**(只有 UI 與設定),新 PACS 反而有真的(per-AE `dicomImportModified` + `dicomTagFilter`);ServiceManager 重啟由 systemd 取代。**缺口只剩院區歸屬**,也就是本設計。
- **Worklist 線**:診所端 NxVet → `www.horoview.vet/hcs/<院號>/mwl`(反代)→ 各院 VM `:6060/Api/v2.0/MwlInsert`。**院區身分本來就在 URL 裡**,所以新制診所端零改動:反代改指總機相容端點 + nginx 注入院區 header + 內部金鑰(順便補掉那支 Flask 的零認證與 SQL 注入洞)。院區對照是**雙 key**:儀器線用 UserUUID、worklist 線用 hcs 院號,同表對到 SITE_CODE。
- **存量**:一院一 VM、50+ 台,適用「分界日 + 按需重送」(見上)。
- **`PATIENT_ID_SHARED` = `false`**:各家診所獨立編號,嚴格隔離。
