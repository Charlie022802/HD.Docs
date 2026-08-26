---
name: project_hd_admin_console
description: HD 後端管理主控台—金鑰/匯出/稽核/裝置授權四大功能+Keycloak登入;已部署.191:5200;http站台OIDC三坑已修
metadata: 
  node_type: memory
  type: project
  originSessionId: 13e6b6ed-984d-4c27-aed8-2170077bfa02
  modified: 2026-08-13T18:39:55.648Z
---

**✅ 第六鏟完成(2026-08-14):`/licenses` 支援線上註冊,已部署 .191 `alpha.3`。** 詳見 [[project_viewer_license]]。看片端會自己把申請寫進 `HD_DEVICE_LICENSE`(DB 當信箱),頁面新增待簽發清單+一鍵簽發(不必上傳檔案)+「本站台的簽發公鑰」可展開。**修掉一個會讓整頁打不開的洞**:`IssuedAt`/`LastIssuedAt` 是非 nullable,pending 列一進來 Dapper materialization 就炸。**打包眉角**:csproj 的 `<Version>` 與 `deploy/hdctl-manifest.json` 的 `version` 是**兩個地方**,上次只 bump 了 manifest(csproj 還停在 alpha.1);`hdpack` 只讀 manifest,但兩邊不同步日後會查不出現場跑的是哪一版。scp 上傳要**明列 tgz 與 .sha256 兩個檔**(PowerShell 不對原生指令做 glob,`*` 不會展開);遠端安裝路徑**不要加引號**(bash 的 `~` 在引號裡不展開)。

**✅ 第五鏟完成(2026-08-14):`/licenses` 裝置授權(第四大功能),已部署 .191 `alpha.2`。** 詳見 [[project_viewer_license]]。要點:**同一份程式碼靠「簽發私鑰檔在不在」自動切換原廠(可簽)/醫院端(唯讀)**,不必維護兩個版本;私鑰在 `/etc/hd-admin-console/license-signing.key`,**必須 chown `hdadmin`**(維持 root 會讀不到而靜默退成唯讀模式,畫面完全看不出原因);scope `admin.licenses` ← `HD_ROLE` 的 `admin.manageLicenses`(比照 `dicomWeb.manageApiKeys`,不隨 admin 區段全給)。**部署改走 hdctl**(`.191` 已是 hdctl 管理):`python hdctl\hdpack.py --publish <framework-dependent publish> --manifest deploy\hdctl-manifest.json` → scp **tgz 與 .sha256 兩個檔** → `sudo /usr/local/bin/hdctl install <tgz>`(**sudo 的 secure_path 不含 /usr/local/bin,要用絕對路徑**)。hdctl 包是 **framework-dependent**(26 檔),與舊 `install.sh` 的 self-contained(354 檔)不可互換。

**✅ 第四鏟完成(2026-08-07):部署 .191:5200 + 整圈驗證通過(`77e0640`→`087f7ed`)。** self-contained linux-x64(.191 不賭 ASP.NET Core runtime)、落 **/opt/hd-admin-console**(/home 下 SELinux 擋 systemd 執行,semanage usr_t)、systemd `hd-admin-console`、deploy/install.sh(自動防火牆、`/etc/hd-admin-console/database.env` 連本機 HDPACS、更新時保留 DB 設定);更新流程=tgz scp 到 `~/deploy-adminconsole` → `sudo bash install.sh`。Keycloak redirect URI 已加 `http://192.168.68.191:5200/*`。**http 站台 OIDC 三坑**(每個接 SSO 的 http 內網站都會踩,詳 [[project_auth_keycloak_plan]]):①correlation/nonce cookie 預設 Secure→改 SameAsRequest+Lax ②回跳預設 form_post→改 ResponseMode=Query ③.NET 9+ 自動 PAR→sso.hdtech.tw 該路徑 502→PushedAuthorizationBehavior.Disable。另修:publish 會帶 appsettings.Development.json(含DB密碼)→csproj CopyToPublishDirectory=Never;Routes.razor `<Layout.MainLayout>` qualified name 坑。**SSO 黏死節點症狀**:帶舊 sso.hdtech.tw cookie 穩定 502、無痕正常→清該站 cookie 解;待回報同事。

