# HyperDigital 系統文件

這裡是所有系統的規劃文件總索引。目的：**即使開發環境/對話被清空，也能從這裡查回整個系統的設計、狀態與待辦。**

## 文件結構
- `systems/` — 每個系統一份（用途、主機、架構、現況、關鍵決策、待辦）。
- `backlog.md` — 需求清單（新增／變更／刪除），含狀態。
- `todo.md` — 可執行待辦，依系統分組。
- 更新原則：**做了什麼、決定了什麼，就順手更新對應系統文件 + backlog/todo。**

## 主機 / 部署對照
| 主機 | 角色 | 服務 / 埠 |
|---|---|---|
| 192.168.68.234 | 舊版 HDPACS 正式機（暫不動）| PostgreSQL＋舊 PACS |
| 192.168.68.191 | 新版測試床：主 PACS＋DB＋**管理主控台** | 主 PACS 各服務、PostgreSQL（v2.0.27）、hd-admin-console :5200 |
| 192.168.68.199 | DicomWeb＋Export（對外 REST）| hd-pacs-dicomweb :5080、hd-export :5090（讀 **.191** DB）|
| 192.168.68.195 | LoggingPlatform（集中日誌）| ingest :5101 / query / web UI（podman）|
| 192.168.68.222 | Animal Proxy（獸醫 PACS 代理）| SCP :2020/3320、WebController :8080 |

## 環境與發布
- [environments.md](environments.md) — 主機盤點（含 .191 測試機）+ 發布資料位置 `D:\HD-Release\` + 舊換新討論。
- [machine-setup.md](machine-setup.md) — **換一台機器怎麼建構這個專案**：路徑要一致、clone 11 個 repo、
  git 帶不過去的 7 個設定檔、Claude 記憶的 junction 接法、兩台之間的同步紀律。

## Claude Code 的記憶
`claude-memory/` 是 Claude Code 跨對話記憶的**正本**，各機器的
`~/.claude/projects/D--Dev-HyperDigital/memory` 是指向它的 junction，
所以 `git pull` 就等於同步記憶。接法與還原方式見 [machine-setup.md](machine-setup.md)。
**憑證明文不要寫進去** —— 它進版控了，git 歷史很難真正抹掉。

## 原始碼託管（2026-08-17 起）
`D:\Dev\HyperDigital` 底下的 **11 個 repo** 一律雙 remote，`origin` 指向公司自架 Forgejo：

| remote | 位址 | 角色 |
|---|---|---|
| `origin` | `https://forgejo.hdtech.tw/charlie/<repo>.git` | **正本**，`git push` 的預設去向 |
| `github` | `https://github.com/Charlie022802/<repo>.git` | 鏡像，要推得明寫 `git push github master` |

repo 名稱與目錄名相同，**唯一的例外是 `Database\` 目錄對應的 repo 叫 `HDPACS-DB`**。

`hd-web-server\` 是**第 12 個目錄但不是我們的 repo** —— 同事維護的 Node 服務，
2026-08-19 為排障而放進來的工作副本（下載的壓縮檔，不含 `.git`）。
只讀不改，見 [systems/hd-web-server.md](systems/hd-web-server.md)。
`docs\`（本目錄）也是其中之一，repo 名 `HD.Docs` —— **改完文件要 commit + push，否則只留在這台開發機**。

搬遷時的坑：`git remote rename origin github` 會連 `branch.master.remote` 一起改寫，
所以對調兩個 remote 之後必須補 `git branch -u origin/master master`，
否則 `git push` 仍然往 GitHub 跑，而且沒有任何提示。

## 系統一覽
| 系統 | 文件 | 狀態摘要 |
|---|---|---|
| 主 PACS（HD.Net10）| [systems/main-pacs.md](systems/main-pacs.md) | 出口疊合+日誌改造中；部署到 .234 規劃中 |
| DicomWeb（HD.Pacs.DicomWeb）| [systems/dicomweb.md](systems/dicomweb.md)・[端點總覽](systems/dicomweb-endpoints.md) | 生產 .199；QIDO/WADO/STOW/UPS/DELETE/Import；登入已切 Keycloak、金鑰只驗不管 |
| HD 後端管理主控台（HD.AdminConsole）| [systems/admin-console.md](systems/admin-console.md) | **已上 .191:5200**：金鑰/匯出/稽核 + Keycloak 登入 |
| Export WebApi（HD.Export）| [systems/dicomweb.md](systems/dicomweb.md) | **已上 .199:5090**：媒體打包/燒錄 API（API Key） |
| 身分/認證（Keycloak SSO + API Key）| [systems/identity.md](systems/identity.md) | 主控台+DicomWeb 已切 Keycloak；OIDC 八坑清單在此 |
| Animal Proxy（HD.Animal）| [systems/animal-proxy.md](systems/animal-proxy.md) | 生產 .222；WebController 已上 |
| 影像看片（HD.DicomImageViewer / .Server）| [systems/viewer.md](systems/viewer.md) | 桌面看片 + Server 化進行中 |
| **hd-web-server**（同事維護，非我們的 repo）| [systems/hd-web-server.md](systems/hd-web-server.md) | **看片端影像的實際來源**（`/api/v2.0/wado-uri`）。只讀不改；排障入口是 journald 不是 log 檔 |
| 共用日誌套件（HD.Shared.Logging）| [systems/shared-logging.md](systems/shared-logging.md) | 套件完成；各產品接入中 |
| LoggingPlatform（HD.LoggingPlatform）| [systems/logging-platform.md](systems/logging-platform.md) | 生產 .195 |
| 統一部署框架（hdctl）| [systems/deployment.md](systems/deployment.md) | 階段二完成：.191 pacs/export/adminconsole 全遷入（hdctl 0.2.1）|
| 多語系（i18n）| [i18n-plan.md](i18n-plan.md) | 已定案規劃（resx+IStringLocalizer），P0 骨架待做 |
| 多院區主機（院區歸屬） | [multi-site-design.md](multi-site-design.md) | 設計完備待開工：SITE_CODE 進檔蓋章＋出口過濾＋RLS。一台主機承載多院區，涵蓋「多家動物醫院共用總機」與「一家醫院的多分院」兩種形狀 |
| 媒體匯出／燒錄 重新設計 | [media-export-redesign.md](media-export-redesign.md) | 設計中：新表＋新 proc（UID 三層級選擇、佇列併發、拆開 kiosk/rimage 專屬欄位）|
| 儲存層與資料補回 | [systems/storage-tiers.md](systems/storage-tiers.md) | online/nearline/archive 資料模型、autopilot 清快取、稽核與補回 runbook。**v2.0.22 以下沒有 nearline 守門會清掉唯一一份**（若瑟 2026-08-24 事件） |

## 慣例
- DB：單一 **HDPACS**（.234）。DB 變更用冪等 SQL，人工在 pgAdmin 執行（不由程式自動跑）。
- 版本：語意版本固定於發布，序號交付才 +1；build 靠台灣時間戳區分（見各系統）。
- 部署：publish/打包由開發端做，上傳/安裝由使用者在主機跑（ssh 需密碼）。
