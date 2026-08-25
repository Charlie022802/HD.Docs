---
name: project_hdctl_hospital_host
description: "hdctl 進真實醫院主機(CentOS 7)踩到的三顆坑—Python 3.6、hdadmin 帳號不存在、tgz 沒有執行位元;前兩顆已修,第三顆待修"
metadata: 
  node_type: memory
  type: project
  originSessionId: ea8648ec-751b-449c-aab0-36db86e8c1e2
  modified: 2026-08-25T08:10:03.566Z
---

**2026-08-25 把 `viewerapi` 佈到 `.163`（`STJOHO_68_163`，若瑟形態的醫院主機）時,一路撞出三顆 hdctl 的坑。**
`.191`／`.199` 是我們自己養的機器,早就有 hdadmin、Python 也新,所以這半年都沒暴露。

**① hdctl 需要 Python 3.7+,醫院是 CentOS 7 / Python 3.6。**
`add_subparsers(required=True)` 直接 TypeError、`subprocess.run(text=True)` 也是 3.7 才有。
**已修**(`universal_newlines=` + 解析後自己檢查 `args.cmd`)。hdpack.py 掃過沒有同類問題。

**② 全新主機沒有 `hdadmin`,unit 帶 `User=hdadmin` 會以 `217/USER` 失敗。**
症狀極惡劣:unit 一直 `activating`、健檢逾時,**表面完全看不出跟使用者有關**,非得翻
journal 才知道。hdctl 原本只警告「找不到使用者,略過 chown」就照樣寫 unit。
**已修**:加 `ensure_run_user()`,不存在就 `useradd -r -s /sbin/nologin -M` 建起來。

**③ Windows 打的 tgz 沒有執行位元 → `203/EXEC`。待修。**
`tar -tvzf` 看到的是 `-rw-rw-rw-`。以前不會踩到,因為其他元件的 exec 都是
`dotnet app/xxx.dll`(被執行的是 dotnet,dll 不用執行位元);**viewerapi 是第一個
self-contained 元件**,exec 就是二進位本身。
**修法**:hdctl 解壓後(`hdctl.py` 約 line 494 的 `tf.extractall`)對每個 service 的
exec 取 argv[0],若是相對路徑且檔案存在就 `chmod 0755`。修在 hdctl 而不是 hdpack,
這樣已經打好的包也能用。

**還沒驗到的第四件事**:self-contained 的 .NET 10 二進位在 CentOS 7 的 glibc 上到底跑不跑得起來。
③ 修好之後如果出現 `GLIBC_2.xx not found`,那是更根本的問題(要改 framework-dependent 加裝 runtime)。

相關:[[project_main_pacs_deploy]](hdctl 慣例、sudo 要全路徑)、[[project_viewer_server]]。
