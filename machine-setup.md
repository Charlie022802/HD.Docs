# 換一台機器怎麼建構這個專案

同一個人在多台機器上輪流開發（例如租屋處一台、家裡一台）。網路不是限制 ——
兩邊都能用 VPN 連到 `192.168.68.x` 的 `.191` / `.199`。真正要處理的是
**git 帶不過去的東西**。

正本：這份文件。照著跑完就能接續前一台的工作。

---

## 1. 用完全相同的路徑：`D:\Dev\HyperDigital`

看似小事，但它決定了 Claude Code 的記憶能不能對上。

Claude Code 把每個專案的狀態放在 `~/.claude/projects/<路徑編碼>/`，
編碼是從工作目錄路徑轉出來的：

```
D:\Dev\HyperDigital  ->  D--Dev-HyperDigital
```

路徑不同，資料夾名就不同，記憶與 `/resume` 都對不上，得手動改名去湊。
**直接用一樣的路徑最省事。**

---

## 2. clone 11 個 repo

`origin` 是公司自架的 Forgejo（走外網，在家連得到），GitHub 是鏡像。

**兩個 repo 的目錄名與 repo 名不同**，要分開處理：

| 目錄 | repo 名 |
|---|---|
| `Database\` | `HDPACS-DB` |
| `docs\` | `HD.Docs` |

```bash
cd /d/Dev/HyperDigital
for r in HD.AdminConsole HD.Animal HD.DicomImageViewer HD.Export HD.LoggingPlatform HD.Net10 HD.Pacs.DicomWeb HD.Shared hdctl; do
  git clone https://forgejo.hdtech.tw/charlie/$r.git
done
git clone https://forgejo.hdtech.tw/charlie/HDPACS-DB.git Database
git clone https://forgejo.hdtech.tw/charlie/HD.Docs.git docs
```

補上鏡像 remote（`repo` 換成目錄名，`Database` 要用 `HDPACS-DB`、`docs` 用 `HD.Docs`）：

```bash
git remote add github https://github.com/Charlie022802/<repo>.git
```

推送慣例不變：`git push` 走 Forgejo，鏡像要明寫 `git push github master`。

---

## 3. 手動帶 7 個設定檔（git 不會帶）

這些被 gitignore 掉，因為含連線字串與密碼。**不要為了方便把它們加進版控。**
全部加起來不到 20 KB，用隨身碟或加密管道帶。

| 檔案 |
|---|
| `HD.AdminConsole/src/HD.AdminConsole.Web/appsettings.Development.json` |
| `HD.DicomImageViewer/src/HD.DicomImageViewer.Executer/appsettings.json` |
| `HD.DicomImageViewer/src/HD.DicomImageViewer.Server/appsettings.json` |
| `HD.DicomImageViewer/src/HD.DicomImageViewer/localconfig.json` |
| `HD.Export/src/HD.Export.Api/appsettings.Development.json` |
| `HD.LoggingPlatform/.env` |
| `HD.Pacs.DicomWeb/src/HD.Pacs.DicomWeb.Api/appsettings.Development.json` |

少了它們的症狀通常是「build 過但一跑就連不上 DB」，不會有明顯的錯誤指向設定檔，
所以這一步漏掉會很花時間。

---

## 4. 接上 Claude Code 的記憶

記憶正本放在 **`docs/claude-memory/`**（也就是 `HD.Docs` repo 裡），
機器上的 `~/.claude/projects/D--Dev-HyperDigital/memory` 是一個
**指向它的 junction**。

這樣做的理由：memory 是「跨對話傳遞背景知識」的機制，如果每台各留一份副本，
兩邊都會各自長出內容，而這種狀態紀錄一旦分岔比程式碼更難合。讓 repo 當唯一正本，
`git pull` 就等於同步記憶。

新機器上（PowerShell，路徑自行代換使用者名稱）：

```powershell
$live = "C:\Users\<你>\.claude\projects\D--Dev-HyperDigital\memory"
$repo = "D:\Dev\HyperDigital\docs\claude-memory"
if (Test-Path $live) { Rename-Item -Path $live -NewName "memory.pre-junction" }
New-Item -ItemType Junction -Path $live -Target $repo
```

驗證（應該看到 `Junction` 和目標路徑）：

```powershell
(Get-Item "C:\Users\<你>\.claude\projects\D--Dev-HyperDigital\memory") | Select-Object LinkType, Target
```

**要還原成一般資料夾**：刪掉 junction（`Remove-Item` 只會刪連結，不會動到 repo
裡的檔案），再把 `memory.pre-junction` 改名回 `memory`。

注意：記憶現在會跟著 git 走，所以 `git checkout` 到舊 commit 會讓記憶回到那個時間點。
平常不會這樣操作，但心裡要有數。

### 憑證不進記憶

2026-08-20 清掉了 5 處寫在記憶裡的憑證明文（3 個 API 金鑰、1 組 DB 密碼），
改成指向式描述。**之後也不要把明文寫進記憶**，因為它現在進版控了，
git 歷史很難真正抹掉。

---

## 5. 不用帶的東西

**對話紀錄 `~/.claude/projects/D--Dev-HyperDigital/*.jsonl`（約 160 MB）** ——
帶過去 `/resume` 是認得，但價值低：內容大半是工具輸出，結論早就萃取進
`claude-memory/` 和 `docs/` 了。

**`hd-web-server/`** —— 同事維護的服務，不是我們的 repo（見
[systems/hd-web-server.md](systems/hd-web-server.md)），需要時再取。

**`logs/`** —— 本機 log。

**`D:\HD-Release\`** —— 發布產物，可以重新打包，見
[environments.md](environments.md)。

---

## 6. 日常同步紀律

一個人兩台機器，靠 git 就夠，但有一條要守：

**離開任一台之前先 commit + push；回到另一台先 pull。**

忘記推的代價不只是程式碼分岔 —— `docs/` 和 `claude-memory/` 是狀態紀錄，
分岔之後兩邊都「看起來是對的」，很難判斷哪邊才是最新。

檢查全部 11 個 repo 有沒有漏推：

```bash
cd /d/Dev/HyperDigital && for d in Database HD.AdminConsole HD.Animal HD.DicomImageViewer HD.Export HD.LoggingPlatform HD.Net10 HD.Pacs.DicomWeb HD.Shared docs hdctl; do printf "%-22s 未提交=%-4s 未推=%s\n" "$d" "$(git -C $d status --porcelain | wc -l)" "$(git -C $d rev-list --count origin/master..HEAD 2>/dev/null)"; done
```

---

## 7. 其他環境相依

- **VPN**：兩台都要能連 `192.168.68.x`（`.191` 測試床、`.199` DicomWeb/Export）。
  沒有 VPN 時 `Test-NetConnection 192.168.68.191 -Port 5432` 會是 `False`，
  而症狀會是 Npgsql 逾時，不會明講是路由問題。
- **.NET SDK**：net10（`dotnet --list-sdks` 確認）。
- **pgAdmin**：DB 變更依慣例人工執行，不由程式自動跑。
- **開發機的 build 產物**：`bin/` `obj/` 不進版控，第一次 build 會慢一點，正常。
