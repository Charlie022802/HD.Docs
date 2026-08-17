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

## 原始碼託管（2026-08-17 起）
`D:\Dev\HyperDigital` 底下的 **11 個 repo** 一律雙 remote，`origin` 指向公司自架 Forgejo：

| remote | 位址 | 角色 |
|---|---|---|
| `origin` | `https://forgejo.hdtech.tw/charlie/<repo>.git` | **正本**，`git push` 的預設去向 |
| `github` | `https://github.com/Charlie022802/<repo>.git` | 鏡像，要推得明寫 `git push github master` |

repo 名稱與目錄名相同，**唯一的例外是 `Database\` 目錄對應的 repo 叫 `HDPACS-DB`**。
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
| 共用日誌套件（HD.Shared.Logging）| [systems/shared-logging.md](systems/shared-logging.md) | 套件完成；各產品接入中 |
| LoggingPlatform（HD.LoggingPlatform）| [systems/logging-platform.md](systems/logging-platform.md) | 生產 .195 |
| 統一部署框架（hdctl）| [systems/deployment.md](systems/deployment.md) | 階段二完成：.191 pacs/export/adminconsole 全遷入（hdctl 0.2.1）|
| 多語系（i18n）| [i18n-plan.md](i18n-plan.md) | 已定案規劃（resx+IStringLocalizer），P0 骨架待做 |
| 動物醫院總主機：院別歸屬 | [hospital-code-design.md](hospital-code-design.md) | 設計中：HOSPITAL_CODE 蓋章＋出口過濾（Proxy 退役後架構）|
| 媒體匯出／燒錄 重新設計 | [media-export-redesign.md](media-export-redesign.md) | 設計中：新表＋新 proc（UID 三層級選擇、佇列併發、拆開 kiosk/rimage 專屬欄位）|

## 慣例
- DB：單一 **HDPACS**（.234）。DB 變更用冪等 SQL，人工在 pgAdmin 執行（不由程式自動跑）。
- 版本：語意版本固定於發布，序號交付才 +1；build 靠台灣時間戳區分（見各系統）。
- 部署：publish/打包由開發端做，上傳/安裝由使用者在主機跑（ssh 需密碼）。
