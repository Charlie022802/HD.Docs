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

**選擇影像 — 巢狀 `studies[]`，一條規則遞歸適用：省略下一層＝該層全要。**

```jsonc
{
  "studies": [
    {
      "studyInstanceUid": "1.2.826.0.1.3680043.10.688.…",
      "series": [
        { "seriesInstanceUid": "1.2.840.113619.2.4" },        // 省略 instances → 整個 series
        {
          "seriesInstanceUid": "1.2.840.113619.2.5",
          "instances": [                                       // 只要這幾張
            { "sopInstanceUid": "…110" },
            { "sopInstanceUid": "…1104" }
          ]
        }
      ]
    },
    { "studyInstanceUid": "1.2.826.0.1.3680043.10.688.…2" }   // 省略 series → 整個 study
  ]
}
```

（另可用 `patientId`+`accessionNumber` 成對指定，語意是整個 study。）

> #### 為什麼不收 `studyRef`（2026-08-17 移除）
> v2.0.28／2.0.30 原本也收 `studyRef`（`RC_STUDY.STUDY_REF` 整數），名義上是「相容既有呼叫端」，
> 但這支 API 是全新的、**沒有任何既有呼叫端**——舊呼叫端走的是舊 `EXPORT_JOB` 那條路。
> 真正的問題是它把**資料庫代理鍵**放進對外契約：呼叫端得先知道我們的內部識別才能點影像，
> 而 UID 才是跨系統穩定的那個。
>
> 它同時還是個地雷：型別是 `int[]`，但說明寫「STUDY_REF 清單」、周圍欄位又全是 UID 字串，
> 餵 UID 進去會拿到一個**沒有 body 的 400**（ASP.NET Core 的 JSON 綁定失敗預設不回訊息），
> 呼叫端完全看不出錯在哪。實測時我自己就踩了這一腳。
>
> **注意方向性**：移除的只有「輸入側」。worker payload 的 `studyInfoList` 仍然會**輸出**
> `studyRef`（legacy worker 需要），那個不能動。

> #### 為什麼不是三個平行陣列（2026-08-17 改掉）
> 原本 v2.0.28 的 API 平行收 `studyInstanceUid` / `seriesInstanceUid` / `sopInstanceUid`，
> 論證是「DICOM UID 全域唯一，所以選出的影像集合不會有歧義」。那個論證本身沒錯，
> **但它沒有處理呼叫端會不會誤用**，而那是更重要的問題：
>
> ```
> 平行：series=[B] + sop=[x,y,z]   →  B 全部 ∪ {x,y,z}     （聯集）
> 巢狀：series B, instances=[x,y,z] →  B 裡「只要」這三張   （子集）
> ```
>
> 呼叫端的直覺幾乎一定是後者 ——「我給了 series 又給了 sop，當然是在這個 series 裡選這幾張」。
> 舊設計要表達「只要 3 張」得**只送 sop、不送 series**，非常反直覺。
> 而 Viewer 的 UI 本來就是一棵樹（study → series → 影像，勾選狀態天然巢狀），
> 硬要它攤平成三個陣列，是把它的資料結構弄壞來配合 API。
>
> **`instances` 用物件陣列而不是字串陣列**，是為了三層都是同一個 `{ uid, 子容器? }` 形狀，
> 而且與 `resolve_package_job_files` 回給 worker 的**輸出對稱**（那邊本來就是
> `instances: [{ sopInstanceUid, filePath, fileLength, … }]`）——呼叫端可以拿查詢結果
> 直接改造成下一次的請求。字串陣列雖然短，但將來要指定 frame、光碟檔名、
> 標註 key image 就塞不進去了。
>
> `PACKAGE_JOB_SELECTION` 也跟著改成三欄式（`STUDY_UID`／`SERIES_UID`／`SOP_UID`，
> `NULL`＝該層全要，見 `v2.0.30`），所以**事後直接看表就能還原使用者當初勾了什麼** ——
> 舊的扁平 `(LEVEL, UID)` 連「這個 series 屬於哪個 study」都沒記。

**選項** — 省略即套用預設：

