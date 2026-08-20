# 換一台機器怎麼建構這個專案

同一個人在多台機器上輪流開發。網路不是限制 —— 兩邊都能用 VPN 連到
`192.168.68.x` 的 `.191` / `.199`。真正要處理的是 **git 帶不過去的東西**。

2026-08-20 完整走過一遍，下面的指令與坑都是實際跑出來的。

**指令一律用 PowerShell。** Windows PowerShell 5.1 不支援 `&&`，也沒有
`for ... do ... done`，貼 bash 指令會直接 parser error。要用 bash 就開 Git Bash。

---

## 1. 用完全相同的路徑：`D:\Dev\HyperDigital`

看似小事，但它決定了 Claude Code 的記憶能不能對上。專案狀態放在
`~\.claude\projects\<路徑編碼>\`，編碼由工作目錄路徑轉出：

```
D:\Dev\HyperDigital  ->  D--Dev-HyperDigital
```

路徑不同就對不上，得手動改名去湊。

```powershell
New-Item -ItemType Directory -Force D:\Dev\HyperDigital
```

---

## 2. clone 11 個 repo

**11 個都要 clone，不能只挑要用的** —— 專案之間有跨 repo 參考（例如
`HD.Net10\HD` 參考 `HD.Shared\src\HD.Shared.Logging`），少一個就 build 不起來。

名稱一致的 9 個：

```powershell
Set-Location D:\Dev\HyperDigital; foreach ($r in 'HD.AdminConsole','HD.Animal','HD.DicomImageViewer','HD.Export','HD.LoggingPlatform','HD.Net10','HD.Pacs.DicomWeb','HD.Shared','hdctl') { git clone "https://forgejo.hdtech.tw/charlie/$r.git" }
```

**目錄名與 repo 名不同的 2 個**，最後的目錄名參數不能省，否則資料夾會叫
`HDPACS-DB\` 和 `HD.Docs\`，路徑就跟另一台對不上：

```powershell
Set-Location D:\Dev\HyperDigital; git clone https://forgejo.hdtech.tw/charlie/HDPACS-DB.git Database
```

```powershell
Set-Location D:\Dev\HyperDigital; git clone https://forgejo.hdtech.tw/charlie/HD.Docs.git docs
```

補上 GitHub 鏡像 remote：

```powershell
Set-Location D:\Dev\HyperDigital; foreach ($d in 'HD.AdminConsole','HD.Animal','HD.DicomImageViewer','HD.Export','HD.LoggingPlatform','HD.Net10','HD.Pacs.DicomWeb','HD.Shared','hdctl') { git -C $d remote add github "https://github.com/Charlie022802/$d.git" }
```

```powershell
Set-Location D:\Dev\HyperDigital; git -C Database remote add github https://github.com/Charlie022802/HDPACS-DB.git; git -C docs remote add github https://github.com/Charlie022802/HD.Docs.git
```

確認 11 個都有 `origin` 和 `github`：

```powershell
Set-Location D:\Dev\HyperDigital; Get-ChildItem -Directory | Where-Object { Test-Path "$($_.FullName)\.git" } | ForEach-Object { "{0,-22} {1}" -f $_.Name, ((git -C $_.FullName remote) -join ' ') }
```

推送慣例不變：`git push` 走 Forgejo，鏡像要明寫 `git push github master`。

---

## 3. 補上 7 個 gitignore 掉的設定檔

這些含連線字串與密碼，所以不進版控。**但幾乎都不必從另一台搬** ——
repo 裡有範本，只有 DB 密碼要自己填。

四個直接從範本複製：

```powershell
Set-Location D:\Dev\HyperDigital; Copy-Item 'HD.DicomImageViewer\src\HD.DicomImageViewer.Executer\appsettings.json.sample' 'HD.DicomImageViewer\src\HD.DicomImageViewer.Executer\appsettings.json'; Copy-Item 'HD.DicomImageViewer\src\HD.DicomImageViewer\localconfig.json.sample' 'HD.DicomImageViewer\src\HD.DicomImageViewer\localconfig.json'; Copy-Item 'HD.DicomImageViewer\src\HD.DicomImageViewer.Server\appsettings.template.json' 'HD.DicomImageViewer\src\HD.DicomImageViewer.Server\appsettings.json'; Copy-Item 'HD.LoggingPlatform\.env.example' 'HD.LoggingPlatform\.env'
```

三個 `appsettings.Development.json` 手動新建（存成 UTF-8），內容只差連線字串，
`Host` 指測試床 `192.168.68.191`、密碼填看片端 `Program.cs` 裡寫死的那組：

| 檔案 | Pool 設定 | 其他 |
|---|---|---|
| `HD.Export\src\HD.Export.Api\appsettings.Development.json` | Min 2 / Max 50 | 加 `Logging.LogLevel` |
| `HD.Pacs.DicomWeb\src\HD.Pacs.DicomWeb.Api\appsettings.Development.json` | Min 5 / Max 100 | 加 `PostProcess.Enabled=false`、`Serilog` |
| `HD.AdminConsole\src\HD.AdminConsole.Web\appsettings.Development.json` | Min 2 / Max 20 | 只要連線字串 |

連線字串長這樣：

```
Host=192.168.68.191;Port=5432;Database=HDPACS;Username=postgres;Password=<自己填>;Pooling=true;Minimum Pool Size=2;Maximum Pool Size=50;Connection Idle Lifetime=300;Command Timeout=30
```

驗收：

```powershell
Set-Location D:\Dev\HyperDigital; foreach ($f in 'HD.AdminConsole\src\HD.AdminConsole.Web\appsettings.Development.json','HD.DicomImageViewer\src\HD.DicomImageViewer.Executer\appsettings.json','HD.DicomImageViewer\src\HD.DicomImageViewer.Server\appsettings.json','HD.DicomImageViewer\src\HD.DicomImageViewer\localconfig.json','HD.Export\src\HD.Export.Api\appsettings.Development.json','HD.LoggingPlatform\.env','HD.Pacs.DicomWeb\src\HD.Pacs.DicomWeb.Api\appsettings.Development.json') { if (Test-Path $f) { "OK  $f" } else { "缺  $f" } }
```

**漏掉的症狀是「build 過但一跑就連不上 DB」** —— 錯誤訊息不會指向設定檔，
所以這一步漏掉會很花時間。

### localconfig.json 的兩條線

`Database.Host`（查 metadata）與 `DownloadHost`（抓影像）是**分開的兩個欄位，
指向不同主機**。範本刻意把兩個都留空。

`Database.Host` 填 `192.168.68.191`。`DownloadHost` 要指向跑影像 API 的主機 ——
**`.191` 上沒有**（80/443/5000 都沒有服務在聽），所以純開發機跑不起完整看片端。
這不影響 build 與 DB 相關工作。

2026-08-19 有一次「清單查得到、影像調不出來」的排障，根源就是這兩條線指向不同
主機而其中一台沒有那筆影像。見 [systems/hd-web-server.md](systems/hd-web-server.md)。

---

## 4. 接上 Claude Code 的記憶

記憶正本放在 **`docs/claude-memory/`**（`HD.Docs` repo 裡），機器上的
`~\.claude\projects\D--Dev-HyperDigital\memory` 是**指向它的 junction**。

這樣做的理由：memory 是跨對話傳遞背景知識的機制，若每台各留一份副本，兩邊都會
各自長內容，而狀態紀錄一旦分岔比程式碼更難合。讓 repo 當唯一正本，`git pull`
就等於同步記憶。

先把上層資料夾建出來（junction 需要它已存在）：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\projects\D--Dev-HyperDigital"
```

