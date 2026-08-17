# 看片版面狀態重構設計(Viewer Layout State)

狀態:設計定案、未動工(2026-08-12)。對象:`D:\Dev\HyperDigital\HD.DicomImageViewer`(WinForms net10 桌面看片)。
起因:若瑟醫院陳醫師需求 (4)「關閉歷史影像不要整個重舖版面」,追查後發現是版面狀態架構問題,需重構而非局部修補。

## 一句話

**把「哪一格在看什麼」從畫面控制項裡搬出來存成資料,控制項退化成單純的顯示器。**

## 問題根因

現行的三層版面(study 格 → series 格 → 影像格)都由 `LayoutManager` 管理,規則是「**沿用既有控制項、只增減差額**」:

```csharp
// LayoutManager.ChangeLayout
if (container.Controls.Count <= i)
    container.Controls.Add(createLayoutControl(...));   // 不夠才新增
else
    ((LayoutControl)container.Controls[i]).ControlIndex = ...;  // 夠 → 沿用既有實例
// 多的才 RemoveAt + Dispose
```

所以同一個 StudyControl 實例會被反覆重用,原本放 A 檢查、之後被指派成 B 檢查。而「這格在看什麼」只存在控制項身上,一被重新指派就沒了 —— **這就是為什麼任何版面變動都得先備份才能還原**(既有的 `LayoutRecordManager` 就是為此而生,用在「展開/收合序列」與「手動改版面」兩處)。

### 狀態散落現況

| 狀態 | 現在住哪 | 控制項重用時 |
|---|---|---|
| W/L、縮放、平移、翻轉、旋轉、反白 | `ObjectElementStatus`(資料層,在 tree 裡) | **保留** |
| record → SeriesRef 對應表 | `StudyElement.recordSeriesList`(資料層) | `InitializeRecord()` 清掉 |
| 這格顯示哪筆檢查 | `StudyControl.studyElement`(控制項) | 丟失 |
| 這格顯示第幾個 record | `SeriesControl.recordIndex`(控制項) | 丟失 |
| 捲到第幾張 | `ImageControl.objectIndx`(控制項) | 丟失 |
| 版面格數 | `ImageViewerForm.CurrentViewerLayout`(表單層,全格共用) | 被新檢查的 modality 設定覆蓋 |

而且「下一個序列該給誰」(`GetNextRecordIndex`)與「下一張影像該給誰」(`GetNextObjectIndex`)是**掃描整棵畫面控制項樹反推**的,狀態沒有正本。

### 觸發路徑

- **開歷史**:`OpenLinkStudies(isHistory:true)` → `AddStudies` → `ImageViewerForm.LoadStudy` → `InitializeStudy(element)` 對**所有格**塞同一筆檢查
- **關歷史**:HIS 目前送 `REFRESH_STUDY` → `RefreshStudy` 對**所有 `ShowViewer` 的螢幕**重跑 `InitializeLayout` + `LoadStudy`
- 開的時候有依 `studyDisplayMode` 限定螢幕,關的時候沒有 —— **開關不對稱**,這是原本沒被碰過的螢幕也跟著重舖的直接原因

註:程式裡沒有任何 study 層級的移除機制,`CloseLinkStudies` 走的是 `ClosePatient`(整個病人關掉)。

## 定案原則

1. **狀態與渲染分離**:控制項不再持有狀態,只負責把資料畫出來;重建控制項必須是無損的。
2. **「一邊」的單位是 study 格,不是螢幕**。雙螢幕=兩顆螢幕各一格;寬螢幕=同一顆螢幕切兩格。兩種硬體配置走同一套邏輯。
3. **雙螢幕當一顆用**:一般操作連動;只有歷史比對刻意單邊(醫師只想在一邊比對完就關掉)。
4. **序列排序對應表維持跨螢幕共用**(現況掛在 `StudyElement` 上就是對的,不搬)—— 換序、重複顯示要兩顆螢幕連動。
5. **不做 StudyControl 與檢查 1:1 綁定**。理由:series 層當初就是為了「任意換序 / 重複顯示」才引入 `recordIndex` 間接層,study 層 1:1 等於退回已被拋棄的設計;且「同一筆檢查出現在多格」現在就是預設行為。需要時比照 series 層加 study record 間接層即可(現無需求,結構留位置)。
6. **關閉歷史的規則只有一條,無例外**:

   > **關閉歷史 = 那一格回到被佔用前的樣子(含格數),其他格一律不動。**