| 參數 | 預設 | 說明 |
|---|---|---|
| `anonymous` | `false` | 去識別 |
| `containViewer` | DB `true` / **Export API `false`** | 附光碟 viewer。這是唯一「API 預設刻意不同於 DB 預設」的欄位，見下 |
| `ignoreCompress` | `true` | 不壓縮 ⚠️ 不給就是不壓縮 |
| `dicomStoragePath` | `DICOM/{D8}.dcm` | 輸出內的相對路徑樣板 |
| `contents` | `["dicom"]` | 包裡要放什麼：`dicom`／`jpeg`，**可同時給兩個** |

`priority` 不在上表 —— 它是**佇列屬性**不是打包選項，有自己的欄位 `PACKAGE_JOB.PRIORITY`
（`integer`，預設 0）與索引，不進 `OPTIONS` jsonb（否則 claim 排序得先解 jsonb）。
範圍 −9～9 由 API 擋（proc 不擋）：欄位是 `integer`，不設上限的話一個 `2147483647`
就能永久霸佔佇列頭，而那種值本身沒有意義——排序只看相對大小。

### `containViewer`：曾經會靜靜出一張沒有看片程式的光碟（2026-08-18 修）

先前記錄寫「`.191` 的 `cd-viewer-win` 是 0 bytes,所以 `containViewer=true` 的打包會失敗,測試一律傳 false」。**實測結果相反,而且更糟**：

| | zip 內容 | viewer 執行檔 | job 狀態 |
|---|---|---|---|
| `containViewer=true` | DICOM + DICOMDIR + `rules.enc` + `study_elements.json` | **0** | `ready` |
| `containViewer=false` | DICOM + DICOMDIR | 0 | `ready` |

打包**沒有失敗**。產出的是一張「宣稱含看片程式、附了授權規則檔與影像索引、但沒有看片程式本體」的光碟——病患拿到就是張打不開的片,而整條管線一聲不響。比失敗更難發現。

根因在 `PackageService.DirectoryCopy`：來源目錄不存在時它只 `LogError` 然後 **`return`**,不丟例外;目錄存在但是空的話,連那行 error 都不會有。兩種情況都讓打包一路標成完成。

**已修**（HD.Net10）：`containViewer=true` 分支複製前先擋——`viewerPath` 未設定／目錄不存在／目錄是空的,三種都丟例外,由外層 catch 寫進 `ERROR_TEXT` 變成 `failed` 並說明原因。

**同時補上真正的缺口**：`cd-viewer-win` 之所以是空的,不是某次漏傳,而是 **`HD.DicomImageViewer/deploy/publish.ps1` 只發佈 Viewer／Executer／LinkClient 三個,`HD.DicomImageViewer.Media`（光碟版）從來不在清單裡**——net10 時代沒有人產出過它。新增 `deploy/publish-cdviewer.ps1`（與 installer 的 staging 刻意分開,交付對象與更新節奏都不同）：self-contained win-x64（光碟會交到病患手上,那台電腦不會有 .NET Runtime）、`viewer.media.json` 以正式檔而非 `.sample` 出貨（光碟上沒有安裝程式能補產）、缺 mesa 就中止（軟體 OpenGL,無 GPU 機器少了它 3D/MPR 會靜靜黑掉）。

**產出 245 MB / tar.gz 96 MB**,其中 `mesa/libgallium_wgl.dll` 佔 58.7 MB、其餘是 .NET self-contained（含 Windows Desktop runtime pack 固定帶的 WPF 組件約 23 MB,`PublishTrimmed` 官方不支援 WinForms 故不能砍）。對 DVD（4.7 GB）無妨,但**燒 CD（700 MB）只剩約 455 MB 放影像**——744 張的 CT 約 166 MB 還放得下,要知道有這個上限。

### `priority`：診間急件插隊（2026-08-17 開放）

`claim_package_job_payload` 從一開始就是 `ORDER BY "PRIORITY" DESC, "JOB_ID"`（高的先領、
同值 FIFO），`create_package_job` 也一直收 `priority`，**只差 API 沒開這個欄位**——
呼叫端送了會被當未知屬性忽略，所有 job 都是 0。整條線上就缺這一格，所以補上。

順帶補的是 `get_package_job` 的回傳：它原本沒有 `priority`，呼叫端送了值卻無法確認
有沒有被採用。開一個寫得進去、讀不回來的旋鈕沒有意義，所以兩邊一起。

legacy worker 用一個 `onlyJpeg` 布林值表達，那只夠表達「純 DICOM」與「純 JPEG」——
**表達不出「兩者都要」**，而那正是 Viewer 要的第三種。所以改成可列舉的集合：

