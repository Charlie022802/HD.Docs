---
name: project-jit-provisioning
description: 使用者佈建改走 JIT（Keycloak 認得但無 HD_USER 就地建零角色），起因是同事訂閱制前端先上線、原雙寫契約沒發生
metadata:
  type: project
---

同事的**前端訂閱制系統**先上線了：使用者在那邊自行註冊、Keycloak 在他那端整合。
原本 2026-08-06 定的「雙寫 provisioning」契約從來沒發生，於是 `HD_USER` 永遠不會長出來 ——
拿合法 token 打 DicomWeb／Export 一律 **401**（`ctx.Fail("無對應 HD_USER")`）。

**2026-08-26 改成 JIT 佈建**：Keycloak 認得但本系統沒有對應 `HD_USER` → 就地建一筆**零角色**的，
而不是拒絕。`HdUserRepository.ResolveByIdAsync(userId, provisionIfMissing, ct)`（HD.Shared.Auth，
DicomWeb／Export／AdminConsole 三支共用）。開關 `Keycloak__JitProvisionUsers`，**預設 false**。

**為什麼選 JIT 而不是推播同步**：訂閱制的重點不是建立、是**權益會一直變**。推播每漏一次就是靜默漂移，
且方向很糟（已取消訂閱的人還留著權限）。JIT 沒有這個失敗模式 —— 取消訂閱時 Keycloak 不發 token，
人根本到不了我們這裡。

**Why:** 這是把一致性問題「消掉」而不是「管理它」；而且各醫院之後自建 Keycloak 時，
推播/對帳都要每間配 service account，JIT 一個都不用。

**How to apply:**
- 設定**一定要走環境變數**（`/etc/hd-*/keycloak.env`）。`appsettings.json` 在 hdctl preserve 清單裡，
  新增區塊不會上到既有機器。見 [[reference_hdctl_preserve]]。
- **不要對 `GROUP_REF` 做 `MIN()` fallback** —— 種子是 `0=admin`/`1=build-in`/`2=DEFAULT`，
  取最小值會把自動註冊的人丟進 admin 群組且無聲無息。只用 2，不在就大聲失敗。
- **`HD_USER."ID"` 沒有唯一約束**（只有非唯一索引），`ON CONFLICT` 用不了。
  併發會插出多列同 ID，而 `LIMIT 1` 讓之後查到哪一列變不確定 → 權限飄且無錯誤訊息。
  用 `pg_advisory_xact_lock(hashtext(...))` ＋ `INSERT … WHERE NOT EXISTS`。
- **不要寫沒人讀的欄位**：`ENABLE`／`EXPIRE_DATE` 是 [[project_db_chain_drift]] 的第 4、5 個分岔項，
  若瑟這種舊站台根本沒有那兩欄 → `42703`。`OTHERS` 是 v2.0.35 才進鏈的，要條件式寫入。

**已部署並端到端驗證（2026-08-26，`.199` 生產）**：dicomweb `1.0.0-alpha.10`／export `0.1.0-alpha.16`。
env 目錄是 **`hd-pacs-dicomweb`** 不是 `hd-dicomweb`（加到不存在的路徑不會報錯，只會靜默沒開）；
兩個 unit（5080＋5081 UPS）共用同一份 envFiles。主控台（`.191`）刻意不開 —— 它本來就不會 401，
而且三支共用同一張 `HD_USER`，人打過 `.199` 一次就在表裡了。

**驗證方法值得複用**：`active`＋`/health` 200 完全證明不了 JIT（那條路徑根本沒被走到）。
做法是把 `.191` 的 `hdtest` 暫時改名，造出「Keycloak 有、`HD_USER` 沒有」的狀態 ——
`/me` 從 10 scopes 變 `scopes:[]`、QIDO 從 200 變 **403 而不是 401**（401＝不知道你是誰，
403＝知道你是誰但沒權限），且新列的 `OTHERS.keycloakSub` 等於 token 的 `sub`
（那個 UUID 沒有別的管道拿得到，能對上才證明存的是真身分）。還原用單一交易先刪後改名 ——
`ID` 沒有唯一約束，順序反了會短暫出現兩列同 ID 而查詢是 `LIMIT 1`。

**還沒解**：權益等級。JIT 讓人進得來，但權限仍要人工指派。方向＝訂閱方案對應 Keycloak group、
我方做 group → `HD_ROLE` 映射（`groups` claim 現在就已經在 token 裡）。待與同事確認對照表。
相關洞：`HD_USER.ROLES` 全 DB 沒有任何寫入路徑，見 [[project_hd_admin_console]]。
