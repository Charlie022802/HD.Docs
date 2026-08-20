---
name: project_dicomweb_deploy
updated: 2026-08-10
description: HD.Pacs.DicomWeb 部署到生產 .199 的指令與非互動/防回滾要點
metadata: 
  node_type: memory
  type: project
  originSessionId: 4955439c-e319-4882-9ff7-dc4be5c80843
  modified: 2026-08-10T06:58:40.786Z
---

**⚠️ 2026-08-10 起 .199 改由 hdctl 管理,以下 install.sh 流程退役(只留全新環境用)。現行更新流程:**
```
cd HD.Pacs.DicomWeb && dotnet publish src/HD.Pacs.DicomWeb.Api/... -o publish/hd-pacs-app
python ../hdctl/hdpack.py --publish publish/hd-pacs-app --manifest deploy/hdctl-manifest.json --out D:/HD-Release/hdctl-test
# 使用者 scp tgz+sha256 → sudo /usr/local/bin/hdctl install ~/hd-dicomweb-<ver>.tgz;退版=hdctl rollback dicomweb
```
元件=hd-dicomweb(兩 unit:主 5080 Modules dicomweb+admin、UPS 5081 Modules ups——**模組設定正本在 manifest,舊 systemd drop-in 已清除**);`links: data→元件層`(access.db/audit-spool 在 releases 外);appsettings preserve 自動帶;env 檔沿用 /etc/hd-pacs-dicomweb/*。Export 同機同模式(hd-export 元件,manifest envFiles 雙主機共用)。舊 flat 目錄備份在 /home/HD/service-backup/pre-hdctl/。**HTTPS**:nginx TLS 終結 443(deploy/setup-https.sh+nginx/hdpacs-tls.conf,名稱 hddicomweb;proxy buffer 已加大防 SaveTokens cookie 502)。

DicomWeb 生產部署到 **hdadmin@192.168.68.199**(host newdicomweb),服務名 `hd-pacs-dicomweb` port 5080。**⚠️ DB 連線:.199 現在連 192.168.68.191 的 HDPACS DB(新版測試床),不是 .234**(2026-08-06 證實:v2.0.27 proc 修正只跑在 .191,.199 API 行為即刻改變;.234 的 insert_package_job 無 TRIM 修正。連線在 /etc/hd-pacs-dicomweb/database.env)。要連線前先開 VPN 並告知使用者。ssh 需密碼(BatchMode/key 目前不通)→ **上傳/安裝由使用者自己在終端機跑**,我只負責 publish+打包。

**本機 publish + 打包**(在 repo 根 D:\Dev\HyperDigital\HD.Pacs.DicomWeb):
```
dotnet publish src/HD.Pacs.DicomWeb.Api/HD.Pacs.DicomWeb.Api.csproj -c Release -r linux-x64 --self-contained false -o publish/hd-pacs-dicomweb
tar -czf publish/hd-pacs-linux.tgz -C publish/hd-pacs-dicomweb .
```
(deploy/hd-pacs-linux.tgz 是舊習慣路徑,打包後順手 cp 覆蓋它避免上傳到舊檔。)

**上傳/安裝**(使用者跑):
1. 清家目錄殘留防回滾:`ssh hdadmin@192.168.68.199 "rm -f ~/install.sh ~/uninstall.sh ~/hd-pacs-linux.tgz && mkdir -p ~/hd-pacs-deploy"`
2. `scp deploy/hd-pacs-linux.tgz deploy/install.sh deploy/uninstall.sh hdadmin@192.168.68.199:~/hd-pacs-deploy/`
3. `ssh -t hdadmin@192.168.68.199 "cd ~/hd-pacs-deploy && chmod +x install.sh uninstall.sh && sudo ./install.sh"`

**Process 拆分(2026-07-31 上線,commit `8159897`)**:UPS 已拆成獨立 process。一次性跑 `deploy/install-ups-unit.sh`(sudo):由主 unit 衍生 `hd-pacs-dicomweb-ups`(port 5081, Modules=ups)、主 unit 加 drop-in override 只掛 dicomweb+admin(5080)、自動開防火牆(firewalld/ufw)。**之後更新只跑 install.sh 即可** —— 它會偵測 UPS unit 並一併重啟(兩 process 都套新 binary)。分流:5080=取像+管理網頁(/admin 只在這)、5081=UPS REST(/workitems,非網頁,要 X-API-Key;/scalar 兩邊都有列各自端點)。install.sh 本身不開防火牆(5080 是使用者早先自己開的)。

**install.sh 互動點**:`[4.5/6]` 問「是否覆蓋資料庫連線設定？[y/N]」→ 按 Enter(預設 N)=保留既有 /etc/hd-pacs-dicomweb/database.env(.234)。非互動可 `sudo ./install.sh < /dev/null`(EOF→預設 N)。**曾發生**從家目錄跑到殘留舊 install.sh+tgz 導致回滾→務必從乾淨 ~/hd-pacs-deploy 跑。data/(含 dev-signing-key.pem)勿刪否則 JWT 全失效。相關:[[project_immutable_original_coerce]] [[project_dicomweb_impl_split]]
