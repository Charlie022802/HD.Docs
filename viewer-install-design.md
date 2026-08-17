# 看片端安裝與更新設計(HD.DicomImageViewer)

狀態:**已實作並實機驗證**(2026-08-14)。對象:`D:\Dev\HyperDigital\HD.DicomImageViewer`(WinForms net10 桌面看片)。
起因:過去都用「直接複製過去」佈署,造成安裝路徑混亂、沒有安裝紀錄、無法退版。改用 Inno Setup 統一。

> **交給安裝同事前一定要講的兩件事**
>
> 1. 全新安裝出來的位址是**空的**,第一次啟動一定連不上。要在登入畫面的齒輪 →
>    「啟動設定」填**兩個**:「資料庫連線」的主機位址,以及**下載主機(DownloadIP)**。
>    後者現在是必填 —— 登入一律走 WebApi(直連資料庫那條路已移除),WebApi 的位址就是它。
>    位址留空是刻意的(見下方「設定範本」),但不先講他們會以為裝壞了。
> 2. 從舊的手動安裝換過來時,精靈第一頁會問**舊資料夾在哪**(通常已自動填好)。
>    指定之後資料庫位址、DownloadIP、螢幕配置都會沿用,上面那一項就不必重打。
>    路徑留空 = 當成全新機器。

## 要交付的三個元件

| 元件 | 裝在哪 | 備註 |
|---|---|---|
| `HD.DicomImageViewer` | 看片端 | 主程式,含 mesa(無 GPU 時的軟體 OpenGL) |
| `HD.DicomImageViewer.Executer` | 看片端 | 常駐 tray + gRPC :5002,HIS 連動的中繼 |
| `HD.DicomImageViewer.LinkClientDesktop` | **可能在另一台 HIS 電腦** | 需要 x64 與 x86 兩種 |

