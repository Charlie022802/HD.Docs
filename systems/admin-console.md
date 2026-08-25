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

## 部署（.191）
- `deploy/install.sh`：**self-contained** linux-x64（.191 不賭 ASP.NET Core runtime）；落 `/opt/hd-admin-console`（**/home 下 SELinux 擋 systemd 執行**，semanage usr_t）；systemd `hd-admin-console`、port **5200**、自動放行防火牆；DB 連線在 `/etc/hd-admin-console/database.env`（本機 HDPACS）。
- 更新流程：本機 publish＋tgz → scp 到 `~/deploy-adminconsole` → `sudo bash install.sh`（保留 DB 設定）。
- Keycloak client 需含 redirect URI `http://192.168.68.191:5200/*`（post-logout 用 `+` 沿用）。

## http 站台 OIDC 三坑（2026-08-07 實戰，之後每個接 SSO 的 http 內網站都會踩）
1. **correlation/nonce cookie 預設 Secure** → http 站台瀏覽器拒收 → Correlation failed（localhost 是特例測不出）。修：`SecurePolicy=SameAsRequest` + `SameSite=Lax`。
2. **回跳預設 form_post** → https 的 Keycloak POST 到 http 本站，Chrome 攔「提交的資訊未受到保護」且跨站 POST 不帶 Lax cookie。修：`ResponseMode=query`。
3. **.NET 9+ 自動用 PAR** → sso.hdtech.tw 的 PAR 路徑 502（一般 auth 參數路徑正常）。修：`PushedAuthorizationBehavior.Disable`。
- 另：SSO 主機節點死掉時**帶舊 session cookie 的瀏覽器會穩定 502、無痕正常**（黏著 session 沒摘）→ 清 sso.hdtech.tw cookie 即恢復；症狀回報同事。
- 另：publish 產物預設會帶 `appsettings.Development.json`（含 DB 密碼）→ csproj `CopyToPublishDirectory=Never` 排除。

## 待辦
- 稽核頁併 Keycloak 登入事件（Admin API 拉 events、UUID→帳號）。
- 主 PACS SCP 打 connection 事件（LoggingPlatform P2 慣例）→ 稽核頁「連線」分類有資料。
- ~~授權細化~~（✅ 2026-08-10 上線：登入時查 HD_USER→scopes 進 cookie claims；/apikeys=`admin.api_keys`、/audit=`admin.audit`、/exports=`export.read`；無 HD_USER＝零權限；**權限異動需重新登入**。DicomWeb 管理頁同步細化）。
- ~~DicomWeb 側金鑰管理 UI/REST 下架~~（✅ 2026-08-07/08 完成，隨 DicomWeb 切 Keycloak 一起；主控台成為金鑰唯一管理面）。
- （P2）使用者 provisioning（對接 [Keycloak](identity.md)）。

相關：[identity.md](identity.md)、[dicomweb.md](dicomweb.md)、記憶 project_hd_admin_console / project_auth_keycloak_plan。
