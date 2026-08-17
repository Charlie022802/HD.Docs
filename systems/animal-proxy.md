# Animal Proxy（HD.Animal）

> ## ⚠️ 此專案目前凍結，不要修改（2026-08-18 決策）
>
> 整個 `HD.Animal` repo 暫不變更，未來走向未定。要動之前先確認這個標記還在不在。
>
> **`.222` 線上實際跑的是這四支**（2026-08-18 由使用者確認）：
> `HDAnimalProxyCStoreSCP`、`HDAnimalProxyWorklistSCP`、`HDAnimalProxyServiceManager`、
> `HDAnimalProxyWebController`，加上 `proxyConfig.json`。
> **`HD.Animal.Proxy.Controller`（WinForms 桌面版）不在其中** —— 它是本機執行的工具，非部署元件。
>
> 這個區分決定了弱點的優先序，見下方「凍結期間的已知問題」：SSH.NET 與 ASCII 那兩件都在
> **沒有部署的 Controller** 裡；唯一落在線上程式的是 WebController 的 SQLitePCLRaw。

獸醫 PACS 代理。舊 HD.Proxy.* 遷移到 HD.Animal.Proxy.*（net10 + fo-dicom 5）。

- **原始碼**：`D:\Dev\HyperDigital\HD.Animal`（git，`HD.Animal.slnx`）。
- **生產**：**192.168.68.222**（Linux，SELinux Enforcing）。部署 + 穩定。
- 核心 lib `HD.Animal.Proxy`（ProxyConfig 模型）；SCP 服務 C-STORE / Worklist；fo-dicom 5.2.6 C-ECHO。

## 服務
- SCP 服務（C-STORE / Worklist），埠 2020 / 3320。
- ServiceManager（root，處理需權限的操作）。
- **WebController**（Blazor Server，取代舊 WinForms Controller）：瀏覽器設定代理，同機 :8080（HTTPS 自簽）。**`.222` 上跑的設定介面就是這支。**
- `HD.Animal.Proxy.Controller`（WinForms）留在 repo 裡但**不是部署元件**，是可從本機執行、以 SFTP 直接編輯 `.222` 上 `proxyConfig.json` 的舊工具。它仍能寫到線上設定檔，所以它的 bug 不是完全無害（見下方第 2 項）。

## WebController（已上）
- Blazor Web App，net10，EF Core Sqlite + Identity PasswordHasher。使用者存 SQLite `/var/lib/hdanimal/webcontroller.db`，種 super-admin `hdadmin/hdadmin`。
- Cookie auth，兩角色 Admin / User。頁面：/login、/config（RemoteAE/UUID/PACS-Worklist/ServiceManager/Rules/歷史版本）、/logs、/users。
- **Phase 1–6 已上機驗證**；**Phase 7（config 版本歷史）已建、未 redeploy 到 .222**（web-only swap）。

## SELinux / 部署重點（都踩過）
- proxyConfig.json 實體放 `/var/lib/hdanimal/`（var_lib_t，可寫）+ `/opt/hdanimal/proxyConfig.json` 為 symlink（服務讀得到、web 寫得到）。
- 8080 name_bind、polkit（hdadmin 重啟 hdanimalproxy* units）、憑證/db 在 /var/lib。
- ContentRoot 要指 `AppContext.BaseDirectory`（否則 systemd WorkingDirectory 讀不到 appsettings）；DataProtection keys 放 /var/lib/hdanimal/keys。

## 凍結期間的已知問題（2026-08-18 盤點，皆刻意不修）

按「是否在線上程式裡」排序 —— 這個區分比嚴重性標籤重要。

### 0. WebController 的 SQLitePCLRaw High（**唯一落在線上程式的一個**）

`SQLitePCLRaw.lib.e_sqlite3` 2.1.11（`GHSA-2m69-gcr7-jv3q` / CVE-2025-6965，CVSS 7.2）由 `Microsoft.EntityFrameworkCore.Sqlite` 10.0.10 傳遞帶進 `HD.Animal.Proxy.WebController`。內容是 SQLite 的記憶體毀損：aggregate 項數可超過可用欄位數。

