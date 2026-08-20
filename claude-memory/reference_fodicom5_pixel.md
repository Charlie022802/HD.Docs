---
name: reference_fodicom5_pixel
description: "fo-dicom 5 pixel-read gotcha — ObjectElement.Dataset is metadata-only (no PixelData); read pixels from LocalPath file, transcode if compressed"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 10efd79d-b98a-455d-b25d-f92ac8364777
---

底部狀態列 HU/pixel 空白的真正根因（2026-07 查到）:**`ObjectElement.Dataset` 是查詢/tree 來的 metadata dataset,不含 PixelData tag**。真正像素在 `LocalPath` 檔案裡（`image`(DicomImage) 也是從 LocalPath 開的,所以畫面正常）。

fo-dicom 4 舊碼讀 `image.PixelData`（檔案來、有像素）;fo-dicom 5 的 `DicomImage` 不再公開 `.PixelData`,遷移時被改成 `DicomPixelData.Create(this.Dataset)` → metadata 沒像素 → `TryGetPixelValue` 靜默回傳空、**不丟例外**(log 乾淨,極難查)。

**修法（已實作於 `ObjectElement.GetSourcePixelData()`）:** Dataset 有 PixelData 就用它,否則 `DicomFile.Open(LocalPath).Dataset`;若 `InternalTransferSyntax.IsEncapsulated`(JPEG/JPEG2000/RLE 壓縮)先 `DicomTranscoder(ts, ExplicitVRLittleEndian).Transcode(ds)`;結果快取(`_sourcePixelData`,Dispose 時清)。四個像素讀取點共用。診斷關鍵:in-bounds 卻空、又無例外 → 先懷疑「來源 dataset 沒像素」。

**單位顯示（`TryApplyModalityLut`）:** 只要有 RescaleSlope/Intercept 就套用,單位取 Rescale Type (0028,1054);CT→HU;有 rescale 無單位→"U";無 rescale(MR/US)→原始像素 "xxx px"。沒做 PET SUV(需劑量/體重/半衰期,工程大,使用者暫不要)。

專案:fo-dicom 5.2.6 (net10)。相關:[[project_display_pipeline_optimization]]。
