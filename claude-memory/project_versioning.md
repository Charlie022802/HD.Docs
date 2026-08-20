---
name: project-versioning
description: HD.DicomImageViewer version is set in src/Directory.Build.props (not AssemblyInfo.cs); currently 2.2.0
metadata: 
  node_type: memory
  type: project
  originSessionId: 67bc2ae6-64eb-431b-aeab-11935a1b18ab
---

HD.DicomImageViewer 版本號集中設在 `HD.DicomImageViewer/src/Directory.Build.props`（`<Version>`/`<AssemblyVersion>`/`<FileVersion>`/`<InformationalVersion>` + `IncludeSourceRevisionInInformationalVersion=false` 以免 InformationalVersion 被附加 git hash）。SDK-style 專案由這些 MSBuild 屬性自動產生版本 attribute。

**不要改 AssemblyInfo.cs**：舊 .NET Framework 的 `Core/Properties/AssemblyInfo.cs` 已由各 csproj `<Compile Remove>` 排除，改了不生效。要改版只改 Directory.Build.props 一處。

沿革：.NET Framework 舊版 2.0.0.85 → 遷移到 .NET(net10) 後設為 2.1.0（2026-07-05）→ **2.2.0**（2026-07-13，加入 MPR 3D 重建、CPU/GPU 軟體渲染 fallback、狀態列即時 HU/pixel）。

範圍注意：該 props 在 `src/`，套用到 src 底下所有專案（含 HD.WebApi、OverlayPreview）。若這些要獨立版本需加 Condition 或改放位置。相關：[[project-build-paths]]

**exe 圖示**也集中設定：`src/Directory.Build.targets`（用 .targets 而非 .props，因需在 OutputType 定義後才用 Condition 判斷 Exe/WinExe）將所有可執行檔的 ApplicationIcon 設為 `src\hyper_logo64.ico`。5 個 exe：HD.DicomImageViewer、Executer、LinkClientDesktop、Media、OverlayPreview。Library 不套用。驗證用 `dotnet msbuild <csproj> -getProperty:ApplicationIcon`。
