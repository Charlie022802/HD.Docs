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

**已落地 `.191`（2026-08-27，`db_update_v2.0.40`）。** 驗的是結構不是「表在不在」：
10 個欄位、`SCOPES` 的索引**實際型別是 `gin`**、`USERNAME` 是 unique、`@> ARRAY['dicomweb.read']`
查得動。程式碼那端 `ExistsAsync()` 是每次開頁面檢查，所以表建好之後不必重新部署主控台。

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
| `hd-pacs-identity-admin` **confidential client + service account roles** | 開個 client 給權限，不動他任何流程 |
| `hdUserUuid` 設成 **admin-only** attribute | 這是安全性修補（使用者能自改＝能冒充別人的歷史紀錄） |
| client `hd-pacs` 底下的 roles 命名空間**歸我們管** | 我們自己的 client，跟他的訂閱 roles 不衝突 |

service account 要掛的 `realm-management` 角色：`view-users`／`query-users`（列出搜尋）、
`manage-users`（建立／修改／停用）、`view-realm`、
**`view-clients`（找得到 client）、`manage-clients`（建立 client roles）**、`view-events`（之後稽核頁拉登入事件）。
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

**五個已知要繞開的坑**（寫 `KeycloakAdminClient` 時）：

1. **Admin base 不是 Authority 接路徑。** `https://sso.hdtech.tw/realms/hd` →
   Admin 是 `https://sso.hdtech.tw/admin/realms/hd/…`，要把 host 與 realm 拆出來重組。直接接會 404。
2. **`PUT /users/{id}` 的 attributes 是整個覆寫，不是 merge。** 只送 `hdUserUuid` 會把其他 attribute
   全清掉——必須先 `GET` 再合併。（跟 `OTHERS` jsonb 那個教訓一模一樣。）
3. **`enabled=false` 不會撤銷已發出的 token**（見上方「撤權有延遲」）。
   要撤 session 得另打 `POST /users/{id}/logout`，但已發出的 access token 仍有效到過期。
4. **service account 自己也是一個 user**（`service-account-hd-pacs-identity-admin`），會混在清單裡，要過濾。
5. **改了 service account 的角色之後，要重啟服務才會生效。** token 是快取的（約 15 分鐘），
   而 Admin API 是看 token 裡的角色。更麻煩的是**權限不足回的是 200 加空陣列不是 401**，
   所以 401 重試那條路不會觸發、快取不會自動作廢 —— 症狀變成「權限明明給了卻還是說找不到 client」。
   2026-08-27 實際踩到。

另：`search=` 是模糊比對 username／姓／名／email，要精確找帳號得用 `username=xxx&exact=true`。

### 「設定」不要進 Keycloak

Keycloak user attributes 每次登入都會被讀、可能進 token，且只能透過 Admin API 改，
**不適合放使用者的個人偏好**（版面、快捷工具、報告範本那類）。
那些留在各系統自己的 DB、用 `hdUserUuid` 當 key 就好。`HD_USER_CONFIG` 的內容跟著看片端重做走。

### realm 設定的版控產物

realm `hd` 原本**只存在那台 Keycloak 裡**——2026-08-27 是照著步驟一格一格點出來的，沒有正本。
共用 realm 上任何人的誤觸，我們也看不出來。

`docs/keycloak/export-hd-pacs.py` 把屬於我們的部分抓下來：`hd-pacs*` 三個 client、
`hd-pacs` 的角色（**composite 展開**，因為那才是職務實際給了哪些權限）、群組、user profile 屬性。

**刻意不用 Keycloak 內建的 realm 匯出**：①整份匯出會把同事的 client 一起抄進我們的 repo
②`partial-export` 端點要 `manage-realm`，那把權限大到可以改整個 realm，service account 不該有。

輸出是穩定排序的 JSON，所以**有 diff 就代表真的有人改過設定**。用法與重建順序見
[../keycloak/README.md](../keycloak/README.md)。

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

### 2026-08-27 已上線：三支服務都改用 Keycloak 的角色

`ScopesFromToken=true` 已套用在 **DicomWeb（.199）／Export（.199）／管理主控台（.191）**，
各自用不同方式驗過（不是「服務起來了」）：