> **不要為了建這個資料夾去終端機打 `claude`** —— 桌面版應用程式不會在 PATH 裡
> 註冊 `claude` 指令（兩台都是如此），只會得到 `CommandNotFoundException`。
> 直接用上面那行建資料夾即可，Claude 桌面版之後會認得。

建 junction（不需要系統管理員權限，junction 跟 symlink 不同，不用提權）：

```powershell
$live = "$env:USERPROFILE\.claude\projects\D--Dev-HyperDigital\memory"; $repo = "D:\Dev\HyperDigital\docs\claude-memory"; if (Test-Path $live) { Rename-Item -Path $live -NewName "memory.pre-junction" }; New-Item -ItemType Junction -Path $live -Target $repo
```

驗證（要看到 `Junction` 和目標路徑，以及 48 個檔）：

```powershell
Get-Item "$env:USERPROFILE\.claude\projects\D--Dev-HyperDigital\memory" | Select-Object LinkType, Target
```

```powershell
(Get-ChildItem "$env:USERPROFILE\.claude\projects\D--Dev-HyperDigital\memory\*.md").Count
```

**要還原成一般資料夾**：刪掉 junction（只會刪連結，不動 repo 裡的檔案），
再把 `memory.pre-junction` 改名回 `memory`。

注意：記憶現在跟著 git 走，`git checkout` 到舊 commit 會讓記憶回到那個時間點。

