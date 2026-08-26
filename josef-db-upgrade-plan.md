# 若瑟 DB 升級評估（2.0.22 → 2.0.27）

**結論先講（2026-08-26 已用若瑟的 DB 複本實際預演過）**：

- 腳本層面**只有一個阻擋項**，已修好並驗證通過 —— 現在 `2.0.22 → 2.0.27` 整條鏈跑得完。
- 升完之後**還有一處會壞**：`hd-web-server` 的報告格式清單端點（見三之三），需要與同事協調。
- 順帶查出 `insert_routing_job` 從來沒進過版控（已於 `2.0.38` 補回），
  以及**更新鏈與實際資料庫已經分岔**——那是本次最重要的發現，見三之四。

盤點日期 2026-08-26。對象主機 `10.10.1.148`（`HDPACS148`）。

> **預演方法**（結果可信的原因）：取若瑟的 schema dump ＋ `HD_CONFIG` 實際資料，
> 還原進 podman 的 `postgres:16` 容器（若瑟是 16.0），確認基準與實機一致
> （版本 2.0.22、`VIEW_MWL` 與 `HD_USER_AUDIT_LOG` 皆不存在），
> 再用 `-v ON_ERROR_STOP=1` 依序跑 23→27。**完全不碰任何生產機。**
>
> dump 是 pg_dump 18.2 產的、伺服器是 16，還原前要拿掉 `transaction_timeout`
> 與 `\restrict` 這些 17+ 才有的語句。

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
| 2.0.26 | `DROP VIEW public."VIEW_MWL"` | 不存在 | ✅ 安全 —— **同一支腳本前面就建了它**（見 A） |
| 2.0.27 | `DROP FUNCTION IF EXISTS report.get_report_format_list()` | 存在且有人用 | ⚠️ **升完功能失效** |

### 其他語句

`ALTER TABLE` 幾乎全用 `ADD COLUMN IF NOT EXISTS`，是冪等的。但**`IF NOT EXISTS` 只保護欄位、
不保護表** —— 表不存在照樣中止。實測結果：

| 物件 | 若瑟 | 判定 |
|---|---|---|
| `export."EXPORT_JOB"`、`kiosk."KIOSK_DISC_EVENT"`、`kiosk."KIOSK_CARD_EVENT"`、`report."REPORT_SAVED"`、`public."HD_CALLBACK"` | 存在 | 安全 |
| `public."VIEW_MWL"` | 不存在 | ✅ 2.0.26 自己會先建（見 A） |
| `public."HD_USER_AUDIT_LOG"` | **不存在** | ⛔ **唯一的腳本阻擋項**（見 B，已修） |
| `idx_hd_callback_destination_status`（無 `IF NOT EXISTS`） | 不存在 | 安全 |
| `KIOSK_DISC_EVENT."IS_COPIED"`（2.0.25 唯一沒加 `IF NOT EXISTS` 的欄位） | 不存在 | 安全 |

---

## 三、三個推測的阻擋項，實跑後只剩一個

### ~~A. `VIEW_MWL` 不存在，但 2.0.26 無條件 DROP 它~~ —— **這個判斷是錯的**

我原本預測 2.0.26 的 `DROP VIEW public."VIEW_MWL";`（沒有 `IF EXISTS`）會中止，
因為若瑟沒有那個 view。**預演證明不會** —— **2.0.26 自己在第 1123 行就先建了那個 view**
（註解寫著「Jill 增加查詢mwl view」），第 2010 行才 DROP 重建。同一支腳本內先建後刪。

**錯在哪**：我拿每一支腳本去對「2.0.22 的基準」做靜態分析，但**更新鏈是累積的，
而且單一腳本內部也有順序**。靜態分析看不出這兩件事。

→ **這就是為什麼要預演。** 三個推測的阻擋項，實跑之後只剩一個。

### B. `HD_USER_AUDIT_LOG` 是 DicomWeb 的表，但 2.0.27 假設它存在

```sql
-- db_update_v2.0.27.sql:830
ALTER TABLE public."HD_USER_AUDIT_LOG" ADD COLUMN IF NOT EXISTS "PRODUCT" ...
```

那張表**只有 `HD.Pacs.DicomWeb/db/init_dicomweb.sql` 會建**，主更新鏈從來沒建過它。
若瑟沒裝 DicomWeb，所以沒有那張表。

**這不是若瑟特有的問題** —— **任何沒裝 DicomWeb 的醫院都會卡在 2.0.27**。
主 PACS 的更新鏈相依於另一個產品才會建立的表，是設計上的洩漏。

**✅ 已修（2026-08-26）**：`db_update_v2.0.27.sql` 的那三行包進 `DO` 區塊，
先用 `to_regclass` 判斷表在不在，不在就 `RAISE NOTICE` 跳過。
對已經跑過 2.0.27 的站台（`.191`／`.199`）行為完全不變。

