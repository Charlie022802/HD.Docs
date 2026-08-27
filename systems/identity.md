# 身分 / 認證（Keycloak SSO + API Key）

**目標模型（2026-08-27 起）**：AuthN 與 **AuthZ 都交 Keycloak**——token 同時證明「你是誰」與「你能做什麼」，
各服務**不再回頭查 DB**。見下節。

> 舊的目標模型是「AuthN 交 Keycloak、AuthZ 查 `HD_USER`/`HD_ROLE.ACCESS`」，本文件後半多處仍是那個寫法，
> 那是決策前的紀錄，已逐段標註。**機器憑證（API Key）不在此列**，它的授權仍然是本地的。

**進度**：主控台（.191:5200，2026-08-07）、**DicomWeb（.199:5080，2026-08-07/08）**、**Export API（.199:5090，2026-08-18，`0.1.0-alpha.11`）** 皆已切完；dev-token/自鑄 token 全退役。剩 Viewer（見下）與 provisioning API（待同事契約）。

> **Export 的 MultiScheme 是照 DicomWeb 抄的**，三處值得注意：①`Keycloak.Authority` 走 `/etc/hd-export/keycloak.env` 而非 appsettings（各院之後自建 Keycloak，理由見 [deployment.md](deployment.md)「設定要放哪」）②沒設 Authority 就只收 API Key、不註冊 JWT scheme，服務照常運作 ③呼叫端是純前端時**還需要 CORS**，且要 expose `Content-Disposition`，否則前端讀不到下載檔名。

## 2026-08-27 定案：Keycloak 是唯一正本，`HD_USER` 退場

**決策**：使用者的**身分與角色全部交給 Keycloak**，HDPACS 不再存帳號、**也不再存授權**。
`HD_USER` 連同 `HD_USER_CONFIG`、整個 `report` schema 一併退場。
本地只留一張**唯讀投影表**（`HD_IDENTITY_MIRROR`）供查詢與備份，**絕不參與授權判斷**。

> **本節取代同日稍早的「`HD_PRINCIPAL` 三張表」版本。** 那版把授權留在本地，理由是
> `HD_ROLE.ACCESS` 屬產品領域知識。**在「報告與看片端都要拆成獨立系統」確立之後這個理由不成立**——
> 它們看不到 HDPACS 的 `HD_ROLE`。當時反對「授權進 Keycloak」的論點（報告的簽核權與 HDPACS 的
> QIDO 權會混成一坨）也**站不住**：那是 realm roles 的全域命名空間才有的問題，
> 用 **client roles** 天然就分開了。

### 成立的前提（都已拍板）

| 前提 | 影響 |
|---|---|
| **hd-web-server 淘汰** | `HD_USER.PASSWORD` 的最後一個消費者消失 |
| **報告換成全新系統**，`report` schema 淘汰 | 5 條 FK 消失，含最硬的「報告簽署醫師」（法定病歷） |
| **看片端重新處理** | `VW_KEY_IMAGE`／`VW_OBJECT_PR` 2 條 FK 隨之處理 |
| `MAP_JOB.HD_USER_UUID` 判定為不重要 | 改存快照、去 FK |

`HD_USER` 原本被 **12 條 FK** 指著，上述決策清掉全部 12 條。
**所以「能不能拔」不是技術問題，是這四件事有沒有拍板——少一件就破功。**

**不受影響的**：主 PACS 九支服務、日誌平台、HD.Animal。它們認 AE Title 或 API Key，不碰使用者。

### 授權怎麼放：client roles + composite roles

Keycloak 原生就有對應物，不需要自己發明：

| 現在 | 換成 |
|---|---|
| `ScopeCatalog` 的一個 scope（`dicomweb.query`） | **client role**（掛在 client `hd-pacs` 底下） |
| `HD_ROLE`（一個職務 = 一組 `ACCESS`） | **composite role**（展開成一堆 client roles） |
| `HD_USER.ROLES` → join `HD_ROLE.ACCESS` → `ResolveScopes` | **token 直接帶展開後的完整清單** |

Keycloak 會自動把 composite 展開進 token，各服務拿到的就是最終 scope 清單，**一次 DB 查詢都不用**。
`HD_ROLE` / `HD_GROUP` 隨之退場。

