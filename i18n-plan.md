# 多語系（i18n）規劃

2026-08-10 立案。現況：所有 UI（DicomWeb 管理端、管理主控台、LoggingPlatform Web、桌面 Viewer）字串硬編繁體中文；未來要支援簡中／英文／日文。**現在立慣例，新程式照規矩寫，舊頁面排程搬**——越晚立，搬遷成本越高。

## 目標語言

`zh-Hant`（預設）→ `zh-Hans` → `en` → `ja`。culture 代碼採 BCP-47。

## 決策（定案）

1. **機制走 .NET 標準**：resx 資源檔 + `IStringLocalizer<T>`。不自造框架、不引第三方。
   - Blazor（Server）：`AddLocalization()` + culture cookie（`CookieRequestCultureProvider`）；UI 放語言切換器，選擇存 cookie（登入使用者另存偏好，見 3）。
   - WinForms（HD.Desktop/Viewer）：**集中 Strings.resx**（`Strings.zh-Hans.resx`…）+ `Thread.CurrentThread.CurrentUICulture`；**不用** Form.Localizable designer 模式（每個 Form 一份 resx 難維護）。
2. **共用機制放 HD.Shared.Localization**（新葉子包，待建）：
   - culture 解析/切換 helper（cookie 名、支援清單、fallback 規則統一）。
   - **共通詞彙 resx**：儲存/取消/刪除/登入/登出/確認/錯誤……各產品重複的字只翻一次。
   - 各產品**自己的字串 resx 放各自 repo**（`Resources/` 夾），不集中（避免跨 repo 相依地獄）。
3. **使用者語言偏好**：登入系統（Keycloak）使用者 → Keycloak user attribute `locale`（OIDC 標準 claim，登入時帶回）；未登入/單機 → cookie / 本機設定。
4. **不翻的東西**（劃清界線，省一半工）：
   - **日誌與稽核訊息不翻**——面向工程師，保持單一語言才能 grep/比對（LoggingPlatform 的資料本身也不翻）。
   - DB 資料（產品名、AE Title、設定鍵）不翻。
   - DICOM/HL7 協定詞彙（C-STORE、Modality…）不翻。
   - **API 文件（Scalar）＝中英兩份、不做四語**（2026-08-10 定案並完成）：Scalar 框架字串無語言設定（控制不了）；
     內容做**兩份 OpenAPI 文件**——`v1`（繁中正本）＋`v1-en`（`EnglishOpenApiTransformer` 以中文 summary 查表換英文，
     35 端點＋11 群組），Scalar 固定路由 `/scalar` 出文件下拉（中文/English）。**新端點要在 transformer 的 Map 補英文對照**，
     缺了只是顯示中文不會壞。`/hd/culture` 已 ExcludeFromDescription。
   - 翻的只有：**使用者看得到的 UI 文字、驗證/錯誤提示、Email 通知**。
5. **翻譯流程**：繁中 resx 為正本 → 機翻初稿（Claude 可批次產）→ 人工校對。新增字串時四語一起補（PR 檢查點）。

## 導入階段

- **P0 ✅（2026-08-10 完成）**：`HD.Shared.Localization` 建好（HdCultures 四語清單／culture 解析 cookie→locale claim→Accept-Language／`MapHdCultureEndpoint` 切換端點／共通詞彙 resx×3）；**管理主控台全站四語完成**（116 keys、topbar 切換器、title/lang 隨 culture），本機四語切換驗證通過。接線三行：`AddHdLocalization()`＋`UseHdRequestLocalization()`（放 UseAuthentication 之後，claim provider 要讀登入者）＋`MapHdCultureEndpoint()`。
- **P1（從今起）**：**新寫的 UI 一律 `IStringLocalizer`**，不再硬編中文（code review 檢查點）。
- **P2（排程搬遷）**：舊頁面逐 repo 搬——優先序＝客戶可見度：Viewer／管理主控台 → DicomWeb 管理端 → LoggingPlatform Web（純內部維運，最後；可考慮維持繁中不翻）。
  - **DicomWeb 管理端 ✅（2026-08-10）**：全站四語（139 處、108 keys+切換器），本機驗證通過。
  - LoggingPlatform Web：未做（內部工具，低優先）。Viewer：等新版。
- **P3**：語言切換器全產品統一位置（右上使用者選單）、Email 模板多語。

## 備註

- Blazor Server culture 是 per-circuit：cookie 方案在重整後生效即可，不追求即時熱切（成本高、價值低）。
- 日期/數字格式跟著 culture 走（`CultureInfo`），時區已另有機制（各 app 的顯示時區設定），兩者不混。
