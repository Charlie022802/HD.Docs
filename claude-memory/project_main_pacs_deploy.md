---
name: project_main_pacs_deploy
description: 主 PACS(HD.Net10) 部署—既有 D:\ProgramPublish 安裝流程分析 + 新版決策(沿用 /home/HD/service、DicomWeb 併入、root→hdadmin 權限/SELinux)
metadata: 
  node_type: memory
  type: project
  originSessionId: a23fe480-c347-41d9-ba5a-eb699a5d1cf4
  modified: 2026-08-17T16:48:58.610Z
---

**🔑 `.191` 與 `.199` 都用 `hdadmin` 這個帳號 SSH 登入(不是 root,root 直登被擋)。上傳的元件包放 `~/` 就好,再 `sudo /usr/local/bin/hdctl install ~/hd-<元件>-<版>.tgz`(tgz 與 .tgz.sha256 兩個檔都要傳)。**

**🔑 `.191` 現在 `pacs 2.0.11+20260818153626`(2026-08-18 連佈五次:2.0.8 進度回寫→2.0.9/2.0.10 加診斷 log→2.0.11 修 continue)。**

**🔑 .191 現況(2026-08-17):pacs 元件已在 `2.0.6+20260817215344`**(當日連續佈兩次:2.0.5 帶媒體匯出 worker 新表支援+兩個 BaseDirectory 修正,2.0.6 修 JPEG 的 fo-dicom ImageManager 與「全失敗仍標 ready」)。**打包=`bash deploy/pack-pacs.sh /d/HD-Release/packages`**(Git Bash;它 publish 七個專案到各自子目錄再呼叫 hdpack)。版本改 `deploy/hdctl-manifest.json`(各專案 csproj 的 `<Version>` 混雜且與 manifest 不同步——2.0.4/2.0.5 都有,值得日後用 Directory.Build.props 統一)。安裝一次動七個服務故主 PACS 會短暫中斷;裝完 `sudo systemctl is-active` 七個都要 active。

**~~containViewer=true 會失敗~~ 這句是錯的,2026-08-18 實測更正**:打包**不會失敗**,job 標 `ready`,產出的是「宣稱含看片程式、附了 `rules.enc`+`study_elements.json`、但沒有看片程式本體」的光碟——比失敗更難發現。根因:`PackageService.DirectoryCopy` 對不存在的來源只 `LogError` 然後 `return`(不丟例外),空目錄連 error 都沒有。**已修**(pacs 2.0.7):`containViewer` 分支複製前先擋三種情況(viewerPath 未設/目錄不存在/目錄是空的)並丟例外→`failed` 帶原因。

**`cd-viewer-win` 為什麼一直是空的**:不是漏傳,而是 `HD.DicomImageViewer/deploy/publish.ps1` 只發佈 Viewer/Executer/LinkClient,**`HD.DicomImageViewer.Media`(光碟版)從來不在清單裡**,net10 時代沒人產出過。已新增 `deploy/publish-cdviewer.ps1`(self-contained、`viewer.media.json` 以正式檔而非 .sample 出貨、缺 mesa 就中止),**2026-08-18 已部署 .191(247M)**。
- 產出 245MB/tar.gz 96MB(`mesa/libgallium_wgl.dll` 58.7MB + .NET self-contained 含 WPF 組件 23MB;`PublishTrimmed` 官方不支援 WinForms)。DVD 無妨,**燒 CD 只剩約 455MB 放影像**。
- **副作用要注意:`containViewer` 預設是 `true`**。目錄空的時候這預設沒代價,填好之後**任何沒明確傳 false 的呼叫下載都從 700KB 變 131MB**。Export API 的 zip 用 `CompressionLevel.Fastest`(131MB;參考:zlib L1=105MB、L6=96.5MB、tar.gz=95.4MB→**zip 容器本身只比 tar.gz 差 1%**,差距全在壓縮等級),且**每次下載重壓一次不快取**。**Export API 的預設已於 alpha.8 翻成 false**(DB 端仍 true,kiosk/legacy 要的正是它)。