**但長遠仍該搬走**：「幫 DicomWeb 的表加欄位」本來就不該出現在主 PACS 的更新鏈裡，
那是跨產品的相依洩漏。加判斷只是讓卡住的站台先能升上去。

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

## 三之二、預演的實際結果（2026-08-26）

修好 B 之後，從乾淨基準重跑整條鏈：

```
2.0.23 ✔   2.0.24 ✔   2.0.25 ✔   2.0.26 ✔   2.0.27 ✔
最終版本：{"version":"2.0.27"}
```

升級後的狀態逐項驗證，六項預測全部命中：

| 驗證項 | 結果 | 判定 |
|---|---|---|
| `report.get_report_format_list` 的簽章 | 只剩 `(inparams json)` | ⚠️ 無參數版確實被刪 → C 成立 |
| `export.get_disc_info` 的簽章 | `(integer)` ＋ `(integer,text)` ＋ `(jsonb,text)` | ✅ 舊多載留著，舊呼叫端安全 |
| `HD_USER_AUDIT_LOG` 是否被建出 | 否 | ✅ 判斷正確跳過，沒有誤建 |
| `VIEW_MWL` 是否存在 | 是 | ✅ 2.0.26 自己建的 |
| `get_next_delete_study` 有 nearline 保護 | 是 | ✅ |
| `store_dicom` 是否建出 | 是 | ✅ 新增，舊服務不呼叫 |

**限制**：這是 schema-only 的預演（dump 不含資料，只補了 `HD_CONFIG` 的 26 列）。
它能證明「腳本跑得完、物件變成預期的樣子」，**不能證明資料相關的行為**
（例如某個 backfill 在有幾百萬列時的表現）。不過本次三個風險點都與資料無關。
## 三之三、最新版 hd-web-server 與 DB 2.0.27 的完整相容性檢查（2026-08-26）

既然預演資料庫已經在 2.0.27，就把 `hd-web-server`（repo 內目前最新版）呼叫的每一支 proc
拿來對照。**36 支呼叫裡有 34 支吻合，兩支對不上：**

| proc | 程式傳的參數 | DB 2.0.27 | 判定 |
|---|---|---|---|
| `report.get_report_format_list` | **0 個** | 只有 1 個參數版 | ⚠️ 2.0.27 刪了無參數版，程式沒跟上 |
| `public.insert_routing_job` | 1 個 | **完全沒有這支** | ⚠️ 見下 |
| 其餘 34 支（含 `export.get_disc_info` 的 2 參數版） | — | 吻合 | ✅ |

### `insert_routing_job` 不是版本落差，是「不在版控裡的 proc」

| 來源 | PostgreSQL | 有這支嗎 |
|---|---|---|
| `HDPACS_20260720.sql` | 16.3 | **有** |
| `HDPACS_20260811.sql`（`.191`） | 18.4 | 沒有 |
| 若瑟（`10.10.1.148`） | 16.0 | 沒有 |

**而所有 `db_update_v2.0.*.sql` 從來沒有一支建立或刪除過它。**

也就是說它**是某台生產機上手動加的，從來沒進版控更新鏈**。
任何新建的資料庫都不會有它 —— `.191` 就沒有，若瑟也沒有。

呼叫點在 `src/routes/api/v2.0/report/utils.query.ts:319`（報告把影像路由到指定 AE）：

```
SELECT public.insert_routing_job($1)
```

**這比 `get_report_format_list` 嚴重**：那個只是版本落差，改一邊就好；
這個是**有一段功能靠著手工加在某台機器上的東西活著**。那台重建、或要部署到新醫院，
那條路就是死的，而且不會有任何警告。

主 PACS 這邊的對應功能是 `insert_study_job` 的 `jobType = 'ROUTE'` 分支
（那支在版控裡、也在若瑟上）—— 但兩者的參數與行為要比對過才能斷定是不是替代品。

### 要跟同事確認的兩件事

1. **`get_report_format_list`**：hd-web-server 要改成傳 json，還是 2.0.27 保留無參數多載？
2. ~~**`insert_routing_job`**：這支該進版控，還是改呼叫 `insert_study_job`？~~
   **✅ 已補回版控（`db_update_v2.0.38.sql`，Database repo `f59aa51`）** —— 使用者確認
   web 那邊有在用，所以是加回來而不是淘汰。定義逐字取自 2026-07-20 的 dump，
   相依性確認過（`get_ae_ref` 的第二參數有 `DEFAULT false`，一個參數的呼叫仍合法），
   並在容器裡實際套用與呼叫驗證過。