```
resource_access.hd-pacs.roles    = [dicomweb.query, dicomweb.retrieve, export.create]
resource_access.hd-report.roles  = [report.sign, report.draft]
```

### 四個必須遵守的約束

1. **一定用 client roles，不要用 realm roles。** realm 是同事在管的；權限掛在我們自己的 client 底下，
   跟他的訂閱 roles 井水不犯河水。**這是「正本住在別人家」唯一有效的隔離手段。**
2. **`ScopeCatalog` 要留在程式碼裡當共同語言。** 因為 **API Key 那條路仍然是本地的**——
   儀器、Export worker 用 `hdp_…` 長期憑證走 `HD_API_KEY` + `ScopeCatalog` 算 scope，不經過 Keycloak。
   於是會有兩個授權來源，**它們必須產出一字不差的相同 scope 字串**。
   程式碼那份當正本，由 `HD.Identity` 同步到 Keycloak 的 client roles。
3. **`hdUserUuid` 由我們的介面產生。** 既然建立使用者的介面是我們寫的，UUID 就在那裡生成並寫進
   Keycloak attribute，**不需要跟同事談任何回寫契約**。只有「從訂閱系統自行註冊」的人沒有，
   那種第一次登入時由服務端補生成並寫回（我們會有 `manage-users`）。
   **必須設成 admin-only attribute**——使用者能自助改它 ＝ 能冒充別人的歷史紀錄。
4. **DB 裡的 proc 要改。** `site_scope_for_user(user_id)` 現在讀 `HD_USER.OTHERS ->> 'siteCode'`，
   `HD_ROLE_RBAC_functions` 那六支也在 DB 裡跑。權限搬走後這些讀不到東西，
   要改成由 C# 把 scope／siteCode 當參數傳進去。**這是實質工作量，不是零成本。**

### 四個要接受的代價

| 代價 | 說明 |
|---|---|
| **撤權有延遲** | 改權限／停用帳號後，那個人在 access token 到期前（現在 15 分）仍是舊權限。**這讓驗證變棘手——停用後馬上測「還進得去」不代表沒生效**，要等過期或強制 logout 才有鑑別力 |
| **token 變大** | composite 展開後每個 scope 都進 token。幾十個沒事，上百個要小心——**nginx proxy buffer 502 那個坑會回來**（見下方坑⑨，已加大過但 buffer 有限） |
| **「誰有這個權限」不能 SQL 查** | 見下節 |
| **Keycloak 是單點，備份責任變重** | 全部身分與權限都在那裡，沒有本地 fallback。院內自架時每間醫院都要顧它的 DB 與備份 |

### 唯讀投影表 `HD_IDENTITY_MIRROR`

**為什麼不能直接查 Keycloak 的資料庫**（它是有 DB 的，但不該查）：

1. **那是別人家的 DB。** 在同事的機器上，跨 DB 沒有 join。
2. **schema 不保證穩定。** Keycloak 內部表是實作細節，跨大版本會變、啟動時自動跑 migration。
   今天寫的查詢升版後可能**靜默錯**——查得出結果，只是結果不對。
3. **composite 展開要自己遞迴。** 「誰有 `dicomweb.query`」大部分人是透過 composite 或 group 繼承來的，
   自己寫遞迴 CTE 等於**重寫 Keycloak 的權限計算邏輯**。

**Admin API 有端點但有尖角**：`GET /admin/realms/{realm}/clients/{id}/roles/{role}/users`
**只回直接指派的，不含 composite 與 group 繼承** —— 回 200、清單看起來合理，但少了一大半人。
正確做法是撈全部使用者逐一取 effective roles 再比對，人一多就很慢。

所以本地留一張投影：

```
HD_IDENTITY_MIRROR   hdUserUuid / username / display_name / email / enabled
                     roles[]（展開後的完整 scope 清單）/ synced_at
```

由 `HD.Identity` 在指派權限時順手更新，另加定期全量 sync 校正。
**它一份解掉兩個代價**：「誰有這個權限」變回一句 SQL，同時也是「Keycloak 是唯一正本、attribute 掉了
就沒有第二份」的那份保險。

