---
name: project_auth_keycloak_plan
description: Keycloak(SSO)—AuthN交Keycloak/AuthZ查DB;取+驗token已live實測通過;改為核心架構早期就要做(綁畫面登入)
metadata: 
  node_type: memory
  type: project
  originSessionId: 13e6b6ed-984d-4c27-aed8-2170077bfa02
  modified: 2026-08-17T03:23:31.207Z
---

**🔑 定案(2026-08-06 晚):所有產品的「人」登入一律改走 Keycloak。** 隨之而來的稽核分層定案:**登入事件正本=Keycloak Events**(各產品不再自記登入;要請同事開 realm Events:LOGIN/LOGIN_ERROR/LOGOUT+保留期,沒開=沒紀錄);**操作事件+API Key(機器)=共享事件表**(各產品寫、主控台查;主控台稽核頁未來雙源:事件表+Keycloak Admin API 拉登入)。DicomWeb dev-token 的登入稽核隨退役自然消失。現況三落點亂象(DicomWeb→DB 表、Export→LoggingPlatform、主控台→ILogger)由共享事件表收斂。

**2026-08-06 提升優先序:改「先測好加進核心架構」(原暫緩)。** 管理主控台與各產品的「畫面登入 + 拿 token」都靠它,屬核心架構 `HD.Shared.Auth` 早期件。**已 live 實測通過**:最小 .NET 工具取 token(password grant)→ OIDC discovery 自動抓 JWKS → 驗 RS256 簽章+issuer+生命週期 → 取 sub/preferred_username/email/groups 全通。**第二個坑(實測抓到):claim 映射** —— 舊 `JwtSecurityTokenHandler` 預設把 sub→nameidentifier、email→schema URI,要 `MapInboundClaims=false`(ASP.NET `options.MapInboundClaims=false`)才讀得到。JWKS 兩把 key(sig RS256 / enc RSA-OAEP,依 kid 自動挑 sig)。可用 grant 含 authorization_code(瀏覽器 SSO)/password/client_credentials。這支工具＝`HD.Shared.Auth` Keycloak 部分種子(scratchpad sso-test)。

同事開發中的 SSO 平台(**Keycloak**)上線後,HD 需登入的程式都去跟它要 token。**這輪暫緩、只保留一條路,不實作**(2026-08-06 決策)。設計已談定:

**核心=AuthN / AuthZ 分離。** Keycloak 只負責「證明你是誰」(驗 JWKS 簽章＝放行);**權限仍查 DB**(`HD_USER` + `HD_ROLE.ACCESS`→`ResolveScopes`→scope)。token 裡帶的 scope 一律不信,拿到身分後回頭查 DB 決定放不放。

**現況利多(讓遷移幾乎是換零件):** 現在自鑄的 JWT 已是 **RS256 非對稱**(`JwtIssuer` 用 RsaSha256、私鑰 `DevSigningKeyProvider` 存 `./data/dev-signing-key.pem`,config `Auth:DevKeyPath`;issuer/audience 見 `Auth:Issuer`=`https://hd-pacs.local`/`Auth:Audience`=`dicomweb`)。token **無狀態、哪裡都沒存**(沒有 token/session 表、沒有 refresh);只有登入「事件」進稽核。→ 接 Keycloak 只需把 `TokenValidationParameters` 的 issuer/audience/signing key 指向 Keycloak(有 JWKS 就抓公鑰),驗證程式主體不動,**零 token 資料搬遷**。

**要退役的自鑄件:** `JwtIssuer`、`/api/v1/auth/dev-token`(`AuthEndpoints`)、`DevSigningKeyProvider`、`HD_USER.PASSWORD`(密碼改只在 Keycloak;`DevSigningKeyProvider` 註解本就寫「Production 應改外部 IdP(Keycloak)」)。

