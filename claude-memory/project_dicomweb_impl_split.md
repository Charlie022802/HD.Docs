---
name: project_dicomweb_impl_split
description: "HD.Pacs.DicomWeb 有兩套 QIDO/WADO/STOW 實作;生產(.199)用 Infrastructure 的 HdPacs* 版,不是 Application 的 EF 版"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 4955439c-e319-4882-9ff7-dc4be5c80843
  modified: 2026-08-02T17:18:48.146Z
---

**踩過的坑:改對實作。** HD.Pacs.DicomWeb 每個服務有兩套實作:
- Application 層 EF Core 版:`QidoService` / `WadoService`(查 EF `Instance` 等實體)。
- Infrastructure 層 Dapper 版:`HdPacsQidoService` / `HdPacsWadoService` / `HdPacsStowService`(查舊 HDPACS `RC_STUDY`/`RC_SERIES`/`RC_OBJECT`)。

`Infrastructure/ServiceCollectionExtensions.cs` **覆蓋** DI,把 IQidoService/IWadoService/IStowService 全綁到 HdPacs* 版。**生產(.199,接真 HDPACS DB 192.168.68.234)跑的是 HdPacs* 版** —— 改生產行為要改這些,別只改 EF 版(會變成改到沒被用的路徑)。

**Transfer syntax / MPEG4 判斷(已完成):** HDPACS `RC_OBJECT` 沒有 transfer syntax 欄位;`DATASET` jsonb 也不含(它是 `ConvertDicomToJson(dataset)`,group 0002 File Meta 不在 dataset)。真值只在 NAS 原始檔的 file-meta。作法:
- STOW(`HdPacsStowService`)入庫時把 file-meta 的 transfer syntax 以 `AvailableTransferSyntaxUID (0008,3002)` 併入 `DATASET`(只影響新資料)。
- QIDO instance 查詢(`HdPacsQidoService`,3 條列 instance 路徑共用)`DATASET -> '00083002' -> 'Value' ->> 0` 取值;**DB 沒值(舊/C-STORE 資料)時,快速讀實體檔頭 fallback 補上**(`get_object_path` 帶路徑 + `DicomFile.OpenAsync SkipLargeTags`,限並行 8)→ **舊資料也查得到**。源頭修好(PACS C-STORE 也寫 0008,3002)後 fallback 自然不再觸發。
- WADO metadata **不做** fallback(標準上 transfer syntax 不屬 metadata;查能力走 QIDO 的 0008,3002)。
- MPEG4 = transfer syntax `.102`–`.106`;`Domain/DicomTransferSyntaxes`(IsVideo/IsMpeg4)EF 路徑用,TestClient 內嵌一份。

**WADO 視訊防呆(其實生產本來就有):** 生產 `HdPacsWadoService` 已內建 `IsVideoTransferSyntax` + frames/rendered 對視訊丟 `NotSupportedException` → 端點回 415。EF `WadoService` 的早期短路是另一條(未用)路徑。thumbnail 端點原本錯回 500,已修為 415。

**QIDO ModalitiesInStudy (0008,0061) 多值(已完成):** `HdPacsQidoService` 改用 PostgreSQL 陣列 overlap(`regexp_split_to_array(upper(...), '[\\,]') && @modalities::text[]`),支援逗號/反斜線/重複參數(ParseQuery 用 StringValues.ToString() 併成逗號),token 精準比對、順序無關,修掉 ILIKE %CT% 誤中 OCT/CTA。

**QIDO study 欄位 + 通用 includefield(2026-07-31,commit 20b93f7):** 同事回報 study 少生日/年紀/description。`HdPacsQidoService`:study 新增預設回 PatientBirthDate(00100030)/Sex(00100040)/Age(00101010)—— 不在 RC_STUDY 欄位,用 `LEFT JOIN LATERAL`撈該 study 一筆 object 的 DATASET 取(LIMIT 1);Study/SeriesDescription 改預設就回。**通用 includefield**:接受 8 碼 hex 或 DICOM keyword(`DicomDictionary.Default` 解析)或 all,從 RC_OBJECT.DATASET 撈值疊回(Append* 記 outKeys 去重);有 includefield 時 study/series 才 LATERAL 多帶整份 `DATASET::text`(一般查詢零成本),instance 直接帶。limit 預設 100、offset 本就支援(ParseQuery)。

**QIDO 效能索引(2026-08-03):** SQL 存 repo `db/perf_indexes.sql`(不由程式跑,pgAdmin 手動)。比對 HDPACS_20260720.sql:FK join 索引老表全有(RC_OBJECT index_rc_object_2 SERIES_REF/_3 STUDY_REF、RC_SERIES index_rc_series_1、UNIQUE STUDY_INSTANCE_UID/SOP_INSTANCE_UID/accession_number_index),不用重建。真缺口=study 清單 `ORDER BY STUDY_DATE DESC, STUDY_TIME DESC` 沒索引→整張排序。**A 已在生產 .234 建好**:`CREATE INDEX CONCURRENTLY "index-RC_STUDY-STUDY_DATE" ON RC_STUDY(STUDY_DATE DESC, STUDY_TIME DESC)`。B(RC_SERIES 單欄 SERIES_INSTANCE_UID,現有 UNIQUE 把它放第二欄單獨查用不到)、C(PATIENT_ID/NAME/DESCRIPTION 的 pg_trgm GIN 供 ILIKE %..%,需擴充、整庫生效)= **決定先不做**,以註解保留在同檔。

**部署 / 版本:** DicomWeb 自有流程(非 [[project_shared_logging]] 的 podman):`deploy/install.sh`(framework-dependent, systemd, 保留 data/logs),打包 `publish/hd-pacs-linux.tgz`。版本在 `Directory.Build.props`,現為 **1.0.0-alpha.1 + 台灣時間 build 戳**(見 [[feedback_versioning_convention]]);/health 與 conformance 讀組件版本(`Domain/AppVersion.cs`,回 version+build)。

**已提交:2026-07-27 全部 commit+push** — HD.Pacs.DicomWeb `master`(GitHub Charlie022802/HD.Pacs.DicomWeb)、HD.Shared `master`(HD.Shared.Logging 共用包)。兩 repo 需 clone 到同層維持 ProjectReference 相對路徑。
