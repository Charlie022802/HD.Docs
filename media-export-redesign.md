# 媒體匯出／燒錄 重新設計（新表 + 新 proc + Viewer API 規格）

**狀態**：設計討論中（2026-08-17 起草）。相關 backlog：REQ-003（Export WebApi）、REQ-010（WebExport 前台）。
**起因**：Viewer 要接燒錄，發現 job 只能用 `studyRef` 且只能整個 study；順著查下去發現 `EXPORT_JOB`
這張表同時服務六種用途，而 Kiosk 之後也要重構 —— 所以決定**先把資料模型做對**，再往上接。

---

## 1. 現況：一張表，六種消費者

`export."EXPORT_JOB"` 是唯一的 job 表，靠 `PRODUCT_UUID` 當多型判斷：

| `PRODUCT_UUID` | 誰在用 | 專屬欄位 |
|---|---|---|
| `export` | **HD.Export API**（.199:5090，新） | — |
| `dicomweb` | DicomWeb 舊薄殼端點（已下架） | — |
| `rimage` | **HD.MediaExportSuite** 燒錄工作站（.NET Framework） | `DISC_INFO`、`EST_DISCS`、`DEVICE_UUID` |
| `kioskExport` | Kiosk 自助取件 | `PICKUP_NO`、`FEE`、`PAY_STATUS`、`PAY_ACCOUNT`、`SOURCE_DEVICE_UUID` |
| `mms` | 舊 MMS | — |
| `archive` | 歸檔／nearline 取回 | — ｜**⛔ 淘汰**：功能要改版，這條流程不納入新設計（2026-08-17 決策） |

`get_job_package_info()` 用 `WHERE "PRODUCT_UUID" != 'mms' AND != 'kioskExport' AND != 'archive'`
把不屬於自己的排除掉 —— **排除法**，所以每次新增用途都得回來改這個 WHERE。

Kiosk 另外三張表（`KIOSK_CARD_EVENT`／`KIOSK_DISC_EVENT`／`KIOSK_DISC_TRANSFER`）只存卡片與光碟事件，
job 本身仍然回到 `EXPORT_JOB`。

## 2. 兩種互不相容的 `BURN_INFO` 形狀

同一個 jsonb 欄位，兩種結構，靠 proc 裡的分支決定組哪一種：

**扁平**（給 net10 `HD.MediaPackage` worker，`Class/PackageJob.cs`）
```
studyInfoList[] = { studyRef, patientId, patientName, accessionNumber, studyInstanceUid,
                    fileList: [ "實體路徑", … ] }
```

**階層**（給 `HD.MediaExportSuite` 燒錄工作站，`Job/PackageJob.cs`）
```
studyInfoList[] = { aeTitle, studyRef, patientId, accessionNumber, studyInstanceUid, modality,
                    studyDate/Time, patientName/Sex/BirthDate, studyDescription,
                    worklistStudyInstanceUid,
                    seriesInfoList[] = { seriesInstanceUid, modality, seriesDescription,
                                         seriesDate/Time, imageCount,
                                         imageInfoList[] = { sopInstanceUid, filePath,
                                                             fileLength, discFileId } } }
```

切換的條件是（`get_job_package_info:2420`）：

```sql
IF product_uuid = 'rimage' AND hd_user_uuid = '76b856c5-05e8-44c5-b0f4-e5e7e5802060' THEN
```

**一個硬編碼的使用者 UUID 是功能開關。** series 層級的篩選（`seriesInstanceUidList`）
也只活在這個分支裡。

> **值得注意**：階層模型**已經做對了我們現在想要的事** —— 用 UID 三層識別、帶 `fileLength`
> （所以容量估算與 `estDiscs` 分片做得到）、`discInfo` 可把一個 job 切成多張光碟。
> 新設計不是發明，而是**把它一般化並正規化**。

`BurnInfo.archiveItems`（`arcLocationRef`／`fileLength`／`filePath`）是「打包前先把檔案從 nearline
撈回來」的前置步驟 —— **屬於要改版的 archive 流程，不遷移**（見第 1 節）。

## 3. `EXPORT_JOB` 的問題清單

