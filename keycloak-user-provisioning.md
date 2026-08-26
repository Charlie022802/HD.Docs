# 建立使用者：給前端／SSO 端的約定

**對象**：在 Keycloak 建立使用者的那一端（訂閱系統前端、或院內 SSO 的管理者）。
**結論先講：建立帳號不需要呼叫 HD 這邊的任何 API。** 帳號建在 Keycloak 就好，
使用者第一次帶 token 打進來時，HD 這邊會自動補上對應的資料列（JIT 佈建）。

但**建立的方式有幾個約束**，違反了會出事，而且症狀都不明顯。

---

## 一、必須遵守的三件事

### 1. `preferred_username` 是身分鍵，而且必須永久不變

HD 這邊用 `preferred_username` 對應到自己的使用者資料（`HD_USER.ID`）。

**改掉 username＝變成另一個人。** 系統會把他當成新使用者、自動建一列新的、
**權限歸零**，而舊那列還留著。畫面上不會有錯誤，那個人只會說「我突然什麼都不能做了」。

> 要改顯示名稱請改 `name`，不要改 `username`。

### 2. 不要用 email 當帳號

email 會變（換單位、改網域），而變了就等於上面那個問題。
另外目前 realm 的 email 多為佔位值且 `email_verified=false`，不適合當識別。

### 3. client 必須掛 `hd-api` client scope

HD 的服務會**嚴格驗證 audience**：access token 的 `aud` 必須含 `hd-pacs`，否則一律 401。

`hd-api` 這個 client scope 帶著 Audience mapper（`Included Custom Audience = hd-pacs`、
`Add to access token = On`）。**新建的 client 只要掛上這個 scope 就有**，不必逐一設定。

沒掛的症狀：token 看起來完全正常、簽章也對，但每個 API 都回 401。

---

## 二、可以給、但不是必要的

| claim | 用途 | 沒有的話 |
|---|---|---|
| `email` | 存進 HD 的使用者資料，管理介面顯示用 | 該欄空白，不影響登入 |
| `name` | 同上（顯示名稱） | 以 username 代替 |
| `groups` | 顯示／分流用（需掛 Group Membership mapper） | 不影響 |

> `groups` **目前不影響權限**。HD 的權限一律查自己的資料庫，不看 token 裡的角色或群組。
> （若之後要用群組決定權限，那是另一個設計，需要雙方先約定對照表。）

---

## 三、建立之後會發生什麼

1. 那個人拿 token 打 HD 的任何服務。
2. HD 發現「Keycloak 認得，但本系統還沒有這個人」→ **就地建立一列，零權限**。
3. 他**進得來**，但每個功能都會被擋（403，不是 401）。
4. 他會出現在 HD 後端管理主控台的使用者清單裡，標示為「自動註冊」、排在最前面。
5. **管理者在那裡指派角色**，他才真正能用。

所以標準流程是：**你建帳號 → 他登入一次 → 管理者給權限**。
不需要事先通知 HD、也不需要任何 API 呼叫。

> 第 3 步的 403 是正常的，不是設定錯誤。401（不知道你是誰）才是。

---

## 四、停用與刪除

**停用請在 Keycloak 停用。** 那裡是身分的正本，停了就拿不到 token，也就到不了 HD。
HD 這邊另有一個停用旗標，但那是第二道防線，不是主要手段。

**刪除要留意**：在 Keycloak 刪掉使用者，HD 這邊的資料列會留著（連同他做過的事的歷史紀錄）。
那是刻意的——稽核紀錄不該因為帳號被刪就查不出是誰做的。要一併清掉請通知 HD 的管理者。

---

## 五、停用的涵蓋範圍（已知限制）

HD 後端管理主控台可以停用使用者，語意是**這個帳號不得使用 HD 的服務**。
已在管理主控台／DicomWeb／Export API 三個入口生效。

**但看片端的帳密登入不受影響。** 那條路（hd-web-server 的 `loginCheck` 驗
`HD_USER.PASSWORD`）不檢查這個旗標，而且**不會為此修改**——看片端遲早會切到院內 Keycloak，
切完之後那條路就退場，這個限制自然消失。

所以在那之前，**要完全停掉一個人，請在 SSO 也停用該帳號**。SSO 是身分的正本，
停了就拿不到 token，任何入口都到不了。

> 這件事在主控台的停用確認框裡也寫著，管理者不需要記得它。

---

## 六、給 HD 這端佈署者（不是給前端的）

各服務要開 JIT 才會自動建立使用者：

```
Keycloak__Authority=https://<院內 SSO>/realms/<realm>
Keycloak__JitProvisionUsers=true
```

**必須走環境變數**（各服務的 `/etc/hd-*/keycloak.env`）——`appsettings.json` 在 hdctl 的
preserve 清單裡，新增的設定不會上到既有機器。詳見 [systems/identity.md](systems/identity.md)。

**已知限制**：`name`／`email` 只在**第一次建立時**從 token 帶入，之後在 Keycloak 改了不會同步過來。
目前要靠管理介面手動改。（若要每次登入都更新，是小改動，但會覆蓋管理者手動修正過的值，
所以先不做。）

---

相關：[systems/identity.md](systems/identity.md)（JIT 佈建的實作與坑）、
[systems/admin-console.md](systems/admin-console.md)（指派角色的介面）。