```json
"contents": ["dicom"]            // 預設，等同 legacy onlyJpeg=false
"contents": ["jpeg"]             // 只要 JPEG，等同 legacy onlyJpeg=true
"contents": ["dicom", "jpeg"]    // 兩者都要 ← legacy 表達不了
```

大小寫、前後空白、重複都會被正規化（`["JPEG"," dicom "]` → `["dicom","jpeg"]`）；
值打錯（例如 `"jpg"`）會回 **400 並列出錯的值**，不會靜靜忽略——那種錯最難查。
為了讓 legacy worker 至少「純 JPEG」是對的，`OPTIONS` 裡會**同時**寫入 `onlyJpeg`。

**JPEG 是 worker 打包時即時從 DICOM 轉的**（fo-dicom `DicomImage.RenderImage()`），
不是預生檔案，所以 REQ-007 停掉 DicomToImage 對它沒有影響。輸出在 `JPG/` 子目錄、
檔名為 `{SOPInstanceUID}.jpg`。

> #### ⚠️ 階段 3 動 worker 前必須先修的兩件事
> 1. **`job.burnInJpeg` 完全沒有 null 檢查**（`PackageService` 169／172-173／176／182 行：
>    `fontSizePercent`、`fontColor[0]`、`topLeft.Count()`、`padding[0]`），而 `burnInJpeg`
>    目前**沒有任何設定來源**（`BURN_WORKSTATION/SYSTEM` 只有 `burnTempPath`／`queryLimit`／
>    `viewerPath`／`viewerSize` 四個鍵）。所以「只要 JPEG、不要燒字」這個最自然的需求
>    會直接讓 worker 吃 NullReferenceException。**燒字必須變成選配。**
> 2. **`onlyJpeg` 只能二選一**，要支援 DICOM+JPEG 得改成讀 `contents`。
>
> 目前這條路**不會被執行**（worker 還在讀舊表，領不到新 job），所以現在送 `jpeg` 不會
> 造成任何後果——但 worker 一改成領新表，上面兩件沒修就會立刻炸。
>
> 另外燒字用的是 `System.Drawing`（`Font`／`Graphics.FromImage`，套件 `System.Drawing.Common 4.7.3`），
> 在 Linux 依賴 libgdiplus（離線環境包有含）。但因為這條路從未被啟用，**它從來沒有在 Linux 上
> 真的跑過**。程式碼裡其實已經在用 ImageSharp（`AsSharpImage()`／`SaveAsBmp`），只是又轉回
> `System.Drawing.Bitmap` 才燒字——改用 ImageSharp 繪字就能整段拿掉 GDI+ 依賴。

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

`DELETE /export/packages/{jobRef}`（scope `export.write`）→ 取消還沒開始打包的工作。
`200` 回取消後的狀態／`409` 已在打包中或已完成（不能取消）／`404` 查無或非本人。
**只允許 `queued`／`claimed`** —— 要不要能中斷正在 `processing` 的 job 仍是待決（worker 得在
打包迴圈裡輪詢檢查）。

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
| 3 | ✅ **已實作＋驗證（2026-08-17，未部署）**：worker 改領新表、支援 DICOM+JPEG、拆掉燒字的 NRE 地雷 | 新舊並行；舊表那條路不受影響 |
| 4 | Kiosk 重構時接新表（`PACKAGE_JOB_DISC`） | 屆時一起 |
| 5 | `rimage` 燒錄工作站接新表，硬編碼 user UUID 退場 | 最後 |
| 6 | legacy `EXPORT_JOB` 與兩支 proc 停用 | 全部搬完才動 |

`archive` **不在遷移路徑上** —— 功能要改版，舊流程直接淘汰（見第 1 節）。

### 階段 3 怎麼做的（2026-08-17）

**關鍵決定：讓資料庫組出與 legacy 同形的 payload**，而不是讓 worker 去接階層結構。
`export.claim_package_job_payload(product, worker)` 一次完成「領取 ＋ 組 payload」，
回傳 ＝ `HD_CONFIG` 系統設定 ‖ legacy 預設值 ‖ job 的 `OPTIONS` ‖
`{ jobRef, studyInfoList, jobSource, contents, onlyJpeg }`。

