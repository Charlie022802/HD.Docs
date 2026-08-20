---
name: feedback_code_hygiene
description: 使用者要求—程式碼與 SQL 不要用 emoji(會夾帶不可見字元);我自己的教訓—別用 PowerShell 讀寫 UTF-8 檔案(會把中文寫成亂碼)
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ea8648ec-751b-449c-aab0-36db86e8c1e2
  modified: 2026-08-17T14:09:20.347Z
---

**④ 斷言全綠不代表功能達成目的——要檢查「時序」而不只是「結果」(2026-08-18 學到)。**

**Why:** 打包進度回寫的第一版通過了四項斷言(有中間值、單調遞增、上限 99、最終 100),但**佔 88% 執行時間的階段完全沒有進度**,而那正是功能要解決的問題。同一組斷言在壞版本與好版本都通過,差別只在**進度出現的時機**。這種綠燈比紅燈危險,因為它讓人停止檢查。

**How to apply:** 驗證「持續性/漸進式」的功能時,除了值本身,要斷言**值出現的時間分布**——例如「首個進度不得晚於全程 35%」「進度點數不得少於 N」「最長間隔不得超過 X」。發現異常的線索通常是**「這個時間軸不合理」的直覺**(60 秒空白然後 8 秒衝完),然後去比對 log 時間戳。另外:**推論錯了就加 log 拿實際數字**,不要連續猜——那次我猜錯兩次(先猜某階段本來就慢、再猜分母算錯),都是靠新增的 log 才排除。

**① 程式碼與 SQL 裡不要用 emoji(2026-08-17 使用者明確要求:「把 emoji 拿掉」)。**

**Why:** emoji 會夾帶不可見字元——`⚠️` 帶的是 `U+FE0F`(變體選擇符),使用者把 SQL 貼進 pgAdmin 時跳「含隱藏／雙向 Unicode 字元」警告。Trojan Source 那類攻擊正是利用看不見的字元讓程式碼「顯示一回事、執行另一回事」,所以工具警告是合理的。

**How to apply:** `.sql`／`.cs`／`.ps1`／`.sh`／`.csproj` 一律用純文字(`⚠️` → 「注意：」)。**`→ ← ① ② ─` 這些排版符號可以留**——它們不是 emoji、都是可見字元,在註解裡表達流程與編號很有用。**markdown 文件不受此限**(使用者說「2 沒關係」),emoji 在給人讀的文件裡是慣例。2026-08-17 已一次清掉 30 個檔案跨 7 個 repo(各 repo 一個純註解 commit,清完先 build 過才 commit)。掃描腳本思路:找 `U+26A0 / FE0F / 2705 / 2714 / 2718 / 26D4 / 1F511 / 23F3 / 1F51C`。

**② 別用 PowerShell 讀寫含中文的檔案——我自己踩過(2026-08-17)。**

**Why:** Windows PowerShell 5.1 的 `Get-Content -Raw` **預設用 ANSI(CP950)讀 UTF-8**,中文全變亂碼;再 `Set-Content -Encoding utf8` 寫回就把亂碼存進檔案。我用它改 csproj 與 hdctl-manifest 的版本號,把兩個檔的中文註解全毀了(靠 `git checkout` 還原)。

**How to apply:** 改檔案一律用 **Edit／Write 工具**(編碼正確)。真的需要腳本處理時用 **Python 明確 `encoding='utf-8'`**。相關但不同的一顆:**寫 `.ps1` 檔要存成 UTF-8 with BOM**,否則 PowerShell 5.1 讀不出中文註解、直接 parse error(既有的 build.ps1 能跑就是因為有 BOM)。

**③ 驗證素材要挑「多 series 多影像」的 study——我同一天犯兩次。**

用只有 1 張影像的 study 測「study/series/instance 三層級」,四個數字全是 1,**測試全綠但什麼都沒驗到**。改用 744 張／9 series 才真正驗到差異。**判準:如果各測項的期望值互相不衝突,那個測試就沒有鑑別力。**

相關:[[reference_pacs_db_schema]](migration 驗證方法)、[[project_media_export_redesign]]。

**5. 加一個新的列舉值／狀態，要回頭掃所有既有的分支與訊息。**
2026-08-21 給 `PACKAGE_JOB` 加了 `expired` 狀態，DB、API、清單全都對，但下載被拒的
409 訊息還是舊的「打包尚未完成」—— 而 `expired` 的 `progress` 是 100、也不是還在跑，
使用者會一直等一個永遠不會好的東西。**功能全對，訊息說謊。**
新值加得越乾淨（值域集中、CHECK 有擋），越容易忘記那些**沒有型別保護的地方**：
字串訊息、`switch` 的 default、前端的狀態文字對照。加值之後搜一遍舊值出現的所有位置。

