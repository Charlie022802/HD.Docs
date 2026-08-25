---
name: project_viewer_qc_position
description: "Viewer 內建的 QC 是單機時代的遺產,只剩幾間醫院在用;大部分 QC 走 AdminTool 網頁—這決定了它值不值得投驗證成本"
metadata:
  node_type: memory
  type: project
---

**Viewer 裡的 QC 功能是單機 Viewer 時代的產物,現在只有少數幾間醫院還在用。
大部分 QC 是去我們的 AdminTool 網頁做的**(2026-08-25 使用者說明)。

所以它不是「還沒補完的功能」,是**準備退場的功能** —— 之後看到 Viewer QC 相關的
待辦或缺口,先問「這間醫院是不是該改用 AdminTool」,而不是直接動手補。

**但它跟 [[project_viewer_server]] 的 ④ 有硬相依**:
ViewerWebApi 的 `/api/v2.0/qc/*` 六個端點伺服器端已經寫好,**但一次都沒被真的呼叫過**。
④(移除客戶端的 `SafePostgresConnection`)一旦做了,QC 就只剩 API 這條路——
沒驗過就上,那幾間醫院會在升級後才發現壞掉。

三條路:
- **A** ④ 之前補驗 QC(過渡做法,要付驗證成本在一個要退役的功能上)
- **B** ④ 先做、QC 保留直連 DB(那「客戶端不再持有 DB 密碼」就沒達成)
- **C** 那幾間改用 AdminTool、Viewer QC 退役(最乾淨;前提是確認他們的 QC 流程
  AdminTool 都做得到)

依使用者的說法,**C 才是真正想去的方向**,A 只是過渡。動工前要先確認 AdminTool 的
功能覆蓋度,以及那幾間到底是誰。

相關:[[project_viewer_server]]、[[project_hd_admin_console]]。