**Provisioning(使用者確認):** 使用方打 API 去 Keycloak 註冊帳號(帳密),同一動作建 `HD_USER`(同 ID/Email、配 role)→ 兩邊由建立當下同步,無孤兒。**對照鍵用 ID 或 Email 皆可**(`HdUserRepository` 現成有 `FindByIdAsync`/`FindByEmailAsync`,零 schema 改)。建議註冊時順手把 Keycloak 回傳的 `sub` 也存進 `HD_USER`(將來改名不怕,可切成用 sub 對照,近乎零成本)。

**共用 Auth lib(三塊):** 驗 Keycloak JWT(JWKS/issuer/audience)＋ 身分→HD_USER 解析+`ResolveScopes` ＋ API Key handler(機器對機器,不變)。DicomWeb / 未來 Export 獨立版 / 其他程式都 reference。這也回收了「token 管理焊在 DicomWeb」的問題——DicomWeb 退化成純消費者。

**待同事給的 Keycloak 規格(開工前提):** ①驗 token:issuer、audience、JWKS URL、身分 claim 放哪(`email`/`preferred_username`/`sub`);②註冊 API:URL、請求/回應格式、它自己怎麼認證(service client 憑證)、回應有無 sub;③取 token:標準 OIDC 導頁 or password grant。

**Keycloak 實測(2026-08-06,同事已建置):** token 端點 `POST https://sso.ltcd.tw/realms/hd/protocol/openid-connect/token`(password grant 測試:client `hd-viewer`)。issuer `https://sso.ltcd.tw/realms/hd`、JWKS `.../protocol/openid-connect/certs`(.NET `AddJwtBearer` 設 `Authority=issuer` 自動抓 + 處理 kid 輪替,別寫死公鑰)。**✅ audience 已解決(2026-08-06):** 在 realm `hd` 建 client scope `hd-api`(Default)+ Audience mapper(Included Custom Audience=`hd-pacs`、Add to access token=On)掛到 client;access token `aud` 現帶 `hd-pacs,account`。**嚴格 aud live 測過**(`ValidateAudience=true`+`ValidAudiences=["hd-pacs"]` 通過)→ 直接用嚴格 aud、不留過渡。專用 client `hd-pacs-client`(public、Direct access grants On);新 client 掛 `hd-api` scope 即有 aud。定案 KeycloakOptions:Authority=`https://sso.ltcd.tw/realms/hd`、Audience=`hd-pacs`、ValidateAudience=true。(原坑:Keycloak 預設 aud=account,不加 mapper 開嚴格會 401。)身分鍵用 `preferred_username`(→HD_USER.ID),**別用 email**(此 realm email 佔位 `@example.com`、`email_verified=false`)。access 15 分/refresh 30 分。註冊 API=Keycloak Admin REST(需 service client 憑證,契約待同事)。docs 正本 [systems/identity.md](D:\Dev\HyperDigital\docs\systems\identity.md)。

**✅ DicomWeb 已切 Keycloak(2026-08-07/08,部署 .199 整圈驗證):** Admin UI=OIDC 導頁、API JWT=AddKeycloakJwtBearer+OnTokenValidated 查 HD_USER 補 scopes(無對應→401);**退役** JwtIssuer/DevSigningKeyProvider/dev-token/固定管理帳密/HD_USER.PASSWORD 驗證。共用包 `AddKeycloakJwtBearer` 加了 configure callback(HD.Shared `79ee858`)供掛事件。**再+三坑(導頁登入實戰):** ④RP-initiated 登出要 `id_token_hint`→**SaveTokens=true 必開**(Keycloak 報 Missing parameters: id_token_hint);⑤**DefaultChallengeScheme 別設 OIDC**(未登入開受保護頁會跳過自家登入卡直彈 Keycloak;讓 cookie 預設 challenge 導 LoginPath,OIDC 只由 login 端點明確 Challenge);⑥Keycloak client 的 **Valid post logout redirect URIs 設 `+`**(沿用 redirect URIs;留特定網址會漏站台→Invalid redirect uri)。**工具已更新(2026-08-08,HD.Pacs.DicomWeb `f033af4`→`4e93682`)**:ApiTest/TestClient 改 API Key 或 Keycloak password grant;TestClient 帳號欄貼 hdp_ 直接當 key、登入即打 /me 驗證(壞 key/無 HD_USER 不再假成功);Smoke 依 /me scopes 決定跑/SKIP,**13/13 全綠實測(.199)**。**帳密路已打通(2026-08-09)**:`hdtest`=首個雙邊帳號(HD_USER ID=hdtest、ROLES=[1] admin、email=hdtest@hyperdigital.biz 兩邊一致);password grant→/me 200 實證。新帳號照此模式兩邊建,直到 provisioning 雙寫。**groups claim 同日加**:`hd-api` scope 掛 Group Membership mapper(claim=groups、Full path Off)→掛 hd-api 的 client 全帶;DicomWeb /me 回傳(`782ed6f` 部署 .199)。groups=顯示/分流用,授權仍查 DB。剩:Viewer 隨新版切。

