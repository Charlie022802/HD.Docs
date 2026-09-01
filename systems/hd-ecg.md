# HD.Ecg

DICOM ECG Waveform 的讀取與波形繪製。**不是獨立服務，是一個函式庫** —— 唯一的消費者是
DicomWeb 的 `/rendered`（波形那一類），沒有自己的主機、埠或部署單元。

- **原始碼**：`D:\Dev\HyperDigital\HD.Ecg`（Forgejo `charlie/HD.Ecg`，GitHub 鏡像）。2026-09-01 建立，是第 12 個 repo。
- **授權**：Apache 2.0（與上游一致）。`NOTICE` 逐項列出修改，見下方「來源」。
- **輸出**：PNG（看）／PDF（印）／SVG（嵌網頁）。

## 來源與「搬」的代價

程式碼搬自公司內部的 `EcgConverter`（同事以 ECGToolkit 為基礎移植到 .NET 10、
DICOM 外掛以 fo-dicom 重寫）。**只搬了「讀 DICOM waveform → 畫圖」所需的閉包**，
其餘格式（Sierra／aECG／ISHNE／MUSE-XML）、批次管線與 Blazor 後台都沒有帶進來。

> **搬過來就是分岔。** 上游之後修的 bug 不會自動流到這裡，反之亦然。
> 這是「搬」相對於「引用」的真正代價 —— 不是路徑問題，是維護權的歸屬。
> （已與同事講好。）

## 三種輸出的取捨

| 格式 | 大小（實測 12 導程）| 特性 | 何時用 |
|---|---:|---|---|
| PNG | 291 KB | 點陣。小字級下字型渲染比路徑填色清楚 | 看 |
| PDF | 72 KB | 向量，**列印尺寸精確**；文字是路徑，**不可選取** | 印 |
| SVG | 120 KB | 向量，文字可選取可搜尋，可進 DOM 套 CSS | 嵌網頁 |

**為什麼 ECG 特別需要向量**：心臟科醫師拿卡尺量紙本上的間期，25 mm/s 必須是紙上真實的
25 毫米 —— PNG 列印出來的尺寸不保證。

**PDF 的文字為什麼是路徑**：SkiaSharp 的 PDF 後端**完全不做字型子集化** —— 實測畫一個中文字
與畫五個中文字，嵌進去的位元組數完全相同（13,929,553），它就是把整份字型塞進去。
一份二十個字的報表因此要背 13.9 MB。改成向量路徑後是 96 KB（145 倍小），而且仍然是向量。
`tools/EcgRenderProbe -- pdf-font <資料夾>` 保留了那個決定性的實驗，換 SkiaSharp 版本時可重跑。

## ⚠️ 部署前提：Linux 主機要有字型

開發機（Windows）上永遠是好的，所以**只會在部署到 Linux 時才現形**。

```bash
sudo dnf install -y fontconfig freetype google-noto-sans-cjk-vf-fonts   # RHEL 9/10
```

**① 缺 `libfontconfig`／`libfreetype`** → 繪製直接失敗並回明確錯誤。**這個是吵的**，看得到。

**② 缺 CJK 字型 → 這個是安靜的，比較危險。** 波形照樣畫得出來，標籤自動退回英文（良性降級），
但**病人姓名沒有英文可退，會變成一排豆腐**。全程沒有錯誤、沒有警告，HTTP 照樣 200，
只有拿到圖的人看得到。而且**只有全新環境會踩到** —— 既有機器裝過就不會再犯，
所以「既有機器升級沒事」證明不了什麼。

實測：`.199` 初次部署時是 `Latin`（37 個字型、`fc-list :lang=zh-tw` 為 0）。
這個差異是靠「本機 266 KB vs 伺服器 282 KB」的 **6% 檔案大小差**追出來的 ——
只看「有沒有回 200」會完全錯過。

**所以呼叫端要把字型狀態暴露到健檢裡，別只寫進部署文件**（文件會被漏掉，健檢不會）：

```bash
curl -s http://192.168.68.199:5080/health | jq -r .ecgFontCoverage   # 要是 Cjk
```

**SVG 是三種輸出裡唯一不受這個影響的** —— 文字是 `<text>` 元素，由瀏覽器用自己的字型畫。
需要在沒把握的主機上出圖時，SVG 是最安全的一種。

## 顯示參數

排版引擎（`EcgLayout`）三種輸出共用，所以參數對三種都有效。DicomWeb 以 query string 開放：

| 參數 | 可用值 | 預設 |
|---|---|---|
| `layout` | regular／3x4／3x4+1／3x4+3／6x2／median | `3x4+1` |
| `filter` | none／diagnostic／muscle／display05 | `diagnostic`（0.05–40 Hz）|
| `grid` | none／1mm／5mm | `1mm` |
| `palette` | red／blue／green／gray | `red` |
| `speed` | 5–200 mm/s | `25` |
| `gain` | 1–40 mm/mV | `10` |
| `zoom` | 0.25–4 | `1` |
| `info` | true／false | `true` |

**報表第一列印著實際生效的 `speed`／`gain`／濾波**，跟真的心電圖紙一樣 —— 這是敢把濾波
開放給客戶端的前提：拿到圖的人看得出來它是用什麼設定畫的。

> ⚠️ `filter=display05`（0.5 Hz 高通）**會扭曲 ST 段**，可能製造出不存在的 ST 抬高或下降，
> 而 ST 正是判讀心肌缺血最關鍵的部分。它存在的理由是與機器印出的報表比對，**不是拿來判讀**。
> 上游在濾波標籤裡就帶了警語，所以圖上看得到。

## 去識別

`EcgViewOptions.Anonymize` 會遮蔽姓名（畫成 `(anonymised)`）與病歷號。
**圖上那兩個欄位是我們自己畫的，所以遮得掉** —— 對照封裝 PDF：那是一份完整的文件，
病人資訊在內容裡不在 DICOM tag 上，改不了，DicomWeb 只能拒絕（403）。

DicomWeb 在金鑰綁了匿名規則時會開這個旗標，**且不吃 query 參數** —— 那是權限不是顯示偏好。

## 建置

```
dotnet build HD.Ecg.slnx -c Release
```

全部 `net10.0`。`Directory.Build.props` 刻意關閉 nullable 與 implicit usings、開啟 unsafe，
並壓下一批舊警告 —— 那是 2004 年風格原始碼的必要條件，不是疏忽。

| 專案 | 行數 | 說明 |
|---|---:|---|
| `EcgConverter.Core` | 21,396 | 中介模型與轉換框架。零外部相依 |
| `EcgConverter.Formats.Dicom` | 3,843 | DICOM Waveform 讀寫（fo-dicom）|
| `EcgConverter.Rendering` | 1,375 | 繪圖抽象層 ＋ **SVG 實作**（不碰 SkiaSharp）|
| `EcgConverter.Rendering.Skia` | 485 | SkiaSharp 繪製器，PNG 與 PDF |

`Core` 佔 79% 且拆不開；裡面含有我們用不到的格式（SCP-ECG／CSV／RAW），**刻意先不動** ——
砍了會更難跟上游對齊，而且容易砍到間接相依。

## 相關

- [dicomweb.md](dicomweb.md) — 波形怎麼接進 `/rendered`、分流順序、快取鍵、匿名
- `HD.Pacs.DicomWeb/tests/manual/HD-DicomWeb-rendered.postman_collection.json` — 顯示參數的實驗資料夾
