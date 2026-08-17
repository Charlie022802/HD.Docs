# 影像看片（HD.DicomImageViewer / HD.DicomImageViewer.Server）

桌面 DICOM 看片（WinForms）+ 進行中的 Server 化。

- **原始碼**：`D:\Dev\HyperDigital\HD.DicomImageViewer`（git）。net10-windows（WinForms）+ 共用 lib。
- 管線：fo-dicom 解碼 → System.Drawing (GDI+) 軟體繪製。核心 `HD.DicomImageViewer.Core`。

## 桌面看片現況
- **顯示管線優化**：8 點計畫，1/2/4/6/7/8 完成 + 3 部分（cine 預取；跨 instance CT/MR 待）。重繪快取、W/L 拖曳降解析度預覽、記憶體預算 LRU、GDI handle 洩漏修正、Timer 30fps。剩：跨 instance CT/MR 預取（需設計審查）。
- **MPR 3D**：2D + 3D 皆完成；3D 走 OpenTK.GLControl（GLSL raymarch）。
- 狀態列：ZoomFactor/PixelValue 等移到 StudyControl 底部。

## Viewer Server / ViewerWebApi（進行中）
新專案 `HD.DicomImageViewer.Server`（ASP.NET Core net10，Blazor Server 管理 UI + Web API），部署為 Linux systemd。目的：把客戶端「直連 Postgres」收到伺服器後面（**DB 密碼只留伺服器**）+ 管理後台。

### 目標架構（2026-08-17 定案）
**看片端只跟兩個後端說話**，不再直接碰資料庫：

```
Viewer ──► ViewerWebApi   登入 / 查詢 / 設定 / QC / KeyImage / 診斷包上傳
       └─► HD.DicomWeb    影像（WADO-RS）
```

舊的 `DownloadHost`（DICOMServer）退場，`localconfig.json` 從「DB 帳密 + DownloadHost」瘦成兩個網址。

- **部署＝hdctl，跟 .191/.199 同一套**。**先獨立成自己一個元件**（`viewerapi`），日後要不要跟別的元件整併再說。
  每間醫院都會裝這一支——這點反過來讓「診斷包上傳」有地方落腳（見下）。

### 現況盤點（2026-08-17 實查）
- **Server 端 API 已完成**（薄代理既有 stored proc）：`Auth` / `Query` / `KeyImage` / `Config` / `QC` 五個 controller。與現有客戶端契約相容（login cookie、access）。
- **客戶端側幾乎還沒接**：`ViewerApiGateway` 開關做好了，但**只有 `DicomQuery` 裡 1 處**真的走 API；
  **其餘 56 處仍直連 DB**（`DicomQuery` 26、`QualityControl` 17、`SystemConfig` 11、`AccessDefinition` 2）。
  → **工作量全在客戶端這 56 處**，伺服器端幾乎就緒。
- Blazor Users/Clients/Settings 頁、`/account/login` CSRF 待補。

### 施工順序決策
**診斷包上傳（REQ-016）先做、不排在 56 處遷移後面。** 它是這支服務上最獨立的一塊——不碰既有查詢、不改 stored proc、失敗了也只是少一份診斷資料。
拿它當這支服務**第一個真正上線的功能**，先把「進到每間醫院、hdctl 部署與更新」這條路走通；
之後查詢遷移就是往一台已經在跑的服務上加端點，風險小得多。

## 待辦
- 診斷包上傳端點（REQ-016）＋ hdctl `viewerapi` 元件（第一鏟）。
- 客戶端側 56 處改走 API（上述）。
- 跨 instance CT/MR 預取（顯示管線最後一項）。
- 接入共用日誌。
