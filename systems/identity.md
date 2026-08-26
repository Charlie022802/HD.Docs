# 身分 / 認證（Keycloak SSO + API Key）

**目標模型**：AuthN 交 Keycloak、AuthZ 查 DB。token 只證明「你是誰」，能做什麼一律回頭查 `HD_USER`/`HD_ROLE.ACCESS`。

**進度**：主控台（.191:5200，2026-08-07）、**DicomWeb（.199:5080，2026-08-07/08）**、**Export API（.199:5090，2026-08-18，`0.1.0-alpha.11`）** 皆已切完；dev-token/自鑄 token 全退役。剩 Viewer（見下）與 provisioning API（待同事契約）。

> **Export 的 MultiScheme 是照 DicomWeb 抄的**，三處值得注意：①`Keycloak.Authority` 走 `/etc/hd-export/keycloak.env` 而非 appsettings（各院之後自建 Keycloak，理由見 [deployment.md](deployment.md)「設定要放哪」）②沒設 Authority 就只收 API Key、不註冊 JWT scheme，服務照常運作 ③呼叫端是純前端時**還需要 CORS**，且要 expose `Content-Disposition`，否則前端讀不到下載檔名。

## Keycloak 的佈署拓樸（2026-08-26 定案：固定架構）

**一個產品、兩種 Authority，依站台的網路環境決定：**

| 站台 | Authority 指向 | 說明 |
|---|---|---|
| 外網連得到的 | `https://sso.hdtech.tw/realms/hd` | 現行，同事建置與維運 |
| 封閉網路的醫院 | **院內自架的 Keycloak** | 我們架，每間一套 |

**這不是過渡方案，是固定架構。** 所以：

- **不做帳密雙軌**（曾評估過「沒有 Keycloak 就退回 `HD_USER` 帳密」，不採用）——
  每個站台都會有 Keycloak，`HD_USER.PASSWORD` 維持在退役清單裡。
  （Viewer 現行的 WebApi 帳密路是**既有現場的相容需求**，與此無關，見下節。）
- **主控台的啟動護欄（`Authority` 為空就 throw）是對的，不用改。** 在這個架構下
  「沒有 Authority」只可能是佈署漏設，大聲失敗正確。
- **主控台進醫院不需要改任何程式碼** —— `Keycloak:Authority` 本來就走各機器的
  `/etc/hd-*/keycloak.env`（當初就是為了「各院位址不同」才這樣設計的）。
- 各服務驗 token 用 `Authority=issuer` 自動抓 JWKS，issuer 逐站不同不影響。

**這個架構帶出兩件還沒解的事：**

1. **realm 設定必須變成可重現的產物。** 現在 `sso.hdtech.tw` 的 realm 是手動點出來的，
   我們這邊只有散文紀錄（`hd-api` client scope、audience mapper `hd-pacs`、
   `hd-pacs-client`、Group Membership mapper、下面那九個 OIDC 坑…）。要在每間醫院重建一次、
   靠人照文件點，遲早會漏 —— 而漏掉的症狀就是那九個坑之一，每個都難查。
   Keycloak 有 realm export/import（JSON），**應該把 realm 匯出成版控檔案當部署產物**。
2. **兩個身分域的關係還沒定。** 中央有同事的訂閱使用者，院內 Keycloak 有醫院自己的人。
   訂閱使用者需不需要進到某間醫院的 PACS？不需要＝兩邊各自獨立、乾淨；
   需要＝院內 Keycloak 要把中央設成 identity provider（brokering），那是另一個設計。
   **這直接影響 JIT 的語意**：院內 Keycloak 的 JIT 是「醫院員工自助長出 `HD_USER`」，
   跟訂閱使用者那個情境不是同一回事。

營運面要一併想的：每間醫院的 Keycloak 要升級、憑證、備份，而 Keycloak 自己也要一個 DB。

## Viewer 切 Keycloak（2026-08-17 決策：雙軌，提前實作、不替換）

**背景**：醫院多為封閉網路，連不到外部的 `sso.hdtech.tw` —— 看片端跑在醫師個人電腦、連的是醫院內部主機，
登入若要繞出去打 Keycloak，封閉網路的醫院會直接登不進去看片。

