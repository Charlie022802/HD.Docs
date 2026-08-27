---
name: reference-keycloak-realm-hd
description: realm hd 是與同事的訂閱平台共用的；哪些 client 是我們的、哪些不能碰；我們的 client 一律 hd-pacs 開頭
metadata: 
  node_type: memory
  type: reference
  originSessionId: ea8648ec-751b-449c-aab0-36db86e8c1e2
  modified: 2026-08-27T12:15:42.841Z
---

**`sso.hdtech.tw` 的 realm `hd` 是與同事的訂閱平台共用的**，client id 是同一個扁平命名空間。

| Client | 誰的 | 用途 |
|---|---|---|
| `hd-pacs` | 我們 | **角色容器**：15 個 scope + 職務 composite。四個 flow 全關（bearer-only） |
| `hd-pacs-identity-admin` | 我們 | Admin API 的 service account |
| `hd-pacs-client` | 我們 | 登入與測試（public + direct grants）。主控台目前也用它做 OIDC 登入 |
| `hd-console`／`hd-meet`／`hd-platform-backend`／`hd-viewer` | **同事** | **不要碰，連 Description 都不要補** |

**我們的 client 一律以 `hd-pacs` 開頭。** 2026-08-27 我提議把主控台的登入 client 叫 `hd-console`，
結果那是他既有的 client —— 差一點動到別人的東西。將來的看片端登入 client 要叫 **`hd-pacs-viewer`**，
**不能叫 `hd-viewer`**（那是他的；2026-08-06 早期實測只是「借用」，不代表是我們的）。

**群組 `hyperdigital` ＝ 我們的人。** 管理主控台的使用者清單預設只列這個群組。

`realm_access` 裡的 `member` 是他的訂閱會員標記 —— 我們的 `TokenScopeResolver`
**刻意不採用 realm roles**，這條約束因為 realm 共用而從「理論上的謹慎」變成實際承重。

service account `hd-pacs-identity-admin` 掛的 `realm-management` 角色（八個）：
`view-users`／`query-users`／`manage-users`／`view-realm`／`view-clients`／`manage-clients`／
`query-groups`／`view-events`。

user profile 屬性：`hdUserUuid`、`siteCode`，兩個都是 **Who can edit / view 只勾 Admin**。

**同事的訂閱平台不會拿使用者 token 打我們的 DicomWeb／Export**（2026-08-27 確認），
只有 DicomWebViewer 會。

相關：[[project-hd-user-retirement]]、[[project-auth-keycloak-plan]]。
