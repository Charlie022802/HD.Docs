# 儲存層（online / nearline / archive）與資料補回

主 PACS 的影像分三層存放，本文記錄**資料模型**、**autopilot 清快取的機制**、
以及 2026-08-24 在若瑟醫院處理資料流失時建立的**稽核與補回流程**。

相關：[main-pacs.md](main-pacs.md)、[backlog REQ-022/REQ-023](../backlog.md)

---

## 1. 資料模型

### 三層與兩組欄位

| 層 | `VOLUME_CACHE.TYPE` | `RC_LOCATION` 的欄位 | `RC_STUDY` 的旗標 |
|---|---|---|---|
| 線上 | `ONLINE` | `VOLUME_REF` | `IS_CACHED` |
| 近線 | `NEARLINE` | `NEARLINE_VOLUME_REF` | `IS_NEARLINE_CACHED` |
| 歸檔快取 | `ARCHIVE` | `ARCHIVE_VOLUME_REF` | `IS_ARCHIVE_CACHED` |
| 已歸檔 | （`ARC_*` 系列） | `ARC_LOCATION_REF` | `IS_ARCHIVED` |

**位置是 per-object（`RC_LOCATION`），旗標是 per-study（`RC_STUDY`）。**
旗標只是彙總，正本永遠是 `RC_LOCATION`。重算的唯一入口是
`public.update_study_statistical_info(study_ref)`。

這個「彙總」有個會咬人的性質：**同一筆 study 的影像若散在不同層，四個旗標可能全部是 false**
（沒有任何一層「全部都有」）。四個全 false 的 study 會出現兩種症狀：

- `query_dicom` 查不到（系統認為它哪裡都沒有）
- `get_next_map_job` 的 STUDY_CLOSE 分支報
  `Cache volume error: All object paths must use the same cache type.`
  （那段其實是在測「四個旗標有沒有任何一個為 true」）

### 檔案路徑

```
VOLUME_CACHE.DIR_PATH / RC_LOCATION.DIRECTORY / lpad(to_hex(ORDINAL), 8, '0')
```

`DIRECTORY` 是**檢查日期**（例：`2024/0904`）。

組路徑要用 `||` 不要用 `CONCAT_WS`：`CONCAT_WS` 會**跳過 NULL**，於是
「這一層根本沒有位置」會被組成一個看起來合法的相對路徑，接著被誤判成「檔案遺失」。
（實際踩過：一次稽核因此報出 3463 個假的遺失，真實數字是 7。）

### get_object_path

```sql
public.get_object_path(object_ref, specify_type, file_type)
```

`specify_type` 給 NULL 時會**依 study 旗標自動選層**；四個旗標都 false 就落到
`ELSE RAISE EXCEPTION 'Not recognize specify type: <NULL>'`——這個例外會往上冒到
`get_next_map_job`，**整批 job 一起掛掉**，不是只跳過那一筆。

明確指定層別（例如 `'online'`）時不會拋例外，但**查不到位置就回 NULL**，
而拿到 null 路徑的 C# 端會丟
`Value cannot be null. (Parameter 'fileName')`——同樣是整批 job 掛掉。

---

## 2. autopilot 清快取

設定在 `AE_CONFIG` 的 `WORKFLOW` / `AUTOPILOT`：

```json
{ "sleepTime": 3000, "redLine": 90, "amberLine": 70,
  "red":   { "isUsing": true,  "hrsSinceCreated": 12,  "hrsSinceAccessed": 12 },
  "amber": { "isUsing": false, "hrsSinceCreated": 24,  "hrsSinceAccessed": 24 },
  "green": { "isUsing": false, "hrsSinceCreated": 168, "hrsSinceAccessed": 168 } }
```

`VOLUME_CACHE.ACTIVITY` 的 G/Y/R 由 `update_workflow_info` 依這兩條水位線算出，
`get_next_delete_study` 再依當前顏色套用對應的規則組挑出要清的 study。

