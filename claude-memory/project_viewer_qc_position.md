---
name: project_viewer_qc_position
description: "Viewer 內建 QC 的定位待重新釐清(單機時代產物、只剩幾間在用、大多走 AdminTool)—不是要退場,是還沒想清楚;但它與「移除客戶端直連 DB」有硬相依"
metadata:
  node_type: memory
  type: project
---

**Viewer 裡的 QC 是單機 Viewer 時代的產物,現在只有少數幾間醫院還在用,
大部分 QC 是去 AdminTool 網頁做的。**(2026-08-25)

**定位還沒定案——使用者說的是「想重新整理這邊的定位」,不是要退場。**
(我一度記成「準備退場」,那是過度延伸,已更正。)所以現在不要往任何一個方向推進:
不要主動補功能、也不要規劃退役,先擱著等定位想清楚。

**但它跟 [[project_viewer_server]] 的 ④ 有硬相依**:
ViewerWebApi 的 `/api/v2.0/qc/*` 六個端點伺服器端已寫好。④(移除客戶端的
`SafePostgresConnection`)一旦做了,QC 就只剩 API 這條路,沒驗過就上,
那幾間醫院會在升級後才發現壞掉。

**已驗過**(2026-08-25,使用者實測):`qc/tree` 的 Study／Series／Image 三層、
以及 Study 修改(`CALL viewer_station.qc`)。三層都有資料回來,順帶證實
`SelectJsonRows` 的修正是對的(`get_qc_tree` 回 SETOF jsonb,原本用 `SelectJson`
只會拿到第一列)。
**還沒驗**:`qc/config`、`qc/transmit-jobs`、`qc/transmit-job`、`qc/exist-data`
——其中「影像傳送」那兩支最值得補。

相關:[[project_viewer_server]]、[[project_hd_admin_console]]。