| # | 問題 | 後果 |
|---|---|---|
| 1 | **職責混雜**：六用途共用一表，`PICKUP_NO`／`FEE`／`DISC_INFO`／`EST_DISCS` 對多數 job 永遠是 NULL | 看不出哪些欄位跟自己有關；加用途就得改 proc 的 WHERE 排除法 |
| 2 | **`BURN_INFO` 什麼都塞**：選項＋展開後的檔案清單＋`jobTimeRecord`（時間戳當 key）＋**明文 `storagePassword`** | 無 schema、無法索引、無法查「哪些 job 含某個 study」；**密碼明文落庫** |
| 3 | **併發無保護**：`SELECT … STATUS='N' … LIMIT 1` → 展開全部檔案路徑（慢） → `UPDATE STATUS='p'`，中間**沒有 `FOR UPDATE SKIP LOCKED`** | 目前只有一個 worker 所以沒事，**多開一個就會重複打包同一筆** |
| 4 | **狀態碼單字母且大小寫有意義**（`p`=處理中／`P`=完成），無 `CHECK`，`m/M/b/B/Y/C` 連對照表都沒有 | 極易寫錯；case-insensitive collation 下會直接錯亂 |
| 5 | **選擇條件只能整個 study**（一般分支） | Viewer 無法「只燒這幾張」 |
| 6 | **`fileList` 存實體路徑快照** | 檔案歸檔／搬移後 job 失效；一個 study 幾百張就是幾百個長字串 |
| 7 | **兩套時間記錄並存**：`ACTIVITY_RECORDS` jsonb ＋ `BURN_INFO.jobTimeRecord` | 不知道該信哪個 |
| 8 | `ERROR_MSG` 用 jsonb 存錯誤訊息 | 讀寫都要繞 |
| 9 | `PATIENT_ID` 平放在 job 上 | 一個 job 可含多個病患，這欄語意不明 |

索引只有一個 `idx_export_job_status_product_user (STATUS, PRODUCT_UUID, HD_USER_UUID, JOB_REF)`，
對 worker 的輪詢夠用。

---

## 4. 新設計

原則：**job 生命週期、使用者的選擇、產出結果、各產品專屬欄位，四件事分開。**
新的一組表與 proc **完全不動 legacy**（`EXPORT_JOB` 與那兩支 proc 原封不動繼續服務桌面端／kiosk／rimage），
新舊並行，等新的穩定再逐一搬。

### 4.1 表

```sql
-- ① job 生命週期（所有用途共用的最小集合）
CREATE TABLE export."PACKAGE_JOB" (
    "JOB_ID"        bigserial PRIMARY KEY,
    "PRODUCT"       text NOT NULL,                  -- 'export' | 'kiosk' | 'rimage' | 'archive'
    "REQUESTED_BY"  text NOT NULL,                  -- HD_USER_UUID 或 API key 的 sub
    "STATE"         text NOT NULL DEFAULT 'queued'
                    CHECK ("STATE" IN ('queued','claimed','processing','ready','failed','canceled')),
    "PROGRESS"      int  NOT NULL DEFAULT 0,
    "PRIORITY"      int  NOT NULL DEFAULT 0,
    "OPTIONS"       jsonb NOT NULL DEFAULT '{}',    -- 只放打包選項，不放資料
    "RESULT_PATH"   text,                           -- 產出目錄或檔案
    "ERROR_TEXT"    text,                           -- 純文字
    "CLAIMED_BY"    text,                           -- 哪個 worker 實例領走的
    "CLAIMED_AT"    timestamptz,
    "CREATED_AT"    timestamptz NOT NULL DEFAULT now(),
    "MODIFIED_AT"   timestamptz NOT NULL DEFAULT now(),
    "CANCELED_AT"   timestamptz
);
CREATE INDEX ON export."PACKAGE_JOB" ("STATE", "PRODUCT", "PRIORITY" DESC, "JOB_ID");

-- ② 使用者「要什麼」——存 UID，不存實體路徑
CREATE TABLE export."PACKAGE_JOB_SELECTION" (
    "JOB_ID" bigint NOT NULL REFERENCES export."PACKAGE_JOB"("JOB_ID") ON DELETE CASCADE,
    "LEVEL"  text   NOT NULL CHECK ("LEVEL" IN ('study','series','instance')),
    "UID"    text   NOT NULL,
    PRIMARY KEY ("JOB_ID", "LEVEL", "UID")
);

-- ③ 實際打包了什麼（快照，稽核用；由 worker 打包時寫入）
CREATE TABLE export."PACKAGE_JOB_ITEM" (
    "JOB_ID"              bigint NOT NULL REFERENCES export."PACKAGE_JOB"("JOB_ID") ON DELETE CASCADE,
    "SOP_INSTANCE_UID"    text   NOT NULL,
    "SERIES_INSTANCE_UID" text   NOT NULL,
    "STUDY_INSTANCE_UID"  text   NOT NULL,
    "FILE_BYTES"          bigint,
    "DISC_FILE_ID"        text,          -- 光碟／輸出中的檔名（對應 MediaExportSuite 的 discFileId）
    "DISC_NO"             int,           -- 切成多張光碟時屬於第幾張
    PRIMARY KEY ("JOB_ID", "SOP_INSTANCE_UID")
);
CREATE INDEX ON export."PACKAGE_JOB_ITEM" ("STUDY_INSTANCE_UID");

-- ④ 產品專屬欄位（光碟／取件／付費）——不要再擠進主表
CREATE TABLE export."PACKAGE_JOB_DISC" (
    "JOB_ID"            bigint PRIMARY KEY REFERENCES export."PACKAGE_JOB"("JOB_ID") ON DELETE CASCADE,
    "DEVICE_UUID"       uuid,
    "SOURCE_DEVICE_UUID" uuid,
    "EST_DISCS"         int,
    "DISC_INFO"         jsonb,
    "PICKUP_NO"         text,
    "FEE"               int  NOT NULL DEFAULT 0,
    "PAY_STATUS"        boolean NOT NULL DEFAULT true,
    "PAY_ACCOUNT"       text
);
```

