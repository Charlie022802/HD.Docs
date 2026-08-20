---
name: reference_dpi_mode
description: App runs default HighDpiMode (SystemAware) with no explicit config; runtime-added controls need manual DPI handling
metadata: 
  node_type: memory
  type: reference
  originSessionId: 10efd79d-b98a-455d-b25d-f92ac8364777
---

主程式 `HD.DicomImageViewer/Program.cs` 只呼叫 `Application.EnableVisualStyles()` + `SetCompatibleTextRenderingDefault(false)`，**沒有** `ApplicationConfiguration.Initialize()` / `SetHighDpiMode`，也無 app.manifest → 吃 WinForms 預設 HighDpiMode（SystemAware）。MainForm 是 `AutoScaleMode.Font`。

後果：designer 控制項會被 form 的 Font-AutoScale 在 InitializeComponent 時縮放；但**執行時才 new 出來、且 `AutoScaleMode.None`／固定 px 尺寸的控制項不會跟著縮放**，在 >100% DPI 會顯得偏小、內容偏上。已修過的例子：`AppHeaderBar`（改成用 `DeviceDpi/96` 自行縮放高度/logo/按鈕，並用實際 Height 置中）。

**How to apply:** 之後任何「執行時建立」的 UI（tab、header、toolbar 固定鍵等），若要在高 DPI 下正確，需自行依 `DeviceDpi` 換算像素尺寸；點數(pt)字型不要再乘 scale（GDI+ 已依 DPI 放大，會 double-scale）。若之後決定全面統一，可評估在 Program.cs 明確設定 High-DPI 模式（全域改動，需整體回歸測試）。
