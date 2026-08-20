---
name: project_hd_animal_proxy
description: HD.Animal veterinary PACS proxy — migrated from old HD.Proxy.* (net6/fo-dicom4) to net10/fo-dicom5
metadata: 
  node_type: memory
  type: project
  originSessionId: 2749927f-4503-4361-8869-e6c48c60f4b7
  modified: 2026-08-17T16:47:56.036Z
---

## 🔒 專案凍結:不要修改(2026-08-18 使用者指示)

整個 `HD.Animal` repo **暫不變更**,未來走向未定。動手前先確認這條還在不在。人可讀正本+完整理由在 `docs/systems/animal-proxy.md`(開頭的凍結標記)。

**`.222` 線上實際跑四支**(使用者以目錄截圖確認):`HDAnimalProxyCStoreSCP`、`HDAnimalProxyWorklistSCP`、`HDAnimalProxyServiceManager`、`HDAnimalProxyWebController`。**`HD.Animal.Proxy.Controller`(WinForms)不在其中**——它留在 repo 裡,是可從本機執行、以 SFTP 直接寫 `.222` 上 `proxyConfig.json` 的舊工具,不是部署元件。使用者一度說「Controller 有在線上跑」後自行更正,我依那句寫進文件的內容已修回。

**「有沒有部署」這個區分比嚴重性標籤重要**,弱點優先序照它排(詳見 [[project_nuget_vulnerabilities]]):

| 弱點 | 在哪 | 判定 |
|---|---|---|
| `SQLitePCLRaw.lib.e_sqlite3` 2.1.11 High(CVE-2025-6965) | WebController,**線上** | 唯一落在生產的一個。真的在用 SQLite(帳號 DB),但攻擊需攻擊者能送任意 SQL,而它只發 EF 參數化查詢、本機檔案、封閉網路→接受。要修只需 `Microsoft.EntityFrameworkCore.Sqlite` 10.0.10→**10.0.11**(實測拉到 SQLitePCLRaw 2.1.12、掃描轉零) |
| `SSH.NET` 2024.1.0 High | Controller,**沒部署** | 弱點在 `ScpClient.Download()`,整個 repo 沒有 `ScpClient`→暴露零。升 2026.0.0 已實測可行(編譯過;假帳號連 `.222` 得 `SshAuthenticationException` 而非協商失敗,對 OpenSSH 9.9 相容)但不值得動線上 |
| `Encoding.ASCII` 存檔(`MainForm.cs:361`/`:367`) | Controller,**沒部署** | 讀 UTF-8 寫 ASCII→中文變 `?`,**`.bak` 同樣受害**。已實查 `.222` 的 proxyConfig.json 是純 ASCII 故未觸發。但它能寫線上設定檔,而 WebController 寫 UTF-8→設定裡一旦有中文就會被它吃掉。若那支確定不用了,**移除比修更乾淨** |

HD.Animal (獸醫 PACS 代理) at `D:\Dev\HyperDigital\HD.Animal` — migrated 2026-07-22 from the old solution `C:\Users\yang\source\repos\HD\HD.Proxy*` projects.

Migration decisions (from the user): **full rename** HD.Proxy → HD.Animal.Proxy (folders, csproj, namespaces, assembly names) and **upgrade net6.0 → net10.0**. Faithful port otherwise.

5 projects under `HD.Animal/src/`, solution `HD.Animal.slnx` (SDK 10 default .slnx format):
- `HD.Animal.Proxy` — core lib (ProxyConfig/ServiceConfiguration/LogTextFormatter). Serilog only; fo-dicom dropped (was unused).
- `HD.Animal.Proxy.CStoreSCP` — Worker, C-STORE SCP (saves incoming .dcm to CacheTemp path template)
- `HD.Animal.Proxy.WorklistSCP` — Worker, MWL C-FIND SCP; forwards query to per-UUID upstream and rewrites `PatientSpeciesDescription` (狗→Feline etc.) — NOTE the 狗/貓 mapping looks swapped in the source; preserved as-is。**優化(2026-08-10, commit `bdce2a7`,本機雙情境驗證過)**:逐筆串流轉發(Channel,不再全收完才回)、上游失敗/逾時回 ProcessingFailure(原本吞錯回空 Success)、接上 Worklist.RequestTimeoutInMs(設定欄位原本沒人用)、物種對照表驅動(行為不變,狗/貓對調仍保留待確認)
- `HD.Animal.Proxy.ServiceManager` — Worker, restarts SCP systemd units on C-ECHO failure / at a set time
- `HD.Animal.Proxy.Controller` — WinForms (net10.0-windows) config editor, edits proxyConfig.json over SFTP (SSH.NET)

