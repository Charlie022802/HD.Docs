# 影像看片（HD.DicomImageViewer / HD.DicomImageViewer.Server）

桌面 DICOM 看片（WinForms）+ 進行中的 Server 化。

- **原始碼**：`D:\Dev\HyperDigital\HD.DicomImageViewer`（git）。net10-windows（WinForms）+ 共用 lib。
- 管線：fo-dicom 解碼 → System.Drawing (GDI+) 軟體繪製。核心 `HD.DicomImageViewer.Core`。

## 桌面看片現況
- **顯示管線優化**：8 點計畫，1/2/4/6/7/8 完成 + 3 部分（cine 預取；跨 instance CT/MR 待）。重繪快取、W/L 拖曳降解析度預覽、記憶體預算 LRU、GDI handle 洩漏修正、Timer 30fps。剩：跨 instance CT/MR 預取（需設計審查）。
- **MPR 3D**：2D + 3D 皆完成；3D 走 OpenTK.GLControl（GLSL raymarch）。
- 狀態列：ZoomFactor/PixelValue 等移到 StudyControl 底部。

## Viewer Server（進行中）
新專案 `HD.DicomImageViewer.Server`（ASP.NET Core net10，Blazor Server 管理 UI + Web API），部署為 Linux systemd。目的：把客戶端「直連 Postgres」收到伺服器後面（**DB 密碼只留伺服器**）+ 管理後台。

- **Server 端 API 已完成**（薄代理既有 stored proc）：query / keyimage / config / qc。與現有客戶端契約相容（login cookie、access）。
- **未做 = 客戶端側**：客戶端要連兩後端（app-server 走登入/查詢=新 ApiBaseUrl；DICOMServer 走 WADO=現有 DownloadHost）→ 拆兩個 ViewerWebApiClient；DicomQuery/SystemConfig/QualityControl 改走 API（gateway 判斷有設 ApiBaseUrl 才啟用、否則維持直連 DB）；Blazor Users/Clients/Settings 頁、/account/login CSRF 待補。

## 待辦
- 客戶端側改走 API（上述）。
- 跨 instance CT/MR 預取（顯示管線最後一項）。
- 接入共用日誌。