| 服務 | 版本 | 驗證方式 |
|---|---|---|
| DicomWeb | `1.0.0-alpha.16` | 同一張 token 打 `/api/v1/auth/me`，scope 從 **10 → 7** |
| Export | `0.1.0-alpha.18` | `GET /export/packages` 回 **200** |
| 管理主控台 | `0.1.0-alpha.23` | 重新登入後首頁 7 個權限、「裝置授權」如預期消失 |

「10 → 7」那個差異才是證據：DB 路徑給 10、token 路徑給 7。
`unit active` 與 `/health 200` 對這件事一個字都沒說。

#### realm `hd` 的實際佈局

**realm 是與同事的訂閱平台共用的**，client id 是同一個扁平命名空間。

| Client | 誰的 | 用途 |
|---|---|---|
| `hd-pacs` | 我們 | **角色容器**：15 個 scope + 職務 composite。四個 flow 全關（bearer-only） |
| `hd-pacs-identity-admin` | 我們 | Admin API 的 service account（confidential + service account） |
| `hd-pacs-client` | 我們 | 登入與測試（public + direct grants）。主控台目前也用它做 OIDC 登入 |
| `hd-console`／`hd-meet`／`hd-platform-backend`／`hd-viewer` | **同事** | 不要碰，連 Description 都不要補 |

**我們的 client 一律 `hd-pacs` 開頭。** 2026-08-27 提議 `hd-console` 時撞到他既有的 client，
差一點動到別人的東西——這個前綴就是那次的產物。
將來的看片端登入 client 要叫 `hd-pacs-viewer`，**不能叫 `hd-viewer`**。

service account 掛的 `realm-management` 角色（七個）：
`view-users`／`query-users`／`manage-users`／`view-realm`／**`view-clients`**／**`manage-clients`**／**`query-groups`**／`view-events`。

user profile 屬性：`hdUserUuid`（HD 識別碼）、`siteCode`（院區代碼），
兩個都是 **Who can edit / view 只勾 Admin**。

#### 職務角色

```
pacs-admin （composite）
  admin.users  admin.audit  admin.settings  admin.api_keys
  dicomweb.read  export.read  export.write
```

**刻意不含 `admin.licenses`** —— 裝置授權簽發會動私鑰，要給的人另建 `license-issuer`。
翻開關之後主控台的「裝置授權」頁會消失，那是預期行為。

#### 翻開關前的盤點（做法可重用）

查 `HD_USER` 現況才知道會影響誰：**「現在真的有權限」的人才會受影響**，
在 `HD_USER` 裡零角色的人翻前翻後都一樣。

`.191` 當時 12 筆，其中 **8 筆是舊系統的服務帳號**
（`HD-offline-print`／`HD-resource-access-user`／`HD-specific-access-user`／
`HD-study-share-user`／`HD-system`／`IDC-web-broker`／`hdservice`／`hduser`）——
**它們在 Keycloak 裡不存在、拿不到 token**，走的是 hd-web-server 的帳密登入，
所以完全不受影響。這 8 個也正好就是「hd-web-server 淘汰」實際要面對的清單。

真正需要事先補角色的只有 `hdserver` 與 `jerry`（後者是同事的測試帳號，暫緩）。

#### 實際佈署時撞到的五個坑

全都是**回 2xx 成功但結果是錯的**那一類：

1. **OIDC 授權碼流程不能用 `FromPrincipal`。** `OnTokenValidated` 的 `Principal` 來自 **ID token**，
   而 `resource_access` 只在 **access token**（Keycloak 的 client roles mapper 預設
   `Add to ID token=Off`）。用錯來源＝所有人零權限。主控台改用 `FromAccessToken`；
   DicomWeb／Export 走 JwtBearer、principal 本來就來自 access token，維持 `FromPrincipal`。
2. **service account 少了 `view-clients`／`manage-clients`。** 症狀是「realm 裡找不到 client `hd-pacs`」，
   但那個 client 明明存在 —— **Admin API 在沒有檢視權限時回 200 加空陣列**，跟「不存在」無法區分。
