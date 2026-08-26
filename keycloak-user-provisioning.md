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

## 五、要請 hd-web-server 配合的一件事：`HD_USER.ENABLE`

HD 後端管理主控台現在可以「停用」使用者。停用的語意是**這個帳號不得登入任何 HD 產品**。

我們已經在自己的三個入口加上檢查（管理主控台／DicomWeb／Export API）。
**但看片端的帳密登入走的是 hd-web-server 的 `loginCheck`，那支還沒檢查這個欄位。**

不加的後果很具體：管理者在主控台把某人停用、畫面顯示「已停用」，**那個人照樣能登入看片端**。
一個會騙人的開關比沒有開關更糟——因為大家會相信它。

### 要改的地方

`loginCheck` 現在取 `PASSWORD` 與 `GROUP_REF`；請一併取 `ENABLE`，並在密碼比對通過之後判斷：

```ts
// 取得使用者資料時把 ENABLE 一起帶出來
includeField: ["PASSWORD", "GROUP_REF", "ENABLE"]

// 密碼正確之後
if (userInfo.ENABLE === false) {
  // 回與「帳密錯誤」相同的錯誤，不要告訴對方「你被停用了」
  return rep.badRequest();
}
```

兩點說明：

1. **回應要與帳密錯誤一致。** 明說「此帳號已停用」等於告訴不該知道的人「這個帳號存在」。
2. **判斷用 `=== false` 而不是 falsy。** `ENABLE` 這一欄是 v2.0.39 才進更新鏈的，
   還沒套用的資料庫**根本沒有這個欄位**，取出來會是 `undefined`——那種情況要視為啟用，
   不然升級當下所有人都會被鎖在外面。

### 需要的資料庫版本

`ENABLE` 由 `db_update_v2.0.39.sql` 補上（既有資料列一律預設 `true`，升級不會鎖住任何人）。
在還沒套用的站台上，主控台不會顯示停用選項，`loginCheck` 也會因為上面第 2 點而照常放行。

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
