---
name: project_hdctl_hospital_host
description: "hdctl 佈 self-contained 元件踩出的四顆坑(執行位元/SELinux/版本護欄靜默失效/InformationalVersion 說謊)—全修完;根源都是既有機制假設 exec=dotnet <dll>"
metadata:
  node_type: memory
  type: project
---

**2026-08-25 把 `viewerapi` 佈到 `.163`(內網測試機,若瑟形態)與 `.199`(AlmaLinux)時,
一路撞出四顆坑——而四顆是同一個根源:`viewerapi` 是第一個 self-contained 元件,
`exec` 是二進位本身,不是 `dotnet app/xxx.dll`,而既有機制全是為後者寫的。**
`.191`/`.199` 是我們自己養的機器(hdadmin 早就有、Python 也新),所以這半年都沒暴露。

| 坑 | 症狀 | 為什麼以前不會踩到 | 修在 |
|---|---|---|---|
| Python 3.6 | `add_subparsers(required=)` TypeError | 我們的機器夠新 | hdctl 0.2.2 |
| `hdadmin` 不存在 | `217/USER`;unit 一直 activating、**表面看不出跟使用者有關** | 全新主機才沒有 | 0.2.2 `ensure_run_user()` |
| 沒有執行位元 | `203/EXEC`(Windows 打的 tar 沒 POSIX mode) | 被執行的是 dotnet,dll 不用 x | 0.2.2 `ensure_exec_bits()` |
| SELinux `user_home_t` | `203/EXEC`,`avc: denied { execute } init_t → user_home_t` | dotnet 在 `/opt` 型別本來就對;`/home` 下的 dll 只被**讀取**——讀允許、執行不允許 | 0.2.3/0.2.4 `label_exec_selinux()` |

**SELinux 那顆有兩個容易寫錯的地方(我兩個都踩了)**:
①必須排在 `restorecon(comp_dir)` **之後**——先 `chcon` 會被它洗掉;
②要標 **`rel_dir`(新 release)不是 `current`**——這函式跑在 `flip_current` 之前,
標 `current` 等於標舊版、新版一個字沒動(0.2.3 因此白做一次)。
做法:`semanage fcontext` 登記涵蓋所有版本的正規式規則(持久、全機 relabel 也在),
再 `restorecon` 套;`semanage` 不在才退用 `chcon`。

**另外兩顆不在 hdctl,在打包與版號:**
- **hdpack 的「manifest 與組件版號一致」護欄對 self-contained 靜默失效**——只認 exec 裡的
  `.dll`,認不到就 `return`。已改成取 argv[0] 檔名。**護欄失效是靜默的,這是重點。**
- **`InformationalVersion` 讓 `/healthz` 說謊**:`Directory.Build.props` 比 csproj 早匯入,
  算的時候 `$(Version)` 還是共用的 2.4.0,專案覆寫的 alpha 版號還沒生效 → `/healthz`
  報看片端的 `2.4.0`。搬到 `Directory.Build.targets` 就對(該檔本來就是為「等 csproj 定義完」而存在)。

**⚠️ 更正(2026-08-26):原本這裡寫「已驗證 self-contained 的 .NET 10 跑得動 CentOS 7 的 glibc」,
那是錯的。** 實測 `.163` 是 **CentOS 8 / glibc 2.28**,不是 CentOS 7。
我當初從「Python 3.6」推論成 CentOS 7,但 **RHEL 8 家族的 platform-python 也是 3.6**,推論不成立。

**不過這個更正不影響結論**:若瑟正式機(`10.10.1.148`)實測是 **RHEL 9.2 / glibc 2.34**,
比 `.163`(glibc 2.28)還新,self-contained 完全沒有相容性疑慮。真正沒被驗過的是「CentOS 7」這種老環境,
而目前**沒有已知的醫院是那個版本**。

**沒直接驗到的**:`.163` 是 `Permissive`,所以「CentOS 8 + Enforcing」這組合沒實證。
但標記機制在 CentOS 8 確實生效(`ls -Z` 已是 `bin_t`),`.199` 的 Enforcing 也證明 `bin_t` 夠用。
真醫院是 Enforcing 的話,看安裝輸出有沒有印 `SELinux 標記 bin_t` 就知道。

**教訓:下次加任何元件層級的機制,先問「它是不是假設 exec = `dotnet <dll>`」。**

相關:[[project_main_pacs_deploy]](hdctl 慣例、sudo 要全路徑)、[[project_viewer_server]]、
[[reference_version_two_sources]](版號雙來源)。
