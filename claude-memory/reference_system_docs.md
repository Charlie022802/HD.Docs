---
name: reference_system_docs
description: 人可讀的系統規劃文件在 D:\Dev\HyperDigital\docs\—各系統/需求backlog/待辦todo;做完事要順手更新
metadata: 
  node_type: memory
  type: reference
  originSessionId: a23fe480-c347-41d9-ba5a-eb699a5d1cf4
  modified: 2026-08-17T03:09:54.314Z
---

使用者的**人可讀系統文件**在 `D:\Dev\HyperDigital\docs\`(2026-08-03 建立)。目的:即使開發環境/對話清空也能查回整個系統設計與待辦。**2026-08-17 起 `docs\` 本身就是 git repo(`HD.Docs`,路徑不變),改完要 commit+push,詳見 [[project_git_hosting]]。** 結構:
- `README.md` — 總索引 + 主機對照(.234 DB/主PACS、.199 DicomWeb:5080、.195 LoggingPlatform:5101、.222 Animal Proxy)+ 系統一覽。
- `systems/` — 每系統一份:main-pacs / dicomweb / animal-proxy / viewer / shared-logging / logging-platform / deployment。
- `backlog.md` — 需求(新增/變更/刪除),狀態 提出→規劃→進行→完成/擱置/取消。REQ-001 出口疊合、REQ-002 主PACS日誌、**REQ-003 燒錄開成 API**(打包/查狀態/下載,新提出 2026-08-03)。
- `todo.md` — 可執行待辦依系統分組。
- `environments.md` — 主機盤點(.234 舊系統/.199 DicomWeb/.195 Log/.222 Animal/**.191 新版測試機本機DB**)+ 發布資料位置。

**發布資料統一放 `D:\HD-Release\`**(2026-08-03 建;取代散落的 Downloads\packages/ProgramPublish):environment\(離線環境包 ENV_VERSION=1.0.3,含 install_offline.sh+PostgreSQL+pgbouncer(6432)+.NET10+ffmpeg+gdiplus+sql,已從 Downloads\packages 整包搬入)、packages\(新版元件 tgz,待hdctl)、hdctl\、releases\、clients\、test\(hd-a1a2b-test.tgz)、legacy\(舊 ProgramPublish 待搬)。**新版 HDPACS 先在 .191 舊換新測試**(本機DB),通過再上.234。同機新舊 HDPACS 不能並存(同unit/埠/目錄)=取代非並存。

**重要:做完事、定了決策,要順手更新這套 docs**(對應系統文件 + backlog/todo),不是只更新我的記憶。這是使用者要長期查閱的正本。內容與各 project_* 記憶重疊,docs 是給人看的敘述版、記憶是給我 recall 用。

REQ-003 燒錄 API 現況分析:燒錄由傳統 PACS **hd-media-package** worker 讀 `export.EXPORT_JOB` 佇列執行(`export.get_job_package_info()`)。API 可能是薄層:建立=寫 EXPORT_JOB(狀態'N')→worker 接手、查狀態=讀 STATUS(P/E)、下載=串流 worker 產出。放哪待決(DicomWeb 有認證/部署基礎 vs worker 在 .234;跨機取檔要處理)。相關 [[project_main_pacs_coerce_logging]] [[project_dicomweb_features]]。