> **一條不能破的線：投影表永遠不參與授權判斷。**
> 一旦有人為了方便寫了「查 mirror 拿權限」，架構就退化成「本地是正本」，兩份資料要同步的老問題全部回來
> ——而且很難察覺，因為平常兩邊是一致的，**只在漂移的那一刻出錯**。
> 建議直接用程式碼結構擋住：**mirror 的 repository 放在查詢用的組件裡，
> 授權路徑（`OnTokenValidated`）根本拿不到它。**

### 不要再談「請同事的系統也呼叫我們的 API」

**這個契約 2026-08-06 定過，從來沒有發生**（見下方 Provisioning 段）。再談一次會再失敗一次，理由是結構性的：

- 註冊是他產品的**核心流程**；要他加一個同步呼叫，等於他的註冊成功與否綁在我方服務的可用性上。
- **失敗了算誰的？** 我方掛掉時他要 retry 還是放行？放行＝資料漂移，擋住＝他的註冊壞掉。
  他理性的做法是 fire-and-forget，而那等於沒有保證。
- 這是分散式雙寫，沒有免費的正確解。

**而且入口本來就已經集中了——集中在 Keycloak，只是那個點不在我們手上。**
他註冊寫進 Keycloak，我們的介面也寫進 Keycloak，**寫的是同一本**。
想要「有人註冊時立刻知道」，Keycloak 的機制（Event Listener SPI、custom registration flow）
都要**部署東西到他的 Keycloak 上**，又回到要他配合。剩下的就是 Admin Events 輪詢，或者 JIT。

### 該向同事要的三件事（給權限，不是改流程）

| 要的東西 | 為什麼他沒理由拒絕 |
|---|---|
| `hd-identity-admin` **confidential client + service account roles** | 開個 client 給權限，不動他任何流程 |
| `hdUserUuid` 設成 **admin-only** attribute | 這是安全性修補（使用者能自改＝能冒充別人的歷史紀錄） |
| client `hd-pacs` 底下的 roles 命名空間**歸我們管** | 我們自己的 client，跟他的訂閱 roles 不衝突 |

service account 要掛的 `realm-management` 角色：`view-users`／`query-users`（列出搜尋）、
`manage-users`（建立／修改／停用）、`view-realm`（讀 roles）、`view-events`（之後稽核頁拉登入事件）。
secret 放 `/etc/hd-admin-console/keycloak.env`，**不要放 appsettings**——preserve 會擋住。

### `HD.Identity`：唯一碰 Admin API 的地方