**清除的行為是把 `RC_LOCATION` 的 volume ref 設成 NULL、保留該列**
（不是刪列），`RC_OBJECT` 也留著。所以「有 `RC_LOCATION` 列」完全不代表「有檔案」，
判斷有沒有檔案一定要看 ref 本身。

### v2.0.22 沒有 nearline 守門（重要）

`get_next_delete_study` 在 **v2.0.27** 才加入「沒有 nearline 副本就不清」的保護。
在那之前的版本會連唯一一份都刪掉，留下沒有任何位置的 `RC_OBJECT` 空殼——
**這就是若瑟 2024 年那批資料流失的成因**。

尚在 v2.0.22 的院所必須升版，否則同一件事會再發生。

---

## 3. 損壞的判定

唯一可靠的判準是**「有 `RC_OBJECT` 但三層都沒有位置」**：

```sql
SELECT DISTINCT o."STUDY_REF"
FROM public."RC_OBJECT" o
WHERE NOT EXISTS (
	SELECT 1 FROM public."RC_LOCATION" l
	WHERE l."OBJECT_REF" = o."OBJECT_REF"
	  AND (l."VOLUME_REF" IS NOT NULL
	    OR l."NEARLINE_VOLUME_REF" IS NOT NULL
	    OR l."ARCHIVE_VOLUME_REF" IS NOT NULL));
```

**不要只判 online。** 「線上被正常清掉、nearline 還在」是完全健康的狀態，
而且是全庫大多數 object 的狀態——只判 online 會撈出幾十萬筆，
拿去當刪除依據就是自己製造資料流失。

另一個常用的風險指標是**「線上有檔但 nearline 沒有」**，這些是下次 autopilot 清快取時
會變成空殼的曝險：

```sql
SELECT count(DISTINCT o."STUDY_REF"), count(*)
FROM public."RC_OBJECT" o JOIN public."RC_LOCATION" l USING("OBJECT_REF")
WHERE l."VOLUME_REF" IS NOT NULL AND l."NEARLINE_VOLUME_REF" IS NULL;
```

**這個數字應該長期維持 0。**

---

## 4. 工具

兩支都在 `HD.Net10/tools/HD.StorageAudit/`。

### hd-storage-audit（C#，self-contained linux-x64）

DB 與實體檔案的對帳，預設唯讀。

```bash
export HDPACS_CONN='Host=127.0.0.1;Port=5432;Database=HDPACS;Username=postgres;Password=...'
hd-storage-audit --study 2451819 --csv /tmp/audit.csv
hd-storage-audit --target flagless                    # 四個旗標全 false 的 study
hd-storage-audit --target flagless --fix-flags        # 檔案齊全者校準旗標
hd-storage-audit --target flagless --repair-tiers --apply   # 補到兩層都有再校準
```

輸出要看三個數字：`部分遺失`、`實際不存在`、**`object 完全沒有任何位置紀錄`**。
最後那個才是真正的內容缺漏——**前兩個是 0 不代表 study 完整**，
因為它們只檢查「DB 說有的檔案在不在」，對「DB 根本沒說它在哪」的 object 視而不見。

`--repair-tiers` 用於「影像分散兩層導致四個旗標全 false」的 study：把每個 object 補到
online 與 nearline 都有一份，再校準旗標。這只解決**可見性**，不會把被刪掉的影像變回來。

自帶執行環境（`SelfContained`），因為各院所的 .NET runtime 版本不一，
到現場才發現版本不合時通常沒有裝 SDK 的餘裕。

### purge-for-resend.sh（bash + psql）

「刪掉受損 study 以便從上游重送」的批次工具，**預設乾跑，要 `--apply` 才動手**。

