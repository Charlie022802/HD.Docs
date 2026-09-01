---
name: reference_dicomweb_api_docs
description: DicomWeb 的 API 文件有三個表面（Scalar 中文正本／英文查表／README+HD.Docs），英文那份會「命中但過時」
metadata:
  type: reference
---

DicomWeb 的 API 文件散在三個表面，改了行為要三邊都動：

1. **`/scalar`（線上互動文件）的中文版 = 正本** — 就是端點上的 `WithSummary`／`WithDescription`。
2. **英文版 `/openapi/v1-en.json`** — `Api/OpenApi/EnglishOpenApiTransformer.cs` 以「**中文 summary** 為 key」查表替換。
3. **README.md + `docs/systems/dicomweb.md` + `dicomweb-endpoints.md`（HD.Docs）**。

**第 2 個有一種安靜的壞法：命中但過時。** key 是 summary，所以只改 description 時查表照樣命中，
英文版顯示的是舊內容——查不到會退回中文（一眼看得出來），查得到卻過時（看不出來）。
2026-09-01 實際發生：PDF／SR／波形做完三輪，英文版還寫著「JPEG or PNG」。

護欄只擋得住一半：整合測試 `OpenApiEnglishDocTests` 掃 v1-en.json 找 CJK 字元，
**抓得到「新端點漏補英文」，抓不到「英文過時」**。後者只能靠改中文時順手改英文。

相關：[[project_dicomweb_features]]、[[project_i18n_plan]]（resx 是 UI 字串，跟這個查表無關）。