於是 worker 只改四個接縫，**700 多行的產出流程一行沒動**：

| 接縫 | 改法 |
|---|---|
| 取 job | 先問新表（有 `SKIP LOCKED`），沒有再退回 `get_job_package_info` |
| 回寫 | 依 `jobSource` 分流；legacy 單字母碼在 `UpdateJobStatus` 內翻譯成 `state` |
| 快照 | 收集 `(SOP UID, 光碟檔名)` → `PACKAGE_JOB_ITEM`；寫失敗只記 log，不讓包變失敗 |
| `contents` | `onlyJpeg` 的 if/else 拆成兩個獨立 `if`（才做得到 DICOM+JPEG）；判斷走 `WantsDicom`／`WantsJpeg`，舊表沒有 `contents` 時自動退回看 `onlyJpeg` |

**驗證時抓到三個「同一個 job 走新舊兩條路會產出不同東西」的問題**，都補在 payload 裡
（預設值的正本本來就該在 DB）：

| 欄位 | 沒補的後果 |
|---|---|
| `dicomStoragePath` | worker 的 `Regex.Matches(null,…)` 直接 `ArgumentNullException` |
| `containViewer` | C# `bool` 預設 false、legacy 預設 **true** → 不會附光碟 viewer |
| `ignoreCompress` | 同上 → 會多壓一次 |

這類差異純看程式碼很難注意到 —— **.NET 的型別預設值與 legacy proc 的預設值方向相反**。
而且 JSON 鍵名對不上時**不會報錯**，只會靜靜落在預設值，所以驗證特地用 worker
真正的 `PackageJob` 類別做反序列化（用複製一份的定義就測不到這件事）。

`onlyJpeg` 改為一律由 `contents` 推導，避免兩個欄位各說各話（`contents` 是正本）。

**兩顆地雷已拆**：`burnInJpeg` 的 NRE（燒字改成選配，`IsUsable` 把「設定夠不夠用」
定義在一處）；不燒字時完全不碰 `System.Drawing`（直接 ImageSharp `SaveAsJpeg`，
少一次 BMP 中轉，也避開 Linux 的 libgdiplus 依賴）。

### 實機驗證（2026-08-17，.191 `pacs 2.0.6`）

三種組合各建一筆真實 job，全部 `ready`：

| contents | ITEM 快照 |
|---|---|
| `["dicom"]` | 6 筆 `DICOM/00000000.dcm`… |
| `["jpeg"]` | 6 筆 `JPG/{SOP UID}.jpg` |
| `["dicom","jpeg"]` | 6 筆（記 DICOM 那一份） |

`claimedBy` 有值，證明 claim 機制運作。

> #### 部署後才現形的兩個問題（都已修）
>
> **① JPEG 每張都 NullReferenceException**（`PackageService.cs:213` 的 `AsSharpImage`）
>
> `new DicomImage(fileName)` 是**直接 new、不經 DI**，靠 fo-dicom 的**靜態
> ServiceProvider** 找 ImageManager。`ConfigureServices` 裡的
> `AddImageManager<ImageSharpImageManager>()` 只設定了 host 的 DI，這條路沒接上，
> fallback 到預設的 `RawImageManager` —— 它產生的 `IImage` 不是 `ImageSharpImage`，
> `AsSharpImage()` 回 null 就 NRE。
>
> 對照專案裡其他用法就看得出來：Viewer 與 TestClient 都有
> `new DicomSetupBuilder().RegisterServices(…).Build()`，DicomWeb 走 ASP.NET Core
> 那條路也沒事，**只有這支 Generic Host 沒接**。
>
> 這是**既有缺陷**，不是階段 3 改出來的 —— 但 JPEG 路徑從未被啟用（`onlyJpeg` 沒有
> 任何設定來源），而 DICOM 那條路不 render，所以一直沒人發現。
>
> **② JPEG 全部失敗卻標成 `ready`**
>
> 逐檔的 `try/catch` 只記 log 不中斷，所以六張全炸也會走到最後標 `ready`。
> 實測就是這樣：那筆 DICOM+JPEG 的 job，DICOM 完全正常、JPEG 全滅，卻顯示成功。
> 現在累計成功／失敗數：全失敗丟例外標 `failed`；部分失敗仍交包，但把
> 「JPEG 有 N 張轉檔失敗」寫進 `ERROR_TEXT` —— 否則「248 張只出了 200 張」沒有人會發現。
>
> **教訓**：API 層與 DB 層都能在本機驗，但 worker 的影像轉檔依賴 ImageManager 的
> **執行期初始化** —— 那種東西只有真的部署跑起來才會現形。

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