## 三之四、更新鏈是不完整的（2026-08-26 最重要的發現）

把若瑟的 DB 複本一路往上推，`2.0.28` ~ `2.0.34` 全過，**`2.0.35` 失敗**：

```
ERROR: column u.OTHERS does not exist
```

那是多院區的 `site_code_of_user`，它讀 `HD_USER."OTHERS" ->> 'siteCode'`。
**若瑟的 `HD_USER` 沒有 `OTHERS` 欄位，而更新鏈裡沒有任何一支加過它。**

這已經是同一天內第三個例子：

| 物件 | 誰需要它 | 更新鏈裡有嗎 | 誰有 |
|---|---|---|---|
| `public."HD_USER_AUDIT_LOG"` | `2.0.27` 的 `ALTER TABLE` | ❌ | 只有裝了 DicomWeb 的站台（`init_dicomweb.sql` 建的） |
| `public."HD_USER"."OTHERS"` | `2.0.35` 的 `site_code_of_user` | ❌ | `.191` 有，2026-07-20 的 dump 與若瑟都沒有 |
| `public.insert_routing_job` | hd-web-server 的報告路由 | ❌（已於 `2.0.38` 補回） | 2026-07-20 的 dump 有，`.191` 與若瑟都沒有 |

### 為什麼會這樣

`.191` 是**從 dump 建起來的**，不是靠跑腳本長出來的。所以只要有人直接在某台資料庫上改結構
（加欄位、加 proc），那個變更就會存在於後續的 dump 裡，卻**永遠不會進入更新鏈**。

### 這代表什麼

**你沒辦法靠跑腳本，把一個舊醫院升到 `.191` 的狀態。**

這不是「某幾支腳本有 bug」，是**更新鏈與實際資料庫已經分岔**。而且分岔是靜默的：
- 腳本在 `.191` 上跑得過（因為那些物件本來就在）
- 只有在**乾淨的舊站台**上跑，才會撞到「column does not exist」

也就是說，**每次只在 `.191` 驗證，就永遠驗不出這類問題**。

### 建議

1. **短期**：若瑟只需要到 `2.0.27`，上面的阻擋項都已排除，可以照計畫走。
2. **中期**：想讓任何站台能升到 `2.0.35+`，得先補上 `HD_USER."OTHERS"` 的 migration
   （以及後續版本可能還有的其他缺口——**要用同樣的方式一路試到最新版才知道**）。
3. **長期**：新的結構變更一律經由 migration 腳本，不要直接改資料庫。
   驗證時**至少要在一份「舊站台的 dump」上跑一次**，不能只在 `.191` 上跑。

> 本次已經證明這種驗證很便宜：一份 schema dump ＋ 一個 podman 容器，
> 十分鐘就能把整條鏈試完，而且失敗零成本。


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
在上面跑一遍不能證明什麼。**已採用的做法**（見開頭的預演方法）是取若瑟的 dump
還原進容器，那會**精確重現**若瑟會遇到的每一個錯誤，而且失敗零成本、不碰生產機。

日後其他醫院升級前應照同一套流程走一遍——**每間醫院缺的物件不一樣**
（若瑟缺的是 `HD_USER_AUDIT_LOG`，別間可能缺別的），靜態分析猜不準。

> 順帶一提：若瑟的 DB **自 2026-04-02 起沒有備份**（`SQLBACK` 裡最新的一份就是那天）。
> 升級前無論如何都要先做一份完整 dump —— 而這件事本身的優先級可能比升級還高。

### 升級順序

1. ~~修好 A、B~~ ✅ **已完成** —— A 是誤判、B 已加判斷，整條鏈預演通過。
2. **與同事確認 C**，決定是「一起更新 hd-web-server」還是「在 2.0.27 保留無參數多載」。
   **這是目前唯一還沒解決的事。**
3. ~~取 dump → 預演~~ ✅ **已完成**（見三之二）。
4. 排維護時段，**先做完整備份**（含資料，不是只有 schema），再依序上 23→27。
5. 升完的驗證重點：**進檔（C-STORE）**、**MWL 查詢**、**報告格式清單**。
   前兩項是臨床路徑，第三項就是 C。

### 這次升級**不包含**服務更新

若瑟的服務是 net6 + fo-dicom 4，而現行原始碼是 net10 + fo-dicom 5，那是跨兩個世代的遷移，
應該是**獨立的一項工程**，不要跟 DB 升級綁在一起。本評估的前提是「**服務不動，只升 DB**」，
而上面的盤點正是在回答「舊服務能不能在新 DB 上活下去」。

---

相關：[systems/storage-tiers.md](systems/storage-tiers.md)、[systems/hd-web-server.md](systems/hd-web-server.md)、
記憶 `project_josef_site`、`project_nearline_flag_race`。