**方向**：**之後會在各醫院封閉網路內部自建 Keycloak SSO**（尚未架設）。所以：

- 登入這塊**可以提前先做**——寫好 Keycloak 路徑（Authority 指向院內 SSO 位址，由設定決定）。
- **但不能替換現行方式**。現行＝登入視窗輸入帳密 → 打醫院主機 WebApi `/api/v2.0/user/login` 驗 `HD_USER`
  → 回 `access`/`userInfo`（`LoginForm.CheckUser` / `WebApiClient.LoginWithCredentialsAsync`）。
  現場所有醫院現在都靠這條，院內 SSO 架起來以前它必須維持可用、且是預設。
- 因此是**雙軌**：新的 Keycloak 路徑與既有 WebApi 帳密路徑並存，靠設定切換；院內 SSO 到位的醫院才開。
- AuthZ 不變：仍是 Keycloak 只證明身分、權限回頭查 `HD_USER`/`HD_ROLE.ACCESS`。

（同一個封閉網路根因也卡住看片端授權簽發 REQ-015、以及「醫院端裝唯讀主控台」的規劃；院內 SSO 一旦落地，
後者的 OIDC 登入問題會一併解掉。）

**帳密路（2026-08-09 打通）**：`hdtest` 現為首個雙邊帳號（Keycloak + `HD_USER` ID=hdtest、ROLES=[1] admin、email=hdtest@hyperdigital.biz 兩邊一致）；password grant → `/me` 200 實證。新人類帳號要走 API 的，照此模式兩邊都建（直到 provisioning API 落地自動雙寫）。

**groups claim（2026-08-09）**：`hd-api` client scope 掛 **Group Membership mapper**（Token Claim Name=`groups`、Full group path=Off、Add to access/ID token=On）→ 所有掛 `hd-api` 的 client 的 token 都帶 `groups`；DicomWeb `/api/v1/auth/me` 回傳。**用途定位：顯示/分流；授權仍查 DB**（要群組→權限映射屬架構變更，另議）。

**OIDC 導頁登入實戰坑（每個新站台都會遇）**：
1. access token `aud=account` → client scope `hd-api`+Audience mapper（`hd-pacs`）。
2. `MapInboundClaims=false` 必關（否則 sub/email 變長 URI）。
3. http 站台：correlation/nonce cookie `SameAsRequest`+`Lax`（預設 Secure 被拒收）。
4. http 站台：`ResponseMode=Query`（預設 form_post 被 Chrome 攔且不帶 cookie）。
5. `PushedAuthorizationBehavior.Disable`（sso.hdtech.tw 的 PAR 路徑 502）。
6. **`SaveTokens=true` 必開**——RP-initiated 登出要 `id_token_hint`，沒存會被 Keycloak 拒（Missing parameters）。
7. **`DefaultChallengeScheme` 別設 OIDC**——未登入開受保護頁會跳過自家登入卡直彈 Keycloak；讓 cookie 預設 challenge 導 LoginPath，OIDC 只由 login 端點明確 Challenge。
8. Keycloak client 的 **Valid post logout redirect URIs 設 `+`**（沿用 redirect URIs 清單）。
9. **反向代理的 proxy buffer 預設 4k 撐不住 OIDC——兩邊都要加大**（2026-08-10 實案，皆已修）：
   - **站台自己的 nginx（TLS 反代）**：OIDC 回呼 `/signin-oidc` 的回應要寫入 `SaveTokens=true` 的登入 cookie
     （access+id+refresh 分塊 Set-Cookie 近 10KB）→ `upstream sent too big header` → **502 頁署名自家 nginx**。
     症狀特徵：**直連 app port 正常、走反代固定 502**。修＝conf 加
     `proxy_buffer_size 32k; proxy_buffers 8 32k; proxy_busy_buffers_size 64k;`（已入 deploy/nginx/hdpacs-tls.conf）。
   - **sso.hdtech.tw 前的 openresty**：`KEYCLOAK_IDENTITY` 隨 claims 長大＋`KC_RESTART` 含整串 state，cookie 疊厚後
     也會 502（**坑 5 的 PAR 502 同根因**；清 sso cookie 可暫解）。已由同事加
     `proxy_buffer_size 16k; proxy_buffers 8 16k; proxy_busy_buffers_size 32k; large_client_header_buffers 4 32k;`。
   - 除錯要訣：**看 502 頁的署名（nginx vs openresty）＋DevTools 看是哪個網址 502**，才知道是哪一台反代在擋。

