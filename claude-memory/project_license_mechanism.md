---
name: project-license-mechanism
description: License-file mechanism deferred in net10 version; where the old one lives + how to redo it if revisited
metadata: 
  node_type: memory
  type: project
  originSessionId: 67bc2ae6-64eb-431b-aeab-11935a1b18ab
---

新版 net10 `HD.DicomImageViewer` **暫不做 license 機制**（決定於 2026-07-06）。理由：現階段有內部使用者登入把關，優先度低。要做的話排在對外正式商用鋪貨前。

舊版機制在舊 repo `C:\Users\yang\source\repos\HD.Desktop`：
- `HD.Core/Register/`：`FingerPrint.cs`(WMI 取 CPU+主機板 id → MD5 = 機器指紋)、`Encryption.cs`(RSA)、`LicenseInfo.cs`(SystemInfo/ProductName/ProductUUID/DeadLine/ContainLogin/AllowImplementationClassUID)、`RegisterForm.cs`(匯出 .key 申請、匯入 license 驗證)。驗證 = exe 旁 `license` 檔 RSADecrypt → 比對機器指紋 + DeadLine>Now，硬鎖。
- `HD.LicenseCreater/`：產生端，連 HDCRM Postgres(insert_register/update_register) 配 ProductUUID 後產 .lic。

重做時務必修的三點：
1. 🔴 舊版把 **RSA 私鑰(含 P/Q/D)寫死在客戶端 `Encryption.cs`** → 只是混淆非簽章，反編譯即可偽造。改成**只放公鑰、私鑰留產生端、client 驗章**(RSA-2048/ECDSA P-256)。
2. 到期改**臨床安全**行為(預警+寬限+唯讀)，勿硬鎖黑畫面。
3. 指紋加容錯(CPU 或 主機板其一)＋重發流程；net10 需加 `System.Management` NuGet。

客戶端部分好移植(WinForms+System.Text.Json 幾乎原樣)；產生端需 HDCRM DB。相關：[[project-versioning]]

**DB 密碼(不同議題)**：2026-07-06 因趕功能，先做「簡易隱藏」——client `Program.cs` 在 PostgresDefaults.InitializeFromJson 後，若 config 無密碼則預設 `PostgresDefaults.Current.Password="`<密碼不記於此>`"`；client `localconfig.json` 移除 Password。屬嚇阻級(可反編譯)、且密碼進 git 源碼(與現況同等曝露)。真正解仍是走 app-server(見 [[project-viewer-server]])。此改動當時未 commit。client 的 app-server 查詢遷移碼(ApiBaseUrl/ViewerApiGateway/apiClient/DicomQuery 分支)已寫但以 ApiBaseUrl 空值停用、未 commit。

**DB 密碼明文刻意不記在這裡**（2026-08-20 移除，為了讓 memory 能納入版控）：它寫死在看片端 `Program.cs` 的 `PostgresDefaults.Current.Password`，同一組也出現在 hd-web-server 的 `src/utils/utils.initial.ts`（見 [[project_hd_web_server]]）。
