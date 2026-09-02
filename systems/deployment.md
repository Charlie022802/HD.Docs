# 統一部署框架（hdctl）

目標：所有元件集中 `/home/HD/service`，但**每元件可獨立安裝／更新／退版**（共置 ≠ 綁定更新）。

**完整設計文件**：[hd-unified-deploy-design.md](../hd-unified-deploy-design.md)（已收進本 repo）。
**實作**：`D:\Dev\HyperDigital\hdctl\`（自有 git repo）——**階段一 MVP 已完成（2026-08-10）**：
`hdctl.py`（install/rollback/list/prune/version；sha256 驗證、requires 檢查、保留設定、產 unit、
防火牆、symlink flip、健檢失敗自動退回）+ `hdpack.py`（publish → tgz+sha256，自動 build 時間戳）。
manifest 正本放各元件 repo `deploy/hdctl-manifest.json`（HD.Export / HD.Net10(pacs **8** 服務) / HD.AdminConsole）。用法見 `hdctl/README.md`。

> **⚠️ 包裡的服務清單與專案清單不一致過（2026-09-02 修）。** HD.Net10 有九支服務，`pack-pacs.sh` 與 manifest 卻只列七支——`HD.CacheDelete` 與 `HD.ArchiveManager` 從來沒被打包。
> 沒有 CACHE_DELETE 的 worker 代表 `delete_dicom` 排的刪除工作**永遠沒人處理**：DB 照做、檔案留著、工作卡在佇列裡，**完全不報錯**。而 `MAP_JOB` 是空的看起來像「一切正常」，實際上是「從來沒有人排過刪除」——直到真的去刪一次才會發現。
> 2.0.14 補上 `hd-cache-delete`（實測：一啟動就把積壓的 job 236～246 全部清完）。`ArchiveManager`／`NearlineBackup` 依決定暫不納入（要先調整），**所以 `IS_ARCHIVED`／`IS_NEARLINE_CACHED` 在 .191 永遠不會變 true**。
> 新增服務時，`pack-pacs.sh` 的 `SVC`、manifest 的 `services` 與 `preserve` 三處要一起改。
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
  - **「放 releases 外」要自己確認，不是自動的（2026-09-02 實案）。** DicomWeb 的 `./logs` 與 `app/logs`（含 `logplatform-buffer`）一直落在 `releases/<版本>/` 裡，prune 保留 3 版 → **舊日誌隨更版消失**。9/1 部署十次，隔天查前一天的問題時完全沒有東西可看。`logplatform-buffer` 更嚴重：那是送不出去時的暫存，prune 掉等於把還沒送到集中日誌的紀錄丟了；`app/data/access.db` 同理。
  - 修法是 manifest 的 `links` 接到元件目錄（alpha.31 起四條：`data`／`logs`／`app/logs`／`app/data`，涵蓋 CWD 與 ContentRoot 兩種基準）。需 **hdctl 0.2.9**——它會把不存在的目錄型連結目標先建出來，否則符號連結懸空、程式 `CreateDirectory` 會撞上「連結已存在但不是目錄」。
  - pacs 不受影響：它的 `../../logs` 相對 CWD 解析後正好落在 releases 外面。**同一個包裡兩種寫法，結果天差地遠**。
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

## `preserve` 的三個性質（2026-08-26 一天內全部撞到）

manifest 的 `preserve` 會在升版時把**舊 release 的設定檔複製到新 release**，
讓機器上的設定不會被新版覆蓋。立意正確，但它有三個容易忘記的後果：

**① 退版不會帶設定過去（hdctl 0.2.5 已修）**
目標 release 用的是它**當初被安裝時**那份設定，可能是幾個月前的。
實案：Keycloak 換 domain 改了 current 的 appsettings，退版後登入立刻壞掉，
而症狀看起來像「退版沒解決問題」——最不該在退版當下遇到的那種誤導。
現在退版會把現行設定帶過去，目標版原檔留成 `.pre-rollback`。

**② 但帶過去也可能出事：設定的來源跨版本改變時（hdctl 0.2.6 加警告）**
「設定是機器狀態、跟版本無關」這個前提，在**設定從 appsettings 搬到 env 檔**這種變更下不成立。
實案：alpha.5 把 `Keycloak:Authority` 搬進 env（appsettings 留空），退到 alpha.4 時空的
appsettings 被帶過去，但 **unit 是照目標版 manifest 重寫的**，alpha.4 沒有那個 env 檔
→ 兩邊都沒有 Authority → **服務 active 但每個請求都 500**。
hdctl 現在會比對兩版的 `envFiles`，目標版少了就出聲（只警告不擋——退版是逃生路徑）。

**③ 它會遮住壞掉的設定檔——最陰的一個**
新版隨包附上的 appsettings **永遠不會抵達既有安裝**（一律被舊的蓋掉）。
所以如果包裡的 appsettings 是壞的，**既有安裝完全正常，只有全新安裝會炸**，也就是下一間新醫院。
實案：加註解時在同一層多疊了一個 `"_comment"`，JSON 語法上合法、編輯器與 python 都不抱怨，
但 .NET 的 `JsonConfigurationProvider` 對重複鍵直接 `InvalidDataException`。
`.191`／`.199` 升級後健檢 200、登入正常、JWT 也過——**而包是壞的**。

→ **打包腳本現在會擋**：`pack-*.sh` 除了檢查密碼沒漏進包裡，也會驗每個 `appsettings*.json`
能不能載入（重點是重複鍵；python 的 `json.load` 預設允許重複、後者覆蓋前者，
要用 `object_pairs_hook` 才抓得到）。護欄本身先驗過會叫：壞的 exit=1、好的 exit=0。

**推論**：改設定檔之後，光看「既有機器升級沒事」不足以證明包是好的。要嘛靠打包時的檢查，
要嘛真的做一次全新安裝。

## 元件對主機的相依（不是 .NET 的、hdctl 管不到的）

self-contained 的包解決了「主機有沒有 .NET」，但**沒有解決「主機有沒有那個原生程式庫」**。
這一類相依 hdctl 檢查不到，而且失敗形態通常很糟。

| 元件 | 需要 | 缺了會怎樣 |
|---|---|---|
| `dicomweb` | `libfontconfig`、`libfreetype` | ECG 波形完全畫不出來（`/rendered` 回 415 並說明） |
| `dicomweb` | **CJK 字型** | **完全無聲**：波形照樣畫、HTTP 200、日誌不吭聲，只有病人姓名變豆腐 |

```bash
# RHEL 9/10
sudo dnf install -y google-noto-sans-cjk-vf-fonts
sudo /usr/local/bin/hdctl restart dicomweb    # 字型偵測有快取
```

**第二列是重點，它示範了這類問題的形狀：**

- 失敗完全無聲，錯誤訊息、狀態碼、日誌都不會提
- **只有全新環境會踩到**——既有機器裝過就不會再犯，所以「既有機器升級沒事」證明不了什麼
- 只有比對才看得見（是靠「本機 266 KB vs 伺服器 282 KB」的 6% 差異追出來的）

跟 [`preserve` 的三個性質](#preserve-的三個性質2026-08-26-一天內全部撞到) 裡「它會遮住壞掉的
設定檔」是同一個形狀：**既有安裝全正常，只有新醫院會炸。**

**做法：讓元件自己講，不要只寫進文件。** `dicomweb` 的 `/health` 有 `ecgFontCoverage`
（`None`／`Latin`／`Cjk`）——hdctl 的健檢本來就會打 `/health`，等於自動涵蓋。
文件會被漏掉，健檢不會。

新元件若有這類原生相依，照這個做：**一個可以從外面看到的狀態欄位**，而不是一行 README。

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
