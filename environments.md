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

## hdctl 實際安裝清單（2026-09-01 以 `hdctl list` 實測）

三台的 `hdctl` 都是 **0.2.7**，語系都是 **`zh_TW.UTF-8`**（這一點有意義：0.2.6 的 SELinux
判斷拿英文字串比對 semanage 的輸出，中文語系會誤判成失敗並印出兩行假警告，0.2.7 修掉）。

**192.168.68.191**（`hdpacs191`，hdadmin）
| 元件 | current | units |
|---|---|---|
| `hd-adminconsole` | `0.1.0-alpha.31+20260831203427` | `hd-admin-console` |
| `hd-pacs` | `2.0.13+20260825100752` | `hd-pacs`、`hd-worklist-server`、`hd-callback`、`hd-dicom-transmit`、`hd-media-package`、`hd-workflow-manager`、`hd-dicom-service-manager`（7 支） |

**192.168.68.199**（`newdicomweb`，hdadmin）
| 元件 | current | units |
|---|---|---|
| `hd-dicomweb` | `1.0.0-alpha.23+20260901154626` | `hd-pacs-dicomweb`、`hd-pacs-dicomweb-ups` |
| `hd-export` | `0.1.0-alpha.18+20260827171839` | `hd-export` |
| `hd-viewerapi` | `0.1.0-alpha.6+20260901155711` | `hd-viewer-api` |

**192.168.68.163**（`STJOHO_68_163`，**root**——見主機配置表；注意 VPN 同 IP 兩台機器）
| 元件 | current | units |
|---|---|---|
| `hd-viewerapi` | `0.1.0-alpha.6+20260901155711` | `hd-viewer-api` |

每台都保留最近 3 版（hdctl 自動 prune），所以上面每個元件底下都還有兩版可以 `hdctl rollback`。
換 hdctl 當下留了 `/usr/local/bin/hdctl.0.2.6.bak`——換掉的是**退版工具本身**，需要一條不依賴它的退路。

> 這張表會過時。要現況一律 `hdctl list`，別信這裡的版本號；留著它是為了回答
> 「**哪台上面有什麼**」——那個問題不常變，而且出事時最先要問。

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

## ⚠️ `192.168.68.0/24` 在兩個站台重疊（2026-08-28 實際踩到）

**有兩條 VPN 通道，兩邊都用 `192.168.68.0/24`**，哪條起來，`192.168.68.163` 就指到哪一台。
而且那兩台是**複製出來的 VM**：主機名（`STJOHO_68_163`）、`machine-id`
（`ed1b2bfc146a41f5ae4411bdbb0413f2`）、MAC（`bc:24:11:96:81:63`）**全部相同**，
從機器內部完全分辨不出來。

**所以 `machine-id` 在這裡沒有鑑別力。** 真正能分辨的：

| 判準 | 我們的機器 | 誤連的那台 |
|---|---|---|
| `uptime -s` | 2026 年（測試機 2026-07 前後） | **`2025-12-24`** |
| `ls /usr/local/bin/` | 有 `hdctl` | **空的** |
| `ls /home/HD/service/` | 有 `hd-viewerapi` | 沒有，全是舊系統服務 |

**最可靠的是「內外交叉比對」**：從自己機器 `curl http://<host>:5100/health`，
再在對端 `curl http://127.0.0.1:5100/health`，**兩邊版本字串要逐字相同**。
（viewerapi 到 alpha.5 為止只有 `/healthz`；alpha.6 起兩條都通，`/health` 與其他三支一致。）
服務版本騙不了人，而 IP、主機名、machine-id 都會。

Windows 端可先看走哪條通道：`Find-NetRoute -RemoteIPAddress <ip>` ——
2026-08-28 走的是本地位址 `10.8.0.3` 的「區域連線」，OpenVPN Connect 那條是斷的。

**動手前的最小檢查（唯讀，一行）**：

```bash
uptime -s; ls /usr/local/bin/ | head -5; ls /home/HD/service/ | grep -c viewerapi
```

那天差一步就把 `viewerapi` 裝到別人的機器上 —— 擋下來的是「那台沒有 hdctl」這個意外，
不是我們的流程。
