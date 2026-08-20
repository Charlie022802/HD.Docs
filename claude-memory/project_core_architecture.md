---
name: project_core_architecture
description: HD 核心架構—HD.Shared 四柱(Core/Logging/Auth/Events)+集中管理台+Keycloak;各產品只驗+打事件;建置中
metadata: 
  node_type: memory
  type: project
  originSessionId: 13e6b6ed-984d-4c27-aed8-2170077bfa02
  modified: 2026-08-06T13:25:27.141Z
---

**目標樣貌(2026-08-06 定案,開始實作)。** 把共用地基長在既有 `D:\Dev\HyperDigital\HD.Shared\`(共用 repo,DicomWeb + 主 PACS 已用相對 ProjectReference `..\..\..\HD.Shared\src\...` 引用),各產品只做業務 + 驗憑證 + 打事件。系統全貌 artifact: https://claude.ai/code/artifact/34bbfc5f-2c7c-4901-8888-b84b9aa8700e

**四根柱子(HD.Shared/src):**
- `HD.Shared`(核心,已有)、`HD.Shared.Logging`(技術日誌→HawkLog,已有)
- **`HD.Shared.Auth`(新)**：Keycloak 取+驗 token｜API Key 驗證｜`ScopeCatalog`(+Product 欄)｜身分→HD_USER→scope(`ResolveScopes`)。管理台(管)+各服務(驗)共用。
- **`HD.Shared.Events`(新)**：結構化事件 `AuditEvent`(+`Product`+`Category`:Connection/Operation/Audit)｜`IAuditLogger`｜事件表存取(待加)。各產品打事件、管理台統一讀。

**共享契約(單一 HDPACS DB):** `HD_API_KEY`、`HD_USER`/`HD_ROLE`、活動事件表(擬擴 `HD_USER_AUDIT_LOG` 加 `product`+`category`,即 A 案,含連線紀錄)。

**建置順序:** ①開 HD.Shared.Auth/Events 骨架+搬 ScopeCatalog/ApiKeyService+Keycloak → ②DicomWeb 改 ref 共用包(87 測試當護體)→ ③立 HD 管理主控台(登入走 Keycloak、管 key、事件檢視)→ ④主 PACS 打結構化連線事件→主控台呈現(服務人員排查目標)→ ⑤Export 上共用包。

**進度(2026-08-06):**
- ✅ **①(第一鏟,net-new 不動 DicomWeb):** 建好 `HD.Shared.Auth`(Scopes/ScopeCatalog+Product、Keycloak `KeycloakTokenClient`/`KeycloakTokenValidator`/`KeycloakValidationParameters`/`KeycloakOptions`——實測種子落成)+ `HD.Shared.Events`(AuditEvent+Product+Category、IAuditLogger、EventCategory、常數)。加進 HD.Shared.sln、**build 0 err**。ASP.NET 的 `AddKeycloakJwtBearer` 接線**延到②**(web 產品本來就有 JwtBearer 包)。
- ✅ **②a(2026-08-06):** `Scopes`+`ScopeCatalog` 搬到 HD.Shared.Auth;DicomWeb(Api+Infrastructure)加 ProjectReference、刪 Domain 的 Scopes/ScopeCatalog、各檔加 `using HD.Shared.Auth`(Program/ApiKeyService/ApiKeysEndpoints/HdUserRepository/ApiKeys.razor)。**build 綠 + 87/87 測試通過**。引用鏈證明打通。注意版本:DicomWeb.Infrastructure 用 IdentityModel 8.3.1、HD.Shared.Auth 用 8.14.0,NuGet 自動統一到高版,build 過。
- ✅ **②b-1(2026-08-06):** `ApiKeyHasher`+`IpWhitelist`+`HdUserRepository`(三個可攜件,無 audit 耦合)搬進 HD.Shared.Auth;HD.Shared.Auth.csproj 加 Npgsql/Dapper/BCrypt.Net-Next/Logging.Abstractions。DicomWeb 六處改引用(handler 加 using、ApiKeyService 別名改指向、razor 去全限定、AuthEndpoints/ServiceCollectionExtensions/ApiKeyHasherTests 加 using)。**build 綠 + 87/87 測試通過**。原 handler 因會打 audit 暫留 DicomWeb。
- ✅ **②b-2(2026-08-06):** audit 模型(`AuditEvent`/`IAuditLogger`/`AuditResources`/`AuditStatus`/`AuditActorTypes`)收斂到 HD.Shared.Events;刪 DicomWeb 副本、`AuditActions` 產品詞彙留 Domain。**手法:三專案各加 `global using HD.Shared.Events;`(GlobalUsings.cs)→ 19 個 call site 零改動**;`Product="dicomweb"` 在 `ChannelAuditLogger` 集中標記(等事件表加 product/category 欄就持久化)。測試專案 AuditEventEnricherTests 補 using。**build 綠 + 87/87 通過**。
- ✅ **②b-3(2026-08-06):** `ApiKeyAuthenticationHandler` 搬 HD.Shared.Auth,**EF→Npgsql**(Dapper 讀 HD_API_KEY、背景 UPDATE LAST_USED_AT 獨立連線),去掉 PacsDbContext/ICurrentTenant/IServiceScopeFactory 相依。新增 `AuthAuditActions`(通用 auth 動作詞彙)+`AuthDefaults.TenantId`(單租戶預設);handler audit 的 Product 仍由各產品寫入器標記。HD.Shared.Auth.csproj 加 `FrameworkReference Microsoft.AspNetCore.App`(handler 要 AuthenticationHandler/HttpContext;與 IdentityModel 套件無衝突)。刪 DicomWeb 原 handler;Program.cs 註冊行不動(型別走 using HD.Shared.Auth 自動解析)。**HD.Shared + DicomWeb build 綠 + 87/87 通過**。→ **DicomWeb 的 API Key 驗證現已完全跑在共用包**。
- **決策微調:`ApiKeyService`(管理 CRUD)不搬 HD.Shared.Auth** —— 它是 management,歸宿是 [[project_hd_admin_console]](等主控台一建就進去、DicomWeb 金鑰管理 REST/Blazor 下架)。先留 DicomWeb(已用共用 ScopeCatalog/Hasher/IpWhitelist)。
- ✅ **b4(2026-08-06):** `AddKeycloakJwtBearer` 擴充加進 HD.Shared.Auth(JwtBearer 10.0.7,對齊 DicomWeb.Api;`AddJwtBearer` 擴充在 `Microsoft.Extensions.DependencyInjection` 命名空間)。HD.Shared build 綠、DicomWeb build+87 綠。**⚠️ 此變更僅在 HD.Shared 工作區、未 commit。** audience 也已解決(見 [[project_auth_keycloak_plan]]:client scope hd-api + hd-pacs,嚴格 aud live 測過)。
- **共用 Auth 完整:** 兩條驗證路齊 —— API Key(handler/Npgsql)+ Keycloak JWT(TokenClient/Validator/AddKeycloakJwtBearer)。真正把登入切 Keycloak 仍待「身分→HD_USER 映射 + 退 dev-token」(獨立一步)。
- **共用 Auth 現況:** Scopes/ScopeCatalog、ApiKeyHasher、IpWhitelist、HdUserRepository、Keycloak(TokenClient/Validator/Options)、ApiKeyAuthenticationHandler、AuthConstants —— **驗證面已完整**。
- ✅ **已 commit(未 push,2026-08-06):** HD.Shared `1af8e6c`(新增共用地基)、HD.Pacs.DicomWeb `f64704b`(抽到共用包,淨 −847 行)。工作區乾淨、全綠。
- ✅ **共享事件表落地(2026-08-06 程式面全完成):** v2.0.27 migration(`HD_USER_AUDIT_LOG` 加 PRODUCT/CATEGORY 欄+`(PRODUCT,OCCURRED_AT)` 索引,既有資料 default dicomweb/audit,Database `e36249a`);HD.Shared.Events 加 **`DbAuditLogger`**(可攜 Npgsql 寫入器:寫事件表+同步落 ILogger→LoggingPlatform,失敗不拋,`69e08a2`);DicomWeb entity/mapping/flush 補兩欄+ChannelAuditLogger **category 粗分**(auth./user./config.=audit,其餘=operation,`a15cb65`);Export 改 DbAuditLogger(product=export,`ad734b3`);主控台金鑰稽核改 DbAuditLogger(product=admin-console,`34ca38d`)。**✅ 全部完成+實測(2026-08-06 晚):** .191 已套 migration(2000 筆歷史自動 default 歸戶);DicomWeb/Export 已重部署 .199;**三產品實測入表**:dicomweb/operation(qido)、export/audit(壞 key 攔截,經共用 handler→DbAuditLogger)、admin-console/audit(金鑰生命週期),SOURCE_IP 皆正確(VPN 來源/本機 ::1;主控台 IP 靠 AddHttpContextAccessor,`0360d82`)。**部署慣例更新:.199 家目錄分資料夾 `~/deploy-dicomweb`、`~/deploy-export`(install.sh 同名互蓋問題解)**。稽核分層定案:登入=Keycloak Events(已開)、操作/機器=此事件表、排障=LoggingPlatform。WebExport(客戶前台)另立 REQ-010。下一步:主控台稽核查詢頁(讀此表+Keycloak Admin API)。

相關:[[project_dicomweb_apikey_consolidation]](被搬進 Auth 的來源)、[[project_auth_keycloak_plan]]、[[project_hd_admin_console]]、[[project_shared_logging]]。
