# 若瑟 DB 升級評估（2.0.22 → 2.0.27）

**結論先講**：不能直接跑。`2.0.26` 與 `2.0.27` 各有一處會**讓腳本中止**，另有一處會在升完之後
**讓 hd-web-server 的報告端點失效**。三處都有明確修法，但其中一處牽涉同事維護的服務。

盤點日期 2026-08-26。對象主機 `10.10.1.148`（`HDPACS148`）。

---

## 一、現場環境（實測）

| 項目 | 值 |
|---|---|
| OS | RHEL 9.2、glibc 2.34 |
| PostgreSQL | **16.0** |
| SELinux | Permissive |
| .NET | **只有 6.0.22**（沒有 8 也沒有 10） |
| DB 版本 | **2.0.22** ＋ 已單獨補上 2.0.27 的 `get_next_delete_study`（版本號未動） |
| 服務 | 全部 `net6.0`、`Dicom.Core.dll`（**fo-dicom 4**） |
| 部署方式 | **手工平鋪目錄**，無版本化目錄／current；unit 檔最早 2023-09 |
| 服務部署日期 | 2024-12 ~ 2026-03（多數 2026-01-09；`hd-pacs` 是 2025-12-18） |

**服務的版本號判斷不了新舊**：`deps.json` 一律 `HD.*/2.0.4`，但原始碼的 csproj 現在也還是
`2.0.4` —— 那個欄位自 net10 遷移後就沒動過。真正能判斷世代的是 `tfm`（net6）與相依套件
（fo-dicom 4 vs 我們現在的 fo-dicom 5）。

**存在的 schema**：`admin`(10)、`dicom_util`(9)、`export`(23)、`kiosk`(7)、`report`(26)、
`viewer_station`(34)。**沒有 `customize`**（那是台大 EEG 客製）。

---

## 二、變更盤點

`2.0.23` ~ `2.0.27` 共動到 **70 支** function／procedure。逐一比對簽章的結果：

- **簽章改變：2 支**
- **真正的 `DROP`：3 個**
- 其餘皆為「簽章相同（只改內部）」或「全新物件」

### 簽章改變

| proc | 若瑟現況 | 升級後 | 影響 |
|---|---|---|---|
| `export.get_disc_info` | `(job_ref integer)` | `(jsonb, text)` | **無** —— 沒有 `DROP`，新的是**多載**，舊簽章留著 |
| `report.get_report_format_list` | `()` | `(json)` | **有** —— 2.0.27 明確 `DROP` 了無參數版（見下） |

### 真正的 DROP

| 版本 | 語句 | 若瑟狀態 | 後果 |
|---|---|---|---|
| 2.0.25 | `DROP FUNCTION IF EXISTS export.get_job(jsonb)` | 存在 | 安全（drop 後重建同簽章） |
| 2.0.26 | `DROP VIEW public."VIEW_MWL"` | **不存在** | ⛔ **腳本中止** |
| 2.0.27 | `DROP FUNCTION IF EXISTS report.get_report_format_list()` | 存在且有人用 | ⚠️ **升完功能失效** |

### 其他語句

`ALTER TABLE` 幾乎全用 `ADD COLUMN IF NOT EXISTS`，是冪等的。但**`IF NOT EXISTS` 只保護欄位、
不保護表** —— 表不存在照樣中止。實測結果：

| 物件 | 若瑟 | 判定 |
|---|---|---|
| `export."EXPORT_JOB"`、`kiosk."KIOSK_DISC_EVENT"`、`kiosk."KIOSK_CARD_EVENT"`、`report."REPORT_SAVED"`、`public."HD_CALLBACK"` | 存在 | 安全 |
| `public."VIEW_MWL"` | **不存在** | ⛔ 見上 |
| `public."HD_USER_AUDIT_LOG"` | **不存在** | ⛔ **腳本中止**（見下） |
| `idx_hd_callback_destination_status`（無 `IF NOT EXISTS`） | 不存在 | 安全 |
| `KIOSK_DISC_EVENT."IS_COPIED"`（2.0.25 唯一沒加 `IF NOT EXISTS` 的欄位） | 不存在 | 安全 |

---

## 三、三個阻擋項與修法

### A. `VIEW_MWL` 不存在，但 2.0.26 無條件 DROP 它

```sql
-- db_update_v2.0.26.sql:2010
DROP VIEW public."VIEW_MWL";
CREATE OR REPLACE VIEW public."VIEW_MWL" AS ...
```

那是「重建」而非「移除」（改欄位名必須先 drop），但**沒有 `IF EXISTS`**。
若瑟從來沒有這個 view（它的 MWL 走 `query_worklist(jsonb, jsonb)`），所以腳本會在這裡中止。

**修法**：改成 `DROP VIEW IF EXISTS public."VIEW_MWL";`。
這對已經有該 view 的站台行為完全不變，是純粹的加固。

