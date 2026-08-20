---
name: project_dicomweb_thumbnail_cache
description: REQ-004 DicomWeb 縮圖/rendered 效能—現況盤點 + 記憶體快取設計(含 W/L 校正需可重轉)
metadata: 
  node_type: memory
  type: project
  originSessionId: 913e10e5-5ad9-400e-82d5-b8e1163936aa
  modified: 2026-08-05T18:09:07.520Z
---

REQ-004:DicomWeb 縮圖/rendered 加快取。承接 [[project_intake_slimming]] REQ-007(移除 hd-dicom-to-image 預生 JPEG 後,JPEG 全導 DicomWeb 即時 render)→ 此為「全面改去 HDDicomWeb」的**技術先決條件**(DicomWeb 供圖夠快才能取代 hd-web-server)。相關 [[project_immutable_original_coerce]] [[project_dicomweb_impl_split]]。

**現況盤點(2026-08-04, HD.Pacs.DicomWeb):**
- **生產 rendered/thumbnail 完全無快取**:生產走 `Infrastructure\DicomWeb\HdPacsWadoService.cs`(Dapper→HDPACS `RC_OBJECT`+`get_object_path()`;`ServiceCollectionExtensions.cs:65` 覆蓋 Application EF 版)。`GetThumbnailAsync`(:400)/`GetRenderedAsync`(:374)→`RenderFrame`(:498):每次 `DicomFile.OpenAsync`→fo-dicom `DicomImage.RenderImage().AsSharpImage()`→ImageSharp resize(ResizeMode.Max 只縮不放)→`JpegEncoder{Quality=85}`,零快取。thumbnail 固定 frame 1、尺寸靠 `?viewport=`(預設 128);**W/L 完全沒套用**(用 DicomImage 預設、且讀的是原檔非 DB 校正後 dataset)。
- **已有一套 pre-gen 縮圖 pipeline 但「錯棚」**:`Infrastructure\Workers\PostProcessWorker.cs`+`Domain\ThumbnailKeyResolver.cs`(key=`thumb/<sha[:2]>/<sha>.jpg`,只綁 SHA)+`PostProcessOptions.cs`(ThumbnailMaxDimension=128/Quality=75)。STOW 後 enqueue(`StowEndpoints.cs:87`)+ 每 30 分 catch-up sweep,寫 `IStorageBackend`(FileSystem `thumb/`)。**但**:①`appsettings.json` `PostProcess:Enabled=false` 關著;②綁 EF `PacsDbContext.InstancesSet`+`IStorageBackend`,與生產 legacy 堆疊不通—生產 STOW 給 `InstanceId=Guid.Empty`+`StorageKey=絕對路徑`,`FileSystemStorageBackend` 遇 rooted key 直接丟例外;③生產 `HdPacsWadoService` 根本不讀 `thumb/`。→ 對 EF WadoService 是接好待啟用,對生產是完全沒接+會炸。**決定:不救這套,走記憶體快取。**
- **唯一現役快取範本 `CoercedInstanceCache.cs`**:只快取「整份 DICOM 下載 byte[]」不碰影像;MemoryCache、SizeLimit 256MB(byte 計)、LRU、SlidingExpiration 30分、**key=SOP UID、version=`studyUid|seriesUid|物件 DATE_TIME_MODIFIED`**(校正/split-merge 自動失效)。singleton 註冊 `ServiceCollectionExtensions.cs:66`。REQ-004 照抄此模式。

**設計方向(記憶體 render 快取,仿 CoercedInstanceCache):**
- 切入點:`HdPacsWadoService` 的 `GetThumbnailAsync`/`GetRenderedAsync`—render 前查快取、miss 才算、算完存。
- key=`sopUid|frame|format|maxDimension`。容量 MemoryCache+SizeLimit(byte)+LRU。singleton 註冊在 CoercedInstanceCache 旁。
- **⚠️ W/L 校正需可重轉(2026-08-04 使用者提點,關鍵)**:原本以為「A3 後像素不可變→縮圖永久有效、key 只用 SOP UID」是錯的—**W/L(WindowCenter/Width 0028,1050/1051)是可校正的 metadata,校正後 render 應反映新 W/L**。故:①快取 **version 要綁物件 `DATE_TIME_MODIFIED`**(比照 CoercedInstanceCache),任何校正(含 W/L)bump 時間→快取自動失效→重轉,這就是「能重新轉」的機制;②要讓重轉真的變不一樣,**render 需套用 DB 校正後的 W/L**(把 RC_OBJECT.DATASET 的 W/L 疊到 dataset 再交 DicomImage render)—目前生產 render 讀原檔、不套校正 W/L,這是一個**功能增強**(rendered 尊重 coerce W/L),可與快取同批或另立。③可另加手動 cache-bust/強制重轉入口(選)。
- 純像素部分(無 W/L 影響時)本來就不會因 metadata 疊合而變,version 綁修改時間是安全上界(偶爾多失效一次可接受)。

**範圍決策(2026-08-04):W/L 校正工作流「目前還沒、未來預留」→ 這批只做純記憶體快取,version 綁 `DATE_TIME_MODIFIED`(失效機制先備好,未來 W/L 一校正就自動 miss 重轉);「render 套 coerce W/L」延後、等真的有工作流再補(架構已留路)。**

**實作完成(2026-08-04,build 過 + 單元測試 4/4 綠,未部署未整合驗):** ①新增 `Infrastructure\DicomWeb\RenderedImageCache.cs`(仿 CoercedInstanceCache:MemoryCache、SizeLimit **128MB**、LRU、30分 sliding;Entry(Version,Bytes,ContentType);TryGet(key,version,out)/Set(key,entry));②`ServiceCollectionExtensions.cs:67` 註冊 singleton(CoercedInstanceCache 旁);③`HdPacsWadoService` 主建構子加 `RenderedImageCache renderedCache`;`GetThumbnailAsync`/`GetRenderedAsync` render 前查快取→miss 才 RenderFrame→存,key=`sopUid|frame|format|maxDim`(rendered 用 "full"、thumbnail 用 maxDim)、version=`info.ObjectModified.ToString("O")`;④`ObjectInfo` 加 `ObjectModified`,GetObjectInfo 兩支查詢(sqlSimple+fallback)都補 `"DATE_TIME_MODIFIED" AS ObjectModified`。⑤單元測試 `tests\...\RenderedImageCacheTests.cs`(hit/miss/version失效/key不衝突)。**已 commit+push:HD.Pacs.DicomWeb `9dfa1ff`。整合驗證通過(2026-08-05,.199 新 build 連 .191 DB、圖從 NAS 讀)**:同一縮圖取兩次→**1st 664ms → 2nd 22ms(~30×)**、log `WADO thumbnail | 影像快取命中`、JPEG 128x128 3662B 一致。REQ-004 完成。 第二階段(選):pre-gen 改 legacy 相容磁碟快取(冷啟動/跨程序持久)。

**✅ 完成收案(2026-08-06):** RenderedImageCache 其實早已 commit(`9dfa1ff`,先前記「未 commit」為過時資訊),並隨 2026-08-06 部署上 .199。**生產整合驗證通過**:同一縮圖三連打 **1.164s→0.073s→0.043s(16~27×)**,快取命中明確。「選項2 吃 hd-dicom-to-image 的 .jpg」確認已死(REQ-007 服務移除)。剩選配:render 套 coerce W/L(等 W/L 工作流)、pre-gen 磁碟快取(第二階段)。