**✅ 第一鏟完成(2026-08-06):骨架 + Keycloak SSO 登入整圈驗證通過。** 名稱定案「**HD 後端管理主控台**」(另有前端管理畫面,故加「後端」)。repo `D:\Dev\HyperDigital\HD.AdminConsole`(local git `30fbbf0`,無 remote),Blazor Server SSR + cookie,**登入=標準 OIDC 授權碼+PKCE 導 Keycloak**(使用者**定案 A 導頁案**:「保持導頁,之後做 Keycloak theme,在 Keycloak 修正就好、程式不用動」;棄自家表單 password grant)。品牌:sidebar/登入卡/favicon 用公司鯨魚 logo(`雲智_鯨魚_logo_彩色_256X256.png`,與 DicomWeb 同顆,Logo 資料夾在 `D:\Dev\HyperDigital\Logo`)。client=`hd-pacs-client`、本機 http://localhost:5200。驗過:登入卡→Keycloak 登入(hdtest)→身分頁(preferred_username/sub/email/groups)→**RP-initiated 登出**(SignOut cookie+OIDC,連 SSO 會話一起)。技術眉角:①`[Authorize]` 首頁會**自動 challenge 直接彈 Keycloak**,要登入卡得 AllowAnonymous+頁內 AuthorizeView;②Blazor SSR 元件 qualified name `<Pages.X/>` 不解析會**默默輸出成 HTML tag**(空白頁),用 _Imports+短名;③登出鈕要 `data-enhance-nav="false"` 防 enhanced nav 攔;④Keycloak Valid post logout redirect URIs 用 **`+`**(沿用 redirect URIs)最穩——實測欄位混入不可見字元導致比對永遠失敗;⑤Keycloak User profile 的 firstName/lastName 對「User」情境必填→首次登入被要求補(admin 表單看不出來),Realm settings→User profile 可改。視覺照 DicomWeb Manager(Bootstrap 5.3 CDN+深色 sidebar #1a2535)。

**✅ 第三鏟完成(2026-08-06 晚):稽核紀錄頁+匯出紀錄頁(`99b385e`→`dec5fef`,本機對 .191 實測)—— 三大功能到齊(金鑰/匯出/稽核)。** `/audit`:讀共享事件表,**全欄位過濾**(產品/分類/結果/操作者+類型/動作/對象類型+ID/IP/時間含自訂)+keyset 分頁;產品 badge 同色相;長 ResourceId 顯前 8 碼點開展開。`/exports`:讀 export.EXPORT_JOB 唯讀管理視圖(狀態碼人話 StatusLabel、進度條、錯誤展開;建立/下載屬 HD.Export API/WebExport REQ-010,本頁不做)。UI 眉角:**寬表格 min-width+水平捲動、首欄 sticky**(使用者要求);**Dapper 坑:positional record+DateTimeOffset 會因 DateTime 簽章不符炸 materialization,要 class+屬性**。待:稽核頁併 Keycloak 登入事件(Admin API)、主 PACS connection 事件(P2)後 connection 分類才有資料。

**✅ 第二鏟完成(2026-08-06):API Key 管理搬入主控台(`b80aaff`→`f8533af`),本機對 .191 DB 實測通過。** `/apikeys`(InteractiveServer):清單/建立/編輯/撤銷/一次性金鑰+複製;`Services/ApiKeyAdminService`=**Npgsql 直連 HDPACS HD_API_KEY**(可攜,不綁 EF;驗證規則與 DicomWeb 原版同套);與各服務驗證**同一張表**(主控台發、服務立即可用)。UI 打磨(使用者逐項調):**badge 配色=產品定色相**(DicomWeb 藍/Report 紫/Workitem 青/Export 琥珀,讀淺寫深,刪除紅壓軸)、badge 順序照 ScopeCatalog 目錄序、勾選依產品分組同色相、**用語去黑話**(「儀器 AE」+tooltip,不寫 AE_MAIN/ROUTING_ANONYMISE 表名)。ScopeCatalog 新增 `ProductOf` + DicomWeb 群組順序改「讀→上傳→匯入→刪除」(HD.Shared `779b95f`)。DB:dev 用 appsettings.Development.json(gitignored)連 .191;正式走 `Database__ConnectionString` env。**✅ 授權細化已上線(2026-08-10,`90ba655`;DicomWeb 同步 `c712aa1`)**:OIDC OnTokenValidated 查 HD_USER→ResolveScopes 蓋 cookie claims;/apikeys=admin.api_keys、/audit=admin.audit、/exports=export.read;無 HD_USER=零權限(首頁警告+Forbidden 卡);側欄按權限顯示;**權限異動要重新登入**。角色 1 已補 dicomWeb.manageApiKeys。**DicomWeb 側管理 UI/REST 已下架**(2026-08-07/08 隨 DicomWeb 切 Keycloak 一起;主控台=金鑰唯一管理面)。

原規劃範圍:集中的內部管理網頁,把散落各產品的「管理平面」收成一支獨立程式。系統全貌圖 artifact: https://claude.ai/code/artifact/34bbfc5f-2c7c-4901-8888-b84b9aa8700e

