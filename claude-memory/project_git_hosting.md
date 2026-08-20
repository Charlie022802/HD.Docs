---
name: project_git_hosting
description: 全部 11 個 repo 搬到公司自架 Forgejo(origin)+ GitHub 降為鏡像;docs\ 變成 HD.Docs repo
metadata: 
  node_type: memory
  type: project
  originSessionId: 13e6b6ed-984d-4c27-aed8-2170077bfa02
  modified: 2026-08-17T14:09:53.602Z
---

**2026-08-17 完成搬遷**。公司建了自架 Forgejo,`D:\Dev\HyperDigital` 底下**全部 11 個 repo** 現在都是同一套配置:

| remote | 位址 | 角色 |
|---|---|---|
| `origin` | `https://forgejo.hdtech.tw/charlie/<name>.git` | **正本、預設推送目標** |
| `github` | `https://github.com/Charlie022802/<name>.git` | 鏡像,要明寫 `git push github master` |

11 個:`HD.Net10`、`HD.Pacs.DicomWeb`、`HD.DicomImageViewer`、`HD.LoggingPlatform`、`HD.AdminConsole`、`HD.Shared`、`HD.Export`、`HD.Animal`、`hdctl`、`docs`,以及 **`Database` 目錄對應的 repo 叫 `HDPACS-DB`**(目錄名與 repo 名不同,唯一一個)。`hdctl` 與 `docs` 是這次才新建的,先前根本沒有 remote。

**對調 origin 的四步,第四步不能省**:`remote rename origin github` → `remote rename forgejo origin` → `fetch origin` → **`branch -u origin/master master`**。`git remote rename` 會連 `branch.master.remote` 一起改寫,只換名稱的話 `git push` 仍然往 GitHub 跑,**而且完全沒有提示**。

**`docs\` 現在是 repo,根目錄就是 `docs\` 本身**(路徑沒變)。順手收進去:`hd-unified-deploy-design.md`、`Logo\`、`RC Database (Revised).xlsx`(都從 `D:\Dev\HyperDigital` 根目錄搬入,根目錄現在只剩 repo 目錄)。設計文件搬家修了兩處引用:`docs\systems\deployment.md` 的絕對路徑、`hdctl\README.md` 的相對連結。**注意 `Database` repo 裡另有一份 `HDPACS/RC Database (Revised).xlsx`,與 `docs\` 那份可能重複,哪份是正本未確認。**

**`主機配置表.txt`** 原本因含五台主機 SSH 明文密碼而刻意留在 repo 外;已把密碼欄改成 `**`、只留主機之間的關係提示(哪三台共用、哪台獨立、哪台走 root),然後收進 `docs\`。**這份表從沒進過 git,歷史裡沒有密碼,不需要 rewrite。**

**⚠️ 未處理:`HD.Net10` 有寫死在原始碼裡的密碼**——`HD\Database\PostgresConnection.cs`(postgres)、`HD\Web\WebApiClient.cs`(服務帳號)、`HD.MediaPackage\Service\RetrieveStudy.cs`(Philips Oracle)。使用者知情且說「沒關係,就推吧」,所以連同整段歷史一起上了兩個伺服器。**若那個 GitHub repo 是 public,這幾組密碼等於已公開,是要換密碼的層級。**

**Forgejo push 會間歇性認證失敗**(2026-08-17 一天內約五次):`fatal: Authentication failed for 'https://forgejo.hdtech.tw/...'`,**同一秒 GitHub 那邊卻成功**,而且**原地重跑一次就過**。不是憑證過期(重試不需重新輸入),看起來是 Git Credential Manager 對這個 host 的快取偶發沒對上。**遇到就直接重試 `git push origin master`,不要去動憑證設定。**

**auto mode 分類器的坑**:`/auto-mode-setup` 掃描 `D:\Dev\HyperDigital`,但**那層本身不是 git repo**,所以它一律得出「沒有 remote、沒有受信任網域」,把 `git push` 到 `forgejo.hdtech.tw` 判成外送而擋掉(時好時壞)。重跑精靈救不了(結論相同)。已由使用者手動覆蓋 `~\.claude\settings.json` 的 `autoMode.environment`(補上兩個 remote 與 `forgejo.hdtech.tw` 為受信任網域),`allow` 沒動。**若日後仍被擋**:`PowerShell(git push:*)` 這種前綴規則對不上我慣用的 `git -C <路徑> push`,要涵蓋只能放寬成 `PowerShell(git:*)`,那等於 `reset --hard` 也跳過分類器——要先問使用者。

相關:[[reference_system_docs]](docs 內容正本)、[[project_main_pacs_deploy]]、[[feedback_versioning_convention]]
