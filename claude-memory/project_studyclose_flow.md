---
name: project-studyclose-flow
description: "StudyClose architecture — C# StudyClosedService (file rewrite) + DB study_closed() (downstream fan-out)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7bed9acc-56ee-46ab-93c0-bf8a5ea4e34c
  modified: 2026-07-20T03:45:45.969Z
---

StudyClose 分兩個易混淆的東西：
1. **`STUDY_CLOSE` map job** — 由 C# `HD.WorkflowManager/Service/StudyClosedService.cs`（BackgroundService，輪詢）處理：把改過的 metadata 寫回實體 DICOM 檔（`UpdateDicomFileSafe`：byte+Sequence 比對，無變更跳過；寫 .temp→File.Move 3-retry；MPEG4 副本同步；GC.Collect 釋放 handle）。job 資料/狀態走 MAP_JOB（N→P→D/E），透過 `MapJobManager` + DB functions（`get_next_map_job`/`restart_uncompleted_jobs`/`update_map_job_status`）。
2. **`study_closed()` procedure** — 下游扇出中樞，job 標記 D 時才被呼叫。

時序（先改檔、後扇出）：`insert_study_job('STUDY_CLOSE')`（設 RC_STUDY.STATUS='N'，塞 job）→ C# 改檔 → UpdateDone → `update_map_job_status` → `update_study_active_record('STUDY_CLOSE')` → `study_closed(study_ref)`：STATUS N→X、MWL step COMPLETED、扇出 NEARLINE_BACKUP / ROUTE / ARCHIVE_UPLOAD / 三層 callback(study/series/object, `insert_update_hd_callback`) / NonDICOM / Auto-Fetching。

要點：DB 是編排者，C# 只是檔案 I/O 執行者。`STUDY_CLOSE_SKIP_VERIFIED` 是別名（跑統計後轉 STUDY_CLOSE）。`modifiedFiles` 旗標控制是否真的改檔。callback 記錄在 study_closed 批次產生（解釋收影像端 callback 的解耦，見 [[project_viewer_server]] 無關；DB schema 位置見 [[reference-pacs-db-schema]]）。SQL 在 HDPACS_*.sql：study_closed / update_study_active_record / update_map_job_status / insert_study_job。
