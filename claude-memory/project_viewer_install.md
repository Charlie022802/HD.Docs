---
name: project-viewer-install
description: "看片端(HD.DicomImageViewer)Inno Setup 安裝/更新/退版—已實作並實機驗證(2026-08-14);試裝抓到開機自啟的致命 bug"
metadata: 
  node_type: memory
  type: project
  originSessionId: 13e6b6ed-984d-4c27-aed8-2170077bfa02
  modified: 2026-08-14T10:05:37.972Z
---

**✅ 已實作並實機驗證(2026-08-14,正本 `docs/viewer-install-design.md`)**。三個包:看片端(Viewer+Executer,Components 勾選)、連動用戶端 x64/x86。打包 `deploy\build.ps1`(`-SkipPublish` 只改 .iss 時)。

**定案**:版本化目錄 `app\<版本>\` + 固定 `current` junction、**self-contained**(現場可能鎖安裝,而裝 .NET Runtime 同樣要提權)、根目錄 `C:\HyperDigital\DicomImageViewer`(可改)、只留最近 3 版、**紀錄檔放 `{app}\logs`(版本目錄外)**。

**⚠️ `current` junction 是非做不可的**:.NET 使用者設定路徑含**安裝路徑雜湊**,執行路徑一變就掉登入帳號/面板狀態,而 `Settings.Upgrade()` 救不回。(後來 user-settings 已改存 exe 旁 JSON,但 junction 對捷徑/ViewerPath/退版仍是核心。)

**✅ 2.4.0 加了「沿用舊版設定」(REQ-013,2026-08-14 實裝驗證過)**:醫院現行是「直接複製資料夾」佈署,`MigrateConfig` 只認得前一版目錄與 `.sample`,搬不到。做法=精靈多一頁,**舊 Executer 從開機自動啟動項回推、舊 Viewer 再從它設定的 `ViewerPath` 回推**(比猜兄弟資料夾可靠);舊版與現行 `localconfig.json` **欄位結構相同**,所以**整份複製**比逐欄搬安全(螢幕配置那種巢狀陣列不適合字串手術),缺的新欄位再從 `.sample` 補(否則「全新裝」與「搬過來」行為不一致)。連動端**只搬埠號**——`ViewerPath` 必須指新 `current\`,綁定位址不能沿用舊版的 `localhost`。更新既有安裝時跳過這頁。

**⚠️ 由此帶出的螢幕坑(現場幾乎必踩)**:設定存的是 `DISPLAY1`/`DISPLAY2` 這種 Windows 裝置名,**換插孔/顯卡/擴充座就會變**(實測一台是 `DISPLAY1 + DISPLAY6`)。只照名稱配對 → 對不上的那顆被當成「沒設定」→ **啟動時不開視窗**(查得到片卻沒地方顯示,無錯誤訊息);而在「啟動設定」畫面被當成新螢幕 → **打開按個確定就把配置歸零**。規則抽成 `Configurations/MonitorPairing.cs` 一份共用(原本 `CreateForms` 與 `StartupSettingsForm` 各一份):先名稱精確配對、剩下依序補;比對用**相等不是 Contains**(否則 DISPLAY10 被 DISPLAY1 吃掉);另補「有視窗但沒人負責看片就強制第一個兼看片」。16 項測試。

**✅ 2.4.0 出貨包(2026-08-14,`0bd4c32` / `2.4.0+20260814-175614+0800`;先前 `c571782` 那顆作廢)**,含授權(蒐集階段)、登出、舊設定匯入、舊工具列轉換、連線重試、三個設定頁的 UI。**動到登入路徑與啟動流程,第一台裝完要走完整圈冒煙測試再裝其他台。** ⚠️ **`DownloadHost` 變必填**(直連 DB 的登入路徑已移除,登入一律走 WebApi);**醫師電腦 80 與 5432 兩個埠都要通**(查詢/設定/授權仍直連 DB,只開 WebApi 會變成「登入成功但查不到東西」)。靜默安裝:`setup.exe /VERYSILENT /LEGACYVIEWER="..." /LEGACYEXECUTER="..."`。

**安裝精靈四頁**(第一頁見上):①連動來源限制(HIS IP→防火牆規則;**填 `0.0.0.0` 直接擋下**——那在防火牆來源欄位是「位址等於 0.0.0.0 的電腦」不是「任何來源」,規則建得起來但不通,而服務的**綁定位址**確實用 0.0.0.0 表示所有網卡,所以這樣填很自然)②紀錄檔位置(並 icacls 授權 Users 可寫,否則提權安裝建的目錄一般使用者寫不進去→完全沒有 log)③連動服務位址(指向 localhost 會再確認)。

**⚠️ 設定範本用 `.sample`,工作檔已 gitignore**:`localconfig.json` / Executer `appsettings.json` 原本身兼「開發機工作檔」與「出貨範本」,值必然不同,每次 commit 前要換值、commit 後換回(一天做三次,漏一次醫院端就裝到開發機 DB 位址)。現在 repo 只留 `*.json.sample`,`publish.ps1` 優先讀它、沒有才回退 `git show`。**範本 `Host`/`DownloadHost` 刻意留空**——醫院端不會是任何 `192.168.x`,給一個一定錯的預設值只會拖延發現問題。**⇒ 交付時要告訴安裝同事:裝完 DB 位址是空的,要在「啟動設定」填。**

**試裝抓到兩個 bug(沒實裝就出貨會直接踩)**:
1. **Executer 開機自啟讀不到設定** —— `WebApplication.CreateBuilder()` 以工作目錄為 ContentRoot,開機自啟時是 `C:\Windows\system32`。後果全靜默:Kestrel 退回 `localhost:5000`(連動打 5002 永遠不通)、`ViewerPath` 為 null、完全沒有 log。捷徑啟動正常只是因為捷徑帶 `WorkingDir`。→ 改指 `AppContext.BaseDirectory`。
2. **退版腳本沒提權** —— 要寫 HKLM、重建 `C:\` 下的 junction;失敗點正好是「舊 junction 已刪、新的還沒建」,程式直接開不起來。→ 腳本開頭自行 RunAs。

其他修正:三支的 log 路徑寫死我們機器的磁碟(醫院/HIS 不一定有 D 槽)→建 logger 前先確認可寫、不行退到 exe 旁;`DicomQuery` 自開的查詢 sink 已移除(與主 log 重複);清舊版的版本比大小改**逐段數值**(字串比較在 2.3.10 之後會刪掉最新版)。

**這台開發機反覆踩的編碼坑(一天五次)**:Windows 工具預設用 CP950 讀 UTF-8 檔。`.iss`/`.ps1` 含中文要存 **UTF-8 with BOM**;`psql -f` 要 `$env:PGCLIENTENCODING='UTF8'`;PowerShell 傳含雙引號的參數給原生 exe 會被吃掉(psql 找不到大寫表名)→改用管道餵 SQL。另:**Inno 的 Pascal 註解裡不能出現 `{app}`**,那個 `}` 會提早關閉註解。打包時 ISCC 改寫 exe 資源區常被防毒鎖住(error 110)→ build.ps1 已自動重試三次。

相關:[[project_viewer_license]](註冊機制)、[[project_viewer_doctor_requests]]、[[feedback_versioning_convention]]、[[project_main_pacs_deploy]](Linux 側 hdctl)
