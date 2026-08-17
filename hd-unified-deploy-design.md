# HD 統一部署框架設計（定案）

集中放 `/home/HD/service`，每個元件可**獨立安裝／更新／退版**；共置不綁定更新。
定案：**hdctl 用單檔 Python 3（只用標準庫）**、**每元件各自 tgz**、**symlink 版本切換**、
**manifest 內嵌於包 + sha256/簽章 + 相容性中繼資料**、保留**release 協調包**。

## 1. 原則
- 單一安裝根、單一 hdctl；所有操作以元件（component）為單位。
- 更新一個元件只碰它自己的 unit，不動其他元件。
- 加新元件＝多一個 tgz，既有更新流程不變。
- 一律 **hdadmin** 執行（非 root）；SELinux/權限一次設好、全元件共用。

## 2. 目錄佈局（binary 不可變 + symlink 切換）
```
/home/HD/service/
  hd_conf.json                 共用：DB(host/port/name) + PACS.AETitle（PACS 讀）
  <component>/
    releases/
      <version>/               解壓的 tgz（純 binary，不可變）
    current -> releases/<version>   ← 現行版（原子切換點）
    data/  logs/               放 releases 外，切版/退版都保留
/home/HD/service-releases/     上傳暫存 + 已驗證的包（incoming）
/etc/hd/
  db.env                       共用 DB 完整 connstring（含帳密，DicomWeb 等用）
  logplatform.env              共用 LOGPLATFORM_URL / LOGPLATFORM_API_KEY
```
- systemd unit 的 `WorkingDirectory`/`ExecStart` 一律指 `.../<component>/current`。
- **data/logs/設定放 releases 外** → release 目錄可丟棄、切換乾淨。
- 保留最近 N 個 release 目錄（預設 3），舊的自動清。

## 3. 元件包（tgz）格式
`hd-<component>-<version>.tgz` + 同名 `.sha256`（可選再加簽章 `.sig`）。包內含：
```
manifest.json          元件宣告（見下），隨包走、不另存 components/ 目錄（避免漂移）
app/ …                 dotnet publish 產物
db/migrations/ …       （可選）冪等 SQL
```
`manifest.json`（示意，DicomWeb）：
```json
{
  "component": "dicomweb",
  "version": "1.0.0-alpha.2+20260803-...",
  "services": [
    { "unit": "hd-dicomweb", "exec": "dotnet app/HD.Pacs.DicomWeb.Api.dll", "cpuQuota": null }
  ],
  "envFiles": ["/etc/hd/db.env", "/etc/hd/logplatform.env"],
  "ports": [5080],
  "migrations": "db/migrations",
  "requires": { "hdctl": ">=1.0", "db_schema": ">=HDPACS_20260720" }
}
```
`pacs` 包同理，`services` 列 11 支、`startLast: ["hd-dicom-service-manager"]`、`sharedConfig: "hd_conf.json"`、`ports:[2020,3320]`。UPS 若拆獨立 process 就在 dicomweb 包多列一個 unit（Modules 開關）或另出 ups 包。

## 4. hdctl（單檔 Python 3、stdlib）
```
sudo hdctl install <component> <tgz>     # 首裝：驗 sha256/簽章→檢查 requires→解壓到 releases/<ver>
                                          #      →建/更新 unit（EnvironmentFile 指 /etc/hd）→flip current→configure hook→start
sudo hdctl update  <component> <tgz>     # 驗證→解壓新版→stop→flip current→start→驗證（僅該元件）
sudo hdctl rollback <component> [--to <ver>]   # stop→flip current 回上一版(或指定)→start（瞬間，不複製）
sudo hdctl apply   <release.json>        # 協調發布：一次多元件（見 §6）
sudo hdctl status|start|stop|restart <component|all>
sudo hdctl migrate <component>           # DB 變更，opt-in、預設不自動
sudo hdctl version                       # 各元件 current 版 vs releases 可用版
sudo hdctl prune   <component>           # 清舊 release 目錄（留 N）
```
- **驗證流程（每次 install/update）**：比對 `.sha256`（有簽章則驗簽）→ 讀包內 manifest 的 `requires`，`hdctl` 版本與 `db_schema` 不符就**擋下**並提示。
- **更新＝symlink flip**：新版解壓到 `releases/<ver>`，stop→flip→start；失敗自動 flip 回舊版。
- **退版**：純 flip，無檔案複製；因 data/logs 在 releases 外，天然保留。

