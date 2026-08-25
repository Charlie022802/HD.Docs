---
name: project_nearline_flag_race
description: "IS_NEARLINE_CACHED 旗標的競態:新物件進來到重算之間,旗標還是舊的 true—刪除那端已修(2.0.27),insert_study_job 那端還沒"
metadata:
  node_type: memory
  type: project
---

**`RC_STUDY."IS_NEARLINE_CACHED"` 是重算出來的,不是長期漂移的髒資料。**
`update_study_statistical_info` 直接數 `RC_OBJECT JOIN RC_LOCATION WHERE
NEARLINE_VOLUME_REF IS NOT NULL` 來設 true/false,所以**靜止狀態是準的**
(2026-08-25 在若瑟實測「旗標說有、實際沒有」的檢查數是 **0**)。

**真正的失效是競態**:新物件進來之後、重算跑之前那段窗口,旗標還是舊的 true。
2026-08 若瑟掉資料就是這樣——NONDICOM 重送把物件加進既有檢查,窗口內自動刪除跑了。

**有兩個地方信這個旗標,嚴重度差一個量級:**

| 位置 | 窗口內發生什麼 | 後果 | 狀態 |
|---|---|---|---|
| `get_next_delete_study` | 刪掉沒備份的物件 | **不可逆** | 2.0.27 已修(改成直接查 RC_LOCATION) |
| `insert_study_job` 的 NEARLINE_BACKUP gate | 跳過這次備份排程 | 可回復 | **未修**,併下次正式更新 |

`insert_study_job` 那個 gate **從 2.0.1 就在**,該 procedure 改過六次
(2.0.1/8/12/14/15/20)都沒碰它,`.191` 的 2.0.37 也一字不差——
**不是版本落差,是從沒被回頭看過的原始設計**。旁邊 `ARCHIVE_UPLOAD` 信
`IS_ARCHIVE_CACHED` 是同一個形狀。

**為什麼不單獨 hotfix `insert_study_job`**:它是進檔流程主幹
(STUDY_CLOSE / ROUTE / ARCHIVE 全走它),生產醫院上單獨換掉回報小於風險;
`get_next_delete_study` 則是刪除的最後一道關卡、單獨補風險可控,所以那支先補了。

相關:[[project_josef_data_recovery]]、[[reference_pacs_db_schema]]、[[project_studyclose_flow]]。
