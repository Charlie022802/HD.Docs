---
name: project_new_version_testbed_191
description: .191 = 新版 HDPACS 完整隔離測試床(自有 DB v2.0.27 + NAS .229 掛載);.234/.199 維持舊當對照組
metadata: 
  node_type: memory
  type: project
  originSessionId: 913e10e5-5ad9-400e-82d5-b8e1163936aa
  modified: 2026-08-10T04:27:42.184Z
---

**測試拓樸決策(2026-08-05):** 為了測新版又不動到現有動物醫院系統,把 **.191 做成完整、獨立的新版測試床**,`.234/.199` 那組原封不動當「舊的對照組」。

**三台角色:**
- **.234** = 動物醫院 PACS DB(HDPACS **v2.0.26**,手動維護)+ 舊 PACS 服務;吃 NAS **192.168.68.228**。是測試機但 .199 靠它。
- **.199**(hostname newdicomweb)= 舊 DicomWeb,連 **.234** 的 DB,吃 NAS **.228**(掛在 `/home/HD/CACHE01`,NFSv3)。**維持舊、不動。**
- **.191** = 手動全新裝的新版 PACS(6 支服務 + hd-media-package worker),**自己的本機 HDPACS DB(已 v2.0.27)**、原本影像在本機 `/home/HD/HDPACS-CACHE01`。

**為何不混用:** ①新服務吃 v2.0.27 schema,若 .191 連 .234 的 DB(v2.0.26 且 .199 共用)= 漂移/污染;②升 .234 到 27 會害 .199 舊服務面對新 schema→可能爆。故新版測試全集中在隔離的 .191。

**.191 NAS 掛載(2026-08-05 完成):** 使用者自建 NAS **192.168.68.229**(QNAP,HD-NAS02),export `/HDPACS` **只給主機 .191**;掛在 **`/home/HD/data`**(NFSv4.1、rw)。fstab 持久(`rw,hard,proto=tcp,vers=4.1,_netdev,nofail`)、SELinux `use_nfs_home_dirs on`。**踩雷:** QNAP export 預設 Squash 所有使用者→匿名 `guest`,且共用資料夾有 ACL(`ls -ldn` 顯示 `drwxrwxrwx+ 0 0`,777 是假象、ACL 才算數)→ guest 無寫入權 EPERM。**解:** 匿名 UID/GID 改成 `hdadmin`/`administrators`(NAS 上 hdadmin=uid 1000,對得上 .191)→ 寫入 OK,產出檔 owner=1000。方向:`/home/HD/data` 當「以後所有資料都走這條」的統一掛載點。

**待辦/計畫(規劃中,未做):**
1. ~~在 .191 架 DicomWeb~~ **改成:DicomWeb 續用 .199、repoint 連 .191(2026-08-05 完成)** —— 更貼近正式(DicomWeb 跨機 + 共用 NAS)。做法:①.199 掛同一 NAS `.229:/HDPACS`→`/home/HD/data`(同 .191 路徑,DB 存絕對路徑故必須同路徑);②.191 postgres 開放 /24(postgresql.conf listen_addresses 加 .191、pg_hba host HDPACS postgres 192.168.68.0/24 scram、firewall 5432、重啟);③備份 .199 舊設定(連 .234)到 `~/dicomweb-bk-*`(database.env+2 unit+42M app tgz,還原步驟在該處);④部署新 build(現 HEAD 含 REQ-004)：publish Api→`hd-pacs-linux.tgz`+`deploy/install.sh`(update 用、互動設 DB→填 191)→.199 `sudo bash install.sh`;⑤`db-init/run-all.sh` 在 .191 跑(init_dicomweb.sql+RBAC functions+perf_indexes)建 DicomWeb 專屬表(HD_API_KEY/HD_USER_AUDIT_LOG/UPS_*)+ 種 3 key + 2 匿名規則。**結果:.199 DicomWeb 新 build 連 .191、/health ok**。**API Key/匿名種子(改了 repo `db/init_dicomweb.sql`,待 commit):** 3 key(DicomWebViewer 無匿名 hdp_***、ShareServer→規則「ShareServer去識別」hdp_***、OnlineMeeting→「OnlineMeeting去識別」hdp_***;皆沿用舊 KEY_HASH 故舊明文續用)+ 2 條強化匿名規則(姓名/病歷號/accession *遮、其餘直接識別欄位 Remove、UID 保留)。MeetingsRoom 使用者決定不建。金鑰格式=`hdp_`+Base64URL(24B),hash=SHA256(ascii(整串));ROUTING_ANONYMISE 是原生表、init 順帶種規則。**端到端驗證通過(2026-08-05):** QIDO 從 .199 讀到 .191 study(DicomWebViewer 看完整 460185/D016/19500425);ShareServer key→QIDO 姓名/病歷號/accession `*`、生日/轉診醫師 Remove(**連搜尋端都套匿名**);WADO 縮圖 1st 664ms→2nd 22ms(REQ-004 快取命中,圖從 NAS `/home/HD/data/...` 讀)。整套隔離測試環境(DicomWeb 跨機+共用 NAS+.191 新版 DB)成形。REQ-003 Export WebApi 已完成(HD.Export 上線 .199:5090,見 [[project_req003_export_webapi]])。**2026-08-10 再確認定案:DicomWeb 不上 .191、長留 .199**(日後納 hdctl 管理也在 .199 做)。

