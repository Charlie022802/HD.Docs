---
name: reference_dicomweb_auth
description: HD.Pacs.DicomWeb 各 API 的認證方式對照(Keycloak JWT / API Key / cookie / 公開)與 MultiScheme 分派邏輯
metadata: 
  node_type: memory
  type: reference
  originSessionId: a23fe480-c347-41d9-ba5a-eb699a5d1cf4
  modified: 2026-08-08T14:00:30.266Z
---

**2026-08-07/08 更新:人類認證全面切 Keycloak(部署 .199)。** JWT scheme=`AddKeycloakJwtBearer`(aud=hd-pacs 嚴格);token 不帶 scopes → `OnTokenValidated` 以 `preferred_username` 查 HD_USER → `ResolveScopes` 補 scopes claims(**無對應 HD_USER 一律 401**);Admin UI=登入卡→OIDC 導頁(cookie 會話同名沿用);**退役** JwtIssuer/DevSigningKeyProvider/`POST /api/v1/auth/dev-token`/固定管理帳密/HD_USER.PASSWORD;**金鑰管理端點+UI 下架**(搬主控台,見 [[project_hd_admin_console]]),只留驗證。稽核 ActorId 優先 `preferred_username`(sub 是 UUID)。

HD.Pacs.DicomWeb 認證架構(Program.cs)。三種 scheme:
- **MultiScheme**(PolicyScheme):Keycloak JWT + API Key **兩者皆可**。分派:`X-API-Key` header 或 `Bearer hdp_...`(ApiKeyHasher.LooksLikeApiKey)→ ApiKey scheme;其他 `Bearer` → JWT。任一成功即認證成功,不會兩者都跑。
- **AdminCookie**("AdminCookie"/cookie `hdpacs_admin`):**預設 scheme**,只給 Admin Blazor UI,未登入導 `/admin/login` 登入卡(**challenge 保持 cookie 預設;DefaultChallengeScheme 別設 OIDC,否則跳過登入卡直彈 Keycloak**);OIDC 選項含 http 三坑修正+**SaveTokens=true(登出要 id_token_hint)**。見 [[project_dicomweb_features]]、[[project_auth_keycloak_plan]]。
- 公開(AllowAnonymous)/內部自呼叫祕鑰。

**各 API 認證對照(所有對外資料/管理 API 都 JWT+API Key 雙支援;例外見底):**

| 端點 | Policy/scope | JWT | API Key |
|---|---|---|---|
| QIDO `GET /dicomweb/studies…` | DicomWebRead | ✅ | ✅ |
| WADO-RS `GET /dicomweb/…`(metadata/影像/frames/rendered/thumbnail) | DicomWebRead | ✅ | ✅ |
| WADO-URI `GET /wado` | DicomWebRead | ✅ | ✅ |
| STOW `POST /dicomweb/studies[/{uid}]` | DicomWebWrite | ✅ | ✅ |
| DELETE `DELETE /dicomweb/studies…` | DicomWebDelete | ✅ | ✅ |
| Import `POST /api/v1/import` | ImportWrite | ✅ | ✅ |
| UPS-RS `/workitems…` | WorkitemRead/Write | ✅ | ✅ |
| ~~API Key 管理 `/api/v1/api-keys`~~ | **已下架**(搬主控台,404) | — | — |
| 稽核查詢 `/api/v1/audit/logs` | AdminAudit | ✅ | ✅ |
| `GET /api/v1/auth/me` | 需登入(MultiScheme) | ✅ | ✅ |
| ~~`POST /api/v1/auth/dev-token`~~ | **已退役**(token 向 Keycloak 取) | — | — |
| `/health`、`/health/live`、`/health/ready`、`GET /dicomweb/conformance` | 公開 | — | — |
| Admin 主控台 API `/api/v1/admin/*` | **內部限定**:loopback + `X-Self-Call` 祕鑰(SelfCallToken) | ❌ | ❌ |
| Admin 網頁 UI `/admin/*` | **Cookie**(AdminCookie) | ❌ | ❌ |

註:表為「機制」層級;實際存取還要看該 JWT/金鑰有無對應 **scope**(如 dicomweb.read)。

**`anonymise` claim 只有 API Key 認證會鑄**(`ApiKeyAuthenticationHandler` ~L156,對應 HD_API_KEY.ANONYMISE_NAME);JWT(`JwtIssuer`)不鑄——因匿名規則綁金鑰。故取回時去識別=金鑰驅動,JWT 醫生取原始、API Key(SharedServer)取匿名。相關:[[project_dicomweb_features]]。