**要收哪些:**
1. **API Key 管理集中**——使用者要把 key 管理搬離 DicomWeb,一處發/撤/配 scope,涵蓋 DicomWeb/Export/… 各產品;DicomWeb 從此只驗不管。沿用這輪收斂的 `ScopeCatalog`+`ApiKeyService`(要抽成共用 Auth 套件),scope 目錄建議加「所屬產品」欄以分組。見 [[project_dicomweb_apikey_consolidation]]。
2. **DICOM / 結構化 log 檢視**(新需求)——HDPACS 沒有網頁能看 DICOM 相關 log。定位討論中(見下)。
3. **Export job 紀錄查詢**(2026-08-06 新增):HD.Export 的打包/燒錄 job 紀錄檢視(誰建的/狀態/歷史)。**直接讀 `export.EXPORT_JOB` 表(同顆 HDPACS DB),不經 HD.Export API、不用 API Key** —— HD.Export 保持純機器 API,人看紀錄走主控台。

**排障入口定位(2026-08-06 使用者確認):「出事第一站」= LoggingPlatform(.195),不是主控台。** 現場/服務人員不管哪個產品出問題都先去 LoggingPlatform 按產品過濾技術日誌;主控台的 job/連線紀錄檢視是**管理視圖**(歷史/狀態/誰建的),非排障入口。前置:HD.Export 要接 HD.Shared.Logging(現只進 journald)+ 確認 hd-media-package worker log 有送(燒錄失敗關鍵在 worker),見 todo。
4. (未來 P2)使用者 provisioning(打 Keycloak 註冊 API,見 [[project_auth_keycloak_plan]])+ 稽核查詢。

**log 檢視的設計方向(討論中,2026-08-06):** 使用者覺得 DicomWeb 的稽核 viewer 呈現好、LogServer(HawkLog/.195)呈現各產品 log 不佳。釐清=**兩種 log**:①技術日誌→HawkLog(通用水管,除錯,不動)②結構化領域/稽核事件→各產品寫進 DB 稽核表(DicomWeb `HD_USER_AUDIT_LOG` 那種 typed 事件,才好呈現)。**結論方向**:各服務只「寫」自己的結構化事件(owns schema)、**呈現集中到本管理主控台**當「全產品結構化事件統一檢視」(讀各產品稽核表,都在同一 HDPACS DB,不各服務各做 viewer、也不塞進 HawkLog)。**待使用者定**:稽核事件存法 **A 單一共用表+`product`欄(建議,HD_USER_AUDIT_LOG 已夠通用,加 source 欄)** vs **B 各產品各表**。定案後各產品經 HD.Shared 打同一套 typed 事件([[project_shared_logging]])。

**待釐清:** log 要看哪一層(PACS DICOM 活動 vs 稽核 vs HawkLog 技術日誌);主控台自己的登入(過渡 cookie/角色,未來接 Keycloak);部署為 .191 獨立單位。docs 正本 [systems/admin-console.md](D:\Dev\HyperDigital\docs\systems\admin-console.md)。

**2026-08-26 加了右上角 ⓘ「系統資訊」(alpha.8)**:版本／建置時間／執行環境、.NET／OS／主機／
已運行／時區、連到哪個 DB／SSO 指哪／監聽位址,三組 16 項,附「複製全部」。
用途是**排障的第一句話** —— 現場說「怪怪的」就請對方按複製貼過來。DB 只顯示
`使用者@主機:埠/資料庫`,**不含密碼**。

**Blazor render mode 的坑(做這個功能時踩到,之後在 topbar 加任何互動功能都會再踩)**:
`MainLayout` 是**靜態渲染**的(只有 `Pages/*.razor` 各自標 `@rendermode InteractiveServer`),
所以掛在 layout 或其子元件上的 `@onclick` **永遠不會被執行**、`@ref` 也**跨不過**靜態→互動的邊界。
症狀是「按鈕點得下去但什麼都沒發生」。做法:需要互動的元件**自己標 `@rendermode`**
(靜態父元件可以渲染互動子元件),父子溝通走 JS 事件 + `DotNetObjectReference` 回呼,不要用 `@ref`。

**複製到剪貼簿會撒謊**:http 站台走 `execCommand` 備援,而 textarea 掛在 `document.body` 時
會被 Bootstrap modal 的焦點陷阱擋住選取範圍 —— **Chrome 仍可能回 `true`**,變成
「畫面說已複製、剪貼簿是空的」。比失敗更糟因為它撒謊。修法:掛進開啟中的 modal 內、
不要移出畫面、**先確認真的選到東西再回報成敗**。

**部署已改走 hdctl**(`install.sh` 是更早的做法):`bash deploy/pack-adminconsole.sh` 打包,
`Keycloak__Authority` 與 DB 都放 `/etc/hd-admin-console/*.env`,appsettings 留空。
**Authority 沒設會啟動失敗**(刻意:唯一入口就是 OIDC);副作用是好的——
**「服務 active」本身就成了 env 有被讀到的證據**。