> **實作進度（2026-08-27）：核心層與介面已完成，尚未對真實 Keycloak 驗證**（缺 service account secret）。
>
> - **位置＝`HD.Shared/src/HD.Shared.Identity`**（不是獨立 repo）。相依方向刻意是 **Identity → Auth，不可反向**：
>   投影表的 repository 住在 Identity（管理路徑），而授權路徑（`HD.Shared.Auth` 的 `OnTokenValidated`）
>   不參考它 —— **「投影表不參與授權判斷」這條線是靠專案相依擋住的，不靠人自律**。
> - 型別：`KeycloakAdminOptions`（含 Admin base 的組法）／`KeycloakAdminTokenProvider`（singleton，token 快取）／
>   `KeycloakAdminClient`（scoped，只做 HTTP+JSON）／`IdentityService`（規則）／
>   `IdentityMirrorRepository`＋`IdentityMirrorSync`（投影）。
> - **DB**：`db_update_v2.0.40.sql` 建 `HD_IDENTITY_MIRROR`（`SCOPES` 上有 GIN 索引供「誰有這個權限」）。
> - **主控台**：`/identity` 新頁，與既有的 `/users` **並存**。
>   `/users` 管 `HD_USER`（**目前實際生效的授權來源**），`/identity` 管 Keycloak（新架構的正本）。
>   等執行順序第 5 步（權限改讀 token）完成，`/users` 才退場。
> - **沒有 secret 時整頁降級**成「要跟同事要什麼」的說明，主控台其他功能照常可用。
> - **測試 40 條，且做過突變驗證**：把實作逐條弄壞（attributes 改成覆寫、Admin base 接錯、
>   識別碼每次重產、角色改成全刪再全加、只抓第一頁、不濾 service account、
>   生效權限改看直接指派、token provider 改成 scoped…）確認測試都會紅。
>   綠燈只證明沒壞，突變才證明測得到。
> **執行順序第 5 步（權限直接讀 token）也已實作，但預設關閉（2026-08-27）。**
>
> - `TokenScopeResolver`（`HD.Shared.Auth`）從 `resource_access.{RoleClientId}.roles` 取 scope，
>   **產出與 `ScopeResolver.FromAccessList` 同一種東西**（scope 字串），所以下游授權 policy 一行都不用改。
> - 開關 `Keycloak:ScopesFromToken`（**預設 false**）＋ `Keycloak:RoleClientId`（預設 `hd-pacs`）。
>   設定走環境變數，理由同 `JitProvisionUsers`。DicomWeb／Export／主控台三支都接好了。
> - **只認 client roles，不認 realm roles**，即使 realm 裡有同名角色也不採用（有測試釘住）。
> - **這條路徑沒有「帳號已停用」那一道，而且是對的**：停用交給 Keycloak，停用的人換不到 token。
>   留一份本地停用旗標會變成第二個正本。代價是撤權延遲＝access token 存活期。
> - 零 scope 時會 log 出**為什麼**：沒有 `resource_access`（client scope 沒掛／`MapInboundClaims` 沒關）、
>   權限被建成 realm role、`RoleClientId` 對不上。這三種的外顯症狀完全一樣（登入成功、每個動作 403），
>   不指名的話只能去 Keycloak 一層層翻。
> - 17 條測試，同樣做過突變驗證（不過濾 ScopeCatalog／不分 client／混入 realm role／
>   不解釋原因／少驗一層 `ValueKind`）—— 最後那條原本就是真的缺陷，是測試先抓到的。
>
> **翻開關的順序不能顛倒**：先「同步權限清單」把 `ScopeCatalog` 建到 Keycloak → 指派角色 →
> 確認 token 真的帶得到 → 最後才 `ScopesFromToken=true`。順序錯了所有人會變成零權限。
>
> - **還沒做**：對真實 Keycloak 的實測（要 secret）／職務角色的建立介面
>   （`IdentityService.SaveJobRoleAsync` 已經寫好，但頁面上只讀不寫，現階段要在 Keycloak 直接建 composite role）／
>   `siteCode` 的編輯介面（`SetSiteCodeAsync` 同上）。

**介面背後要是一支服務，不要直接在 Blazor 頁面裡打 Admin API。**

```
管理介面 (Blazor，主控台多一頁)
        |
   HD.Identity          <- 唯一碰 Keycloak Admin API 的地方
     |        |            composite 展開、命名規則、hdUserUuid 生成都在這
Keycloak   HD_IDENTITY_MIRROR
 (正本)      (唯讀投影)
```

- 現在：只有管理介面用它
- 之後：DicomWeb／Export／報告系統要管使用者時接它，**不各自接 Admin API**
- 哪天同事願意接：開成 API 即可，**不用重寫**

**四個已知要繞開的坑**（寫 `KeycloakAdminClient` 時）：

1. **Admin base 不是 Authority 接路徑。** `https://sso.hdtech.tw/realms/hd` →
   Admin 是 `https://sso.hdtech.tw/admin/realms/hd/…`，要把 host 與 realm 拆出來重組。直接接會 404。
2. **`PUT /users/{id}` 的 attributes 是整個覆寫，不是 merge。** 只送 `hdUserUuid` 會把其他 attribute
   全清掉——必須先 `GET` 再合併。（跟 `OTHERS` jsonb 那個教訓一模一樣。）
3. **`enabled=false` 不會撤銷已發出的 token**（見上方「撤權有延遲」）。
   要撤 session 得另打 `POST /users/{id}/logout`，但已發出的 access token 仍有效到過期。
4. **service account 自己也是一個 user**（`service-account-hd-identity-admin`），會混在清單裡，要過濾。

另：`search=` 是模糊比對 username／姓／名／email，要精確找帳號得用 `username=xxx&exact=true`。

### 「設定」不要進 Keycloak