既有慣例(`D:\HyperDigital\ProgramPublish\DicomViewer\`)是各元件獨立 zip,舊版號是 .NET Framework 時代的四段式
(`HDVSExecuter_v1.0.0.7.zip`、`HDVSLinkClient_v1.0.0.6_x64/x86.zip`),與現行 `Directory.Build.props` 的 2.3.0 不同體系。

## 已完成的前置整備(2026-08-13)

安裝路徑混亂的根源不是佈署方式,是**程式對自己的位置有三處隱含假設**。全部改成 `localconfig.json` 的設定項後,
程式對安裝位置零假設,才有辦法裝進標準路徑或版本化目錄:

| 項目 | 原本 | 現在 | commit |
|---|---|---|---|
| `hd_conf.json`(同機 PACS) | 寫死 `@"..\hd_conf.json"`,相對**工作目錄**;檔案不存在直接丟例外 | `PacsConfigPath`,留空即略過,全程有防護 | `b38897f` |
| 影像快取 | 固定 exe 旁邊 | `CachePath`:相對路徑以 exe 為基準(預設 `"Cache"`)／絕對路徑／留空用 `%LOCALAPPDATA%` | `b38897f` |
| HD.Importer | 工作目錄的上一層 | `ImporterPath`,未設定與找不到分開提示 | `b38897f` |

其餘相關:
- 版本升 **2.3.0**,Release build 附台灣時間戳(`2.3.0+20260812-235856+0800`)(`561e74e`)
- LinkClientDesktop 拿掉寫死的 `PlatformTarget=x64`,改由 RID 決定,可出 x86(`561e74e`)
- 四個路徑設定進「啟動設定」對話框(登入畫面即可開)(`fabcec7`)
- **升版不再遺失使用者設定**(`50ab585`,見下方陷阱)

## 陷阱:使用者設定的存放位置綁「版本」也綁「安裝路徑」

.NET 使用者設定路徑長這樣:

```
%LOCALAPPDATA%\HD.DicomImageViewer\HD.DicomImageViewer_Url_<安裝路徑雜湊>\<組件版本>\user.config
```

兩段都會讓設定「消失」:

1. **版本一 bump 就換資料夾** —— 已用 `Settings.Upgrade()` + `upgradeRequired` 旗標解決(`50ab585`)。
2. **安裝路徑一變雜湊就變** —— `Upgrade()` **救不回**,它只在同一個雜湊資料夾底下找舊版本。
   開發機上實測就有兩份不同雜湊(Debug 與 Release 輸出各一)。

第 2 點直接決定安裝設計:**版本化目錄不能直接當執行路徑**,必須有個固定不變的
`current` 指標當啟動路徑,否則每次更新都會掉登入帳號、面板停靠狀態等。

## 目錄配置(已實作)

```
C:\HyperDigital\DicomImageViewer\        ← 預設，安裝時可改
├─ app\
│  ├─ 2.3.0\          ← 舊版留著供退版（保留最近 3 版）
│  │  ├─ Viewer\      localconfig.json / user-settings.json / log_config.json
│  │  └─ Executer\    appsettings.json
│  └─ 2.3.1\
├─ current\           ← junction，指向 app\2.3.1；捷徑與 ViewerPath 都指這裡
├─ logs\              ← 紀錄檔（在版本目錄外，更新與清舊版都不影響）
├─ tools\Rollback.ps1
└─ install-history.log
```

- 退版 = 把 junction 改指舊版,不重跑 installer、不搬檔案(秒級)
- 超過 3 版自動清掉;版本比大小是**逐段數值**比較,不是字串
  (字串比較在 2.3.10 之後會把最新版當成最舊的刪掉)
- **統一路徑最直接的好處**:installer 自動把 Executer 的 `ViewerPath` 寫成正確值。
  2026-08-12 踩過這個坑——`ViewerPath` 指向舊開發機路徑,連動整條掛掉且無錯誤訊息。

設定檔**隨版本目錄走**(而不是放獨立的 `config\`),因為程式從 exe 所在目錄讀 `localconfig.json`;
更新時由 `MigrateConfig` 從前一版搬過來,所以升版不掉設定。紀錄檔則刻意放在版本目錄**外面**。

## 紀錄

- 註冊表 `HKLM\SOFTWARE\HyperDigital\DicomImageViewer`:`Version` / `InstallPath` / `InstallDate`
- `install-history.log` 附加每次安裝與退版(何時、從哪版到哪版)
- Inno 本身的解除安裝註冊表項照舊

## 設定檔保留

三個元件都有機器層級設定,更新時**不可覆蓋**:

| 元件 | 設定檔 | 內容 |
|---|---|---|
| Viewer | `localconfig.json` | DB 位址、螢幕配置、Render3D、四個路徑 |
| Viewer | `user-settings.json` | 登入帳號、面板停靠狀態、字體倍率 |
| Executer | `appsettings.json` | **ViewerPath**、gRPC 位址、log 路徑 |
| LinkClient | `appsettings.json` | Executer 位址、log 路徑 |

作法:`MigrateConfig` 在更新時「前一版 → 舊手動安裝 → `.sample`」依序找,找到就用,已存在則不動。

## 設定範本(`.sample`)

出貨範本是 repo 裡的 `<檔名>.json.sample`,**開發機的工作檔已 gitignore**。

先前這兩個檔案同時扮演「開發機工作檔」與「出貨範本」,值必然不同,於是每次 commit 前
都要手動換值、commit 後換回來;漏一次醫院端就會裝到開發機的 DB 位址。分離之後這個來回消失。

**範本的 `Host` / `DownloadHost` 刻意留空**——醫院端不會是任何 `192.168.x` 位址,
給一個看起來像真的、實際上一定錯的預設值只會拖延發現問題的時間。留空則現場非填不可。

`user-settings.json` 這類沒有機器差異的設定不需要 `.sample`,`publish.ps1` 會自動回退到版控版本。

## 已定案

| 項目 | 決定 | 理由 |
|---|---|---|
| 退版機制 | 版本化目錄 + `current` junction | 可退多版、秒級、不搬檔案;對齊 Linux 側 hdctl |
| Runtime | **self-contained** | 現場(尤其醫師電腦)可能鎖安裝,而裝 .NET Runtime 同樣要管理員權限 |
| 安裝根目錄 | `C:\HyperDigital\DicomImageViewer`,安裝時可改 | 免提權、IT 好找 |
| 包怎麼切 | Viewer + Executer 一包(Components 勾選)、LinkClient 獨立(x64/x86) | LinkClient 常裝在 HIS 那台 |
| 紀錄檔位置 | 安裝時指定,預設 `{app}\logs` | 在版本目錄外,更新與清舊版都不影響 |
| 授權檔位置 | `%ProgramData%\HyperDigital\DicomImageViewer`,安裝時建立並 icacls 授權 Users 可寫 | 同上理由;**解除安裝不刪**,重裝要能沿用原授權。見 [viewer-license-design.md](viewer-license-design.md) |

## 安裝精靈的四頁

| 頁面 | 出現時機 | 內容 |
|---|---|---|
| 沿用舊版設定 | 看片端包,**且不是從本安裝程式的前一版升級** | 指定舊的 Viewer / 連動服務端資料夾,把現場設定搬過來 |
| 連動來源限制 | 看片端包,勾選連動服務端時 | HIS 主機 IP →建立防火牆規則。留空=同網段;填 `Any` 會跳警告;**`0.0.0.0` 直接擋下** |
| 紀錄檔位置 | 看片端包 / 連動用戶端包 | 預設 `{app}\logs`,並以 icacls 授權 Users 可寫 |
| 連動服務位址 | 連動用戶端包 | 寫進 `ExecuterUrl`;指向 localhost 會再確認一次 |

### 沿用舊版設定(REQ-013)

醫院現行是「直接複製資料夾」佈署的,沒有前一版目錄可以搬。不匯入的話,每一台換過來的
機器都要重打資料庫位址、DownloadIP、螢幕配置 —— 那正是最容易打錯又最難查的幾項
(打錯的症狀是「連不上」,或更糟:連到別家醫院的主機)。

路徑會自動偵測:**舊 Executer 從開機自動啟動項回推,舊 Viewer 再從它設定裡的 `ViewerPath`
回推**。後者比「猜同一層的兄弟資料夾」可靠 —— 舊版是人工佈署的,位置沒有規律。

舊版與現行的 `localconfig.json` **欄位結構相同**,所以整份複製比逐欄搬安全
(螢幕配置那種巢狀陣列不適合用字串手術);舊檔沒有的新欄位再從 `.sample` 補回去,
免得「全新安裝」與「從舊版搬過來」兩種機器行為不一致。

**連動服務端只搬埠號。** `ViewerPath` 必須指向新的 `current\`,搬舊值會讓連動整條掛掉
而且沒有錯誤訊息;綁定位址也不能沿用 —— 舊版寫的是 `localhost`,那樣 HIS 在另一台就
永遠連不進來。

> ⚠️ **螢幕名稱會變。** 設定裡存的是 `DISPLAY1`、`DISPLAY2` 這種 Windows 顯示裝置名稱,
> 而換插孔、換顯卡、筆電接不同擴充座都會讓編號改變(實測一台是 `DISPLAY1 + DISPLAY6`)。
> 只照名稱配對的話,對不上的那顆螢幕會被當成「沒有設定」——啟動時不開視窗
> (查得到片卻沒地方顯示),在「啟動設定」畫面則被當成新螢幕、**打開按個確定就把配置歸零**。
> 兩邊都沒有錯誤訊息。規則已抽成 `MonitorPairing`:先照名稱、剩下的依序補。

`0.0.0.0` 要擋是因為它在防火牆的來源欄位裡是「位址剛好等於 0.0.0.0 的電腦」而不是「任何來源」——
規則會建立成功、看起來正常,但連動一樣不通。會這樣填是很自然的聯想,因為服務的**綁定位址**
確實用 `0.0.0.0` 表示所有網卡。

## 實機驗證(2026-08-13,以 2.3.0 → 2.3.1 實跑)

安裝、更新、退版、解除安裝全數通過:`current` 為真 junction、開機自啟指向 `current\`、
防火牆規則(埠號從設定讀出而非寫死、先刪再加)、**更新不掉設定**、退版後讀到該版當時的設定、
重裝不覆蓋現場值、一般使用者權限寫得進 log 目錄。

**試裝中抓到兩個 bug**:

1. **Executer 開機自啟時讀不到設定** —— `WebApplication.CreateBuilder()` 以工作目錄為
   ContentRoot,而開機自啟時工作目錄是 `C:\Windows\system32`,找不到 `appsettings.json`。
   後果全部靜默:Kestrel 退回 `localhost:5000`(連動用戶端打 5002 永遠連不上)、
   `ViewerPath` 為 null、完全沒有 log。**等於開機自啟整個是壞的**,而捷徑啟動正常
   只是因為捷徑帶了 `WorkingDir`。
2. **退版腳本沒有提權** —— 要寫 HKLM、要在 `C:\` 底下重建 junction。失敗的位置正好是
   「舊 junction 已刪、新的還沒建」,程式會直接開不起來。

兩個都已修正並重測。第 1 點若沒實裝就出貨,現場會是「重開機之後連動就死了,而且什麼紀錄都沒有」。

## 打包

```powershell
.\deploy\build.ps1              # publish + 打三個包
.\deploy\build.ps1 -SkipPublish # 只改了 .iss 時
```

產出在 `deploy\output\`。ISCC 最後會改寫 exe 的資源區(版本資訊、圖示),
防毒的即時掃描常常正在掃那顆剛寫出來的檔案而失敗(`EndUpdateResource failed`, error 110)——
腳本會自動重試三次,仍失敗就把 `deploy\output` 加進防毒排除清單。

安裝包的圖示與程式相同,`SetupIconFile` 指向 `src\hyper_logo64.ico` 那份正本
(`Directory.Build.targets` 也指同一份)。該 ico 目前只含一張 64×64,Explorer 的大圖示檢視會放大而模糊。

## 看片端連得到什麼(交付時要確認)

看片端目前是**混合的**,DB 存取正在往伺服器端搬(`HD.DicomImageViewer.Server`),還沒搬完:

| 走 WebApi(80) | 直連 PostgreSQL(5432) |
|---|---|
| 登入驗證、影像下載 | 系統與使用者設定、**病人與檢查查詢**、權限、授權 |

所以**醫師的電腦兩個埠都要通**。只開 WebApi 的話症狀是「登入成功但進去什麼都查不到」——
那種半通不通最難查。

`DownloadHost` 現在是**必填**:直連資料庫的登入路徑已移除(驗證帳密是伺服器的職責),
WebApi 的位址就取自它。

### 連線中斷會自動重試一次

連線池會遞出已經死掉的連線 —— 主機重啟、防火牆丟掉閒置的 TCP、VPN 換路由都會造成,
而這邊要等到真的拿去用才會炸。以前使用者看到的是「無法讀取使用者設定,可能是資料庫連線異常」,
得自己再按一次登入;醫師看到那句話只會覺得系統壞了。

現在登入路徑上的三支查詢(系統設定、使用者設定、權限)遇到**連線層**失敗會自動重試一次
(`SafePostgresConnection.RunRead`)。**只給讀取用** —— 連線若是在讀回應途中斷掉,
那道指令可能已經在伺服器上執行過,寫入重試會變成執行兩次。

判斷哪些該重試有個反直覺處:`pg_terminate_backend` 與伺服器重啟送回來的是
**`PostgresException 57P01`**,不是 socket 例外。把 `PostgresException` 一律當成
「SQL 層的錯、不重試」的話,最典型的那個情況反而救不到。

## 靜默安裝(一次裝好幾台)

```
setup.exe /VERYSILENT /LEGACYVIEWER="E:\HD\HDDicomViewer" /LEGACYEXECUTER="E:\HD\Executer"
```

精靈模式下舊路徑取自「沿用舊版設定」那一頁;靜默安裝沒有人可以填欄位,所以改吃命令列參數。
兩個參數都可省略(= 全新機器)。

> ⚠️ 那一頁刻意用**文字輸入框**而不是 `CreateInputDirPage`:後者有 Inno 內建的
> 「必須是完整路徑」驗證,**空白過不去** —— 而「全新的電腦、沒有舊版」正是最常見的情況,
> 用 InputDir 會把每一台新機器都卡在那一頁,錯誤訊息還是看不出關聯的通用字串。

## 這台開發機反覆踩到的編碼坑

Windows 的工具預設用系統編碼(CP950)讀檔,而我們的檔案是 UTF-8。一天內踩了五次:

| 情境 | 症狀 | 解法 |
|---|---|---|
| `.iss` / `.ps1` 含中文 | 中文變亂碼、字串引號被打斷 | 存成 UTF-8 **with BOM** |
| `psql -f 含中文的 .sql` | `byte sequence ... in encoding "BIG5"` | `$env:PGCLIENTENCODING='UTF8'` |
| PowerShell 傳含雙引號的參數給原生 exe | 引號被吃掉(psql 找不到大寫表名) | 用管道餵 SQL,或改用不需引號的寫法 |

另外 Inno 的 Pascal 註解裡**不能出現 `{app}`** —— 那個 `}` 會把 `{ ... }` 註解提早關掉。

## 相關

- 版控規約:user skill `hd-versioning`(語意版本/階段序號/build 戳記三層分工)
- Linux 側的統一部署框架:`hdctl`(versioned dir + symlink flip + sha256 + 健檢自動退回),概念可對齊
- 連動鏈路:HIS → LinkClientDesktop(gRPC :5002)→ Executer(tray)→ NamedPipe → Viewer
- 授權(註冊)機制:[viewer-license-design.md](viewer-license-design.md)、backlog REQ-012
