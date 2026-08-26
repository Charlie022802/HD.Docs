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

## 漏譯怎麼查（2026-08-26 教訓）

**「`IStringLocalizer` 找不到條目就原樣回傳 key」是這套設計的靜默失敗模式。** 本專案的 key 就是
繁體中文本身，所以漏譯不會有任何錯誤、不會有紅字，只會在非繁中介面上默默露出中文——
使用者看到的和「這一頁沒做多語系」一模一樣，分不出是哪一種。

**掃 `L["..."]` 只找得到一半。** 動態查表（`@L[StatusLabel(r.Status)]`、`@L[g.Title]`、
`@L[ScopeCatalog.Label(sc)]`）裡放的是執行期字串，正則抓不到。2026-08-26 連續踩三次：

| 現象 | 真正的原因 |
|---|---|
| 主控台的裝置授權頁整頁沒翻 | 60 個 key 從沒進過 resx（那頁後來才加） |
| API 金鑰的權限名稱**任何語言**都是繁中 | `ScopeCatalog.Label()` 回寫死的字串，**根本沒經過 localizer** |
| Export Job 只有「錯誤」沒翻 | 它在 `CommonStrings`，而 `@L[...]` 查的是 `UiStrings`，**兩本不通** |

**該怎麼查**（五項都要，缺一項就會漏）：

1. 掃 razor 的 `L["字面量"]` 對 resx——**正則要同時吃 `L["k"]` 與 `L["k", 參數…]` 兩種**。
   只比對到 `"]` 的話會漏掉帶參數的呼叫（`L["共 {0} 位", n]`），那是 2026-08-26 第四次踩到
   同一個盲點。可用的樣式：`L\["([^"]+)"\s*(?:\]|,)`。
2. `grep 'L\[[^"]'` 找出**所有動態查表點**，逐一枚舉它們的可能值再比對。
   （主控台九處、DicomWeb 兩處；來源多半是 C# 的 `switch` 對應表或 `ScopeCatalog` 這類目錄。）
3. **三個語言的 key 集合必須完全一致**——只補其中一個，另外兩個就會露出中文。
4. 值裡**還含中文的英文條目**＝實際上沒翻（用 CJK 正則掃 `.en.resx` 的 value）。
5. **`C[...]`（CommonStrings）要分開掃**——它是另一本 resx。同一頁裡 `@L[...]` 過關不代表
   `@C[...]` 也過關。實例：`@C["載入中"]…` 把省略號寫在查表外面，但 CommonStrings 的 key
   是 `載入中…`（含省略號），於是查不到——正確作法是改用既有的 key，不要為了標點多建一個。

修好掃描後回頭重掃，一次挖出兩個**既有**的漏譯（不是當次改動造成的）。
所以掃描本身也要驗：拿一個你知道有漏的頁面試過，再相信它的「零缺漏」。

**跨 resx 的同名陷阱**：同一個中文詞在兩本 resx 可能是兩種意思。實例：「操作」在
`CommonStrings` 是表格的操作欄（Actions）、在 `UiStrings` 是稽核事件的分類（Operation）——
沿用會翻錯。加新條目前先比對兩本有沒有同 key 不同值，刻意不同的要用 resx 的 `<comment>` 註明。

**跨產品用詞一致**：同一個詞在兩支管理介面出現兩種講法，使用者會以為是兩個不同的東西。
補新翻譯時優先沿用另一支既有的譯文（DicomWeb 的系統資訊視窗 27 個 key 裡有 22 個是這樣來的）。

## 備註

- Blazor Server culture 是 per-circuit：cookie 方案在重整後生效即可，不追求即時熱切（成本高、價值低）。
- 日期/數字格式跟著 culture 走（`CultureInfo`），時區已另有機制（各 app 的顯示時區設定），兩者不混。
