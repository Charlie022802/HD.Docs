---
name: project_i18n_plan
description: 多語系規劃已定案(2026-08-10):resx+IStringLocalizer、日誌/稽核不翻、Keycloak locale attribute;正本 docs/i18n-plan.md;新 UI 一律走 localizer
metadata: 
  node_type: memory
  type: project
  originSessionId: 13e6b6ed-984d-4c27-aed8-2170077bfa02
  modified: 2026-08-10T08:02:03.596Z
---

**多語系(i18n)規劃定案(2026-08-10),正本=`docs/i18n-plan.md`**。目標語言 zh-Hant(預設)→zh-Hans→en→ja。

關鍵決策:①機制走 .NET 標準 resx+`IStringLocalizer`(Blazor=AddLocalization+culture cookie;WinForms=集中 Strings.resx,不用 designer Localizable);②共用機制+共通詞彙 resx 放 **HD.Shared.Localization**(待建),各產品字串 resx 放各自 repo;③登入使用者偏好存 Keycloak user attribute `locale`(OIDC 標準 claim);④**不翻**:日誌/稽核訊息(工程師面向,要能 grep)、DB 資料、DICOM 協定詞彙——只翻 UI 文字/驗證提示/Email;⑤繁中 resx 為正本→機翻初稿+人工校。

階段:**P0 完成(2026-08-10)**=HD.Shared.Localization 建好(HdCultures/cookie→locale claim→Accept-Language 解析/`/hd/culture` 切換端點/CommonStrings resx×3)+**管理主控台全站四語**(116 keys+topbar 切換器,本機四語驗證通過);接線=AddHdLocalization+UseHdRequestLocalization(**放 UseAuthentication 之後**)+MapHdCultureEndpoint;**P1=從今起新 UI 一律 localizer 不硬編中文(code review 檢查點)**;P2:**DicomWeb 管理端完成(同日,139 處/108 keys,含切換器,批次替換腳本驗證每筆命中)**;**API 文件=中英兩份(同日完成)**:`v1`(繁中正本)+`v1-en`(EnglishOpenApiTransformer 以中文 summary 查表,35 端點+11 tags),Scalar 改固定路由 `/scalar` 才會出文件下拉(預設 `/scalar/{documentName}` 是一文件一頁);**新端點要補 transformer Map 英文對照**(缺=顯示中文不會壞);Scalar 框架字串無語言設定不翻;**回應格式宣告完成(2026-08-10)**:Export 4/4+DicomWeb 非 DICOM 端點(me/audit/delete/import/health,ApiDocResponses.cs 正式 record+JsonPropertyName 固定既有 snake_case);DICOM 標準端點由 `DicomJsonDocTransformer` 自動補「格式說明+分層情境範例(Study/Series/Instance/Metadata/UPS/STOW 各異)+PS3.18 連結+application/dicom+json 媒體型別」;**新端點維護點:英文補 EnglishOpenApiTransformer.Map、DICOM JSON 範例補 SampleBySummary(中英 summary 都要列)**;Export 也有 /scalar(同款雙語);剩 LoggingPlatform Web(內部工具,低優先/可不翻)與 Viewer(等新版);P3=切換器統一+Email 模板。相關:[[project_auth_keycloak_plan]]、[[project_core_architecture]]。