7. **關的是「顯示」不是「資料」**:歷史檢查關掉後留在 tree 裡,不清記憶體 —— 再開很快,醫師也還能從標題列歷史下拉找到。

## 資料結構

每個 study 格有一本「冊子」,按檢查分頁記錄它對每筆檢查各自的看法:

```
第 1 格
  ├─ 現在貼的是:現檢查
  ├─ 對「現檢查」:切 2×2、看 series 0-3、捲到第 15 張
  └─ 對「歷史檢查」:(還沒看過)

第 2 格                              ← 被歷史佔用中
  ├─ 現在貼的是:歷史檢查
  ├─ 對「現檢查」:切 2×2、看 series 4-7、捲到第 8 張    ← 原封不動躺著
  └─ 對「歷史檢查」:切 2×2、看 series 0-3、捲到第 1 張
```

```csharp
// 掛在 ImageViewerForm(它本來就是「一顆螢幕 × 一個病人」的粒度)
class StudyCellState
{
    StudyElement CurrentStudy;                          // 這格現在貼哪筆
    Dictionary<StudyElement, CellSnapshot> Snapshots;   // 這格對每筆檢查各記一份
}

class CellSnapshot
{
    Size         SeriesGrid;      // 這筆檢查在這格切幾格 series
    SeriesSlot[] Slots;           // 長度 = SeriesGrid 格數
    int          FocusedSlot;     // 展開/收合用
}

class SeriesSlot
{
    int           RecordIndex;        // 這格顯示哪個 series(SeriesElement 由此導出)
    Size          ImageGrid;          // 這格切幾張
    int           FirstObjectIndex;   // 第一張的 index,其餘 = +1, +2 ...
    HangingSeries Hanging;            // 掛片條件(有的話)
}
```

### 為什麼 series/image 兩層不需要各自的狀態物件

因為它們幾乎都是 derived,沒有自己的正本:

- `ImageControl.studyElement` / `seriesElement` 都是往上走 parent chain 取得
- `SeriesControl.seriesElement` 是 `studyElement.GetSeriesElement(recordIndex)` 算出來的 → 正本是 `recordIndex`
- 同一個 series 格內的影像 index 是連續的(`LoadImages` 用 `loadIndex + i`) → 只需存第一張

不可再化簡的只有三個純量(哪筆檢查 / 哪個 series / 第幾張)+ 兩個格數。

### 記憶體成本:零

冊子是純資料(幾個參照 + 幾個 int),一筆檢查幾百 bytes。Bitmap 仍只存在於控制項、控制項仍然重用。

對照被否決的方案:「每筆檢查各自擁有一組 StudyControl」會讓每多開一筆檢查就多一整組原生解析度 bitmap
(`ImageControl.originalImage = new Bitmap(columns, rows)`,32bpp):CT/MR 約 1 MB/張、CR/DR 約 30 MB/張、乳攝約 54 MB/張,一格常見 4 張 → 多開一筆 CR 約 +120 MB。

## 分階段

### 階段 0:寬螢幕能用(**已完成 2026-08-12,單/雙螢幕皆實機驗證通過**;分支 `refactor/viewer-layout-state`,commit `fc4ee7d`)

寬螢幕(單一寬螢幕、study grid 1×1)的醫師現在**完全無法並排比對** —— `studyDisplayMode` 只能指到「哪顆螢幕」,開歷史就整個畫面被接管。

| 改什麼 | 說明 |
|---|---|
| 開歷史時只初始化目標格 | 現在對所有格重塞同一筆檢查,改成只動要放歷史的那格 |
| 格數不夠時自動擴充 | 只有 1 格時自動變 2 格:左留現檢查、右放歷史;關掉時收回 |
| 擴充時不要重設其他格 | `CurrentViewerLayout` setter → `UpdateLayout()` 會照新設定重設**每一格**的 `SeriesGrid`,要改成只設新格 |

實際動到:`ImageViewerForm.cs`(新增 `LoadStudyIntoCell` / `EnsureStudyCells` / `StudyCellCount`)、
`ImageViewerManager.Study.cs`(`AddStudies` 加 `isHistory` 參數 + 新增 `PlaceHistoryStudy`)、
`ImageViewerManager.Navigation.cs`(`OpenLinkStudies` 傳遞 `isHistory`)。`MainForm.cs` 最後沒有動到。

