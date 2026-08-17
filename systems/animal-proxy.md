# Animal Proxy（HD.Animal）

獸醫 PACS 代理。舊 HD.Proxy.* 遷移到 HD.Animal.Proxy.*（net10 + fo-dicom 5）。

- **原始碼**：`D:\Dev\HyperDigital\HD.Animal`（git，`HD.Animal.slnx`）。
- **生產**：**192.168.68.222**（Linux，SELinux Enforcing）。部署 + 穩定。
- 核心 lib `HD.Animal.Proxy`（ProxyConfig 模型）；SCP 服務 C-STORE / Worklist；fo-dicom 5.2.6 C-ECHO。

## 服務
- SCP 服務（C-STORE / Worklist），埠 2020 / 3320。
- ServiceManager（root，處理需權限的操作）。
- **WebController**（Blazor Server，取代舊 WinForms Controller）：瀏覽器設定代理，同機 :8080（HTTPS 自簽）。

## WebController（已上）
- Blazor Web App，net10，EF Core Sqlite + Identity PasswordHasher。使用者存 SQLite `/var/lib/hdanimal/webcontroller.db`，種 super-admin `hdadmin/hdadmin`。
- Cookie auth，兩角色 Admin / User。頁面：/login、/config（RemoteAE/UUID/PACS-Worklist/ServiceManager/Rules/歷史版本）、/logs、/users。
- **Phase 1–6 已上機驗證**；**Phase 7（config 版本歷史）已建、未 redeploy 到 .222**（web-only swap）。

## SELinux / 部署重點（都踩過）
- proxyConfig.json 實體放 `/var/lib/hdanimal/`（var_lib_t，可寫）+ `/opt/hdanimal/proxyConfig.json` 為 symlink（服務讀得到、web 寫得到）。
- 8080 name_bind、polkit（hdadmin 重啟 hdanimalproxy* units）、憑證/db 在 /var/lib。
- ContentRoot 要指 `AppContext.BaseDirectory`（否則 systemd WorkingDirectory 讀不到 appsettings）；DataProtection keys 放 /var/lib/hdanimal/keys。

## 待辦
- WebController Phase 7 redeploy 到 .222。
- 接入共用日誌（見 [shared-logging.md](shared-logging.md)）。
