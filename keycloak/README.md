# Keycloak realm `hd` — 我們這一半的設定正本

`sso.hdtech.tw` 的 realm `hd` 是**跟同事的訂閱平台共用的**。這個目錄只放屬於我們的部分：
`hd-pacs*` 三個 client、`hd-pacs` 底下的角色、我們的群組、user profile 屬性。

> 為什麼需要這個目錄：2026-08-27 整個 realm 是照著步驟在畫面上一格一格點出來的，
> **設定只存在那台 Keycloak 裡**。院內自建 Keycloak 遲早要做（見 [systems/identity.md](../systems/identity.md)），
> 到時候沒有正本可以照著建。而且共用 realm 上任何人的誤觸，我們現在**看不出來**。

## 產生 / 更新

在你自己的終端機跑，secret 不會經過 repo：

```powershell
$env:KC_AUTHORITY  = 'https://sso.hdtech.tw/realms/hd'
$env:KC_CLIENT_ID  = 'hd-pacs-identity-admin'
$env:KC_CLIENT_SECRET = '<貼上 secret>'
python D:\Dev\HyperDigital\docs\keycloak\export-hd-pacs.py
```

然後 `git diff`。**沒有 diff 才是正常的**——有 diff 就代表有人動過設定，
要先弄清楚是誰、為什麼，再決定 commit 還是改回去。

secret 在 `.191` 的 `/etc/hd-admin-console/keycloak.env`。

## 這裡面沒有什麼

- **沒有 secret**。client secret 不在 client representation 裡，腳本另外再濾一次。
  重建時要重新產生並寫進各機器的 `keycloak.env`。
- **沒有使用者**。人是活資料，正本在 Keycloak、查詢副本在 `HD_IDENTITY_MIRROR`。
- **沒有同事的 client**（`hd-console` / `hd-meet` / `hd-platform-backend` / `hd-viewer`）。
  那是他的東西，不該進我們的 repo。

## 重建 realm 時的順序

匯出的 JSON 是**對照用的**，不是 import 檔（Keycloak 的 realm import 吃的是整份 realm，
會連同事的部分一起蓋掉）。重建時照這個順序手動建，然後跑一次匯出比對：

1. realm `hd` 與 user profile 屬性（`user-profile.json`）——
   `hdUserUuid`／`siteCode` 的 **Who can edit / view 只勾 Admin**。
   這條是安全性質：能自改 `hdUserUuid` 等於能冒充別人的歷史紀錄。
2. 群組（`groups.json`）——`hyperdigital` 是我們的人。
3. client `hd-pacs`（`clients/hd-pacs.json`）——四個 flow 全關，它只是角色容器。
4. `hd-pacs` 的角色（`roles/hd-pacs.json`）——先建所有 scope 角色，再建職務 composite
   並掛上 `composites` 列的成員。**composite 的成員才是職務實際給的權限**。
5. client `hd-pacs-identity-admin`——confidential + service account，
   掛 realm-management 的 `view-users` `query-users` `manage-users` `view-realm`
   `view-clients` `manage-clients` `query-groups` `view-events`。
6. client `hd-pacs-client`——public + direct grants，登入與測試用。

## 相關

- [systems/identity.md](../systems/identity.md)——身分架構的正本
- [keycloak-user-provisioning.md](../keycloak-user-provisioning.md)