---

## 8. 歷史清單與過期標記（REQ-020，2026-08-20 定案）

起因：Viewer 端要讓醫師看「自己過去匯出過什麼」。原本 `GET` 只吃單一 `jobRef`，
沒有清單。

### 8.1 身分：只在 JWT 下成立

歸屬取自憑證的 `sub`，這條原則不動：

| 認證 | `sub` | 清單的意義 |
|---|---|---|
| Keycloak JWT | 使用者 UUID | **這個人的歷史** |
| API Key | 金鑰 id | 這把金鑰的歷史（多人共用會混在一起） |

Viewer 走 JWT（2026-08-20 確認），所以「當下使用者的歷史」自然成立，
不必在 `PACKAGE_JOB` 加任何欄位。

**絕對不提供「指定 owner」的查詢參數** —— owner 一律由憑證決定，
否則這個端點就從「只能看自己」退化成越權查詢工具。將來若要管理員看全部，
另開 scope（`export.admin`）分開設計。

### 8.2 端點

```
GET /export/packages
  ?limit=20                                 # 預設 20，上限 100（超過夾到 100，不報錯）
  &beforeJobId=1234                         # 游標：取 jobId 小於它的
  &state=ready&state=failed                 # 可重複；不認識的值回 400
  &createdFrom=2026-08-01T00:00:00+08:00    # 含
  &createdTo=2026-09-01T00:00:00+08:00      # 不含
```

單筆 `GET /export/packages/{jobRef}` 完全不動。

**分頁用 cursor 不用 offset。** 歷史清單一直有新 job 插到最前面，`offset` 分頁
往下捲會重複或漏掉項目。

**排序用 `jobId DESC` 不用 `createdAt DESC`。** 兩者實務同序（`JOB_ID` 是遞增序列），
但資料庫上已有 `idx_package_job_requested_by ("REQUESTED_BY", "JOB_ID" DESC)`，
正好就是這個查詢要的索引；改用 `createdAt` 排序吃不到它，還多一個同秒平手的問題。

**日期邊界起含終不含。** 查 8 月整月就傳 `08-01` 到 `09-01`，不必去湊
`08-31T23:59:59.999` —— 那個「漏掉最後一毫秒」的 bug 每個專案都會犯一次。

**時區必須明確**：只接受帶偏移的 ISO 8601，裸日期 `2026-08-01` 回 400。
裸日期一定要猜時區，猜錯就差 8 小時而且錯得很安靜；前端產帶偏移的字串很容易。

**不給預設日期範圍。** 鎖住成本的是 cursor 分頁（沒帶日期時 `limit=20` 一樣
只取最新 20 筆）。偷偷預設「近 30 天」會讓「找不到三個月前的紀錄」變成隱形問題。
預設範圍是 UI 的事，畫面上看得到。

**回 `hasMore` 不回 `total`。** 取 `limit + 1` 筆、多的那筆只用來判斷不回傳，
比 `COUNT(*)` 便宜得多，對無限捲動也夠用。

回應：

```jsonc
{
  "items": [
    {
      "jobId": 1234, "state": "ready", "progress": 100, "priority": 0,
      "downloadReady": true, "packagedCount": 744, "errorMessage": null,
      "createdAt": "2026-08-19T15:33:12+08:00",
      "modifiedAt": "2026-08-19T15:35:48+08:00"
    }
  ],
  "hasMore": true
}
```

`createdAt` / `modifiedAt` 對單筆 GET 也要補 —— **`get_package_job` 早就有回這兩個值，
只是 API 層沒映射到 `ExportJobStatus`**，所以純粹是 C# 的事，不用改 proc。

**過濾必須在 SQL 裡做。** 單筆是「抓回來再在 API 層比對 `RequestedBy`」，
清單不能這樣（等於先撈全部再過濾），要新開 `export.list_package_jobs(jsonb)`。

**稽核要寫**：記使用者、查詢條件、回傳筆數；**不記回傳的 jobId 清單** ——
那會讓稽核紀錄膨脹得很快，而要追「誰動了哪個 job」，建立／下載那兩條稽核才是正本。