**⚠️ http 內網站接 OIDC 導頁登入的三坑(2026-08-07 主控台部署 .191 實戰,之後每個產品都會踩):** ①correlation/nonce cookie 預設 Secure→http 站台瀏覽器拒收→Correlation failed(localhost 是瀏覽器特例,本機測不出)→`CorrelationCookie/NonceCookie.SecurePolicy=SameAsRequest`+`SameSite=Lax`;②回跳預設 form_post→https 的 Keycloak POST 到 http 本站,Chrome 攔「提交的資訊未受到保護」且跨站 POST 不帶 Lax cookie→`ResponseMode=OpenIdConnectResponseMode.Query`;③.NET 9+ 偵測到 Keycloak 支援 PAR 就自動用(導頁帶 request_uri)→**sso.ltcd.tw 的 PAR 路徑 502**(一般 auth 參數路徑正常)→`PushedAuthorizationBehavior.Disable`。上 https(反代)後 ①② 可回預設,③ 看同事主機修沒修。**SSO 主機不穩症狀**:節點死掉但黏著 session 沒摘→帶舊 sso.ltcd.tw cookie 的瀏覽器穩定 502、無痕正常→清該站 cookie 解;待回報同事。

**🔑 Viewer 切 Keycloak = 雙軌,提前做但不替換(2026-08-17 決策):** 醫院多為封閉網路、連不到外部 sso.ltcd.tw(看片端跑醫師個人電腦、連醫院內部主機),所以**之後會在各醫院封閉網路內部自建 Keycloak SSO——但目前還沒架**。使用者定調:**登入這塊可以提前先做,但還不能替換原本的方式**。→ 實作成雙軌:新 Keycloak 路徑(Authority 指院內 SSO 位址、由設定決定)與**既有 WebApi 帳密登入並存**,設定切換,院內 SSO 到位的醫院才開。現行路徑=`LoginForm.CheckUser` → `imageViewerManager.webApiClient.LoginWithCredentialsAsync(userID, password, accessKey)` → POST `{DownloadHost}/api/v2.0/user/login` 驗 `HD_USER`,回 `access`(→`AccessDefinition`)+`userInfo`(→`LoginSession`),同一組帳密也登 `apiClient`;accessKey 依 Mode = stationViewer/qualityControlViewer/mammoViewer。現場全部醫院都靠這條,必須維持預設可用。AuthZ 不變(仍查 DB)。**同一個封閉網路根因也卡住** [[project_viewer_license]] 的簽發(REQ-015)與「醫院端裝唯讀主控台」——院內 SSO 落地後 OIDC 登入那塊會一併解掉。

相關:[[reference_dicomweb_auth]]、[[project_dicomweb_apikey_consolidation]]、[[project_req003_export_webapi]]、[[project_hd_admin_console]]、[[project_viewer_license]]。
