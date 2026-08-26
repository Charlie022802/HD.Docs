---
name: feedback_shell_path_form
description: "給使用者的指令要配合他實際用的 shell——PowerShell 不認 /d/... 這種 Git Bash 路徑，會 No such file or directory"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ea8648ec-751b-449c-aab0-36db86e8c1e2
  modified: 2026-08-25T01:55:33.124Z
---

**給指令時，Windows 路徑一律寫 `D:\...` 或 `D:/...`，不要寫 `/d/...`。**

**Why:** 我自己是用 Bash 工具在跑，習慣了 `/d/Dev/HyperDigital` 這種 MSYS 路徑，就直接把它貼進給使用者的指令裡。但**使用者的終端多半是 PowerShell**，`/d/...` 在那裡不是路徑而是一個不存在的相對路徑，`scp` 直接回 `No such file or directory`。2026-08-25 傳 hdctl 包到 .191 時踩到，使用者說「過一陣子都會發生」——表示不是第一次。

**How to apply:**

- **Windows 端的指令**（scp、cd、檔案路徑參數）：用 `D:\path\to\file` 或 `D:/path/to/file`。**兩種在 PowerShell 與 Git Bash 都通**，`/d/...` 只有 Git Bash 通。
- **遠端 Linux 主機上的指令**：維持 `/tmp/...` 等 POSIX 路徑，那本來就對。
- 指令若一定要在特定 shell 跑（例如用了 heredoc `<<'SQL'`、`$(...)`、`&&`），**在指令上方明講「在 Git Bash 跑」**。PowerShell 5.1 沒有 `&&`、沒有 here-string 相容語法，貼過去會是 parser error。
- 同一段流程橫跨多台機器時，**每個步驟標明在哪台哪個 shell**（例：① 你的 Windows（Git Bash）② .191 ③ .140）。這在多主機維運時特別容易搞混。

相關：[[feedback_code_hygiene]]（別用 PowerShell 讀寫含中文的檔案）、[[project_main_pacs_deploy]]（sudo 要用 /usr/local/bin/hdctl 全路徑，同樣是「環境不同、路徑就不同」的坑）。

**VPN 異常時,同一個 IP 會連到別台機器,而且從機器內部分辨不出來(2026-08-26)。**
早上連 `192.168.68.163` 時,`/usr/local/bin` 是空的、昨天裝的 `hd-viewerapi` 目錄不見了,
`uptime` 卻是 244 天沒重開 —— 我據此推論「VM 被含記憶體的快照回滾」,**那是錯的**。
真相是 VPN 當時不正常,連到的是另一台機器,而**那台回報的主機名也是 `STJOHO_68_163`**,
服務清單看起來是某間醫院的生產主機。VPN 恢復後,昨天裝的東西原封不動都在。

**危險在於當時完全無法察覺**:主機名一樣、路徑結構一樣、連 `ls` 出來的形狀都像。
那天只跑了唯讀查詢所以沒事,**但同樣的情況下跑安裝或刪除,就會打到別人的正式機**。

**做法**:跨機操作前先確認身分,而不是只信 IP 與主機名。最便宜的是
`cat /etc/machine-id` + `ip link show <介面> | grep ether` + `uptime`。
連線行為變怪(逾時、要重試)之後尤其要確認。

**已知指紋(2026-08-26)**:
- `192.168.68.163`(STJOHO_68_163,內網測試機,CentOS 8):
  machine-id `ed1b2bfc146a41f5ae4411bdbb0413f2`、MAC `bc:24:11:96:81:63`、當時 uptime 42 天。
  早上誤連的那台 uptime 是 **244 天**、`/usr/local/bin` 空的、沒有 `hd-viewerapi`
  —— **uptime 差 200 天就是最快的判別點**。