**為什麼 `SELECTION` 存 UID 而不是展開的檔案路徑**：解決問題 #6（快照失效）與 #5（層級）。
worker 領到 job 時**當下**才把 UID 解析成檔案，所以歸檔搬移、W/L 校正、出口疊合都自然吃到最新狀態。
UID 全域唯一，所以三個層級混存在同一張表不會有歸屬歧義。

**`SELECTION` 與 `ITEM` 是兩件不同的事**（2026-08-17 決策：兩者都要）：

| 表 | 語意 | 誰寫 | 何時 |
|---|---|---|---|
| `SELECTION` | 使用者**要求**什麼（可能是 3 個 study UID） | API | 建立 job 時 |
| `ITEM` | 實際**打包了**什麼（248 筆 SOP UID＋大小＋光碟編號） | worker | 打包時 |

沒有 `ITEM` 就回答不出「當初那片光碟到底燒了哪幾張」——而病歷相關的爭議正是會問這個。
`ITEM` 一併取代 `discInfo`（原本是 `Dictionary<string, BurnInfo>` 塞在 jsonb 裡）：
哪張光碟裝哪些檔案，改成 `DISC_NO` 一個欄位就表達完。
**仍然不存實體路徑** —— 要用時由 UID 解析，路徑變動不影響稽核紀錄。

**存放憑證的欄位一律不要**（問題 #2 的密碼）：`storageUserId`／`storagePassword` 這類
留在呼叫端或 `/etc/hd/*.env`，不落庫。

### 4.2 領取 job（解決 #3 併發）

```sql
CREATE FUNCTION export.claim_package_job(p_product text, p_worker text)
RETURNS export."PACKAGE_JOB" AS $$
    UPDATE export."PACKAGE_JOB" SET
        "STATE" = 'claimed', "CLAIMED_BY" = p_worker,
        "CLAIMED_AT" = now(), "MODIFIED_AT" = now()
    WHERE "JOB_ID" = (
        SELECT "JOB_ID" FROM export."PACKAGE_JOB"
        WHERE "STATE" = 'queued' AND "PRODUCT" = p_product
        ORDER BY "PRIORITY" DESC, "JOB_ID"
        FOR UPDATE SKIP LOCKED          -- ← 關鍵：多 worker 各領各的，不會撞
        LIMIT 1)
    RETURNING *;
$$ LANGUAGE sql;
```

同時解決 #1 的排除法：改成 `PRODUCT = ` **白名單**，新增用途不必回來改別人的 WHERE。

### 4.3 新 proc 一覽（全部新開，不動 legacy）

**✅ 已實作於 `Database/HDPACS/db_update_sql/db_update_v2.0.28.sql`**（2026-08-17，尚未套用任何環境）。
驗證方式＝把整份 migration ＋ 功能冒煙測試包在 `BEGIN … ROLLBACK` 裡對 .191 實跑，
所以語法、型別、jsonb 路徑、proc 邏輯都被真的 PostgreSQL 檢查過，而 DB 沒有任何殘留：