擴充判定:目標螢幕數 ≥ 所有 `ShowViewer` 的螢幕數,且該螢幕只有一格 → 擴充。
單螢幕成立、雙螢幕(目標 1 顆/共 2 顆)不成立,兩種硬體配置共用同一條規則。
掛片協定有自己的多格配置(`LastExam`),偵測到 `protocol != null` 就交回原路徑不介入。

註:`ChangeLayout` 本來就是「不夠才新增」,左格控制項實例會被保留 —— 真正的破壞點是後面的 `InitializeStudy` 對所有格重塞。所以這階段不依賴後面的重構。

**收益:寬螢幕從「不能用」變「能用」,立即可見。中途停下來不會半殘。**

### 階段 1:建立冊子(狀態搬家)(**已完成 2026-08-12,雙螢幕實機驗證通過**;commit `b61d60a`)

| 改什麼 | 說明 |
|---|---|
| 新增 `StudyCellState` / `CellSnapshot` / `SeriesSlotSnapshot` | 每個 study 格一本冊子,按 `StudyRef` 分頁 |
| 掛在 `ImageViewerForm` | 一顆螢幕 × 一個病人的粒度;`cellStates` **只增不減** |
| 搬進去 | 這格貼哪筆檢查、每個 series 格看哪個 record、**每個影像格**捲到第幾張、兩層格數 |
| `StudyGridBeforeExpand` | 單螢幕開歷史是「多長一格」而非佔用既有格,關閉時要收回格數而非還原內容 |

**不改顯示流程**——`ApplyCell` 此階段尚無呼叫端,冊子只寫不讀,行為與階段 0 一致。

實作時修正了一個設計錯誤:原本打算「只記第一張 + 推算連續」,但
`ImageControl.ChangeImageNumber` 在該格**有焦點**時只會動它自己(走 `LoadImage`),
不像 `SeriesControl.LoadImagesFrom` 會整格依序重排 —— 同一個 series 格內的張數**不保證連續**,
所以改成逐格記 `ObjectIndexes`,`ApplyCell` 也補上逐格校正。

驗證方式(排不掉的坑):`currentMonitor` 是 `Screen.AllScreens` 的列舉序(Windows 通常主螢幕排第一)
**不是左到右**,光看編號認不出是哪一顆螢幕,驗證時很容易在錯的螢幕上操作。log 已改成連
裝置名稱與左緣座標一起印。

### 階段 2:控制項改看冊子(分水嶺)——**跳過,留待日後**

階段 1 完成後 `ApplyCell` 已具備還原能力,所以直接做階段 3 就能滿足醫師需求,
階段 2 不是前置條件。它是架構純度上的正解(狀態只有一份正本、不再需要拍照),
但風險最集中,且不做也不影響已交付的行為。決定先讓需求落地、現場驗收,
之後有完整時間再單獨處理。

| 改什麼 | 說明 |
|---|---|
| 三層控制項改成從冊子讀 | 不再自己記,顯示時去冊子拿 |
| `GetNextRecordIndex` / `GetNextObjectIndex` 改查冊子 | 現在是掃描整棵控制項樹反推。**最容易漏的地方**,漏了就會有兩份互相打架的狀態 |

主要動到:`StudyControl.cs`、`SeriesControl.cs`、`ImageControl.cs`、`ImageViewerManager.Study.cs`

**最大、風險最集中。停在一半很難收,開工前確保有完整時間。**

### 階段 3:關歷史不重舖(**已完成 2026-08-12,單/雙螢幕實機驗證通過**;commit `724b4bc`)

**改造 `REFRESH_STUDY` 而非新增指令**——HIS 沒有「關閉某筆歷史」的概念,
它就是「回到原本要打的那筆檢查」,視同不看歷史了。因此不需要新 enum,HIS 端也不用改。

`RefreshStudy` 一律走 `ReturnToStudy`,三種格分別處理:

| 格的狀況 | 處理 | 依據 |
|---|---|---|
| 為歷史**擴充出來**的格(單螢幕) | 收回格數 | `StudyGridBeforeExpand` |
| 被歷史**佔用的既有格**(雙螢幕) | 用冊子還原(含 series 格數、每格張數) | `CellSnapshot` |
| **已在顯示目標檢查**的格 | 完全不碰 | — |

