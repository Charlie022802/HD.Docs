# HD 後端管理主控台（HD.AdminConsole）

**一句話**：集中的內部管理網頁，把散落各產品的「管理平面」收成一支獨立程式，**已部署 .191:5200**。

- **性質**：獨立 Blazor Server（技術沿用 DicomWeb Admin UI 風格；鯨魚 logo）。**不是**主 PACS(HD.Net10) 內建。
- **repo**：`D:\Dev\HyperDigital\HD.AdminConsole`（GitHub Charlie022802/HD.AdminConsole）。
- **狀態**：2026-08-07 **三大功能上線 .191**（API 金鑰 / 匯出紀錄 / 稽核紀錄），Keycloak SSO 登入整圈驗證通過。

## 現況（已完成）
- **登入**：Keycloak SSO（OIDC 授權碼 + PKCE 導頁，client `hd-pacs-client`）＋本地 cookie 會話；RP-initiated 登出。
- **/apikeys**：API Key 集中管理（發／撤／配 scope，Npgsql 直連 HDPACS `HD_API_KEY`，與各服務驗證同一張表）。
- **/exports**：匯出工作唯讀管理視圖（讀 `export.EXPORT_JOB`，狀態人話／進度條／錯誤展開）。
- **/audit**：全產品稽核事件（共享事件表 `HD_USER_AUDIT_LOG`，全欄位過濾＋keyset 分頁）。
- 主控台自身操作也寫事件表（product=admin-console）。
- **右上角 ⓘ 系統資訊**（2026-08-26，alpha.8）：版本／建置時間／執行環境、.NET／OS／主機／已運行／時區、
  連到哪個 DB／SSO 指哪／監聽位址，共三組 16 項，附「複製全部」。
  **用途是排障的第一句話** —— 現場說「怪怪的」時請對方按複製貼過來，不必來回問好幾輪。
  **不放機密**：DB 只取 `使用者@主機:埠/資料庫`，密碼連碰都不碰。

## 部署（.191）
**現在走 hdctl**（`deploy/install.sh` 是更早的做法，已不用）。

- 打包：`bash deploy/pack-adminconsole.sh`（publish → 密碼檢查 → 設定檔可載入檢查 → hdpack）。
  **framework-dependent**（`--self-contained false`）：manifest 的 exec 是 `dotnet app/xxx.dll`，
  被執行的是機器上的 dotnet，hdctl 會自己找。
- 安裝：`sudo /usr/local/bin/hdctl install ~/hd-adminconsole-<版本>.tgz`。
- 落 `/home/HD/service/hd-adminconsole`，systemd `hd-admin-console`、port **5200**。
- **設定放 env 不放 appsettings**：`/etc/hd-admin-console/database.env`（DB）與
  `/etc/hd-admin-console/keycloak.env`（`Keycloak__Authority`）。
  appsettings 裡兩者都留空——各醫院之後會自建院內 Keycloak，位址每間都不一樣。
- **Authority 沒設會啟動失敗**（刻意）。這支的唯一入口就是 OIDC，留空等於沒人進得來；
  不擋的話症狀是「服務 active、健檢過、但一按登入就 500」（`AddOpenIdConnect` 會把
  MetadataAddress 組成不合法的 URL，首次解析 options 才丟例外）。啟動就死掉好排查得多。
  副作用是好的：**「服務 active」本身就成了 env 有被讀到的證據**。
- Keycloak client 需含 redirect URI `http://192.168.68.191:5200/*`（post-logout 用 `+` 沿用）。