### B. `HD_USER_AUDIT_LOG` 是 DicomWeb 的表，但 2.0.27 假設它存在

```sql
-- db_update_v2.0.27.sql:830
ALTER TABLE public."HD_USER_AUDIT_LOG" ADD COLUMN IF NOT EXISTS "PRODUCT" ...
```

那張表**只有 `HD.Pacs.DicomWeb/db/init_dicomweb.sql` 會建**，主更新鏈從來沒建過它。
若瑟沒裝 DicomWeb，所以沒有那張表。

**這不是若瑟特有的問題** —— **任何沒裝 DicomWeb 的醫院都會卡在 2.0.27**。
主 PACS 的更新鏈相依於另一個產品才會建立的表，是設計上的洩漏。

**修法（二選一）**：
1. 把那兩行包進 `DO $$ BEGIN IF to_regclass('public."HD_USER_AUDIT_LOG"') IS NOT NULL THEN ... END IF; END $$;`
2. 把「加欄位」搬回 DicomWeb 自己的 migration —— **那才是它該待的地方**

建議 2，1 是過渡。

### C. `report.get_report_format_list()` 被刪，而 hd-web-server 呼叫無參數版

```ts
// hd-web-server/src/routes/api/v2.0/report/utils.query.ts:329
const sql = `SELECT report.get_report_format_list()`;
```

2.0.27 `DROP` 了 `()` 版並改成 `(json)`。升級後這個呼叫會得到
`function report.get_report_format_list() does not exist`，**報告格式清單端點直接失效**。

**⚠️ 這是現行版本就已經斷裂的相容性，不只是若瑟的升級問題。**
我們 repo 裡的 hd-web-server 也是這樣呼叫的 —— 也就是說**任何 DB ≥ 2.0.27 又跑 hd-web-server
的環境，那個端點都是壞的**，只是目前跑 hd-web-server 的機器都還在舊 DB，所以沒人發現。

**需要同事確認**：他手上的 hd-web-server 有沒有改成傳 json 參數的版本？
- **有** → 若瑟升級時必須連 hd-web-server 一起更新，兩者不能拆開
- **沒有** → 那 2.0.27 的那個 `DROP` 本身就該檢討；至少要保留一個無參數多載

---

## 四、不構成風險的部分

- **`store_dicom`、`get_mwl_view`**：若瑟沒有這兩支，它們確實是 2.0.23／2.0.26 新增的。
  建出來對現況零影響 —— 舊服務不會呼叫它們（若瑟的進檔走 `insert_dicom_info`）。
- **`customize` schema**（台大 EEG 客製）：若瑟沒有，建了也不會被用到。
- **`kiosk` 那批**：若瑟有 kiosk schema 與表，但沒有跑 kiosk 服務；欄位加上去無害。
- **PostgreSQL 16**：這些腳本是為更舊的環境寫的，語法上不會有問題。

---

## 五、建議的做法

### 預演環境：用若瑟的 DB 複本，不要用「形似的機器」

`.163` 雖然形態相近，但它的 **DB 狀態與若瑟不同**（2.0.26 vs 2.0.22），
在上面跑一遍不能證明什麼。真正有鑑別力的預演是：

1. 從若瑟取一份 `pg_dump`
2. 還原到任一台的暫存資料庫
3. 依序跑 `2.0.23` → `2.0.27`，**用 `-v ON_ERROR_STOP=1`**
4. 每一版跑完檢查 `HD_CONFIG` 的版本號有沒有前進

這會**精確重現**若瑟會遇到的每一個錯誤，而且失敗零成本。

> 順帶一提：若瑟的 DB **自 2026-04-02 起沒有備份**（`SQLBACK` 裡最新的一份就是那天）。
> 升級前無論如何都要先做一份完整 dump —— 而這件事本身的優先級可能比升級還高。

### 升級順序

1. 修好 A、B 兩個阻擋項（改腳本，讓它們對「沒有那個物件」的站台也能跑）
2. 與同事確認 C，決定是「一起更新 hd-web-server」還是「保留無參數多載」
3. 取 dump → 預演 → 修到全綠
4. 排維護時段，先做完整備份，再依序上
5. 升完的驗證重點：**進檔（C-STORE）**、**MWL 查詢**、**報告格式清單**

### 這次升級**不包含**服務更新

若瑟的服務是 net6 + fo-dicom 4，而現行原始碼是 net10 + fo-dicom 5，那是跨兩個世代的遷移，
應該是**獨立的一項工程**，不要跟 DB 升級綁在一起。本評估的前提是「**服務不動，只升 DB**」，
而上面的盤點正是在回答「舊服務能不能在新 DB 上活下去」。

---

相關：[systems/storage-tiers.md](systems/storage-tiers.md)、[systems/hd-web-server.md](systems/hd-web-server.md)、
記憶 `project_josef_site`、`project_nearline_flag_race`。
