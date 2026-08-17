# 身分 / 認證（Keycloak SSO + API Key）

**目標模型**：AuthN 交 Keycloak、AuthZ 查 DB。token 只證明「你是誰」，能做什麼一律回頭查 `HD_USER`/`HD_ROLE.ACCESS`。

**進度**：主控台（.191:5200，2026-08-07）與 **DicomWeb（.199:5080，2026-08-07/08）皆已切完**；dev-token/自鑄 token 全退役。剩 Viewer（隨新版）與 provisioning API（待同事契約）。

**帳密路（2026-08-09 打通）**：`hdtest` 現為首個雙邊帳號（Keycloak + `HD_USER` ID=hdtest、ROLES=[1] admin、email=hdtest@hyperdigital.biz 兩邊一致）；password grant → `/me` 200 實證。新人類帳號要走 API 的，照此模式兩邊都建（直到 provisioning API 落地自動雙寫）。

**groups claim（2026-08-09）**：`hd-api` client scope 掛 **Group Membership mapper**（Token Claim Name=`groups`、Full group path=Off、Add to access/ID token=On）→ 所有掛 `hd-api` 的 client 的 token 都帶 `groups`；DicomWeb `/api/v1/auth/me` 回傳。**用途定位：顯示/分流；授權仍查 DB**（要群組→權限映射屬架構變更，另議）。

**OIDC 導頁登入實戰坑（每個新站台都會遇）**：
1. access token `aud=account` → client scope `hd-api`+Audience mapper（`hd-pacs`）。
2. `MapInboundClaims=false` 必關（否則 sub/email 變長 URI）。
3. http 站台：correlation/nonce cookie `SameAsRequest`+`Lax`（預設 Secure 被拒收）。
4. http 站台：`ResponseMode=Query`（預設 form_post 被 Chrome 攔且不帶 cookie）。
5. `PushedAuthorizationBehavior.Disable`（sso.ltcd.tw 的 PAR 路徑 502）。
6. **`SaveTokens=true` 必開**——RP-initiated 登出要 `id_token_hint`，沒存會被 Keycloak 拒（Missing parameters）。
7. **`DefaultChallengeScheme` 別設 OIDC**——未登入開受保護頁會跳過自家登入卡直彈 Keycloak；讓 cookie 預設 challenge 導 LoginPath，OIDC 只由 login 端點明確 Challenge。
8. Keycloak client 的 **Valid post logout redirect URIs 設 `+`**（沿用 redirect URIs 清單）。
9. **反向代理的 proxy buffer 預設 4k 撐不住 OIDC——兩邊都要加大**（2026-08-10 實案，皆已修）：
   - **站台自己的 nginx（TLS 反代）**：OIDC 回呼 `/signin-oidc` 的回應要寫入 `SaveTokens=true` 的登入 cookie
     （access+id+refresh 分塊 Set-Cookie 近 10KB）→ `upstream sent too big header` → **502 頁署名自家 nginx**。
     症狀特徵：**直連 app port 正常、走反代固定 502**。修＝conf 加
     `proxy_buffer_size 32k; proxy_buffers 8 32k; proxy_busy_buffers_size 64k;`（已入 deploy/nginx/hdpacs-tls.conf）。
   - **sso.ltcd.tw 前的 openresty**：`KEYCLOAK_IDENTITY` 隨 claims 長大＋`KC_RESTART` 含整串 state，cookie 疊厚後
     也會 502（**坑 5 的 PAR 502 同根因**；清 sso cookie 可暫解）。已由同事加
     `proxy_buffer_size 16k; proxy_buffers 8 16k; proxy_busy_buffers_size 32k; large_client_header_buffers 4 32k;`。
   - 除錯要訣：**看 502 頁的署名（nginx vs openresty）＋DevTools 看是哪個網址 502**，才知道是哪一台反代在擋。

## 兩種憑證
- **人 → Keycloak JWT**：使用者登入 Keycloak 拿 JWT，各服務驗 JWKS 簽章＝「放行」，再用身分查 DB 給 scope。
- **機器 → API Key**（`hdp_…`）：儀器／Export／程式的長期憑證，各服務算 hash 查 `HD_API_KEY`。管理面集中到 [HD 管理主控台](admin-console.md)。

