---
name: project_dicomweb_apikey_consolidation
description: DicomWeb API Key 管理收斂—scope單一正本ScopeCatalog+CRUD單一正本ApiKeyService(EF);已做未commit未部署
metadata: 
  node_type: memory
  type: project
  originSessionId: 13e6b6ed-984d-4c27-aed8-2170077bfa02
  modified: 2026-08-06T05:13:40.642Z
---

**2026-08-06 收斂完成(build 0 err、單元測試 87/87 綠)。已 commit(未 push):併入 HD.Pacs.DicomWeb `f64704b`(該 commit 同時把 ScopeCatalog/Hasher/handler 等抽到共用包 HD.Shared,見 [[project_core_architecture]])。未部署驗。** 起因:API Key 這攤太亂——同一張 `HD_API_KEY` 三條路(REST EF `ApiKeysEndpoints`、Blazor raw-SQL `ApiKeyAdminService`、驗證 handler)＋ scope 清單抄四份各自漂移(Domain `Scopes` 14 個、REST 白名單 6 個、UI 8 個、admin service 完全不驗)。使用者選「全收斂・EF 為主」。

**做法:**
- 新 `Domain/ScopeCatalog.cs`＝scope 單一正本:每個 scope 帶 `DisplayName / Category(Read/Write/Delete/Admin) / ApiKeyAssignable / RequiresAeBinding`。REST 驗證、UI 勾選框、badge 配色全讀它。`ApiKeyAssignable=false` 的是 admin.*(只給登入者,不給 API Key);`RequiresAeBinding=true` 只有 dicomweb.write/import.write。
- 新 `Api/Services/ApiKeyService.cs`＝CRUD 單一正本(EF 存 `HD_API_KEY`,`PacsDbContext.ApiKeysSet`;AE_MAIN/ROUTING_ANONYMISE 清單仍原生 Npgsql 查)。方法 List/Create/Update/Revoke + ListAeTitles/ListAnonymiseRules。驗證(scope 白名單、上傳綁 AE、重名檔大小寫不敏感、IP 合法性)只寫一次。單租戶固定 `TenantConstants.DefaultTenantId`。稽核用 `ApiKeyActor(ActorId/SourceIp/UA/RequestId)` 傳入(REST 由 HttpContext 帶滿、Blazor 電路只帶 ActorId)。
- `ApiKeysEndpoints` 改薄殼委派 service,**補上原本沒有的 `PUT /{id}` 編輯**、IP 白名單、`GET /scopes`、`GET /ae-titles` 目錄端點;`CreateApiKeyRequest` 加 `ip_whitelist`。
- `ApiKeys.razor` 從 `JsonElement`+`TryGet` 改**強型別 `ApiKeyView`**;scope 勾選/標籤/badge 改讀 ScopeCatalog;actor 取自 `AuthenticationStateProvider`。
- **刪 `ApiKeyAdminService.cs`**(raw-SQL 重複實作);DI(`Program.cs`)改註冊 `ApiKeyService`。驗進來的 key 仍走 `ApiKeyAuthenticationHandler`(EF,不變)。

**順手修的真 bug:** 原 REST 白名單(6 個)和 UI(8 個)**都沒 `export.*`**→根本無法從 UI/REST 建 export 金鑰,只能手改 SQL。現在 ScopeCatalog 標為可指派→解掉 [[project_req003_export_webapi]] 測試前置③。

**注意:** 純程式改動、**未動 DB schema**,照舊 build/部署即可。待 commit + 部署 .199 驗。與未來 [[project_auth_keycloak_plan]] 的「共用 Auth lib」形狀相容(ScopeCatalog + service 好抽出)。相關 [[reference_dicomweb_auth]]、[[project_dicomweb_features]]。
