---
name: project-hd-user-retirement
description: 2026-08-27 定案 Keycloak 當唯一正本(人+角色)、HD_USER 退場，本地只留唯讀投影表；成立前提是四件事拍板
metadata: 
  node_type: memory
  type: project
  originSessionId: ea8648ec-751b-449c-aab0-36db86e8c1e2
  modified: 2026-08-26T17:16:56.797Z
---

**2026-08-27 架構定案：使用者的身分與角色全交 Keycloak，HDPACS 不再存帳號、也不再存授權。**
`HD_USER` / `HD_USER_CONFIG` / `HD_ROLE` / `HD_GROUP` / 整個 `report` schema 退場。
本地只留一張**唯讀投影表** `HD_IDENTITY_MIRROR`，供查詢與備份，**絕不參與授權判斷**。
正本在 `docs/systems/identity.md`「2026-08-27 定案」與 backlog 的 REQ-024。

**Why:** 我原本判定這件事做不到 —— `HD_USER` 被 **12 條 FK** 指著，其中
`REPORT_SAVED.REPORT_PHYSICIAN_UUID`（報告簽署醫師）是法定病歷。是使用者接著拍板的四件事把 12 條全清空：
hd-web-server 淘汰／報告換全新系統／看片端重做／`MAP_JOB.HD_USER_UUID` 不重要。
**所以「能不能拔」不是技術問題，是那四件事有沒有拍板 —— 少一件就破功。**

**How to apply:**

- **我在同一天改過兩次結論，第二次才對。** 先建議「授權留本地」(`HD_PRINCIPAL` 三表)，理由是
  `HD_ROLE.ACCESS` 屬產品領域知識、且「報告的簽核權與 QIDO 權會混成一坨」。
  **後者站不住** —— 那是 **realm roles** 全域命名空間才有的問題，用 **client roles** 天然就分開。
  教訓：反對一個方案前，先確認自己想的是它最好的形態。
- **對應關係是 Keycloak 原生的**：`ScopeCatalog` 的一個 scope = **client role**；
  一個 `HD_ROLE` = **composite role**（自動展開進 token）。各服務拿 token 就是最終 scope 清單，零 DB 查詢。
- **四個必守約束**：①**一定用 client roles 不用 realm roles**（realm 是同事在管的，這是「正本住別人家」
  唯一有效的隔離）②`ScopeCatalog` 留程式碼當共同語言 —— **API Key 那條路仍是本地的**，
  兩個授權來源必須產出一字不差的 scope 字串 ③`hdUserUuid` 由我們的介面產生
  （**介面是我們寫的，所以不需要任何回寫契約**），且必須設 **admin-only attribute**（能自改＝能冒充歷史紀錄）
  ④**DB proc 要改**（`site_scope_for_user`、六支 `HD_ROLE_RBAC_functions` 改吃參數）。
- **四個代價**：撤權延遲 = access token 存活期（15 分，**會讓「停用後馬上測」失去鑑別力**）／
  token 變大（nginx proxy buffer 502 會回來）／「誰有這權限」不能 SQL 查／Keycloak 成單點。
- **投影表的那條線不能破：它永遠不參與授權判斷。** 破了就退化成「本地是正本」，
  兩份要同步的老問題全回來，而且**只在漂移那一刻出錯**、平常查不出來。
  用程式碼結構擋：mirror 的 repository 放查詢組件，授權路徑 (`OnTokenValidated`) 根本拿不到。
- **不要再提「請同事的系統呼叫我們的 API」** —— 這契約 2026-08-06 定過、沒發生（他的訂閱系統先上線）。
  而且**入口本來就已經集中在 Keycloak**：他寫、我們也寫，寫的是同一本。
  要即時知道有人註冊，Keycloak 的機制都要部署東西到他的 Keycloak 上，又回到要他配合。
- **該向他要的是三件「給權限」不是「改流程」**：confidential client + service account roles／
  `hdUserUuid` 設 admin-only／client `hd-pacs` 的 roles 命名空間歸我們。成本低一個數量級。
- **`HD.Identity`：介面背後要是一支服務，不要直接在 Blazor 頁面打 Admin API。**
  四個已知坑：Admin base 不是 Authority 接路徑（要拆 host+realm）／`PUT /users/{id}` 的 attributes
  **整個覆寫不是 merge**（先 GET 再合併，跟 `OTHERS` jsonb 同一個教訓）／`enabled=false` 不撤已發出的 token／
  service account 自己也是 user 要過濾。
- **瓶頸是看片端**：Keycloak 登入必須先於 hd-web-server 淘汰。**推翻了 [[project-auth-keycloak-plan]]
  的「Viewer 雙軌、不替換」**。
- **`v2.0.39` 的 `ENABLE`/`EXPIRE_DATE` 作廢**（前一天才加、已佈 `.191`）：腳本不動只加追記。
- **`HD_ACTIVE_USERS` 是 debug 殘留**（使用者確認），不是分岔項：只在若瑟正式機、不在更新鏈、
  **整個 codebase 零引用**。跟 [[project-db-chain-drift]] 那六個不同 —— 那六個至少還有程式在用。

相關：[[project-jit-provisioning]]（「建 HD_USER」整段作廢，401 症狀從根消失）、
[[project-auth-keycloak-plan]]、[[project-hd-web-server]]（凍結 → 淘汰）、[[project-db-chain-drift]]、
[[project-multi-site-host]]（`site_scope_for_user` 要改吃參數）。