3. **改了 service account 的角色要重啟服務。** token 是快取的（約 15 分），而 Admin API 看的是
   token 裡的角色；權限不足回的是 200 不是 401，所以 401 重試那條路不會觸發、快取不會作廢。
4. **`PUT /users/{id}` 是整份取代不是部分更新**（realm 啟用 User Profile 之後）。只送 `attributes`
   會把姓名與 Email 清空，回 204、無警告。已改成 `PatchUserAsync`（先讀回整份再送）。
5. **`commit` 不等於佈署。** DicomWeb 與 Export 的接線早就 commit 了，版本卻沒動；
   機器上寫了 `Keycloak__ScopesFromToken=true` 卻毫無反應，因為那版根本沒有讀它的程式碼。
   **順序必須是「先裝版本 → 確認 `/health` 的版本 → 再翻開關」**，反過來會白跑一輪。

#### 使用者清單只列「我們的人」（2026-08-27，`alpha.25`）

`/identity` 預設只列 `hyperdigital` 群組的成員（`KeycloakAdmin:OwnGroup`）。
取消勾選可列出 realm 全部，但會跳警告，並多出「歸屬」欄標示哪些不是我們的。
投影表同步同樣只抄群組成員。

**這是防誤觸不是防護。** `manage-users` 是 realm 層級的權限，Keycloak 沒有內建
「只管我這幾個人」的範圍 —— 取消勾選就看得到也改得到。真正的隔離要靠
**細粒度管理權限**（把 `manage-users` 限制在該群組）或**分 realm**，兩者都要另外規劃。

兩個刻意的失敗行為：

- **群組查不到（不存在、或少了 `query-groups`）時退回「不過濾」，不是回空清單。**
  空清單看起來像「這個系統沒有任何使用者」，會讓人往完全錯誤的方向查，
  而且比「列太多」危險——管理者以為沒事，實際上整個管理介面失能。
  列太多至少畫面上有警告。
- **標出歸屬只多打一次 API**（撈一次群組成員再比對），不是逐人打
  `GET /users/{id}/groups`。那是 N+1，與「清單頁不逐人查角色」同一個理由。

#### 還沒做

- `jerry` 的角色（同事的測試帳號，用途待確認；他在 `HD_USER` 裡是 `admin`，值得重新評估）
- `license-issuer` 職務（要用「裝置授權」頁的人）
- 主控台的使用者清單**預設只列 `hyperdigital` 群組**（realm 共用，現在看得到也改得動同事的客戶）
- 拆 `hd-pacs-console` 出來當主控台的登入 client（現在借用 `hd-pacs-client`，那是 public + direct grants）
- realm 匯出成版控產物

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

> **2026-08-27 兩次修訂，最後結論是「雙軌」重新成立。**
> 當天稍早推翻過「不替換」（理由：hd-web-server 淘汰後沒有第二軌可留，所以 Keycloak 登入必須是取代，
> 而取代要等院內自建 Keycloak）。同日使用者決定 **hd-web-server 先不淘汰、等所有功能都沒問題再說**——
> 第二軌就還在，**看片端的 Keycloak 登入因此不必等院內 Keycloak，用公開的 `sso.hdtech.tw` 就能實作並驗證**。
> 本節其餘內容（封閉網路根因、OIDC 九坑）仍然有效。

### 2026-08-27 決策：目標是「我方程式與 `HD_USER` 脫鉤」，不是「`HD_USER` 退場」

使用者當天重新界定了範圍：`HD_USER` 這張表**留在資料庫裡**、12 條 FK 不動、`MAP_JOB.HD_USER_UUID` 不動；
報告新系統是同事的事；hd-web-server 先放著、等所有功能都沒問題再淘汰。
**要的只是「我自己的程式不要再跟它有關聯」。**

盤點我方四個 repo 的 29 個 `HD_USER` 命中，**真的碰那張表的只有三支**（其餘是 `HD_USER_AUDIT_LOG`
這張**不同的表**、`HD_USER_UUID` 這個欄位名、註解與 EF migration）：