## Keycloak 實測（同事已建置）
- **token 端點**：`POST https://sso.ltcd.tw/realms/hd/protocol/openid-connect/token`（測試用 password grant：client `hd-viewer`、scope `openid`）。
- **issuer**：`https://sso.ltcd.tw/realms/hd`；**JWKS**：`.../protocol/openid-connect/certs`。.NET 用 `AddJwtBearer` 設 `Authority=issuer` 會自動抓 JWKS + 處理 kid 輪替，**別寫死公鑰**。
- **✅ audience 已解決（2026-08-06）**：在 realm `hd` 建 client scope `hd-api`（Default）+ Audience mapper（Included Custom Audience=`hd-pacs`、Add to access token=On），掛到 client。access token 的 `aud` 現在帶 `hd-pacs,account`。**嚴格 aud 驗證 live 測過**：`ValidateAudience=true` + `ValidAudiences=["hd-pacs"]` → 通過。→ HD.Shared.Auth 直接用嚴格 aud，不留過渡。
  - 專用測試 client：**`hd-pacs-client`**（public、Direct access grants On）；新 client 只要掛 `hd-api` scope 就有 aud。
- **身分鍵**：用 `preferred_username`（→ `HD_USER.ID`）；**別用 email**（此 realm email 為 `@example.com` 佔位、`email_verified=false`）。建議註冊時順手存 `sub`（Keycloak UUID，永久）當將來的永久連結。
- **角色/scope 不看**：`realm_access`/`resource_access`/`scope` 一律忽略，授權出自 DB。
- **生命週期**：access 15 分／refresh 30 分，refresh 由 client 管；我方無狀態、每次驗 access token。

## Live 實測（2026-08-06，通過）
最小 .NET 工具實測「取 token → JWKS 驗簽章 → 取身分」全通（`Authority=issuer` 自動抓 JWKS、`ValidateAudience=false` 過渡）：
- JWKS 有兩把 key：`use=sig`（RS256，kid `7hxOT…Nvhw`，驗簽用）+ `use=enc`（RSA-OAEP，不用）。.NET 依 kid 自動挑 sig key。
- 可用 grant：`authorization_code`（瀏覽器 SSO 登入）、`password`（測試/直連）、`client_credentials`（機器）、`refresh_token`、`device_code`。
- **⚠️ 第二個坑：claim 映射**。舊 `JwtSecurityTokenHandler` 預設把 `sub`→nameidentifier、`email`→schema URI，害讀不到。**要關掉**：`handler.MapInboundClaims=false`，ASP.NET 對應 `options.MapInboundClaims=false`。關掉後 `sub`/`preferred_username`/`email`/`groups` 都正確。
- 端點：token `…/token`、auth `…/auth`、userinfo `…/userinfo`、logout `…/logout`（end_session）。

## Provisioning（決策）
使用方打 API 去 Keycloak 註冊帳號（帳密），同一動作建 `HD_USER`（同 ID、配 role）→ 兩邊建立當下同步、無孤兒。註冊 API＝Keycloak Admin REST（需 service client 憑證），契約待同事給。

## 遷移影響（實作時）
- 退役自鑄 token 那串：`JwtIssuer`、`/api/v1/auth/dev-token`、`DevSigningKeyProvider`、`HD_USER.PASSWORD`。
- 驗證抽成**共用 Auth 套件**（驗 Keycloak JWT ＋ 身分→HD_USER＋ResolveScopes ＋ API Key handler），DicomWeb / Export / 主控台共用。
- **零 token 資料搬遷**（現行 JWT 無狀態、哪裡都沒存）。

## 待同事（Keycloak 端）
~~①audience mapper~~ ✅ 已完成（`hd-api` scope + `hd-pacs`，見上）。②註冊 API 的 URL/格式/認證、回應有無 sub ③正式登入流程走標準 OIDC 導頁 or password grant。

相關：記憶 project_auth_keycloak_plan / reference_dicomweb_auth、[admin-console.md](admin-console.md)、[dicomweb.md](dicomweb.md)。