### 憑證不進記憶

2026-08-20 清掉 5 處寫在記憶裡的憑證明文（3 個 API 金鑰、1 組 DB 密碼、
1 個測試金鑰），改成指向式描述。**之後也不要寫明文** —— 它進版控了，
git 歷史很難真正抹掉。

---

## 5. 驗收

VPN 接上後先測內網。這個一定要先過，否則之後 DB 操作只會看到 Npgsql 逾時，
錯誤訊息不會告訴你是路由問題：

```powershell
Test-NetConnection 192.168.68.191 -Port 5432 -InformationLevel Quiet
```

再 build：

```powershell
Set-Location D:\Dev\HyperDigital; dotnet build HD.Net10\HD\HD.csproj --nologo; "ExitCode=$LASTEXITCODE"
```

> **第一次執行 `dotnet` 會印歡迎訊息（裝開發憑證、遙測說明）並吃掉 build 輸出**，
> 看起來像沒跑。再跑一次就正常。也因此驗收不要用 `-v q`：成功時它什麼都不印，
> 分不出是成功還是沒執行。用 `$LASTEXITCODE` 判斷最可靠，`0` 就是成功。

輸出應該同時看到 `HD.Shared.Logging` 和 `HD` 兩個專案 —— 跨 repo 參考有解到，
代表 11 個 repo 的相對位置正確。

---

## 6. 不用帶的東西

- **對話紀錄 `~\.claude\projects\D--Dev-HyperDigital\*.jsonl`（約 160 MB）** ——
  帶過去 `/resume` 認得，但價值低：大半是工具輸出，結論早就萃取進
  `claude-memory/` 和 `docs/` 了。
- **`hd-web-server/`** —— 同事維護的服務，不是我們的 repo
  （見 [systems/hd-web-server.md](systems/hd-web-server.md)），需要時再取。
- **`logs/`**、**`D:\HD-Release\`** —— 本機 log 與發布產物，可重新產生。

---

## 7. 日常同步紀律

**離開任一台之前先 commit + push；回到另一台先 pull。**

忘記推的代價不只是程式碼分岔 —— `docs/` 和 `claude-memory/` 是狀態紀錄，
分岔之後兩邊都「看起來是對的」，很難判斷哪邊才是最新。

```powershell
Set-Location D:\Dev\HyperDigital; Get-ChildItem -Directory | Where-Object { Test-Path "$($_.FullName)\.git" } | ForEach-Object { "{0,-22} 未提交={1,-4} 未推={2}" -f $_.Name, (git -C $_.FullName status --porcelain).Count, (git -C $_.FullName rev-list --count origin/master..HEAD) }
```

---

## 8. 其他環境相依

- **.NET SDK**：net10（實測 `10.0.400`，兩台一致）。
- **Git**：實測 `2.36.1` 可用。
- **VPN**：要能連 `192.168.68.x`。沒接上時 `Test-NetConnection` 會是 `False`。
- **pgAdmin**：DB 變更依慣例人工執行，不由程式自動跑。
- **Forgejo 認證**：偶爾第一次會回
  `Credentials are incorrect or have expired`，重試一次通常就過。