```bash
export PGHOST=127.0.0.1 PGDATABASE=HDPACS PGUSER=postgres PGPASSWORD=...
purge-for-resend.sh --studies /tmp/studies.txt              # 乾跑
purge-for-resend.sh --studies /tmp/studies.txt --limit 5 --apply
```

每筆的順序（順序本身就是設計，不能調換）：

1. 前置檢查：`STATUS='N'`（未 close）、`IS_ARCHIVED=true`、沒有 accession → 略過
2. **先把 nearline 檔案路徑存檔**——刪除後 `RC_LOCATION` 就沒了，之後清孤兒檔只能靠這份
3. 清掉三層都沒位置的空殼 object
4. `delete_dicom` 排 CACHE_DELETE，輪詢到 `RC_STUDY` 歸零
5. 記下 accession，供上游重送

乾跑的 nearline 清單寫到 `nearline-dryrun-不可刪/`，與實跑的 `nearline/` 分開。
兩者長得一樣但意義相反：實跑的是「已經沒人指向、可以刪」，乾跑的是「還活著、絕對不能刪」。
（曾因萬用字元把乾跑目錄一起收進去，差點刪掉 319 張倖存影像。）

---

## 5. 補回流程（runbook）

以若瑟 2026-08-24 那次為例，上游是 NONDICOM 主機。

### 前置：先讓 study 可見

若損壞的 study 因為影像分散兩層而四個旗標全 false，先補齊，否則 STUDY_CLOSE 會卡
`Cache volume error`：

```bash
hd-storage-audit --target flagless --repair-tiers --apply
```

### ① 產出待處理清單（PACS 端）

用第 3 節的「三層都沒有位置」查詢。

### ② 比對上游有沒有（關鍵閘門）

**上游沒有的絕對不能刪**——刪掉等於把目前倖存的影像也毀掉。
把 accession 清單送到上游主機比對，只處理交集：

```bash
psql -d HDPACS <<'SQL'
CREATE TEMP TABLE acc(a text);
\copy acc FROM '/tmp/resend.txt'
\copy (SELECT DISTINCT r."ACCESSION_NUMBER" FROM public."RC_STUDY" r JOIN acc ON acc.a = r."ACCESSION_NUMBER") TO '/tmp/found.txt'
SQL
```

**兩台主機的 `STUDY_REF` 是各自獨立的編號，唯一的接點是 accession。**

### ③ 刪除（PACS 端）

`purge-for-resend.sh --apply`。先 `--limit 5` 試跑再全量。

### ④ 重送（上游端）

accession 轉成上游自己的 `STUDY_REF`，把送檔 job 打回未處理：

```sql
UPDATE public."NONDICOM_SEND_JOB" SET "STATUS" = 'N'
WHERE "STUDY_REF" IN (SELECT s."STUDY_REF" FROM public."RC_STUDY" s JOIN acc ON acc.a = s."ACCESSION_NUMBER");
```

### ⑤ 驗收

**用 accession 查，不要用 study_ref**——重送回來的是新編號。

close 前上游可能把一筆拆成多筆、且帶著暫時性的 Study Instance UID；
**close 之後 STUDY_CLOSE 會 reconcile 回原本的 UID 並併成一筆**，
所以外部（報告、光碟、既有連結）不會因為重送而斷掉。驗收要等 close 完成。

```bash
hd-storage-audit --study $(paste -sd, /tmp/studies-new.txt)
```

`object 完全沒有任何位置紀錄` 歸零才算補完。

### ⑥ 善後

- 清 nearline 孤兒檔（CACHE_DELETE 只刪 online 檔，但 `RC_LOCATION` 整列刪掉，
  nearline 的實體檔會失去所有指向）。建議放一天再刪。
- 確認全庫「線上有檔但無 nearline」回到 0，沒有的話用
  `insert_study_job` 補 `NEARLINE_BACKUP`。

---

## 6. 踩過的坑

