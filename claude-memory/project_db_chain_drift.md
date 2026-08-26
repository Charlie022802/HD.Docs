---
name: project_db_chain_drift
description: "DB 更新鏈與實際資料庫已分岔:有些結構變更只存在於 .191(從 dump 建的),從沒進 db_update 腳本—所以舊站台跑完整條鏈也到不了 .191 的狀態"
metadata:
  node_type: memory
  type: project
---

**`db_update_v2.0.*.sql` 這條更新鏈是不完整的。** 有些結構變更只存在於 `.191`
(它是**從 dump 建起來的**,不是靠跑腳本長出來的),從來沒有進入版控的腳本。

2026-08-26 用若瑟的 DB 複本一路往上推,一天內撞到三個:

| 物件 | 誰需要 | 鏈裡有嗎 | 誰有 |
|---|---|---|---|
| `public."HD_USER_AUDIT_LOG"` | `2.0.27` 的 ALTER | ❌ | 只有裝 DicomWeb 的站台(`init_dicomweb.sql` 建的) |
| `public."HD_USER"."OTHERS"` | `2.0.35` 的 `site_code_of_user` | ❌ | `.191` 有;2026-07-20 的 dump 與若瑟都沒有 |
| `public.insert_routing_job` | hd-web-server 的報告路由 | ❌(已於 **2.0.38** 補回) | 2026-07-20 的 dump 有;`.191`、若瑟都沒有 |

**結論:沒辦法靠跑腳本,把一個舊醫院升到 `.191` 的狀態。**

**而且分岔是靜默的**:腳本在 `.191` 上跑得過(那些物件本來就在),
只有在**乾淨的舊站台**上跑才會撞到 `column does not exist`。
→ **每次只在 `.191` 驗證,就永遠驗不出這類問題。**

## 做法

- 新的結構變更**一律經由 migration 腳本**,不要直接改資料庫。
- 驗證時**至少要在一份「舊站台的 dump」上跑一次**,不能只在 `.191` 上跑。
- **這種驗證很便宜**:一份 schema dump ＋ 一個 podman `postgres:16` 容器,
  十分鐘跑完整條鏈,失敗零成本、完全不碰生產機。
  (dump 若是 pg_dump 18.x 產的而伺服器是 16,還原前要拿掉 `transaction_timeout` 與 `\restrict`。)

正本:[[project_josef_site]] 與 docs/josef-db-upgrade-plan.md(含完整盤點與逐項驗證)。