## 兩種憑證
- **人 → Keycloak JWT**：使用者登入 Keycloak 拿 JWT，各服務驗 JWKS 簽章＝「放行」，再用身分查 DB 給 scope。
- **機器 → API Key**（`hdp_…`）：儀器／Export／程式的長期憑證，各服務算 hash 查 `HD_API_KEY`。管理面集中到 [HD 管理主控台](admin-console.md)。

## Keycloak 實測（同事已建置）
- **token 端點**：`POST https://sso.hdtech.tw/realms/hd/protocol/openid-connect/token`（測試用 password grant：client `hd-viewer`、scope `openid`）。
- **issuer**：`https://sso.hdtech.tw/realms/hd`；**JWKS**：`.../protocol/openid-connect/certs`。.NET 用 `AddJwtBearer` 設 `Authority=issuer` 會自動抓 JWKS + 處理 kid 輪替，**別寫死公鑰**。
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

## Provisioning

### 原決策（2026-08-06，**未實作，已被現實推翻**）
使用方打 API 去 Keycloak 註冊帳號（帳密），同一動作建 `HD_USER`（同 ID、配 role）→ 兩邊建立當下同步、無孤兒。註冊 API＝Keycloak Admin REST（需 service client 憑證），契約待同事給。

**這個契約沒有發生。** 同事的**前端訂閱制系統**先上線了：使用者在那邊自行註冊、Keycloak 由他那端整合。
於是註冊發生在我們看不到的地方，`HD_USER` 永遠不會長出來——症狀就是拿著合法 token 打 DicomWeb／Export 一律 **401**。

### 現行：JIT 佈建（2026-08-26）

**Keycloak 認得、但本系統沒有對應 `HD_USER` 時，就地建一筆零角色的使用者**，而不是拒絕。
之後管理者再指派角色。等於把「建立當下同步」換成「第一次使用時補資料」。

為什麼是這個而不是雙寫：**自行註冊的情境下沒有人能保證雙寫會發生**。而且訂閱制的重點不是建立、是
**權益會一直變**——推播式同步每漏一次就是靜默漂移，且漂移方向很糟（已取消訂閱的人還留著權限）。
JIT 沒有這個失敗模式：取消訂閱時 Keycloak 不發 token，人根本到不了我們這裡。

- **開關**：`KeycloakOptions.JitProvisionUsers`，**預設 false**，要開的站台明確開。
  設定**必須走環境變數** `Keycloak__JitProvisionUsers=true`（放各服務的 `/etc/hd-*/keycloak.env`）——
  `appsettings.json` 在 hdctl 的 preserve 清單裡，新增的設定不會上到既有機器（2026-08-18 Export 踩過）。
- **實作**：`HdUserRepository.ResolveByIdAsync(userId, provisionIfMissing, ct)`（HD.Shared.Auth，三支服務共用）。
  傳 `null` 給第二個參數＝維持原本行為。
- **佈建出來是零角色**：`ROLES='[]'`、`GROUP_REF=2`（`DEFAULT`）。進得來，但每個 scope 都沒有，
  授權仍然出自 DB。**`OTHERS` 存 `keycloakSub` 與 `provisionedBy:"jit"`**——前者是之後想改用 `sub`
  當連結鍵的唯一資料來源（佈建當下不存就永遠補不回來），後者讓管理介面分得出「自己註冊進來的」。
- **稽核**：`JitProvisioningAudit.Emit`（共用），action `auth.user.jit_provision`。
  這則事件是「這個帳號從哪冒出來的」的唯一線索——建立動作沒有經過任何管理介面。

**三個實作上的坑（都實測撞過）**：

