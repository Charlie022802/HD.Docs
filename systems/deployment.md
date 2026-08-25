# 統一部署框架（hdctl）

目標：所有元件集中 `/home/HD/service`，但**每元件可獨立安裝／更新／退版**（共置 ≠ 綁定更新）。

**完整設計文件**：[hd-unified-deploy-design.md](../hd-unified-deploy-design.md)（已收進本 repo）。
**實作**：`D:\Dev\HyperDigital\hdctl\`（自有 git repo）——**階段一 MVP 已完成（2026-08-10）**：
`hdctl.py`（install/rollback/list/prune/version；sha256 驗證、requires 檢查、保留設定、產 unit、
防火牆、symlink flip、健檢失敗自動退回）+ `hdpack.py`（publish → tgz+sha256，自動 build 時間戳）。
manifest 正本放各元件 repo `deploy/hdctl-manifest.json`（HD.Export / HD.Net10(pacs 7 服務) / HD.AdminConsole）。用法見 `hdctl/README.md`。
**0.2.0（同日）**：+`apply`（release.json 全驗才動、依序裝、失敗整批退回）、`links`（共用設定 symlink 進包內，
pacs 的 hd_conf.json 靠這個、C# 不用改）、`start/stop/restart/status`、`migrate`（列未套 SQL+--done 登記）。
**.191 已遷入 hdctl**：pacs（7 服務一元件）、export、adminconsole。
**.199 也已遷入（2026-08-10）**：dicomweb（兩 unit：主 5080＋UPS 5081，**模組設定正本在 manifest**、舊 drop-in 已清）＋export
（manifest envFiles 雙主機共用）。`links: data→元件層` 讓 access.db 等本機檔活在 releases 外；NAS 掛載（/home/HD/data、CACHE01）
在 service 外不受影響。各 repo 的 install.sh 退役為全新環境用。尚未做：簽章。
**多服務共用 WorkingDirectory 的教訓（.191 實案，四連發）**：
①**ContentRoot=CWD → appsettings.json 整份沒載到**（無檔案日誌/等級與 Service 開關全預設）——hdctl 0.2.1 起
unit 自動塞 `DOTNET_CONTENTROOT`/`ASPNETCORE_CONTENTROOT` 指服務程式目錄，C# 不用改；
②LoggingPlatform 緩衝檔共寫→事件七倍重複（已修：預設錨 AppContext.BaseDirectory）；
③CacheControl Temp ④service-manager History 寫進 release 目錄（已修，下次發版帶上）。
新增多服務元件時，凡 CWD 相對路徑都要過一遍這四類。

## 定案決策
- **hdctl = 單檔 Python 3（只用標準庫）**；指令皆帶元件：install/update/rollback/apply/status/start/stop/restart/migrate/version/prune。
- **每元件各自 tgz** `hd-<component>-<version>.tgz` + `.sha256`（可選簽章）；**manifest.json 內嵌包裡**（services/env/ports/migrations/`requires` 相容中繼）。
- **symlink 版本切換（藍綠）**：`<component>/releases/<ver>/`（不可變）+ `current -> releases/<ver>`；update=解壓→stop→flip→start（失敗自動 flip 回）；rollback=純 flip 不複製；data/logs 放 releases 外故切版保留。
- **release 協調包** `release.json`：多元件一起上（如共用 migration），全驗才動、依序 update、可整批 rollback。
- **單一 HDPACS DB**：安裝只問一次 → 寫 `hd_conf.json`（PACS 讀）+ `/etc/hd/db.env`（DicomWeb 完整連線）。日誌 `/etc/hd/logplatform.env` 全元件共用。

## 設定要放哪：appsettings 還是 env 檔（2026-08-18 定案，踩過才寫下來）

**規範：機器／場域相關的設定一律走 `/etc/<component>/*.env`，`appsettings.json` 只放「所有環境都一樣的預設」。**

### 為什麼不能把新設定塞進 appsettings

manifest 的 `preserve` 清單保留機器上那份 `appsettings.json`（用意是更新不覆蓋現場設定），
副作用是**新版新增的設定區塊永遠不會自動上機**——包裡有、機器上沒有，而且安裝過程完全不會提示。

這不是假設。2026-08-18 Export API 要接 Keycloak，把 `Keycloak` 區塊加進 `appsettings.json`，
部署後 **hdctl 健檢 500、自動退版**：機器上用的還是舊那份，`Authority` 因此是空字串，
`MetadataAddress` 變成 `"/.well-known/openid-configuration"`（不是合法 URL），JwtBearer 首次解析
options 就丟例外；而該 scheme 是預設 scheme、每個請求都會走認證分派，於是**連 `/health` 都 500**。

### 怎麼判斷該放哪

| 問題 | 放 env 檔 | 放 appsettings |
|---|---|---|
| 換一台機器／換一家醫院會不會不一樣？ | 會 | 不會 |
| 是機密嗎？ | 是 | 絕不 |
| 例子 | DB 連線字串、LoggingPlatform 位址與金鑰、Keycloak `Authority` | 日誌等級、`AllowedHosts`、各種行為預設 |

`Keycloak.Authority` 屬於前者常被誤判：它看起來像固定值，但**各醫院之後會自建院內 Keycloak**，
封閉網路連不到 `sso.hdtech.tw`。同理，凡是「現在只有一個值，是因為現在只有一套環境」的設定都該進 env。

既有慣例本來就是這樣——`Database.ConnectionString` 與 `LoggingPlatform.IngestUrl` 在
`appsettings.json` 裡都是**空字串**，實際值由 `/etc/hd-export/*.env` 提供。新設定照抄這個形狀即可。

### 做法

1. `appsettings.json` 留空值 + `_comment` 說明由哪個 env 檔提供。
2. manifest 的 `envFiles` 加上該檔路徑（**這個會隨包上機**，hdctl 會據此重寫 unit）。
3. 主機上建檔：`/etc/<component>/<name>.env`，內容用 .NET 的環境變數格式（區段用雙底線，
   例如 `Keycloak__Authority=…`），權限 `600`（含機密）或 `640`，然後 **`restorecon`** 標成 `etc_t`。

### 程式碼要能容忍設定不存在

**選配功能沒設定時，服務必須照常啟動，不能整支死掉。** 上面那個案例的根因有一半在這裡——
少一個選配的認證方式，結果是整支 API 每個請求都 500。正確做法是判斷後跳過註冊，並記一筆
`WARNING` 說明哪個功能沒啟用（集中日誌看得到）。

這一點對 hdctl 尤其重要：健檢失敗會**自動退版**，所以「設定沒上機」會表現成「新版裝不上去」，
而真正的原因（少一個設定）完全看不出來。反過來說，能容忍缺設定的服務，裝上去之後
**「裝成功」不等於「功能可用」**——部署後要另外確認那行 WARNING 有沒有出現。

## 現有部署現況（統一前）
- **DicomWeb**：自有 `deploy/install.sh`（.199），**不寫版本檔**（靠 /health）。
- **傳統 PACS**：舊 `D:\ProgramPublish` 有 install/update/rollback（/home/HD/service + hd_conf.json 集中設定、寫 version.txt、13 服務含舊 web 元件、root 執行）。新版要一般化進 hdctl。
- **Animal Proxy**：自有 install.sh（.222，SELinux 模組）。

## root → hdadmin 的 SELinux / 權限重點
- dotnet 放 `/opt`（避 init_t 執行 /home 的 user_home_t 標籤被擋）。
- **symlink 藍綠切換的雷（2026-08-10 .191 實案）**：init_t **讀 user_home_t 的 lnk_file 會被擋**（目錄沒事）——unit 的 WorkingDirectory 經過 `current` symlink 時 CHDIR EACCES、服務 crash-loop。解法：symlink 標 `usr_t`；且 **flip 產新 link 標籤會重置，每次 flip 後都要重標**（hdctl `label_current` 已內建 semanage fcontext + chcon -h）。
- **env 一律 `/etc/hd/*`（etc_t、600、restorecon）**；放 /home 會 AVC denied 且 `EnvironmentFile=-` 靜默略過。
  哪些設定該放 env、哪些留 appsettings，見上方「設定要放哪」。
- 解壓新 release 後 `restorecon -R`；低埠綁定用 setcap；atomic tmp+rename 注意標籤繼承。
- hdctl 產 unit 必帶 `EnvironmentFile=/etc/hd/*.env`，否則日誌 no-op。

## 待辦
見 [todo.md](../todo.md)「統一部署框架」。實作前小決定：hdctl 自身上主機方式、簽章要不要做。

## 部署決策
- **主 PACS 正式部署暫緩（2026-08-04 決策）**：`.234` 先不動、**保留舊版 HDPACS**。新版（A0–A3+B 已驗）續留 `.191` 測試機。日後要上正式再規劃 .234（DB/影像同機）舊換新——屆時處理建 hdadmin + 舊 CentOS/runtime，並先確認 .234 舊 PACS 停用避免埠衝突 + worker 雙重處理刪檔/改檔。→ 見 [main-pacs.md](main-pacs.md)。
