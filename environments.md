# 環境與發布資料

主機盤點 + 發布產物擺放。搭配 [systems/deployment.md](systems/deployment.md)（hdctl 框架）。

## 主機盤點
| 主機 | OS / 性質 | 角色 | 部署狀態 |
|---|---|---|---|
| **192.168.68.234** | 舊 CentOS（版本較舊）| HDPACS DB + **舊版 HDPACS**（正式）| **舊系統**；無 hdadmin；未來舊換新，先別實驗 |
| **192.168.68.199** | RHEL/Alma | DicomWeb :5080 | 生產；hdadmin；DicomWeb 已上 |
| **192.168.68.195** | — | LoggingPlatform :5101 | 生產；podman |
| **192.168.68.222** | RHEL/Alma（SELinux Enforcing）| Animal Proxy :2020/3320 + WebController :8080 | 生產 |
| **192.168.68.191** | RHEL/Alma 10（測試機）| **新版 HDPACS 測試目標** + 管理主控台 :5200 | 已裝環境包 + 舊版 HDPACS(ProgramPublish)；**自己本機 DB**（可全測）；hd-admin-console 在 /opt |

> **測試策略**：新版 HDPACS 先在 **.191** 做「舊→新升級」測試（本機 DB，不影響任何正式資料）；流程跑通後再套 .234（那時處理 hdadmin 建帳號、舊 CentOS/runtime）。

## 發布資料位置：`D:\HD-Release\`（新的統一位置）
見 `D:\HD-Release\README.md`。重點：
- `environment\` — 離線環境安裝包（**ENV_VERSION=1.0.4**；1.0.3→1.0.4：dotnet 8.0.29/10.0.10、install_offline.sh 自動探索 SQL/挑最新 dotnet/LF、sql/ 重新同步）。裸機 RHEL/Alma 10 地基：`install_offline.sh` 裝 repos/RPM(base 165)、PostgreSQL、**pgbouncer（DB 6432 埠來源）**、pgadmin、.NET runtime（**含 aspnetcore 10.0.9** + 8/6）、ffmpeg 7.0、libgdiplus 6.1、Podman；`sql/`(create.sql + db_update_v2.0.x 增量)；`doc/`(hd-env-v1.0.3-manual.pdf)。已從 `C:\Users\yang\Downloads\packages` 整包搬入。
- `packages\` / `hdctl\` / `releases\` — 新版應用元件與部署工具（待 hdctl 落地）。
- `test\` — 測試包（hd-a1a2b-test.tgz = A1/A2/B 五支服務測試包）。`hd-workflow-manager.tgz` = A3 後的 hd-workflow-manager 單支包（install-workflow-manager.sh 加裝到既有 /home/HD/service，沿用 hd_conf.json；appsettings 只開 StudyClosedService、其餘 sub-service 關）。
- `legacy\program-publish\` — 舊 HDPACS 安裝包（已從 D:\ProgramPublish 搬入）。
- `clients\chang-gung\` — 長庚客製 SQL（callback / study_closed）。

## 舊版 HDPACS 安裝（D:\ProgramPublish）
舊安裝流程分析見記憶 project_main_pacs_deploy。/home/HD/service 佈局、hd_conf.json 集中設定、install/update/rollback、13 服務（含舊 web 元件 hd-web-server/hd-web-dicom-scu，fo-dicom 4）。

## 舊換新 — 能否並存？（討論結論）
- **同一台主機上：不能並存**。新舊 HDPACS 用相同 systemd unit 名（hd-pacs…）、相同埠（2020/3320）、相同目錄（/home/HD/service）、相同本機 DB → 衝突。所以是**取代**，非並存。
- **.191 舊換新做法**：停用舊 units → 備份舊 /home/HD/service → 裝新版（理想上直接落到 hdctl 的 releases/current 佈局）→ 起。保留舊安裝備份 + 封存舊 ProgramPublish 當退版路徑。
- **發布資料夾裡：可並存**（純檔案）。舊 ProgramPublish 封存到 `D:\HD-Release\legacy\program-publish\` 即可，跟新 packages 互不干擾。