1. **`HD_USER."ID"` 沒有唯一約束**，只有非唯一索引 `index-HD_USER-ID`，所以 `ON CONFLICT` 用不了。
   併發打進來會插出多列同 ID，而 `FindByFieldAsync` 的 `LIMIT 1` 讓「之後查到哪一列」變不確定——
   權限跟著飄，且完全沒有錯誤訊息。解法：`pg_advisory_xact_lock(hashtext('hd_user_jit:'||id))`
   ＋`INSERT … WHERE NOT EXISTS`，不動 schema。（加唯一索引會擋到既有站台可能已有的重複資料，另議。）
2. **不要對 `GROUP_REF` 做 `MIN()` fallback**。安裝種子（`2.initialization.sql`）建的是
   `0=admin`、`1=build-in`、`2=DEFAULT`，取最小值會挑到 **0＝admin 群組**——自動註冊進來的人
   被丟進管理群組，而且不會有任何錯誤訊息。作法：只用 2，不在就大聲失敗（與 `insert_update_user`
   的 `COALESCE(groupRef, 2)` 一致）。
3. **不要寫沒人讀的欄位**。`ENABLE`／`EXPIRE_DATE` 在 `.191` 有、**更新鏈裡沒有**，若瑟這種舊站台沒有
   → `INSERT` 直接 `42703`。全 DB 沒有任何地方讀它們，寫了也沒意義，直接不碰。
   `OTHERS` 則是 `v2.0.35` 才進更新鏈，所以是**條件式寫入**（先查 `information_schema`）。
   詳見 [josef-db-upgrade-plan.md](../josef-db-upgrade-plan.md) 的「更新鏈是不完整的」。

**驗證**：
- **單元層**：`HdUserRepository` 對兩種真實 schema 各跑過 25 項斷言（若瑟原始 schema＝無 `ENABLE`；
  `.191` 型＝有 `ENABLE`），含 12 路併發只插一列、群組 2 缺席時大聲失敗、既有使用者解析不受影響。
- **端到端（2026-08-26，`.199` 生產，dicomweb `1.0.0-alpha.10`／export `0.1.0-alpha.16`）**：
  把 `.191` 的 `hdtest` 暫時改名造出「Keycloak 有、`HD_USER` 沒有」的狀態 →
  `/api/v1/auth/me` 從 10 個 scopes 變成 **200 且 `scopes:[]`**、QIDO 從 200 變成 **403（不是 401）**、
  DB 長出 `ROLES=[]`／`OTHERS.keycloakSub` 等於 token 的 `sub` 的一列 → 還原後全部回到原狀。
  **401→403 是關鍵證據**（401＝不知道你是誰，403＝知道你是誰但沒權限）；
  `active`＋`/health` 200 完全證明不了 JIT，因為那條路徑根本沒被走到。

### 還沒解的：權益等級

JIT 讓人進得來，但**沒有解決「這個人該有什麼權限」**。目前要管理者手動指派。
方向是把訂閱方案表現成 Keycloak group → 我方做 group → `HD_ROLE` 映射
（`groups` claim **現在就已經在 token 裡**，見下方 groups claim 段；當時標註「另議」的就是這件事）。
契約只有一張對照表，比 REST API 契約好談。**待與同事確認。**

## 遷移影響（實作時）
- 退役自鑄 token 那串：`JwtIssuer`、`/api/v1/auth/dev-token`、`DevSigningKeyProvider`、`HD_USER.PASSWORD`。
- 驗證抽成**共用 Auth 套件**（驗 Keycloak JWT ＋ 身分→HD_USER＋ResolveScopes ＋ API Key handler），DicomWeb / Export / 主控台共用。
- **零 token 資料搬遷**（現行 JWT 無狀態、哪裡都沒存）。

## 待同事（Keycloak 端）
~~①audience mapper~~ ✅ 已完成（`hd-api` scope + `hd-pacs`，見上）。②註冊 API 的 URL/格式/認證、回應有無 sub ③正式登入流程走標準 OIDC 導頁 or password grant。

相關：記憶 project_auth_keycloak_plan / reference_dicomweb_auth、[admin-console.md](admin-console.md)、[dicomweb.md](dicomweb.md)。