## 5. 設定模型（單一 HDPACS DB，已定）
安裝**只問一次 DB**（host/port/name/pool/timeout/帳密），一次寫兩處：
- `hd_conf.json` 的 `Database`（host/port/name…）→ PACS 服務。
- `/etc/hd/db.env` 完整 connstring（含帳密）→ DicomWeb（`Database__ConnectionString`）等。
- `/etc/hd/logplatform.env` → 全元件共用日誌設定（留空=不送）。
> 現況落差：PACS `PostgresConnection` 帳密寫死於程式——建議統一後改讀 hd_conf.json/env（後續清理，非前置）。

## 6. release 協調包（保留）
平常各元件獨立更新；需要「一起上」（例如 PACS+DicomWeb 共用一個 DB migration）時用：
`release.json`
```json
{
  "release": "2026Q3-1",
  "components": [
    { "component": "pacs",     "tgz": "hd-pacs-2.0.5.tgz",              "sha256": "…" },
    { "component": "dicomweb", "tgz": "hd-dicomweb-1.0.0-alpha.2.tgz", "sha256": "…" }
  ],
  "order": ["pacs", "dicomweb"],
  "migrations": ["pacs", "dicomweb"]   // opt-in，仍不自動；列出建議順序供 hdctl migrate 提示
}
```
`hdctl apply release.json`：全部先驗 sha256/requires（**全綠才動手**）→ 依 order 逐一 update（各自 flip）→ 任一失敗可整批 rollback。

## 7. hdadmin 權限 / SELinux（一次設好）
- **dotnet 放 /opt（或 /usr/share/dotnet）**，不放 /home（避 init_t 執行 user_home_t 被擋）。
- **env 一律 /etc/hd/*（etc_t、root:600、restorecon）**；放 /home 會 AVC denied 且 `EnvironmentFile=-` 靜默略過（[[project_shared_logging]] 踩雷）。
- 解壓新 release 後對其 `restorecon -R`；全在 /home/HD 下 hdadmin 擁有。
- **current symlink 必須標 `usr_t`（2026-08-10 .191 實證）**：init_t 讀 user_home_t 的 lnk_file 被擋
  （CHDIR EACCES、目錄反而沒事）；flip 產新 link 標籤重置，每次 flip 後重標（hdctl 已內建）。
- 原生執行檔綁低埠→`setcap`；dotnet dll 由 /opt/dotnet 執行。
- hdctl 產 unit 時**必帶 `EnvironmentFile=/etc/hd/*.env`**，否則日誌 no-op（[[project_main_pacs_coerce_logging]] B）。

## 8. DB migration
每元件自帶冪等 SQL；`hdctl migrate <component>` 獨立、**預設不自動跑**（沿用「SQL 我給、你在 pgAdmin 跑」）。首裝 PACS 的 AE Title 三處 DB 動作歸 pacs configure hook，只 install 跑一次。

## 9. 安裝時互動決策
裝哪些元件 / DB（一次問，寫 hd_conf.json + /etc/hd/db.env，單一 HDPACS DB）/ LoggingPlatform env / DicomWeb 拆不拆獨立 unit + HTTPS 反代 / AE Title。

## 10. 從現況遷移
- DicomWeb 現有 `deploy/install.sh` → 改寫成 `dicomweb` 包 + configure hook（行為等價、被 hdctl 調度）。
- 舊 `D:\ProgramPublish` install/update/rollback → 一般化進 hdctl（讀 manifest，不寫死清單）。
- 舊 `hd-web-server` / `hd-web-dicom-scu`（fo-dicom 4，不在 HD.Net10.slnx）：預設不含；要的話另立 legacy 包。

## 11. 後續（實作時）
- 打包腳本：從 `dotnet publish` 產物 + manifest 產 tgz + sha256（+簽章）。
- hdctl 首次如何上主機（自身也做成 hd-ctl 小包 / 或版控單檔 .py）。
- 簽章金鑰管理（若採簽章）。
