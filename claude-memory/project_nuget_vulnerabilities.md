---
name: project_nuget_vulnerabilities
description: REQ-017 NuGet 已知弱點(NU1903)—低風險部分已修+驗證(Export/DicomWeb);SSH.NET(主PACS SFTP)與 Magick.NET 待排回歸;掃描指令與慣例
metadata: 
  node_type: memory
  type: project
  originSessionId: ea8648ec-751b-449c-aab0-36db86e8c1e2
  modified: 2026-08-17T16:48:17.243Z
---

**REQ-017(正本 docs `backlog.md`)。起因:HD.Export 建置時的 `NU1903` 警告——這種警告不會擋建置,所以很容易長期沒人處理**。順手掃全 repo 才發現不只一處、且有幾個 High。使用者反應是「nuget 的警訊滿重要的」→ 值得定期掃。

**掃描指令(每個 repo)**:`dotnet list package --vulnerable --include-transitive`。建議納入發版前檢查。

**✅ 已修+驗證通過(2026-08-17,都是傳遞相依或純 pin=不動程式碼)**:HD.Export 與 HD.Pacs.DicomWeb 的 `Microsoft.AspNetCore.OpenApi` 10.0.7→**10.0.11**(連帶解掉傳遞的 `Microsoft.OpenApi 2.0.0`);DicomWeb 的 `Microsoft.Data.Sqlite` 9.0.6→**10.0.11**(解 `SQLitePCLRaw`,順帶對齊 net10;access.db 在用)與 `System.Security.Cryptography.Xml` 10.0.6→**10.0.11**。**驗證**:DicomWeb 單元 87/87 + 整合 31/31;Export 實跑 /health 與 /openapi/v1.json。**✅ 已部署 .199(2026-08-17)**:Export `0.1.0-alpha.3`、DicomWeb `1.0.0-alpha.2`(兩 unit+UPS 皆 active)。註:`Microsoft.Data.Sqlite` 跨主版本(9.0.6→10.0.11)是 access.db 在用的,整合測試有涵蓋但**生產第一次寫入時值得看一眼 log**(部署當下 journalctl 無 sqlite/error 訊息,但那也代表還沒被寫過)。

**⚠️ 打包時另外抓到的安全問題(2026-08-17)**:HD.Export 的 `appsettings.Development.json`(含**明文 DB 密碼**)會被 `dotnet publish` 帶進部署包 → 密碼會躺在主機 release 目錄。已加 `CopyToPublishDirectory=Never` 並掃過輸出確認。**DicomWeb 本來就有排除**(csproj 有 `CopyToPublishDirectory="Never"`),Viewer/Animal 的 publish.ps1 也有這步,只有 Export 漏了。新專案要記得這件事。

**✅ 全部收尾(2026-08-18):七個 repo 零弱點,`HD.Animal` 因凍結而接受(見 [[project_hd_animal_proxy]])。**

**`SSH.NET`(High)處置是「移除」不是升版**,而且**我先前記錯了**:它在 `HD.Net10` 根本沒被使用——唯一引用是 `Tools/SftpClientExtension.cs` 的 `CreateDirectoryRecursively`,**沒有任何呼叫點**;`GatewaySftp` 也沒有讀取者;`DicomTransmitService` 完全沒碰 SSH.NET(舊記錄寫「主 PACS 的 SFTP 傳輸」不成立)。弱點 `GHSA-q939-rpr3-3284` 在 `ScpClient.Download()`,整個 codebase 沒有 `ScpClient`→暴露零。移除 `PackageReference`+刪死碼,九支服務一次清掉(HD.Net10 `80a0cee`)。

**`Magick.NET` 14.14.0→14.16.0**(清 29 個 advisory:11 中 18 低)。只有一處在用:`HD.DicomTransmit` 的 Encapsulated PDF 轉圖(`pdfToImage`)。**回歸用實測而非推論**:①那組 API 編譯無變動 ②兩版產生的 **Ghostscript 命令列逐字相同** ③真實 CT 影像跑完整 `Scale`+`Alpha`+JPEG 路徑,**輸出像素逐位元相同**。
- **比對要比解碼後的像素**:PNG 檔案位元組會因 ImageMagick 寫入時間戳而每次不同,比檔案 SHA 會誤判成「版本有差異」——我就誤判了一次才發現。
- **ImageMagick 的 PDF 是委派給外部 Ghostscript**(本機沒裝→`gswin64c.exe` exit 127 現形)。升版不改變這件事;`.191` 已確認有 `/usr/bin/gs`(ghostscript-10.02.1)故 `pdfToImage` 可用。

**慣例補充**:advisory 頁面寫「沒有已修的 NuGet 版本」可能過時(SQLitePCLRaw 就是,2.1.12 已修)——**用 `dotnet list package` 實測比讀 advisory 文字準**。

**⚠️ 排錯備忘:整合測試一度 24 失敗不是升版迴歸,是連不到 .191 的 DB**——每個失敗都剛好逾時 15 秒然後回 500(API Key 驗證要查 `HD_API_KEY`)。DB 通了之後 31/31、18 秒跑完。**這類失敗先看「失敗數與耗時的形狀」再判斷**,`Test-NetConnection 192.168.68.191 -Port 5432 -InformationLevel Quiet` 一行就能分辨。開發機不是常時連得到 .191(要開 VPN)。

**`Cryptography.Xml` 的來歷**:csproj 那行本來就是上一輪為修弱點加的顯式 pin(註解寫 CVE-2026-33116 等),程式碼沒用到它的 API(無 `SignedXml`/`EncryptedXml`)→ 升 patch 零行為風險。這類「為了修弱點而 pin 的版本」會再次過期,是需要定期回頭看的。

相關:[[project_req003_export_webapi]]、[[project_dicomweb_impl_split]]、[[project_main_pacs_coerce_logging]]。