fo-dicom 4→5 rewrite reference = the compiled net10 projects `HD.Net10/HD.PACS` & `HD.WorklistServer`. Key v5 changes applied: namespace `Dicom.*`→`FellowOakDicom.*`; drop `Dicom.Log.SerilogManager`, add `services.AddFellowOakDicom()`; service ctor `(INetworkStream, Encoding, ILogger, DicomServiceDependencies deps=null)`; `Logger.Info/Warn/Error`→`LogInformation/LogWarning/LogError`; C-Echo/C-Store handlers → `...Async` returning `Task<>`, C-Find → `async IAsyncEnumerable`; **but `OnReceiveAbort`/`OnConnectionClosed` stay SYNC void** (on IDicomService). Server via injected `IDicomServerFactory.Create<T>(port)` (no options overload — the old 30s RequestTimeout was dropped, matching repo). **SCU: MUST use injected `IDicomClientFactory.Create(host, port, useTls, callingAE, calledAE)` — the obsolete `new DicomClient(...)` ctor THROWS NullReferenceException at runtime** (it resolves loggerFactory/connectionFactory from Setup.ServiceProvider which isn't wired in a Generic Host app; the repo's HD.WorkflowManager uses `new DicomClient` but evidently never exercises it). ServiceManager injects IDicomClientFactory directly; WorklistDicomService (created per-connection by the server) reads it from a static `Worker._dicomClientFactory` set in the Worker ctor. NOTE: the Controller (WinForms, not on the server) still uses the obsolete ctor in MainForm/MainFormAdvance C-ECHO buttons — will NRE, needs the same fix or a DicomSetupBuilder init; deferred (not part of server deploy).

Gotchas hit: (1) `MainForm.cs`/`MainFormAdvance.cs` were **Big5-encoded** — the Edit tool corrupted them reading as UTF-8; recovered by re-transcoding from source with PowerShell `Encoding.GetEncoding(950)`→UTF-8-BOM. (2) net10 WinForms analyzer WFO1000 fires as error on public Form properties — suppressed via `<NoWarn>WFO1000</NoWarn>` in the Controller csproj.

Left as-is deliberately: systemd unit names `hdproxycstorescp.service`/`hdproxyworklistscp.service` in ServiceManager (deployment identifiers), and the test-mode hardcoded path in ServiceConfiguration.cs.