**WebController 真的在用 SQLite**（使用者帳號存 `/var/lib/hdanimal/webcontroller.db`），所以不能用「沒在用」打發。但**攻擊向量需要攻擊者能送任意 SQL**，而這支只發出 EF Core 產生的參數化查詢、資料庫是本機檔案、又在封閉網路內 —— 沒有讓外部 SQL 進來的路徑。因此判定為可接受，不破壞凍結。

**若要修，這個是首選**（比下面兩個都值得）：把 `Microsoft.EntityFrameworkCore.Sqlite` 10.0.10 → **10.0.11** 即可，它會拉到 `SQLitePCLRaw.lib.e_sqlite3` **2.1.12**（已實測：掃描轉為零弱點）。純傳遞相依、不動任何程式碼。注意 advisory 頁面寫「沒有已修的 NuGet 版本」已經過時。

### 1. `SSH.NET` 2024.1.0 有 High 弱點，但在**沒有部署**的元件裡且暴露為零

`SSH.NET` 只被 `HD.Animal.Proxy.Controller` 參考，而那支不是部署元件（`.222` 上跑的四支都沒有它）。

`GHSA-q939-rpr3-3284` 在 **`ScpClient.Download()`** 的遞迴目錄下載（不驗證伺服器回傳的檔名，惡意 SCP 伺服器可用 `../` 寫到目錄外）。修在 2026.0.0。

而且就算它有部署也用不到那條路：整個 repo 沒有任何 `ScpClient`，Controller 只用 `SftpClient` 的 `OpenRead`／`Create`／`UploadFile`（`StartForm.cs` 的 `using Renci.SshNet` 是沒用到的殘留）。

升版可行性已實測（不代表要做）：2026.0.0 編譯無誤；且演算法協商與 `.222` 相容 —— 用假帳號連線得到 `SshAuthenticationException` 而非協商失敗，`.222` 是 OpenSSH 9.9，而 2026.0.0 的預設清單仍含 `ssh-rsa`／`3des-cbc`／`diffie-hellman-group1-sha1`。**結論是「為消掉一個掃描警告去動線上程式」不划算，維持凍結。** 見 `backlog.md` REQ-017。

升版可行性已實測（不代表要做）：2026.0.0 編譯無誤；且演算法協商與 `.222` 相容 —— 用假帳號連線得到 `SshAuthenticationException` 而非協商失敗，`.222` 是 OpenSSH 9.9，而 2026.0.0 的預設清單仍含 `ssh-rsa`／`3des-cbc`／`diffie-hellman-group1-sha1`。見 `backlog.md` REQ-017。

### 2. 舊 WinForms Controller 存設定會吃掉非 ASCII 字元（含 `.bak`）

`MainForm.cs:361` 與 `:367` 用 `Encoding.ASCII.GetBytes` 寫檔，而讀檔是 `StreamReader`（預設 UTF-8）。所以記憶體裡的中文是對的，寫回去全變 `?`；**`.bak` 也是走 ASCII 寫的，備份救不了**。

**未被觸發**：2026-08-18 實查 `.222` 的 `/var/lib/hdanimal/proxyConfig.json` 是純 ASCII（`iconv -f ASCII -t ASCII` 通過）。

**不是完全無害**：雖然這支沒有部署，但它是可從本機執行、以 SFTP 直接寫線上設定檔的工具。WebController 寫 UTF-8、它寫 ASCII，**只要哪天設定裡放了中文（例如 `DicomInputRule.Value` 改寫院名），用 web 存進去之後再有人用這支存一次，那些字就沒了**。

改動設定前值得跑一次：

```bash
iconv -f ASCII -t ASCII /var/lib/hdanimal/proxyConfig.json >/dev/null 2>&1 \
  && echo "純 ASCII，安全" || echo "含非 ASCII，別用 WinForms Controller 存檔"
```

如果那支確定不再使用，最乾淨的處置其實是**把它從 repo 移除**而不是修它 —— 一個沒人部署、卻能寫壞線上設定的工具，留著就是風險。這件事等凍結解除、走向確定後再決定。

## 待辦
- WebController Phase 7 redeploy 到 .222。
- 接入共用日誌（見 [shared-logging.md](shared-logging.md)）。
