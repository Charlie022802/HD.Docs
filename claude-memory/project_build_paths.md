---
name: project-build-paths
description: Which HD.DicomImageViewer copy/solution is the active one to edit and build
metadata: 
  node_type: memory
  type: project
  originSessionId: dc8af855-0b75-4ea2-84b4-e4b433b3f612
---

Two separate copies of the DicomImageViewer source exist on this machine — do NOT confuse them:

- **ACTIVE (edit + build here):** `D:\Dev\HyperDigital\HD.DicomImageViewer\` — SDK-style, `net10.0-windows`. Solution: `D:\Dev\HyperDigital\HD.DicomImageViewer\HD.DicomImageViewer.sln`. Core project under `...\src\HD.DicomImageViewer.Core\`.
- **STALE (ignore):** `C:\Users\yang\source\repos\HD.Desktop\` — old `TargetFrameworkVersion v4.8` (.NET Framework) copy, not kept in sync. Building `HD.Desktop.sln` yields hundreds of MSB3822/MSB3823 resx errors and does NOT contain current edits.

Always build with `dotnet build "D:\Dev\HyperDigital\HD.DicomImageViewer\HD.DicomImageViewer.sln"`.