第三列是關鍵:醫師在歷史開著時對原檢查做的調整,因為那些格沒被碰到而自然保留。
全部都已經是目標檢查時整個是**無動作**,連送多次也不會把版面打掉重排。

原本 `RefreshStudy` 的全螢幕 `InitializeLayout` + `LoadStudy` + `ResetRecordIndex` +
`SwitchToDefault` 整段**移除**——那正是醫師抱怨的「重舖」來源。若日後真需要
「影像被 QC 改過要重讀」,應另做快取失效機制,而不是把版面打掉重排。

`ReturnToStudy` 只在選取的格被收掉時才重設 `SelectedImageControl`,否則保留醫師原本的焦點
——無條件重設會把焦點拉到第一張,等於動到「不該動的格」。

順修一個既有的靜默失敗:`studyDisplayMode` 指定的螢幕上**沒有 Viewer 視窗**時
(螢幕被拔掉／該螢幕設成不顯示／換機器後設定沒跟著改),原本得到空清單、後續迴圈整個不跑,
歷史悄悄不見且無任何提示,現場只會看成「調閱沒反應」。改為退回所有顯示影像的螢幕並記警告。
注意**「螢幕存在」與「該螢幕上有 Viewer 視窗」是兩件事**,警告訊息兩者都要列,只印螢幕清單會誤導。
`"None"` 是刻意不顯示,不在此列。

驗證證據:原檢查那格的四個影像格張數(30/28/27/0)在開歷史→關歷史→再開歷史全程一個數字都沒變;
該組數字不連續,也實證了階段 1 改成逐格記錄 `objectIndx` 的必要性。

**尚未做**:「展開/收合序列」與「手動改版面」仍走舊的 `LayoutRecordManager` 備份還原,
要等階段 2 才能簡化掉。

### 設定變更

`studyDisplayMode` 從「只能指定螢幕」擴充成兩種都能指,沿用掛片協定既有的「螢幕 + 格」定址詞彙
(`HangingProtocol.Screen[].Study[]` 本來就是這個結構):

| 設定值 | 意思 | 相容性 |
|---|---|---|
| `"DISPLAY6"`(舊值) | 整顆螢幕 | 現場設定不用動,行為同現在 |
| `{ Screen: 2, Cell: 1 }` | 第 2 顆螢幕的第 1 格 | 雙螢幕精確控制 |
| `{ Screen: 1, Cell: 1 }` | 同一顆螢幕的第 1 格 | 寬螢幕用這個 |

## 邊角案例

1. **`MergeSeries` 會改變 `SeriesElements` 集合本身**(`CreateMergeSeries()`),一旦合併,`RecordIndex` 就失效。要定義合併/取消合併時冊子怎麼遷移。
2. **格數變動時 `Slots` 長度要跟著變**。建議被砍掉的格狀態**留著**(成本極低),格數變回來就能還原。
3. **Cine 播放中切換檢查**要先停 `SeriesControl.timer`,否則會對著已換掉的 slot 繼續跑。
4. **`hangingSeries` 是配置不是狀態** —— 效果(W/L、旋轉)在 `ApplyHanging` 時已寫進 `ObjectElementStatus`,切回來**不要重跑**,否則會蓋掉醫師後來的調整。
5. **歷史開著時改另一顆螢幕的版面**(如螢幕1 從 2×2 改成 3×3):關閉時螢幕2 照原則 6 純快照還原(回 2×2 / 原本的 series),**不重算、不管螢幕1 現在如何**。可能與螢幕1 顯示重複的 series —— 可接受,因為 `GetNextRecordIndex` 的錯開本來就是載入當下算一次的一次性分配,系統從未保證不重複。
6. **同時開多筆歷史**:字典結構天然支援。HIS 實務上是一筆一筆給(其介面為條列式點選)。

## 風險

1. **沒有自動化測試**,回歸只能人工驗;動到的是版面核心,**掛片協定、乳房攝影模式、展開收合、版面工具**全部受影響。
2. 階段 0、1 中途停下不會半殘;**階段 2 是分水嶺**。
3. 開工前先把「每階段要人工驗哪些情境」列成清單。

## 相關

- 需求來源:`docs/todo.md`「影像看片」區 → 若瑟醫院陳醫師需求 (4)
- 連動鏈路:HIS → LinkClientDesktop(gRPC :5002)→ Executer(tray)→ NamedPipe `HD.DicomImageViewer.Pipe` → Viewer