**階段二完成(2026-08-10 同日,.191 三元件 pacs/export/adminconsole 全在 hdctl 管理下+驗收,含 C-STORE 收檔與重開機測試全過):** 第四顆 CWD 雷=**ContentRoot=CWD→共用 WorkingDirectory 時 appsettings 整份沒載到**(無檔案日誌/等級/Service 開關全預設)→hdctl **0.2.1** unit 自動塞 DOTNET_CONTENTROOT+ASPNETCORE_CONTENTROOT 指服務程式目錄(從 exec 的 dll 路徑推導,C# 不用改;adminconsole 的 wwwroot 也靠這個)。檔案日誌已驗證回來(/home/HD/service/hd-pacs/logs/,worklist/transmit/service-manager 檔案為事件驅動)。舊 /opt/hd-admin-console 留備份待清。hdctl **0.2.0**=+apply(全驗才動/依序/失敗整批退)+links(共用設定 symlink 進包內)+start/stop/restart/status+migrate(列未套 SQL+--done 登記)。**.191 已遷入 hdctl:pacs(7 服務一元件,`HD.Net10/deploy/hdctl-manifest.json`+`pack-pacs.sh`)、export;adminconsole 包已備待裝**。hd_conf.json 正本仍在 /home/HD/service/(links 相對 symlink 回指,GetConfigurationyDirectory 找 dll 上一層不用改)。**多服務共用 WorkingDirectory 三雷**:①LoggingPlatform 緩衝檔 CWD 相對→七行程共寫+各自補送=事件七倍(已修 HD.Shared.Logging 預設錨 AppContext.BaseDirectory+重佈 .191)②CacheControl Temp ③service-manager History(②③已修待下次發版)。檔案日誌改落 /home/HD/service/hd-pacs/logs(舊 /home/HD/logs 不再寫)。workflow-manager 現場 appsettings 的 DicomRetrieveService:false 已搬回新佈局(preserve 之後自動帶)。舊七資料夾備份在 /home/HD/service-backup/pre-hdctl/。hd-web-server 照舊不遷(設計排除)。

**hdctl 三階段計畫(2026-08-10 定案):**
- **階段一 MVP 已完成(2026-08-10)**:`D:\Dev\HyperDigital\hdctl\`(自有 git repo)——hdctl.py(install/rollback/list/prune;sha256+requires 驗證、保留設定、產 unit(EnvironmentFile=/etc/hd)、防火牆、symlink flip、健檢失敗自動退回)+hdpack.py(publish→tgz+sha256+自動 build 戳);manifest 正本放各元件 repo `deploy/hdctl-manifest.json`(首例 HD.Export,envFiles 用統一 /etc/hd/db.env+logplatform.env)。WSL 全流程自測+**.191 試裝 hd-export 驗收完成(2026-08-10)**:install/更新(--force)/rollback 全過(HTTP 200)。**SELinux 新雷:init_t 讀 user_home_t 的 lnk_file 被擋**(WorkingDirectory 經 current symlink→CHDIR EACCES crash-loop;目錄本身沒事,所以直接目錄佈局的主 PACS 服務從沒踩過)→hdctl flip 後自動 semanage+chcon -h 標 usr_t(已內建)。.191 已有 /etc/hd/db.env(Database__ConnectionString);sudo secure_path 沒含 /usr/local/bin→要 `sudo /usr/local/bin/hdctl`。export DB schema .191 沒有(/health 過、建 job 會失敗,試裝只驗機制)。
- **階段二**:.191 全元件逐支遷移(可與現行並存)+release 協調包(release.json 整組升)。
- **階段三**:.234 舊換新正式部署(終極目的,另規劃停機窗口)。
- 過渡工具:`HD.Net10/deploy/update-services.sh`(`33a9779`,tgz+備份+保留 appsettings 的現行慣例)。

主 PACS(HD.Net10)部署。既有安裝包在 `D:\ProgramPublish`(參考的是含舊元件的版本);新版部署另放別位置但**沿用 `/home/HD/service` 佈局**。相關:[[project_main_pacs_coerce_logging]](這批要部署的程式)、[[project_dicomweb_deploy]](DicomWeb 部署,也在 /home/HD/service)。

**既有 D:\ProgramPublish 結構:** `builds\v1.0.0|v1.0.1\`(各含 install/update/rollback/uninstall/start-all/stop-all/restart-all.sh + version.txt + services\ + selinux\ + 打包鏡像 hd-installer-vX\ + .tar.gz);`clients\chang-gung\`(客製 SQL);`docs\install-guide.html`。

**佈局(install.sh):** 安裝根 `/home/HD/service`、log `/home/HD/logs`、備份 `/home/HD/service-backup`(update 時備份、只留 3 份)。執行帳號預設 **hdadmin**。DB 預設 Host 127.0.0.1 Port **6432** Name HDPACS。

**設定機制(重要):** 集中式 `/home/HD/service/hd_conf.json`(Database + PACS.AETitle)**所有 .NET 服務共用**;各服務 `appsettings.json` **只放 Serilog**(File sink 寫 `../../logs/*.log`=/home/HD/logs)。服務靠 `ServiceConfiguration.GetConfigurationyDirectory()` 找 hd_conf.json。

**install.sh 做的事:** ①檢查 root/dotnet、偵測 postgresql service(寫 Requires/After) ②互動問 DB/AE/帳號、選配 Media Package ③複製 services/<name>→/home/HD/service ④產生 hd_conf.json ⑤psql 改 DB 三處(AE_MAIN.AE_TITLE where AE_REF=1、AE_CONFIG 的 dicomServiceManager.pacs/worklist.aeTitle、HD_CONFIG WORKLIST/SYSTEM.aeTitle) ⑥建 systemd unit(Type=simple,User=hdadmin,ExecStart=dotnet …dll,Restart=always RestartSec=30;hd-pacs 加 CPUQuota=50%;**unit 無任何 Environment/EnvironmentFile**) ⑦hd-web-server 特殊:setcap cap_net_bind_service(綁 80)、copy libvips 到 /usr/local/lib+ldconfig、開防火牆 80/2020/3320、`semodule -i selinux/*.pp` ⑧啟動+驗證(hd-dicom-service-manager 最後)。update/rollback/uninstall 皆不動 DB。

**服務清單(13):** hd-pacs/hd-callback/hd-archive-manager/hd-cache-delete/hd-workflow-manager/hd-worklist-server/hd-dicom-to-image/hd-dicom-to-video/hd-dicom-transmit/hd-dicom-service-manager/hd-media-package(選配) 這 11 支=HD.Net10.slnx。舊 web 元件(不在新 slnx)決策(2026-08-03):**hd-web-server=DB/PACS 控制網頁介面,營運需要要裝**(原生執行檔 Node/sharp+libvips+port80,沿用 legacy build 本身沒改;裝法 setcap 綁80+libvips→/usr/local/lib+ldconfig+SELinux .pp(hd-web-server-policy.pp/policy2.pp)+unit 帶 LD_LIBRARY_PATH+SHARP_IGNORE_GLOBAL_LIBVIPS;config.json pg 指本機 HDPACS,port 5432 直連;grpc dicomSCU:5002 需 hd-web-dicom-scu 故網頁 DICOM 功能不動);**hd-web-dicom-scu=舊 dicom-web(fo-dicom4),已被 .199 新 DicomWeb 取代,不裝**。打包 `D:\HD-Release\test\hd-webserver.tgz`(hd-web-server+selinux+install-web.sh)。

**新版決策 / 注意事項:**
- 沿用 `/home/HD/service` 佈局;**DicomWeb 也放 /home/HD/service**(與 [[project_dicomweb_deploy]] 對齊;目前 DicomWeb 部署在 .199 的 ~/hd-pacs-deploy,未來整併時位置要一致)。
- **root→hdadmin 權限/SELinux(關鍵):** 舊版都 root 跑,新版一律 hdadmin(非 root)。要多注意:①systemd(init_t)執行 `/home/HD` 下的執行檔可能被 SELinux 擋(user_home_t/home_root_t)→dotnet 建議放 /opt(比照 DicomWeb install DOTNET_DIR=/usr/share/dotnet 避 /home 標籤);②**EnvironmentFile 必須放 /etc(etc_t)**,放 /home 會被 init_t AVC denied 且 `-` 靜默略過(見 [[project_shared_logging]] 踩雷);③hdadmin 寫 /home/HD/{service,logs} 自己的檔沒問題,但 atomic tmp+rename 會產新 inode 需注意標籤(見 [[project_hd_animal_webcontroller]] 的 var_lib_t 經驗);④低埠(80)非 root 綁定靠 setcap 或 polkit。
- **B 日誌缺口:** 現行 unit 無環境變數,而共用日誌要 `LOGPLATFORM_URL`/`LOGPLATFORM_API_KEY` 才會送。新版 install 要在 hd-pacs/hd-worklist-server(及後續其他服務)unit 加 `EnvironmentFile=/etc/hd/logplatform.env`(/etc、root:600、restorecon etc_t),否則日誌 no-op。

**統一部署框架(定案設計,2026-08-03,詳 `D:\Dev\HyperDigital\hd-unified-deploy-design.md`;未實作):** 集中 /home/HD/service 但每元件獨立更新。定案決策:
- **hdctl = 單檔 Python3(只用標準庫)**,指令皆帶元件:install/update/rollback/apply/status/start/stop/restart/migrate/version/prune。
- **每元件各自 tgz** `hd-<component>-<version>.tgz` + `.sha256`(+可選簽章);**manifest.json 內嵌於包**(services/envFiles/ports/migrations/`requires`{hdctl,db_schema}相容中繼資料),不另存 components/ 目錄避漂移。
- **symlink 版本切換(藍綠)**:`<component>/releases/<ver>/`(不可變 binary) + `current -> releases/<ver>`;update=解壓新版→stop→flip current→start(失敗自動 flip 回);rollback=純 flip 不複製;保留 N 版。**data/logs/設定放 releases 外**故切版天然保留。unit 的 WorkingDirectory/ExecStart 指 `.../current`。
- **release 協調包**保留:`release.json` 列多元件版本+order,`hdctl apply` 全驗(sha256+requires)才動、依序 update、可整批 rollback——供 PACS+DicomWeb 需一起上(如共用 migration)時用。
- **單一 HDPACS DB**:安裝只問一次 DB→寫 hd_conf.json(host/port/name 供 PACS)+ /etc/hd/db.env(完整 connstring 含帳密供 DicomWeb)。日誌 /etc/hd/logplatform.env 全元件共用。
- **DicomWeb 併入**成一個 component(現有 deploy/install.sh 改寫成 configure hook);舊 hd-web-server/hd-web-dicom-scu(fo-dicom4)預設不含。
- 現況落差待清理:PACS `PostgresConnection` 帳密寫死程式,統一後宜改讀 hd_conf.json/env。
- 待辦(實作時):打包腳本(publish→tgz+sha256)、hdctl 自身上主機方式、簽章金鑰管理。

**正式部署暫緩(2026-08-04 決策):** `.234` 先不動、**保留舊版 HDPACS**;新版(A0–A3+B 已 .191 驗過)續留 .191。日後要上正式再處理 .234 舊換新(hdadmin/舊 CentOS runtime/停舊 PACS 避埠衝突)。

**.191 測試部署(2026-08-03,進行中):** 新版 HDPACS 先在 .191(測試機、**本機 DB**)做舊換新驗 A1/A2/B。踩雷:**.191 只裝了 .NET 6,新版是 net10→服務 crash(status=150 找不到 framework)**。教訓:部署前先驗 `dotnet --list-runtimes` 有無目標 framework(install-hd.sh 已加此檢查;hdctl 環境檢查也該擋)。.191 舊 HDPACS 跑在 .NET 6。決定整台清空重來(無測試資料):①teardown HDPACS(停/移所有 hd-* unit + rm /home/HD/service,service-backup,logs,/etc/hd)②環境包 `uninstall_offline.sh`(全移除,含 /home/HD/pgdata)③`install_offline.sh`(.NET 選 **3**=10.0;裝 PostgreSQL18+pgbouncer(6432)+建 HDPACS DB via create.sql)④新版首裝。**環境包 install_offline.sh 的 .NET 是選單 1/2/3(6/8/10),要選 3**。DB 走 pgbouncer 127.0.0.1:6432。**新版首裝包 `D:\HD-Release\test\hd-new-install.tgz`**(6 支子集:pacs/worklist/transmit/callback/media-package/service-manager + `install-hd.sh`;建 unit 帶 `EnvironmentFile=-/etc/hd/logplatform.env`、hd_conf.json、DB AE 更新、firewall 2020/3320、SELinux dotnet bin_t 檢查、排除舊 web 元件)。舊版 `deploy-a1a2b.sh`(只換 binary、需既有 unit)清空後不適用,改用 install-hd.sh。

**DB SQL 維護方式(2026-08-04 更新):** 原本與同事共維、正本放 SharePoint;**現在使用者單人維護,改以本地為 canonical 正本:`D:\Dev\HyperDigital\Database\HDPACS\db_update_sql\`**(剛從 SharePoint 下載的完整集,含真正的 `db_update_v2.0.27.sql`=Charlie 的 convert_studydate_to_age/get_next_delete_study 等)。SharePoint 改成放連結或定期上傳備份。**版本桶概念**:每個 `db_update_v2.0.N.sql` 是一個「開放版本桶」,結案前會累積多筆不同日期/作者的變更(每筆 `-- YYYYMMDD 作者` + DDL);對應 `DB版本.xlsx` 每版一個分頁(row1 B 欄「尚不可更新」=未結案)。**未結案版本就往當前那支加尾,不另開新號**(如 2.0.27 仍開著,REQ-007 就併進 27,不是開 28)。**`D:\Dev\HyperDigital\Database` 已 git init(branch master, baseline `4106cc0`, 2026-08-04)版控**:含 `HDPACS/db_update_sql/`(canonical 增量 SQL)、`HDPACS/DB版本.xlsx`(版本登記表:總覽現況+28版索引)、`HDPACS_20260720.sql`(dump 參考);`.gitattributes` 固定 .sql=LF/.xlsx=binary。**已接遠端私有 repo `origin` → github.com/Charlie022802/HDPACS-DB(master 追蹤)**,異地備份;改完 SQL/版本表就 commit+push。環境包 `D:\HD-Release\environment\sql\` 是給 installer 的衍生副本(自有 git),**已於 2026-08-04 同步到 v2.0.27**(commit `e76fe45`;與 canonical 差異僅補 27,其餘 md5 全同)。日後有新 db_update 就從 canonical 複製過去 + 在 env/sql commit。**下面這段是舊(SharePoint 為主)流程,保留供參:** HDPACS 的 schema/增量 SQL 正本在 SharePoint(RC_share/HyperDigital/DB文件/DB2.0(Revised)/db_update_sql),使用者抓下來放環境包 `environment/sql/`(create.sql + initialization.sql + db_update_v2.0.1..26.sql,採版本化增量)。**原 `install_offline.sh` 寫死每個 `run_sql` 呼叫→每加一個 SQL 要手動加行、會漏。已改成自動探索跑 sql/ 內全部 *.sql**:`for _f in $(ls "$SQL_DIR"/*.sql | sort -V); do run_sql basename; done`。**SharePoint 新版命名改用數字前綴** `1.create.sql`/`2.initialization.sql`(+db_update_v2.0.N),sort -V 即正確執行序(1→2→db_update 依版本、v2.0.22-1 在 22 後)。下載是 zip+時間戳子夾(如 202608031722/,含 1.create/2.initialization/...),要**攤平到 sql/ 扁平**才對得上 installer(SQL_DIR=sql/)。也順手把 env 包 .sh 的 CRLF 洗成 LF(免 shebang `command not found`)。**變更鐵則:db_update 檔 append-only 不可變,要改=加新 db_update_v2.0.(N+1).sql,永不編輯已發布舊檔(否則已套用過的 DB 會漂移)**。**記錄差異用 git**:已對 `D:\HD-Release\environment\sql\` `git init`+baseline commit(2026-08-03,v2.0.26);每次 SharePoint 同步=覆蓋 sql/ 檔案→`git add -A && git commit -m "sql sync <時間戳>"`,`git diff` 即顯示新增/被改(偷改舊檔會現形),取代時間戳資料夾快照。全新安裝跑全部;**既有 DB 只補新增檔**——需 migrations 追蹤表(schema_migrations(filename),跑前查跑後記,已套用跳過)才安全,這是 hdctl `migrate` 該內建的,現全新安裝先不加。改動只在 `D:\HD-Release\environment\install_offline.sh`;使用者若另有 env 包正本要同步回去。

**版本現況（2026-09-01 `hdctl list` 實測，取代上面較舊的版本號）：** .191 的 `hd-pacs` 是 **2.0.13+20260825100752**（七支 unit 全 active）、`hd-adminconsole` 是 **0.1.0-alpha.31**。三台主機（.191/.199/.163）的 hdctl 都已升到 **0.2.7**。各台完整安裝清單記在 `docs/environments.md`。