**測試資料匯入(2026-08-05,兩台 AE 同名故不能 C-MOVE—目的地 AE `HDPACS` 會被 .234 解析成自己):改用直接 C-STORE 推送。** ①.191 唯讀掛 .228(動物醫院 NAS,export `/IJ8XUY`)到 `/mnt/nas228`(`mount -o ro`);.228 檔佈局 `<年>/<日期>/<ordinal>`(JPEG/MPEG4/Error/SQLBACK 是衍生檔略過)。②自製送檔器 **`hdstoresend`**(fo-dicom 5.2.5 console,`D:\HD-Release\test\hdstoresend\hdstoresend-linux.tgz`,原始碼在 scratchpad):遞迴掃目錄→C-STORE 推目標,用法 `dotnet hdstoresend.dll <srcDir> <host> <port> <calledAE> <callingAE>`,非 DICOM 略過、分批(200)。實測 `/mnt/nas228/2023/1024`→.191:2020 called HDPACS calling TESTSCU:8 OK + 8「Duplicate SOP instance(0111)」(重複 SOP 被擋,isAllowDuplicate 關,正常);.191 DB 4 studies/9 objects、檔落 NAS。calling AE 用 TESTSCU(.191 認得)。更多資料照此送(2023/1130=182、2024/0319=289 等)。

   ~~在 .191 架一個 DicomWeb 實例~~(原方案,已改上述)(連 .191 本機 DB、讀本機/NAS 影像)→ 讓新版全套(PACS+worker+DicomWeb)都在 .191 自成一國,供測 REQ-003 Export WebApi / REQ-004 縮圖快取 / 「JPEG 全導 DicomWeb」。DicomWeb 部署:`HD.Pacs.DicomWeb`,DB 連線走環境變數 `Database__ConnectionString`(install.sh 互動設定→`/etc/hd-pacs-dicomweb/database.env`);deploy 工具在 repo `deploy/`(install.sh、hd-pacs-linux.tgz)。目前 HEAD 已含 REQ-004(RenderedImageCache)+REQ-006(STOW 停 .meta)。
2. **把資料真的走 NAS**:**影像已搬(2026-08-05 驗證通過)** —— `VOLUME_CACHE`(VOLUME_REF 1, ONLINE)`DIR_PATH` 由 `/home/HD/HDPACS-CACHE01` 改成 **`/home/HD/data/HDPACS-CACHE01`**(clear_study 清舊 4 檔→改 path→重啟 hd-pacs→C-STORE 新檔落在 NAS、get_object_path 回 NAS 路徑、SELinux 沒擋)。**踩雷來源**:路徑烤在 SQL —— `1.create.sql:167` VOLUME_CACHE.DIR_PATH 欄位 DEFAULT `/home/HD/HDPACS-CACHE01`;`2.initialization.sql:591` burnTempPath `/home/HD/extend/burnSource/burnTemp`。**決策:不改 create/init 基底 SQL(動物醫院共用),改在安裝腳本 init 後加一段 UPDATE(參數化 storage root,預設 /home/HD/data/HDPACS-CACHE01)** —— 此安裝腳本 bake-in 尚未做。**burnTemp/viewer 仍在本機** `/home/HD/extend/burnSource/`,等 REQ-003(DicomWeb 跨機讀打包產出)再搬 NAS。
3. **匿名/API Key 種子**(見 [[project_dicomweb_features]] 的 API Key↔匿名機制):使用者要給 **SharedServer / MeetingsRoom / OnlineMeeting** 這些消費者「固定預設去識別」。機制=`public.ROUTING_ANONYMISE`(NAME+RULE jsonb)存規則、API Key 綁規則 NAME,取圖時 `RoutingAnonymiseRuleProvider` 依 NAME 撈+套。現有一筆「測試去識別」(00100010 ReplaceAll `*`、00100020 Clear、00100030 Remove、UID 不變)+ 一把 key「OnlineMeeting」(scope dicomweb.read)綁它。**待確認**(問了未答):要哪幾把 key、預設規則要不要更完整去識別、匯出(REQ-003)是否也套。是新 .191 DicomWeb 的種子設定,非改程式。

**REQ-003 Export WebApi(原目標,盤點完、設計待定):** 範圍=薄層 API(建立/查狀態/下載)+ 保留 hd-media-package worker(使用者確認)。放 DicomWeb(.199→測試在 .191)。三端點對應 export.* proc、下載讀 `EXPORT_JOB.PACKAGE_DIR`。詳見對話盤點(MediaPackage 與佇列耦合薄、export.* 契約)。

**金鑰明文刻意不記在這裡**（2026-08-20 移除，為了讓 memory 能納入版控）：要用時查 .199 的 `HD_API_KEY`，或主控台的金鑰管理頁。三把的用途與匿名規則對應如上，只有明文被拿掉。