**`delete_dicom` 的 key 是 `level` 不是 `deleteLevel`。**
另外它只回 `true`/`false` 加 WARNING，不會拋例外——批次裡很容易把被擋下當成做完了。
會被擋的情況：`STATUS='N'`（除非 `skipNewStudy=false`）、`IS_ARCHIVED=true` 且要 `deleteDatabase`。

**`delete_dicom` 不是同步刪除**，它只設 `IS_CACHED=false` 並插一筆 CACHE_DELETE job。
DB 的列是在 job 回報 `D` 之後由 `update_map_job_status` 刪的。
job 回報 `E` 就一列都不會刪，留下「study 還在但 `IS_CACHED` 已是 false」的半殘狀態。

**完成的 job 會從 `MAP_JOB` 被刪掉**（`STATUS='D'` 且 `TYPE != 'CMOVE'`）。
所以批次監控的判準是「job 不見了＝成功」，不能等它變成 `D`。
唯一可靠的完成訊號是 `RC_STUDY` 真的歸零。

**整筆都是空殼的 study 不能走 CACHE_DELETE。**
檔案清單會是空陣列，`get_next_map_job` 的 `jsonb_array_length > 0` 不成立就不派工，
job 會**永遠停在 `N` 且沒有任何錯誤訊息**。這種要直接刪 DB
（`RC_LOCATION` → `RC_OBJECT` → `RC_SERIES` → `RC_STUDY`，順序照 `update_map_job_status`）。

**`CALL` 的參數不能放子查詢**，PL/pgSQL 區塊裡也一樣。要先 `SELECT ... INTO` 變數。

**`insert_study_job` 有兩種簽章**（`(text,int,int,bool)` 與 `(jsonb)`），
jsonb 版的 key 是 `studyRef`（單數）。NEARLINE_BACKUP 分支有兩道前置檢查：
沒有可用的 NEARLINE 磁碟區就 `RAISE WARNING` 後放棄、
`IS_NEARLINE_CACHED` 已是 true 就印 `Already backup to nearline!` 後放棄。
旗標說謊時（per-study 蓋不住 per-object）要先 `update_study_statistical_info` 校準才排得進去。

**各院所的 schema 精簡程度不一。** 若瑟 148 沒有 `NONDICOM_OBJECT` / `NONDICOM_STUDY`
（那是 NONDICOM 主機才有的），proc 內部都用 `information_schema` 探表後才刪。
自己寫批次腳本時要照做。

**旗標是宣稱，不是事實。** 這次事件三度因為相信 DB 的宣稱而誤判：
`NEARLINE_VOLUME_REF IS NOT NULL` 就當作有備份、`CONCAT_WS` 組出的路徑就當作檔案該在那裡、
只稽核「DB 說有的檔案」而漏掉沒有位置的 object。**每一次都只有實際去 `File.Exists` 才發現。**

---

## 7. 若瑟 2026-08-24 事件紀錄

| | |
|---|---|
| 成因 | 線上磁碟區在 2024-05~11 觸及 90% 紅線，v2.0.22 的 `get_next_delete_study` 沒有 nearline 守門，把沒有備份的唯一一份刪掉 |
| 受損 | 122 筆 study、748 張影像失去所有位置 |
| 已復原 | **79 筆、1066 個檔案零缺漏**（從 NONDICOM 重送） |
| 不可復原 | 43 筆、449 張（儀器直送、NONDICOM 沒有中繼副本），另有 319 張倖存 |
| 曝險 | 補完 8089 筆 NEARLINE_BACKUP 後歸零 |

處理過程另外做的事：8089 筆待備份的 study 補上 nearline（VOL 7 用量增加約 49 GB）、
126 筆分散兩層的 study 補齊並校準旗標（複製 871 個檔案、1754 MB）。

**尚未處理**：若瑟仍在 v2.0.22（要升到 v2.0.27 以上才有 nearline 守門）、
nearline VOL 3 已達 94.6%、43 筆不可復原的明細要送醫院。
