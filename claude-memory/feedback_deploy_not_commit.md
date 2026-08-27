---
name: feedback-deploy-not-commit
description: commit 不等於佈署（我一天犯三次）；測試替身太寬鬆會讓契約錯誤隱形；先裝版本→確認版本→再改設定
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ea8648ec-751b-449c-aab0-36db86e8c1e2
  modified: 2026-08-27T12:16:14.638Z
---

**寫完程式、commit、push，不等於那台機器上有那段程式碼。**

**Why:** 2026-08-27 我一天犯了三次（主控台的新頁面、DicomWeb 的開關、Export 的開關）。
最糟的一次是 DicomWeb：使用者在機器上把 `Keycloak__ScopesFromToken=true` 寫對了、
`systemctl is-active` 是 active、`/health` 回 200 —— **但那個版本根本沒有讀那個變數的程式碼，
完全沒有任何抱怨**。白跑一整輪才發現版本停在改動之前。

**How to apply:**

- 改了程式又要改機器上的設定時，**順序必須是「先裝版本 → `curl /health` 確認版本 → 再改設定」**。
  反過來做，設定會寫在一個不會讀它的版本上。
- 交付前先問一次：**「這段程式碼現在在哪台機器上？」** 而不是「我寫完了嗎」。
- 版本號有兩份來源（csproj／Directory.Build.props 與 hdctl-manifest.json），
  兩邊要一起 bump，否則 `/health` 會說謊（見 [[reference-version-two-sources]]）。

---

**測試替身太寬鬆，會讓「對方的契約」整類錯誤隱形。**

同一天兩次：
- 假的 Keycloak 什麼 JSON 都收 → `KeycloakUser` 的計算屬性被序列化出去、
  真 Keycloak 回 `400 Unrecognized field`，40 條測試全綠。
- 假的 Keycloak 不理會分頁參數 → 呼叫端「收到不足一頁就是最後一頁」永遠不成立，
  **測試不是失敗而是卡死**（testhost 還會鎖住 DLL，要 `Stop-Process` 才能重跑）。

**測試只覆蓋了我方的假設，沒覆蓋對方的契約。** 寫替身時要問：
真實的那一端會拒絕什麼、會怎麼分頁、哪些欄位是唯讀的。

---

**突變驗證要連「測資本身」一起看。** 有一條測試在拿掉 base64url 的 `-`/`_` 轉換後照樣全過，
因為假 token 的 payload 太短、base64 剛好沒產生 `+` 和 `/`。真實 token 很長，一定會有 ——
那個 bug 會在正式環境炸、在測試裡隱形。修法是**先斷言測資本身含有那些字元**，
不然測資一變，測試會安靜退化成測不到東西。

相關：[[feedback-code-hygiene]]（斷言全綠不代表功能達成目的）、[[project-hd-user-retirement]]。