| 檔案 | 狀態 |
|---|---|
| `HD.Shared.Auth/HdUserRepository.cs` | **死碼**。三支服務在 `ScopesFromToken=true` 之下 token 一到就 return，走不到 |
| `HD.AdminConsole/Services/UserAdminService.cs` | `/users` 那頁，刻意留著管 hd-web-server |
| `HD.DicomImageViewer.Server/Services/UserService.cs` | **唯一還活著的**：`POST /api/v2.0/user/login` 拿帳密查 `HD_USER` |

**所以「脫鉤」剩下的工作就是看片端登入這一條。**

### 看片端的 `access` 是什麼（2026-08-27 對 `.148` 正式機實地盤點）

`viewer_station.get_access_definition(userId, section)` ＝ 把使用者每個角色的
`HD_ROLE.ACCESS -> section` **遞迴合併**。回傳是一棵白名單樹，葉節點是空物件——**鍵存在＝有權限**。

**現在已經有兩道正交的閘，不要混為一談：**

| 閘 | 存在哪 | 回答什麼 |
|---|---|---|
| `Mode` | **本機** `localconfig.json`（裝機時設定） | **這台機器**是一般站／乳房攝影站／QC 站 → 決定去取哪個 section |
| access 樹 | DB `HD_ROLE.ACCESS -> section` | **這個人**在那個 section 裡能做什麼 |

`Mode` 是**機器屬性不是人的屬性**，所以**不要把 mode 帶進 Keycloak scope**——
放進去就變成「這個人只能在乳房攝影站登入」，語意錯了，而且醫師在不同站之間走動就會壞掉。

**客戶端實際會分岔的鍵，掃過整個 `HD.DicomImageViewer.Core` 共 23 個**（`.148` 的 DB 出現過 24 個，
多的那個是 `setting.screen`——**客戶端從不讀，是死鍵**，`.191` 與 `.148` 都有）：

- 頂層 4：`setting`、`qualityControl`、`import`、`queryRetrieve`
- `setting.*` 14：save / system / toolbar / hotKey / dicomTag / titleList / layoutList /
  `annotatioin`（**原始拼字如此，見下**）/ defaultLayout / contextToolMenu / hangingProtocol /
  dicomCommunication / mammoTool / qualityControl
- `qualityControl.*` 5：study / series / object / transmit / saveWindowLevel

拿不到 section（`null`）時，客戶端的行為是**跳「使用者權限不足，請先申請！」然後不開 Viewer**
（`LoginForm.cs:262`）。

### 六個 scope（粒度取自客戶端的 if，不是取自任何一個站台的角色表）

| Key | 顯示名 | Category | 對應的 access 鍵與客戶端位置 |
|---|---|---|---|
| `viewer.use` | 看片端登入 | Read | 總開關。沒有它＝現在的 `null`，`LoginForm.cs:262` 擋下 |
| `viewer.query_retrieve` | 查詢／取回 | Read | `queryRetrieve` →「查詢／取回」分頁（`MainForm.cs:173`）。對外發 C-FIND／C-MOVE |
| `viewer.importer` | 匯入工具 | Write | `import` → 查詢畫面的匯入鈕（`MainForm.cs:134`） |
| `viewer.qc` | 品質管制 | Write | `qualityControl` 整棵（`QCForm.cs` 17 處）。會改動既有檢查的歸屬 |
| `viewer.settings` | 看片端設定 | Write | `setting` 整棵（含 `mammoTool`，不含 `dicomCommunication`） |
| `viewer.dicom_config` | DICOM 連線設定 | Admin | `setting.dicomCommunication` |

**命名遵循現行慣例：單層 `{產品}.{動作}`、多字用底線**（比照 `admin.api_keys`）。
最初提的 `viewer.settings.dicom` 是兩層，會成為 15 個既有 scope 裡唯一的例外，已改掉。

`query_retrieve` 不簡寫成 `query`，是要跟 DicomWeb 的查詢區分——那是 QIDO，這是 C-FIND／C-MOVE。

`viewer.importer` 不叫 `viewer.import`：那顆按鈕**只是去啟動 `HD.Importer.exe`**
（`MainForm.cs:buttonImporter_Click`），本身不匯入任何東西，跟 DicomWeb 那個要綁 AE Title 的
`import.write` 是兩回事，名字要看得出差別。

