---
name: project_mpr_vtk
description: "MPR 2D + 3D volume rendering — done via OpenTK (GLControl + GLSL raymarch), replacing the old VTK/Activiz"
metadata: 
  node_type: memory
  type: project
  originSessionId: 10efd79d-b98a-455d-b25d-f92ac8364777
---

HD.DicomImageViewer.Mpr:2D 三平面 MPR(Axial/Coronal/Sagittal + MIP,`MprVolume` 用 `short[,,]`)+ 3D 體積渲染,**均已完成可用**。

**3D 用 OpenTK(不是 VTK)。** 舊版是免費 Activiz.NET 5.8,但它是 .NET-Framework mixed-mode,net10 載不動。改用 **`OpenTK.GLControl` 4.0.2**(namespace 是 `OpenTK.GLControl`,不是 OpenTK.WinForms)。`Vtk/VtkVolumePanel.cs` 現在是 GLControl + fragment shader ray marching(3D texture R16 + front-to-back DVR + 4 個 preset 顏色/密度 + 沿 Y 裁切),滑鼠左鍵旋轉、滾輪縮放。公開 API 沿用舊 stub,MprViewerForm 未動。⚠️ shader 必須純 ASCII(中文註解會讓 AMD 驅動編譯失敗、報錯行號還會偏)。

**DPI:** OpenTK 的 GLFW 初始化會改 process/thread DPI awareness,造成主視窗縮小、字體改變、MPR 視窗在 150% 螢幕忽大忽小。解法:`Program.cs` 開頭用 `SetProcessDpiAwarenessContext(UNAWARE)` 硬鎖成 unaware(維持 app 原本外觀)。詳見 [[reference_dpi_mode]]。

**其他細節:** MPR 開窗 = 最大化在游標所在螢幕(`PositionOnCursorScreen`)。過場用既有的 `TransitionOverlay`(PMv2 執行緒、實體像素定位,DPI 正確),不要自己用 ProgressForm 算座標(會跑掉)。Volume 建立排除定位像:`ImageType` 含 LOCALIZER + 取多數方向當參考法向量(特殊影像可能在第一或最後張),比照 LinkManager 的 IsLocalizer。

未做(可選):梯度光影 shading、正式分段 transfer function、PET SUV。`ProgressForm.cs` 未被任何地方使用。
