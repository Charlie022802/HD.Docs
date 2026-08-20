---
name: reference_fodicom5_client
description: "fo-dicom 5 兩顆「直接 new 會出事」的坑:DicomClient 不可直接 new(必 NRE,用 Factory);DicomImage 直接 new 靠靜態 provider 找 ImageManager,Generic Host 沒接上→AsSharpImage 回 null"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 13e6b6ed-984d-4c27-aed8-2170077bfa02
  modified: 2026-08-17T14:08:51.940Z
---

**fo-dicom 5 的 `FellowOakDicom.Network.Client.DicomClient` 不可直接 new**(2026-08-10 .191 實案,HD.Net10 `a08bde4` 全修):

- `new DicomClient(host, port, null, callingAe, calledAe, null, null, null, null)` — 建構式**直接解參考** loggerFactory 等參數 → 必 NullReferenceException,host 有沒有註冊 AddFellowOakDicom 都救不了。
- 正解:`DicomClientFactory.Create(host, port, useTls: false, callingAe, calledAe)`(工廠自 fo-dicom 服務容器解依賴)+ host 的 `ConfigureServices` 要 `services.AddFellowOakDicom()`。
- 症狀曾以「DicomServiceManager watchdog C-ECHO failed NRE 每 3 秒一發」現形;DicomTransmit/DicomRetrieve/MwlCFind/AutoFetching 同款(HD.Net10 六個呼叫點已全改工廠)。
- **舊 fo-dicom 4(`Dicom.*` 命名空間)的 `new DicomClient(host, port, false, ...)` 是另一顆類別、簽章不同,不受影響**——HD.Net10 兩代並存(HD/DicomCore 的 SCU 類是舊代),看 using 分辨。

**🔑 第二顆同類的坑:`new DicomImage(file)` 的 ImageManager(2026-08-17 .191 實案,HD.Net10 `8bd3c3d`)。** `DicomImage` **可以**直接 new,但它 render 時是靠 fo-dicom 的**靜態 ServiceProvider** 找 ImageManager——**`ConfigureServices` 裡的 `services.AddFellowOakDicom().AddImageManager<ImageSharpImageManager>()` 只設定 host 的 DI,Generic Host 這條路沒把靜態 provider 接上** → fallback 到預設 `RawImageManager` → 它產生的 `IImage` 不是 `ImageSharpImage` → **`iimage.AsSharpImage()` 回 null,接著在別處 NRE**(無頭錯誤,完全指不出真正原因)。

**正解:照 Viewer/TestClient 的模式明確 `new DicomSetupBuilder().RegisterServices(s => s.AddFellowOakDicom().AddImageManager<ImageSharpImageManager>()).Build()`。** 兩份設定並存沒問題(host DI 給 BackgroundService、靜態 provider 給 `new DicomImage`)。**對照表**:Viewer/TestClient 有 DicomSetupBuilder ✓;DicomWeb 走 ASP.NET Core(`builder.Services.AddFellowOakDicom()`)也沒事 ✓;**只有 HD.MediaPackage(Generic Host + UseSystemd)沒接** ✗。

這個缺陷躺很久沒人發現,因為 **JPEG 路徑從未被啟用**(`onlyJpeg` 沒有設定來源)而 **DICOM 路徑不做 render**。防呆已加:`AsSharpImage()` 回 null 時丟出帶「實際 IImage 型別」的訊息。**日後任何服務要用 fo-dicom render(轉圖/縮圖/燒字),先確認它有 DicomSetupBuilder。**

相關主 PACS 韌性修(同日):`HD.Json.DicomJsonConverter` 數值 VR 容錯(字串包數字/null 不再丟 Malformed DICOM json)+ `MapJobManager.GetJobs` 單筆隔離(壞 dataset 不再卡死整條 MAP_JOB 佇列,STUDY_CLOSE 實案)。見 [[reference_fodicom5_pixel]]、[[project_main_pacs_coerce_logging]]。