`viewer.use` **刻意保留成顯式的總開關**，不用「一個 `viewer.*` 都沒有」去推導 ——
推導那條會讓「給了設定權限但仍不准開 Viewer」變成無法表達，而且日後加新 scope 時語意會悄悄改變。

實作上還要：加 `ScopeProduct.Viewer` 列舉值（主控台的「依產品分組」才顯示得出來）；
**六個全部 `ApiKeyAssignable: false`**，理由同 `admin.*` —— API Key 是機器身分，
「能不能開看片端」對它沒有意義。

### 端點必須真的擋（2026-08-27 決策）

**現況是個缺口**：`ViewerWebApi` 的 `QcController` 只有 `[Authorize]`（登入即可），
沒有任何 scope 檢查。也就是說 `access` 那棵樹**純粹是 UI 層的**，改一下客戶端就整個繞過去。

導入 scope 的同時，`ViewerWebApi` 的端點要開始實際檢查（`[Authorize(Policy = "ViewerQc")]` 之類）。
**現在不做，之後就會有人以為它擋得住** —— 而「以為擋得住」比「知道擋不住」危險。

ViewerWebApi 拿 token 的 scope，在自己這邊展開成**三個 section 的完整結構**，
形狀與現行回傳一模一樣——**客戶端 `GetSectionByMode` 零改動**。

**為什麼是這個粒度：**

- **`viewer.dicom_config` 必須獨立，而且預設不給**：`.148` 的 `remoteAEList` 有 **60 個遠端 AE**，
  改壞會讓整台機器送不出片。這個理由跟角色表怎麼設無關。

  **它的性質是「部署限制的備案」，不是一種職務權限**（2026-08-27 使用者說明）：
  大醫院基本上不開放，唯一會開的情況是**裝不了 Web 版核心控制介面**的站台——那時 AE 設定
  沒有別的地方可以改，只能退回從 Viewer 改。使用率極低。

  所以：①**任何標準職務都不含它**，要開是逐站台的例外 ②**它是永久的不是過渡的**
  （只要還有裝不了主控台的站台就會需要）③長期形狀是「AE 設定住在管理主控台，
  Viewer 那顆按鈕只在沒有主控台的站台亮」。

  > 順帶一提，當年 Viewer 之所以要自己能改 AE，是因為單機裝機時沒有獨立 Linux 主機、
  > 就沒有 hd-web-server 也沒有 AdminTool。但**設定一直都存在 DB**
  > （`viewer_station.get_common_config`，不是本機檔案），當年缺的是**編輯介面不是儲存**。
  > 管理主控台是 self-contained 的 .NET，可以裝在同一台 Windows 上——這是備案能收斂的原因。
- **`qualityControl` 不再細分**：五個子鍵在 `.148` 三個角色全給、零分級，
  拆成五個 scope 是拿真實成本買一個從未使用的能力。
- **`mammoTool` 不獨立成 scope**：`.148` 三個角色都只在 `mammoViewer` 底下有它（三個 section
  逐一驗過），結構是乾淨的——**mode 已經擋住了，再加 scope 是重複同一道閘**。
  殘留行為：沒有乳房攝影判讀資格的人坐到乳房攝影站仍拿得到 mammoTool（擋的是機器不是人）。
  哪天真要用資格區分再加 scope。

### 不要拿若瑟的角色表當設計依據

`.148` 有 5 個角色，`stationViewer` 的組合三種都不同（`server`=queryRetrieve+setting、
`user`=import+queryRetrieve+setting、`useradmin`=import+setting）。**但使用者明確說那邊不標準**，
`import`／`queryRetrieve` 是漏掉沒清的——所以「role 4 沒有 queryRetrieve」很可能不是刻意分級，
只是沒人發現（功能沒人用，少了也不會有人抱怨）。

**遷移的做法因此是「先定義標準職務，再把若瑟的人對進去」**，他們多出來或漏掉的部分是要跟現場確認的
個案，不該變成我們的標準。

`.148` 唯一真正在用的子鍵分級是 `setting.dicomCommunication`：33 位真人（role 2 `user`）拿不到，
只有 4 位 `useradmin` 和 2 個服務帳號有。

