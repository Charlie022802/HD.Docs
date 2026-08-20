---
name: reference_version_two_sources
description: hdctl 元件的版本號有兩個來源(manifest 與 csproj),只改一邊會讓 /health 說謊——而它正是自動退版的判斷依據;hdpack 已加護欄
metadata:
  type: reference
---

hdctl 管理的每個元件，版本號**有兩個獨立來源**：

| 來源 | 誰在用 |
|---|---|
| `deploy/hdctl-manifest.json` 的 `version` | hdctl：決定檔名與 `releases/<版本>` 目錄名 |
| csproj 的 `<Version>` | 組件：**`/health` 回報的是這個** |

2026-08-21 交付 Export 時只 bump 了 manifest，結果 hdctl 說 `alpha.14`、服務自己說 `alpha.13`。
安裝成功、健康檢查也過，**沒有任何東西報錯**。

**Why 這不只是難看**：`/health` 正是用來確認「現在到底跑什麼」的地方，hdctl 的健康檢查與
**自動退版**都靠它（alpha.9 那次退版就是這樣判斷的）。它一旦說謊，出事時的判斷會整個歪掉 ——
你以為在看新版的行為，其實是舊版。

**How to apply**：`hdpack.py` 已加護欄（commit `4e0c94c`），打包前從 publish 目錄的
`<組件>.deps.json` 讀主組件版本（`libraries` 的鍵是 `"<組件名>/<版本>"`），與 manifest 比對，
不一致直接失敗並指出要改哪裡。所以現在**不需要靠記得** —— 但要知道它為什麼會擋你。

只檢查**單一服務**的元件（export／dicomweb／adminconsole）。多服務元件（pacs 有七支）的元件
版本本來就與各服務的組件版本不同，那是刻意的，自動跳過。逃生口 `--skip-version-check`。

相關：[[feedback_versioning_convention]]（序號什麼時候 +1）、[[project_main_pacs_deploy]]、
[[project_req003_export_webapi]]。