- 拿一個 **744 張、9 個 series** 的真實 study 走完 create → claim → resolve → record → update → cancel
- `create` 的 `imageCount` 與 `resolve` 展開的張數一致；每個 series 的 `imageCount` 與 `instances` 長度相符
- 三個層級各自正確（study 744／series 5／instance 2）
- **聯集不重複計算**：study(744) ＋ 其中 2 張 SOP ＝ 744 而非 746
- 負向case也對：空條件、不存在的 UID、對 `ready` 的 job 取消，都正確被拒
- `record_package_job_items` 重複呼叫是 UPSERT，不報錯

（過程中被驗證抓到一個錯：把 `package_job_objects` 從 `plpgsql` 改成 `sql` 時，
開頭的 `BEGIN RETURN QUERY` 拿掉了但**結尾的 `END;` 忘了拿掉** —— body 的最後一個語句
變成 `END;` 而不是 SELECT，PostgreSQL 回 `42P13`。純看程式碼很難發現。）

| proc | 用途 |
|---|---|
| `export.create_package_job(jsonb)` | 建立：寫 `PACKAGE_JOB` + `PACKAGE_JOB_SELECTION`，回 `{jobId, imageCount, totalBytes}` |
| `export.claim_package_job(product, worker)` | worker 領取（`SKIP LOCKED`） |
| `export.resolve_package_job_files(jobId)` | 把 SELECTION 解析成實體檔案清單（階層＋`fileLength`） |
| `export.record_package_job_items(jsonb)` | worker 打包時寫入 `PACKAGE_JOB_ITEM` 快照（SOP UID／大小／`DISC_FILE_ID`／`DISC_NO`） |
| `export.update_package_job(jsonb)` | 回寫進度／狀態／產出路徑／錯誤 |
| `export.get_package_job(jobId)` | 查狀態（給 API） |
| `export.cancel_package_job(jobId)` | 取消 |

`resolve_package_job_files` 直接回**階層結構**（study → series → instance，帶 `fileLength`）——
就是 `HD.MediaExportSuite` 那個模型。新 worker 與燒錄工作站共用同一份形狀，不再有兩套。

---

## 5. Viewer 要打的 API 規格

`POST /export/packages`　認證 `X-API-Key`（scope `export.write`）

**選擇影像** — 三個層級可混用、取聯集：

| 參數 | 型別 | 說明 |
|---|---|---|
| `studyInstanceUid` | string[] | 整個 study |
| `seriesInstanceUid` | string[] | 整個 series |
| `sopInstanceUid` | string[] | 單張影像 |

（既有的 `studyRef` 與 `patientId`+`accessionNumber` 保留，桌面端在用。）

**選項** — 省略即套用預設：

| 參數 | 預設 | 說明 |
|---|---|---|
| `anonymous` | `false` | 去識別 |
| `containViewer` | `true` | 附光碟 viewer ⚠️ 不給就會附 |
| `ignoreCompress` | `true` | 不壓縮 ⚠️ 不給就是不壓縮 |
| `dicomStoragePath` | `DICOM/{D8}.dcm` | 輸出內的相對路徑樣板 |

**`ignoreMultiframe` 不再開放**：舊 proc 用它篩 `CONVERT_STATUS->>'mpeg4'='N'`，但 REQ-008
移除 DicomToVideo 之後進檔一律標 `mpeg4='N'`，對新資料 true/false 結果完全相同；新的
`package_job_objects` 也不做這個篩選。留著就是第二個空頭參數（剛拿掉 7z 那兩個就是這個原因）。

**回應** `201`：
```json
{ "jobRef": 123, "imageCount": 248, "totalBytes": 335544320 }
```
`imageCount` / `totalBytes` 是新加的 —— Viewer 才能顯示「共 248 張，約 320 MB」。
`insert_package_job` 其實一直有算 `imageCount`，只是沒回傳。

`GET /export/packages/{jobRef}`：
```json
{ "jobId": 123, "state": "processing", "progress": 40,
  "downloadReady": false, "errorMessage": null, "packagedCount": 96 }
```
`state` ＝ `queued`／`processing`／`ready`／`failed`／`canceled`。

**legacy 的單字母 `status` 不再回傳** —— 新表沒有那個欄位（先前規格寫「保留供除錯」是錯的，
硬留只會回一個永遠是空字串的欄位）。`packagedCount` 是已寫入稽核快照的張數，可當細粒度進度。

**不對外回傳產出路徑**：那是伺服器的檔案系統結構，呼叫端不需要，而且會出現在錯誤回報與截圖裡。
下載一律走 `/download`。

