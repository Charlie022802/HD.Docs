---
name: project-display-pipeline-optimization
description: Ongoing plan to optimize the DICOM image display pipeline (GDI+/fo-dicom); points 1 & 2 done
metadata: 
  node_type: memory
  type: project
  originSessionId: 67bc2ae6-64eb-431b-aeab-11935a1b18ab
---

影像顯示管線優化計畫。管線為 fo-dicom 解碼 → System.Drawing (GDI+) 軟體繪製。核心檔案：[[project-dicom-status-bar]] 專案 `HD.DicomImageViewer.Core`：`Core/Controls/ImageControl.Drawing.cs`(OnPaint)、`Core/ObjectElement.ImageRender.cs`(LoadDicomImage/RenderImage/DicomBitmaps 快取)、`Manager/ShutterManager.cs`、`Imaging/Invert.cs`、`Core/Controls/LayoutControl.cs`(100ms Timer 刷新)。

分析出 8 個優化點（依影響排序）：
1. ✅ 每次重繪都整張複製 bitmap（new Bitmap/Invert）→ 已加顯示 bitmap 快取，key=來源bitmap參照+invert+flip+shutter簽章
2. ✅ Invert/Shutter 每幀重算 → 摺進快取；ShutterManager.Apply 無 Static/Locked shutter 時提早 return；水平翻轉移進快取建立階段（原本 DrawImageToScreen 每幀 RotateFlip）
3. ✅(部分) 解碼/RenderImage 在 UI 執行緒且無相鄰 frame 預取 → 已做「同一 instance 多幀(US/XA cine)背景預取」：ObjectElement 加 renderLock 串行化 RenderImage、TryPrefetchFrame(背景、Monitor.TryEnter 永不阻塞 UI、不建立 image)、ImageControl.PrefetchNeighborFrames(±8 frame、Task+CTS、掛在 PostFrameChanged)；W/L 改變改為 InvalidateAllFramesLocked 作廢所有 frame(修正重看已快取 frame 殘留舊 W/L 的語意問題)。限制：跨 instance(CT/MR 換 slice)預取未做——因背景建立 image 會動到 UI 的 StatusCollection(在 dicomImageLock 內)，需先讓 image 建立變安全，屬後續項目
4. ✅ W/L 拖曳每次整張重 render → 已做「拖曳降解析度預覽」：ObjectElement.RenderWindowLevelPreview(以 ImageScale*0.5 快速 render、用完還原 image 的 Scale/W-L、不寫主快取)；ImageControl paint 於 imageStatusManager.Windowleveling 且此控件 W/L 與已渲染不同時走 DrawWindowLevelPreview(畫進與正常相同的 destination 矩形、不動 originalImage 故 overlay 座標不偏移)，放開滑鼠 windowleveling=false 走正常 full-res。座標轉換(convertToOrigin 等)重度依賴 originalImage.Width/Height，故降解析度絕不可改 originalImage 尺寸——這是本項設計核心
5. ⛔ 每幀對全解析度做 HighQuality 縮放 → 互動時降插補 —— 已決定「不做」(2026-07-05)：因 DicomImage.Scale=ImageScale，快取 bitmap 已按版面預縮放到接近顯示尺寸，g.DrawImage 每幀非把 12MP 縮成 1MP，自適應插補效益有限
6. ✅ DicomBitmaps[] 每 frame 點陣圖無上限不回收 → 已加記憶體預算制 LRU（ObjectElement.ImageRender.cs：MaxDecodedBytesPerObject=256MB、frameLru、StoreFrameBitmap/TouchFrame/EvictIfNeeded/ClearFrameCache），永不淘汰目前 frame；所有寫入點導向 StoreFrameBitmap；順帶修掉 ApplyWindowLevel 舊 bitmap 未 Dispose 的洩漏。單幀影像不受影響。限制：只解決單一 instance 內多幀（US cine 等）；CT/MR volume 那種「多個單幀 instance 各自常駐」的跨 instance 記憶體是另一個更大的項目（未做）
7. ✅ overlay 每幀 new Font/Pen/Brush 且部分未 Dispose → GDI handle 洩漏 → 已用 using 修正 DrawBorder/DrawTagInformation/DrawScaleToScreen/DrawLinkStatus/DrawImageOrientationPatient/DrawSpatialPointToScreen/DrawReferenceLinesToScreen/DrawDynamicStatus（GetFont/GetSolidBrush 皆回傳 new 物件，可安全 Dispose）
8. ✅ 每 tile 一個 100ms Timer 輪詢 + 一 tick 一筆 → 改「聰明版」：保留 Timer(仍是背景執行緒→UI 的 marshaling 邊界 + fps 上限)但 LayoutControl 間隔 100ms→33ms(30fps、RefreshIntervalMs 可調)、每 tick 一次消化所有待刷新(合併一次重繪)、refreshList(List)改 Interlocked refreshPending 旗標(修 Parallel.ForEach 多執行緒 race)。注意：InsertRefreshJob 被 ParallelForEachImageControl 從多執行緒呼叫，所以不能直接在其中碰 WinForms Timer/Invalidate，Timer tick 是必要的 UI 執行緒邊界

1、2 已於 2026-07-05 完成、建置 0 error、實機驗證正常。下一步候選：第 3（背景解碼+預取，對捲動/cine 順暢感受最直接）或第 6（大檔記憶體上限）。
