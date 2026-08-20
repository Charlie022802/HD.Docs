---
name: project_immutable_original_coerce
description: "目標架構決策—原始檔進PACS後唯讀不可變,校正只寫DB,出口疊合(coerce-on-retrieve);WADO先做試點"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4955439c-e319-4882-9ff7-dc4be5c80843
  modified: 2026-08-02T17:00:52.299Z
---

決策(2026-07-30):PACS 改走「原始檔不可變 + 出口疊合」架構(非破壞式)。動機:舊版 StudyClose 就地改檔曾把原始影像寫壞,非常危險。台灣幾乎每份都要改中文姓名,所以「多存校正副本」會儲存翻倍→否決;改走 DB overlay、零額外儲存。

**核心**:C-STORE/STOW 進檔後檔案唯讀、永不修改;所有校正只寫 DB(RC_STUDY/RC_SERIES/RC_OBJECT.DATASET);出口時把 DB 校正疊到原檔再吐。

**現有 reconcile 機制(要保留)**:抓 STUDY_CLOSE job 時 `get_next_map_job`(HDPACS SQL line ~12851)會呼叫 `update_study_info(updateFromRCStudy=true)`(SQL line ~27650),從 RC_STUDY 反灌 0020000D、從 RC_SERIES 反灌 0020000E + patient/accession 等進 `RC_OBJECT.DATASET`(line ~27855+27863)。所以 STUDY_CLOSE 後 DATASET 是完整校正 overlay(含 UID)。split/merge 本身不動 DATASET,靠這步補 UID。

**要砍的危險步驟**:C# `HD.Net10\HD.WorkflowManager\Service\StudyClosedService.cs` 的 `UpdateDicomFileSafe`(改檔)。決策=保留 STUDY_CLOSE 的 DB reconcile,只砍 C# 改檔。(該版已是 temp+File.Move 原子換檔,但 createBackup:false 沒留 .bak,換完原件即失。)

**疊合統一規則**:base=原檔 dataset;蓋 RC_OBJECT.DATASET;UID 雙保險 0020000D←RC_STUDY、0020000E←RC_SERIES(擋改完未close空窗);pixel 不碰;可加可重建暫存快取。

**落地順序**:WADO(DicomWeb 本專案)先做試點,原檔不可變、可獨立驗證、不影響其他出口。其他出口(C-MOVE/C-GET SCP、桌面 Viewer、archive/route/nearline/callback)之後修正 —— 全系統契約「所有出口都要疊合,不能半套」。相關:[[project_studyclose_flow]] [[project_dicomweb_impl_split]] [[reference_fodicom5_pixel]]

**coerce 穩健性(2026-08-03,commit `805d67a`)**:`ApplyCoercion` 原本 `DicomJson.ConvertJsonToDicom(整份)` 遇某 tag 拋例外→整份 metadata 沒疊、只剩 UID(生產某 JPEG Lossless 中招)。改 `ParseDatasetLenient`:先整份 `autoValidate:false`(關驗證,多數即過、實測那張就過了);仍拋則逐 tag 轉、壞的跳過(記 ok/bad);AddOrUpdate 每 tag 各自 try。效能快取:非匿名疊合結果進 CoercedInstanceCache(commit 前一批),key=SOP、version=studyUid|seriesUid|物件 DATE_TIME_MODIFIED。

**WADO 試點狀態(2026-07-30 DONE + 生產實測通過 + 已 commit `b87e778`)**:只改 `HdPacsWadoService.GetInstanceAsync` —— 從串原檔改成「載入→`ApplyCoercion`(疊 RC_OBJECT.DATASET,跳過 PixelData/group0002)→ UID 父表覆蓋 → (選擇性)匿名 → 重序列化(不轉檔)」。metadata 端點本就讀 DATASET 不用改;frames/rendered/thumbnail 回裸像素/圖不疊。已部署 .199。實測法:pgAdmin 把 TEST001 那筆 RC_OBJECT.DATASET 的 00100010 暫改中文+00080005=ISO_IR 192(不觸發改檔)→ WADO 取回姓名即變、UTF-8 正確、磁碟原檔仍 TEST001 未動 → 驗畢還原。效能注意:非匿名取檔從零複製串流變成載入+重序列化(整份進記憶體)。**已加可重建疊合快取(2026-07-31,commit `8159897`)**:`CoercedInstanceCache`(singleton MemoryCache 256MB LRU),GetInstanceAsync 非匿名結果入快取,key=SOP UID、version=studyUid|seriesUid|RC_OBJECT.DATE_TIME_MODIFIED(校正/ split/merge 都會讓 version 變→自動失效),命中免重載重序列化;匿名不入快取。實測第二次取同一 instance「疊合快取命中」。**已知小問題**:某些 instance(如某張 JPEG Lossless)ApplyCoercion 疊 DATASET 丟例外→退回只套 UID(log「疊合 DATASET 失敗,僅套父表 UID」),待查是哪個 tag 讓 DicomJson.ConvertJsonToDicom 卡住。

**尚未做的(之後回來接)**:其他出口疊合 —— 主程式 C# 的 C-MOVE/C-GET SCP、桌面 Viewer、archive/route/nearline/callback 都要比照疊合,並砍掉 `StudyClosedService.UpdateDicomFileSafe`(停止改檔)。全系統契約「所有出口都要疊合,不能半套」。此議題 2026-07-30 暫停,先轉去做 UPS-RS。

**順帶完成的金鑰管理 UI(commit `dac9a43`)**:建立成功改 modal 置頂面板(不再被塞在長表單底);權限範圍改粉彩藥丸 badge(讀=粉藍/寫=粉綠/刪=粉珊瑚);建立時間/到期日/最後使用格式化(空值「永久」/「尚未使用」);全表字級統一 0.9rem、badge 0.85rem nowrap。