**⚠️ 歸屬檢查在 API 層**：舊的 `get_package_job_status` 把 productUUID+userUUID 傳進 proc 比對、
非本人回 null；新的 `get_package_job` 只吃 jobId，**若不比對，任何持有 `export.read` 的金鑰
都能查到別人的 job**。所以 `ExportService.GetStatusAsync` 取回後比對 `product` 與 `requestedBy`，
不符回 404（不是 403 —— 403 等於告訴對方這個 job 存在）。
日後若有第二個消費者（kiosk）也走新表，這一關要記得各自做，或把它下推到 proc。

`GET /export/packages/{jobRef}/download` → `200 application/zip`／`409` 未完成／`404` 不存在

**輪詢**：worker 每 2 秒撈佇列，Viewer 每 2～3 秒查一次即可。

---

## 6. 遷移路徑

| 階段 | 內容 | 影響 |
|---|---|---|
| 1 | ✅ **已寫好＋已驗證**：建新表 + 新 proc（`db_update_v2.0.28.sql`）；另 `v2.0.29.sql` 把 `HD_DEVICE_LICENSE` 從 DicomWeb repo 搬進共用序列並補回兩筆漏掉版控的設定。**兩份都還沒在任何環境執行** | 無 —— legacy 完全不動 |

> ### ⚠️ 執行順序（版本鏈）
> 每個 migration 結尾都有「Update Database Version」的 DO block，它**刻意不冪等**：
> 重複執行會 `RAISE EXCEPTION 'Already update version: X'`（所以你會知道這版上過了），
> 而且會檢查前一版必須正確，否則 `Need to update version X first!`。
>
> **.191 目前登記的版本是 `2.0.26`**，而 `v2.0.27` 原本沒有版本注記（一直開著）。
> 2026-08-17 已為 `v2.0.27`／`28`／`29` 都補上，所以必須**依序**執行：
>
> ```
> 2.0.26（現況） → v2.0.27 → v2.0.28 → v2.0.29
> ```
>
> 跳過 `v2.0.27` 直接跑 `v2.0.28` 會被擋下來（`Need to update version 2.0.27 first!`）。
> 三個檔的內容本身都是冪等的（`CREATE OR REPLACE` / `IF NOT EXISTS` / 條件式 UPDATE），
> 只有版本注記那一段不是——那是設計如此。
| 2 | Export API 改用新 proc；新增 UID 三層級與 `state` | Export 尚未有人使用，可自由改 |
| 3 | net10 `HD.MediaPackage` worker 改領新 job（`claim_package_job` + 階層 `resolve` + 寫 `ITEM` 快照） | 要與舊路並行一段 |
| 4 | Kiosk 重構時接新表（`PACKAGE_JOB_DISC`） | 屆時一起 |
| 5 | `rimage` 燒錄工作站接新表，硬編碼 user UUID 退場 | 最後 |
| 6 | legacy `EXPORT_JOB` 與兩支 proc 停用 | 全部搬完才動 |

`archive` **不在遷移路徑上** —— 功能要改版，舊流程直接淘汰（見第 1 節）。

---

## 7. 決策紀錄與待決

**✅ 已決（2026-08-17）**

1. **`SELECTION` 與 `ITEM` 兩張都要** —— 要求與實際打包分開記錄；沒有 `ITEM` 就回答不出
   「當初那片光碟燒了哪幾張」。`ITEM` 一併取代 jsonb 裡的 `discInfo`。
2. **`archive` 流程淘汰** —— 功能要改版，不納入新設計、不遷移。`archiveItems`（nearline 撈回）
   一併退場。
3. **新舊並行、legacy 完全不動** —— 新開一組表與 proc，`EXPORT_JOB` 與那兩支 proc 原封不動
   繼續服務桌面端／kiosk／rimage，等新的穩定再逐一搬。

**⏳ 待決**

1. **`PRODUCT` 值域**要不要收斂成 enum／參照表（現在是自由字串）。
2. **取消語意**：`canceled` 是否要能中斷正在 `processing` 的 job（worker 得輪詢檢查），
   或只能取消還在 `queued` 的。
3. **`worklistStudyInstanceUid`**（`MediaExportSuite` 的 `StudyInfo` 有、net10 沒有）：
   新模型要不要保留這個概念？它影響 study 的去重比對鍵——`InsertImage` 目前是
   `worklistStudyInstanceUid ?? studyInstanceUid` 當比對鍵。
4. **`ITEM` 的保留期**：job 本身可以清，但稽核快照要留多久？（跟病歷保存年限有關，
   可能不該跟 job 一起 `ON DELETE CASCADE`。）