> **`.191` 會誤導。** 那台只有 role 1 定義了 viewer section，其他角色三個 section 全空，
> 看起來像「權限是二元的」。**我當天就是這樣推論然後錯了**——現場有真實分級。
> 跟更新鏈分岔是同一種形狀的坑：**只在測試床上驗，永遠驗不出來。**

### `annotatioin` 拼字修正

`annotatioin` 是既有的拼字錯誤，後續版本要改成 `annotation`。做法：

- **Keycloak 軌**：ViewerWebApi 是從 scope 展開那棵樹的，**鍵的拼字由我們決定**，直接寫 `annotation`。
- **帳密軌（讀 DB 的舊路）**：客戶端要**兩個鍵都認**（`annotation ?? annotatioin`）。
  否則舊 DB 的權限會靜默消失——那種「鍵不存在＝沒權限」的錯，畫面上只會看到按鈕不見了，
  沒有任何錯誤訊息。
- **`Database/` 底下 20 幾個歷史 SQL 檔的錯字不要動**（改了會破壞既有站台重跑更新鏈），只在新腳本處理。

### 2026-08-28 實作與實測結果

**七個 scope 已建在 Keycloak**（`.191` 主控台 `alpha.27` 的「同步權限清單」自動建的，
回報「新增 7 項、原本就一致 15 項、另有 2 個非 scope 角色未動」）。三個職務 composite
手動建，刻意做成**巢狀**：

```
viewer-user      -> viewer.use, viewer.query_retrieve, viewer.importer, viewer.settings
viewer-qc        -> viewer-user, viewer.qc
viewer-qc-admin  -> viewer-qc, viewer.qc_delete
```

**巢狀會不會被展平，實測答案是「會」**：`hdtest` 只掛 `viewer-qc-admin`，token 拿到
**14 個權限**（原本 8 個管理權限 + 六個 `viewer.*`，其中四個隔了兩層繼承）；
換成 `viewer-qc` 是 **13 個**。所以不必改成扁平列法。

`viewer.dicom_config` 不掛在任何職務底下 —— 它是部署備案，逐站台例外。

**端點的授權已實際驗過會分辨**（不是只驗「有沒有 403」）：同一個 session、同一支
controller，`GET /api/v2.0/qc/config` 回 **200**、`POST /api/v2.0/qc/action` 送
`Type=Delete` 回 **403**。兩個都 403 只能證明「整支被擋」，什麼也證明不了。

**兩條軌共用同一組 scope**：帳密軌的權限來自 `get_access_definition` 的樹，
由 `ViewerAccessBuilder.ScopesFromAccess` 反推成同一組 scope 字串，端點因此只認 scope
一種東西。**不做這件事的話，端點只認 scope 會把走帳密登入的絕大多數站台全部擋掉。**
`.199` 部署後用真實帳號驗過：登入回的 access 樹形狀不變，`qc/config` 仍是 200。

### `.199` 已切 Keycloak（2026-08-28 21:18）

`/etc/hd-viewer-api/keycloak.env`：

```
Auth__Provider=keycloak
Auth__Keycloak__Authority=https://sso.hdtech.tw/realms/hd
Auth__Keycloak__ClientId=hd-pacs-client
Auth__Keycloak__RoleClientId=hd-pacs
```

**退回帳密軌只要 `rm` 掉這個檔再重啟** —— `appsettings.json` 的預設就是 `database`，
unit 用 `EnvironmentFile=-` 引用（前面的 `-` 代表缺檔照樣啟動）。不必 `hdctl rollback`。

> 路徑要以 unit 為準：`systemctl cat hd-viewer-api | grep -i environmentfile`。
> 猜錯路徑**不會有任何錯誤**，只會讓設定靜默不生效（DicomWeb 那次是
> `hd-pacs-dicomweb` 不是 `hd-dicomweb`）。

**切換前先確認沒人在用**：7 天內 33 次登入全部來自 VPN 來源 `192.168.68.253`，
沒有第三方。切過去之後**只有在 Keycloak 掛了 `viewer.*` 的人登得進去**，
其他人會登入成功但 access 全 `null`（客戶端顯示「使用者權限不足」）。

