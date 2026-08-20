---
name: reference-pacs-db-schema
description: "Where the PACS database schema SQL lives, for referencing table/column structure"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 7bed9acc-56ee-46ab-93c0-bf8a5ea4e34c
  modified: 2026-08-17T09:33:46.280Z
---

**🔑 dump 已重拉 `HDPACS_20260818.sql`(schema-only,含 v2.0.30)。`.191` 現為 v2.0.31 已套用**(版本注記仍 2.0.30,因未結案)。

**大型 proc 的改法(2026-08-18 建立的慣例)**:要改 `store_dicom`(355 行)/`insert_dicom_info`(395 行)/`viewer_station.qc`(405 行)這種,**寫腳本從 dump 抽出後程式化套用修改,不手抄**——`scratchpad/gen31.py` 為例,每處修改 assert「只能匹配一次」,匹配 0 或 2 次直接中止。好處:除修改處外與 dump 逐字相同;dump 更新後重跑即知哪些錨點失效。
- **踩過:`insert_dicom_info` 是 `PROCEDURE` 不是 `FUNCTION`**,腳本寫死 `CREATE FUNCTION` 導致沒加到 `OR REPLACE`,實跑被 `42723 function already exists` 擋下才發現。
- **驗證要查 `pg_proc.prosrc`**(例如 `LIKE '%SITE_CODE%'`)才知道換到的是新版,不能只看「SQL 跑完沒報錯」。

**🔑 migration 慣例(2026-08-17 使用者指正,我第一次寫時漏掉):`Database\HDPACS\db_update_sql\db_update_v2.0.NN.sql` 每個檔結尾都要加「Update Database Version」的 DO block**——寫 migration 沒加這段就是沒結案,使用者不會知道有更新。格式:①`IF EXISTS(...version = 'N') THEN RAISE EXCEPTION 'Already update version: N'` ②`UPDATE HD_CONFIG SET CONFIG_VALUE='{"version":"N"}' WHERE ... CONFIG_VALUE::jsonb = '{"version":"前一版"}'` ③`IF rlt IS NULL THEN RAISE EXCEPTION 'Need to update version 前一版 first!'`。**這段刻意不冪等**(重複跑會 EXCEPTION,讓人知道上過了),而且形成版本鏈、跳版會被擋。查現況:`SELECT "CONFIG_VALUE" FROM public."HD_CONFIG" WHERE "CONFIG_SECTION"='DB' AND "CONFIG_KEY"='SYSTEM'`。**2026-08-17 現況:.191 登記 2.0.26;v2.0.27 原本沒注記(一直開著)、當日補上,並新增 v2.0.28(媒體匯出新表)+v2.0.29(授權表歸位+補設定),三檔都還沒執行 → 要依序 27→28→29。** 另:`DB版本.xlsx` 也要加列(使用者維護)。

**⚠️ dump 是 `--schema-only`,整份沒有一個 COPY 段 → 只能重建結構、不含任何資料。所以設定資料(HD_CONFIG/HD_ROLE 的值)的唯一正本就是 migration 檔**;先前 burnTempPath 與 dicomWeb.manageApiKeys 兩次手動改 DB 沒進 migration,結果只存在於 .191 那顆 DB 裡(已補進 v2.0.29)。

**驗證 migration 的方法(2026-08-17 建立,很有效)**:用 Npgsql 小工具把 migration ＋ 功能測試腳本包在**同一個 `BEGIN … ROLLBACK`** 裡對 .191 實跑 → 語法/型別/jsonb 路徑/proc 邏輯全被真的 PostgreSQL 檢查,DB 零殘留。連線字串要加 `Include Error Detail=true`,否則型別錯誤只說 "return type mismatch" 不告訴你是哪一欄。工具在 scratchpad `SqlCheck`(--one-tx 讓多檔共用一個交易,才能先建表再測 proc)。

PACS 資料庫 Schema 放在 `D:\Dev\HyperDigital\Database\`。目前版本檔案：`HDPACS_20260811.sql`（schema-only,從 .191 測試床拉的;檔名含日期,取最新日期的 .sql)。需要查 PACS DB 的表結構/欄位/proc 時參考此檔。**慣例(2026-08-11 使用者交代):設計要動 DB 的東西時,若手上 dump 可能過時,主動請使用者從 .191 重拉一份新的**(指令:`sudo -u postgres pg_dump -d HDPACS --schema-only -f /tmp/HDPACS_schema_$(date +%Y%m%d).sql`),不要默默用舊 dump 出 migration。