Builds clean on SDK 10.0.302: 0 errors. `Directory.Build.props` at HD.Animal root centralizes Version 2.0.0 / Copyright; Nullable=enable (nullable warnings left unfixed by user's choice). Not git-tracked. Related: [[reference_fodicom5_pixel]], [[project_build_paths]].

## Deployment (new server 192.168.68.222 "horoviewPacsProxy", user hdadmin)
STATUS 2026-07-22: FULLY LIVE & end-to-end verified under SELinux Enforcing. 3 services active; C-ECHO health-check Success (interval now 300000ms=5min to cut log noise); real C-STORE from modality DXIDL1KX saved OK to /home/HD/CacheTemp/IDL1KX/2026/0722/*.dcm (C-Store response: Success). C-STORE runs as root (NFS default-ACL bypass); ServiceManager root; Worklist hdadmin.

Deploy package at `HD.Animal/deploy/` (install.sh + systemd/ + sudoers/ + proxyConfig.json + published services/). Framework-dependent (needs .NET 10 runtime — user installed aspnetcore-runtime-10.0.10 tarball to /usr/lib/dotnet + symlink /usr/bin/dotnet; SDK not needed). Only the 3 workers deploy; Controller is Windows-only. Real config (~45 UUID→MWL mappings on 192.168.68.x) + old buggy systemd units came from `D:\HyperDigital\AnimalGateway`.

**SELinux is Enforcing on the server — this drove the layout.** systemd services run in `init_t` domain (regardless of Unix user — root would NOT help), which is DENIED access to `user_home_t` (anything under /home, incl /home/hdadmin). So everything moved OUT of /home to standard FHS locations:
- Program + `proxyConfig.json`: `/opt/hdanimal/` (usr_t, read-only, chown hdadmin so editable without sudo). Config read two-levels-up from assembly = /opt/hdanimal/proxyConfig.json.
- Logs: `/var/log/hdanimal/` (var_log_t) — appsettings.json Serilog path repointed here from old /home/HD/logs.
- ServiceManager state (History): `/var/lib/hdanimal/` (var_lib_t) — units set WorkingDirectory here (code uses GetCurrentDirectory()/History).
- install.sh applies these via `semanage fcontext` + `restorecon`; copies with `cp -r` (NOT -a) so the home-dir label isn't carried in.
- units: `hdanimalproxy{cstorescp,worklistscp,servicemanager}.service`, Type=notify, `Environment=DOTNET_EnableDiagnostics=0` (kills the /tmp clr-debug-pipe AVC), `UMask=0002`. **C-STORE AND ServiceManager run as root** (no User=); **Worklist runs User=hdadmin**. ServiceManager-root: needs `systemctl restart` (no sudo). C-STORE-root: the NFS cache dirs (/home/HD/CacheTemp, /CacheError from NAS 192.168.68.228) carry an inherited **default ACL that strips owner perms for non-root** — as hdadmin the service created dirs `d---rwsrwx` (owner none) and couldn't write into them; root bypasses DAC+ACL (exactly what the old proxy did as root). Chasing this: first thought it was DAC ownership (chown -R hdadmin worked but wrong fix), then umask (UMask=0002, but `Umask` showed 0022 and owner-none is impossible from umask), finally the `+`/ACL was the real cause → run as root. Reason: under enforcing, a service in init_t is DENIED `execute` on sudo_exec_t — sudo from a daemon domain is a dead end. Root + direct systemctl avoids it (init_t manages units natively). No sudoers file (earlier sudo approach abandoned).
- Firewall: **2020** (C-STORE), **3320** (Worklist); install.sh auto-detects firewalld/ufw.

**SELinux name_connect gotcha**: ServiceManager (init_t) doing C-ECHO to the local SCP ports is denied `name_connect` to unreserved_port_t (2020/3320) under enforcing → echo fails → 60s restart loop. Fix = small SELinux policy module `deploy/selinux/hdanimalproxy.te` (`allow init_t unreserved_port_t:tcp_socket name_connect;` + `dontaudit init_t self:process getsession;` to silence a benign .NET getsid noise). install.sh compiles+installs it (checkmodule/semodule_package, auto-installs checkpolicy); uninstall.sh `semodule -r hdanimalproxy`.

**Config-load gotcha**: `Host.CreateDefaultBuilder` loads `appsettings.json` relative to CWD (= systemd `WorkingDirectory`, which we set to /var/lib/hdanimal), NOT the DLL dir — so Serilog config silently didn't load (no logs at all, and the echo-restart loop below couldn't be diagnosed). Fixed: all 3 Program.cs now `config.SetBasePath(AppContext.BaseDirectory); AddJsonFile("appsettings.json")` before the absolute-path proxyConfig.json. (proxyConfig.json was always fine — loaded via absolute path.)

**DICOM cache = NFS mounts** `192.168.68.228:/CacheTemp` → /home/HD/CacheTemp and `:/CacheError` → /home/HD/CacheError (proxyConfig CacheLocation=/home/HD, writes @{RootPath}/CacheTemp + /CacheError). NFSv3 = single SELinux label per mount (default nfs_t, blocks init_t writes) and can't relabel per-file. Fix = fstab mount option `context="system_u:object_r:var_lib_t:s0"` on both (local-view only, does NOT affect the NFS server or the still-running old machine). This is a manual fstab step (install.sh only pre-checks write access and prints the steps). Shared with old server → never chown/relabel server-side.