### 8.3 過期標記：讓刪檔的人負責記錄

**問題**：`downloadReady` 是 `RESULT_PATH IS NOT NULL AND STATE = 'ready'`，
**從來沒有確認檔案還在不在**。而 worker 主迴圈裡有一段清理
（[PackageService.cs:74](../HD.Net10/HD.MediaPackage/Service/PackageService.cs)）
會按 `CreationTime` 刪掉超過 **寫死 2 天** 的目錄與 zip，**且完全不碰 DB**。

所以檔案清掉之後，清單會一路顯示可下載，點下去才失敗。單筆查詢遇不到
（剛建完就查），清單一定會遇到。

**兩條路，選了 B：**

- **A：查詢時檢查檔案** —— 清單 20 筆就 20 次檔案系統呼叫（NAS 上更慢），
  而且有 TOCTOU：查的時候在、下載時被清掉。
- **B：清理時把狀態改掉** —— 「檔案沒了」由**做這件事的人**負責記錄，
  而不是讓每個讀取者事後去猜。查詢零成本，且永遠正確。

**做法**：新增 `export.expire_package_jobs(p_days integer)` —— 找出 `STATE='ready'`
且 `MODIFIED_AT` 早於 N 天的 job，回傳它們的 `RESULT_PATH`，同時把 `STATE` 改成
`expired`、`RESULT_PATH` 設 `NULL`。worker 改成**先問 DB 要刪哪些**，再去刪那些路徑。

這樣「哪些檔案該刪」與「哪些 job 該過期」變成同一個判斷，而不是現在的兩套各自為政。

需要一併調整 `PACKAGE_JOB_STATE_check`（目前只允許 6 個值，要加 `expired`）。

**已決**：

1. **過期的 job 留著**，只改狀態、清路徑。歷史紀錄的價值就在「我三個月前匯出過這批」，
   而且稽核也需要；整列刪掉的話清單會莫名其妙變短。
2. **保留天數改成設定值，預設 7 天**（現在寫死 2 天）。醫師匯出後隔天想再下載一次，
   2 天太短。放進 `HD_CONFIG` 的 `BURN_WORKSTATION`。

使用者在清單上會看到 `state=expired`、`downloadReady=false`，
比「看起來能載、點了失敗」清楚得多。

### 8.4 順帶查出來的既有問題：光碟封面只認第一個病人

`claim_package_job_payload` 建 `studyInfoList` 是 `GROUP BY STUDY_INSTANCE_UID`，
每個 study 各自帶 `patientId` / `patientName`，**所以一個 job 裝多 study、
甚至跨病人，資料層完全支援**。

但 [PackageService.cs:489](../HD.Net10/HD.MediaPackage/Service/PackageService.cs)：

```csharp
if (job.coverInfo != null)
{
    DicomFile dcmTemp = DicomFile.Open(job.studyInfoList[0].fileList[0]);
    // 從這一張影像抽 tag 去填光碟封面標籤
```

封面標籤的值取自**第一個 study 的第一張影像**。跨病人的 job 燒出來的光碟，
**封面只印病人 A，片子裡卻同時有 A 和 B** —— 拿到片子的人會以為整張都是 A 的。
臨床上會出事。

範圍限於 `coverInfo != null`（燒錄／光碟情境）；Viewer 的 zip 下載不受影響。

**決策（2026-08-20）：封面要能呈現多人**，不是跨病人就拒收。獨立項目，
不併入 REQ-020，見 backlog REQ-021。

### 8.5 已知的擴充點（現在刻意不做）

- **`patientId` / `accessionNumber` 篩選**：那些資料在 `PACKAGE_JOB_SELECTION`，
  是三欄式 UID，`patientId` 還要再往 `RC_STUDY` join，查詢會變重。而且一個 job
  可能橫跨多病人，清單上放單一 `patientId` 欄位反而會誤導。晚一版再說。
- **日期範圍的索引**：加了日期之後它是殘餘過濾 —— 查久遠區間時得從最新往回走。
  單一使用者幾百筆 job 完全無感。等到有人累積到幾千筆而且常查久遠區間，
  再加 `("REQUESTED_BY", "CREATED_AT" DESC, "JOB_ID" DESC)` 並把 cursor 改成
  `(createdAt, jobId)` 複合游標。現在做是過度設計。