#### 驗收證據：兩條軌的輸出「不一樣」

「重啟後還能動」證明不了換了來源。同一個帳號 `hdtest`、同一支服務，
兩條軌的 `stationViewer.setting` 逐字不同：

| 鍵 | 帳密軌 | SSO 軌 | 為什麼 |
|---|---|---|---|
| `dicomCommunication` | 有 | **沒有** | `viewer.dicom_config` 不在任何職務裡 |
| `annotation` | 沒有 | **有** | 新拼字只在我們產出的樹裡 |
| `annotatioin` | 有 | 有 | 過渡期兩個都送 |
| `import` | 沒有 | **有** | DB 的 role 1 剛好沒設，`viewer.importer` 有 |

#### 驗收證據：端點的正負對照

同一個端點、同一個 payload（`SourceRefs` 空陣列，放行也刪不到東西），只換職務：

| `hdtest` 的職務 | `POST /api/v2.0/qc/action` `Type=Delete` |
|---|---|
| `viewer-qc` | **403** |
| `viewer-qc-admin` | **200** |

**單看 403 只證明「有東西被擋」，單看 200 只證明「有東西通過」** —— 要兩邊都跑過，
才知道 policy 是在分辨而不是一律放行或一律擋。

### `viewer_station.update_common_config` 的兩個尖角（會靜默毀資料）

改「沒有 `viewer.dicom_config` 就把送上來的 DICOM 連線設定換掉」時撞到的。
**每一種「省事」的寫法都會毀資料，而且沒有任何錯誤訊息。**

1. **送 `"dicomCommunications": null`** —— jsonb 裡 `'null'` 對 `IS NOT NULL` 是**真**，
   會進到 proc 的 `IF dicom_communications IS NOT NULL` 分支，執行
   `UPDATE "AE_MAIN" SET "AE_TITLE" = dicom_communications ->> 'localAETitle'`，
   把**本地 AE Title 更新成 NULL**。整台機器送不出片。
2. **直接移除該鍵** —— proc 對 `AUTO_FETCHING` 與 `AUTO_TRANS_AE_LIST` 的兩個
   `insert_update_hd_config` 是**無條件執行**的（在 `IF` 之前），而那支函式是
   `ON CONFLICT DO UPDATE SET "CONFIG_VALUE" = config_value`，
   拿到 NULL 就把那兩列設成 NULL。

所以唯一安全的做法是**把現值原封放回去**；讀不到現值就整個拒絕（503），不要猜。
`ConfigController.WithStoredDicomCommunications` 是純函式，9 條測試釘住，
其中 5 條專門釘「絕不產出 JSON null」。

> 這兩個尖角**不是我們加的**，是既有 proc 的行為。任何人要改 `update_common_config`
> 的呼叫端都會踩到，所以記在這裡而不是只寫在程式碼註解裡。

### 撿到的既有問題

- `setting.screen`：DB 三個角色都有，**客戶端從頭到尾沒讀過**。死鍵，而且原因已知 ——
  `SettingsForm.LoadAccessDefinition` 就寫著「螢幕設定併入登入畫面的 StartupSettingsForm」，
  按鈕搬走了、權限鍵留著。可以安全移除。
- `hangingProtocol`：`.148` 的 role 1 在 `mammoViewer` 底下沒有它，但 `stationViewer` 有，
  role 2／4 兩邊都有。看起來是手改 JSON 漏掉的，不是設計。影響僅限服務帳號。

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
- **token 端點**：`POST https://sso.hdtech.tw/realms/hd/protocol/openid-connect/token`（測試用 password grant：client **`hd-pacs-client`**、scope `openid`）。
  > **2026-08-27 更正**：本段原本寫 `hd-viewer`。那是 2026-08-06 早期實測時**借用**同事的 client，
  > 不是我們的。realm `hd` 與同事的訂閱平台共用，`hd-console`／`hd-meet`／`hd-platform-backend`／
  > `hd-viewer` 都是他的。**我們的 client 一律以 `hd-pacs` 開頭**，將來的看片端登入 client
  > 要叫 `hd-pacs-viewer` 而不是 `hd-viewer`。
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