## http 站台 OIDC 三坑（2026-08-07 實戰，之後每個接 SSO 的 http 內網站都會踩）
1. **correlation/nonce cookie 預設 Secure** → http 站台瀏覽器拒收 → Correlation failed（localhost 是特例測不出）。修：`SecurePolicy=SameAsRequest` + `SameSite=Lax`。
2. **回跳預設 form_post** → https 的 Keycloak POST 到 http 本站，Chrome 攔「提交的資訊未受到保護」且跨站 POST 不帶 Lax cookie。修：`ResponseMode=query`。
3. **.NET 9+ 自動用 PAR** → sso.hdtech.tw 的 PAR 路徑 502（一般 auth 參數路徑正常）。修：`PushedAuthorizationBehavior.Disable`。
- 另：SSO 主機節點死掉時**帶舊 session cookie 的瀏覽器會穩定 502、無痕正常**（黏著 session 沒摘）→ 清 sso.hdtech.tw cookie 即恢復；症狀回報同事。
- 另：publish 產物預設會帶 `appsettings.Development.json`（含 DB 密碼）→ csproj `CopyToPublishDirectory=Never` 排除。

## Blazor render mode 的坑（2026-08-26 做系統資訊時踩到）

**`MainLayout` 是靜態渲染的** —— 只有 `Components/Pages/*.razor` 各自標了
`@rendermode InteractiveServer`。所以：

- 掛在 layout（或它的子元件）上的 `@onclick` **永遠不會被執行**，
- `@ref` 也**跨不過**靜態→互動的邊界，父元件拿不到子元件的參考。

症狀是「按鈕點得下去、但什麼都沒發生」，看起來像事件沒綁到，實際上是元件根本沒有互動能力。

**做法**：讓需要互動的元件**自己標 `@rendermode InteractiveServer`**（靜態父元件可以渲染
互動子元件），需要父子溝通就走 JS 事件 + `DotNetObjectReference` 回呼，不要用 `@ref`。
系統資訊視窗就是這樣做的：按鈕只用 `data-bs-target` 開啟，重取資料由 dialog 自己監聽
`show.bs.modal` 完成。

**之後在 topbar 加任何互動功能（通知、主題切換…）都會再踩一次。**

## 複製到剪貼簿會撒謊（2026-08-26）

http 站台不是安全上下文，`navigator.clipboard` 不可用，退回 `document.execCommand`。
原本把 textarea 掛在 `document.body`，但 **Bootstrap modal 的焦點陷阱**會把焦點鎖在 modal 內，
掛在 body 的 textarea 取不到選取範圍 —— 而 **Chrome 在這種情況 `execCommand` 仍可能回 `true`**。

結果是「畫面說已複製、剪貼簿卻是空的」。**比單純失敗更糟，因為它撒謊**：使用者會去貼，
貼出空的，然後懷疑是別的地方壞了。

三處修正：①掛進目前開啟的 modal 內 ②不要用 `top:-1000px` 移出畫面（部分瀏覽器不讓畫面外
元素取得選取範圍）③**先確認真的選到東西再回報成敗**。另外補上失敗提示——沒有回饋的話
使用者只會覺得按鈕壞了；值本身是 `user-select:all`，可以直接手選。

## 待辦
- 稽核頁併 Keycloak 登入事件（Admin API 拉 events、UUID→帳號）。
- 主 PACS SCP 打 connection 事件（LoggingPlatform P2 慣例）→ 稽核頁「連線」分類有資料。
- ~~授權細化~~（✅ 2026-08-10 上線：登入時查 HD_USER→scopes 進 cookie claims；/apikeys=`admin.api_keys`、/audit=`admin.audit`、/exports=`export.read`；無 HD_USER＝零權限；**權限異動需重新登入**。DicomWeb 管理頁同步細化）。
- ~~DicomWeb 側金鑰管理 UI/REST 下架~~（✅ 2026-08-07/08 完成，隨 DicomWeb 切 Keycloak 一起；主控台成為金鑰唯一管理面）。
- （P2）使用者 provisioning（對接 [Keycloak](identity.md)）。

相關：[identity.md](identity.md)、[dicomweb.md](dicomweb.md)、記憶 project_hd_admin_console / project_auth_keycloak_plan。