Keycloak user attributes 每次登入都會被讀、可能進 token，且只能透過 Admin API 改，
**不適合放使用者的個人偏好**（版面、快捷工具、報告範本那類）。
那些留在各系統自己的 DB、用 `hdUserUuid` 當 key 就好。`HD_USER_CONFIG` 的內容跟著看片端重做走。

### 執行順序（有硬相依）

```
0. v2.0.39 的 ENABLE / EXPIRE_DATE 標記作廢（已佈到 .191，腳本不動、只加追記）
1. HD.Identity 骨架 + KeycloakAdminClient          <- 不需等 secret 就能寫，可立即做
2. 向同事要那三件事（client + attribute + roles 命名空間）
3. ScopeCatalog -> Keycloak client roles 同步；HD_ROLE 轉成 composite roles
4. HD.Shared.Auth 改成「權限直接讀 token」，不再查 DB
5. 看片端改接 Keycloak 登入                        <- 是 6 的前置，整條路的瓶頸
6. hd-web-server 淘汰
7. 報告新系統上線 + 舊報告匯出成不可變快照
8. HD_USER / HD_USER_CONFIG / HD_ROLE / HD_GROUP / report schema 收掉
```

### 舊報告資料（唯一剩下的歷史包袱）

若瑟現有的 `REPORT_SAVED` 是病歷，有法定保存年限。三條路：

| 做法 | 代價 |
|---|---|
| 遷進新系統 | 要帶人員識別過去，mapping 問題整包跟著搬 |
| 舊 HDPACS 唯讀保留 | **`HD_USER` 就拔不掉**，整個計畫在若瑟站台破功 |
| **匯出成不可變快照（PDF／報告文件）** | 人名變成純字串，識別問題徹底消滅 |

**建議第三條。** 舊報告不需要再被程式當結構化資料查詢，只需要調閱得到。
材料是現成的——`REPORT_SAVED` 本來就有 `REPORT_PHYSICIAN_NAME`／`PERFORMING_PHYSICIAN_NAME` 兩個字串快照欄位。

### `HD_ACTIVE_USERS`：debug 殘留，不是分岔項

查證結果：**只存在於若瑟正式機**（2026-08-26 dump），`.191`／`20260811`／`20260720` 三份 dump 都沒有，
`db_update_v2.0.*` 更新鏈從頭到尾沒出現過，**整個 codebase 零引用**（含 hd-web-server）。
已由使用者確認是以前 debug 時多建的。**不用管它**，若瑟拔 FK 時順手 `DROP` 掉即可。
（與 [josef-db-upgrade-plan.md](../josef-db-upgrade-plan.md) 記錄的六個「更新鏈分岔項」不同——那六個至少還有程式在用。）

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

> **2026-08-27 已推翻「不替換」。** hd-web-server 確定淘汰，而它是看片端帳密登入的唯一路徑，
> 所以看片端的 Keycloak 登入從「並存」變成**取代**（見上節執行順序第 5 步，那是整條路的瓶頸）。
> 本節其餘內容（封閉網路根因、OIDC 九坑）仍然有效。

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

> **2026-08-27：JIT 的「建 `HD_USER`」整段作廢，但問題意識仍然有效。**
> 新架構下權限直接從 token 讀，**沒有對應 `HD_USER` 就 401 這個症狀從根上消失**，
> 所以不需要「就地建一筆零角色使用者」了。取而代之的是：
> **第一次看到沒有 `hdUserUuid` 的人，補生成一個寫回 Keycloak**（見上節約束 3）。
> 三個坑之中第 1 個（advisory lock）與第 3 個（`ENABLE`／`EXPIRE_DATE`）隨之作廢；
> 第 2 個（不要對 `GROUP_REF` 做 `MIN()` fallback）的教訓仍然值得記住——
> **「取最小值當預設」在權限領域會安靜地挑到最高權限那一個。**
> 以下保留為決策前的紀錄。

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

> **2026-08-27：方向已定。** 訂閱方案就是 Keycloak 的 **composite role**，展開成一組 client roles
> 進到 token。當時說的「group → `HD_ROLE` 映射」不需要了——`HD_ROLE` 本身要退場。
> 契約仍然只有一張對照表（訂閱方案名稱 ↔ composite role 名稱），**待與同事確認**。

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
