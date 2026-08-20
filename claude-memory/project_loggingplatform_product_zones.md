---
name: project_loggingplatform_product_zones
updated: 2026-08-10
description: LoggingPlatform 大改—產品分區(排障第一站);P1 總覽+專區、P2 連線紀錄皆已上線 .195;P3 治理**完成(2026-08-10 部署驗收)**:①服務維度=共用包自動附 properties.Service(進入點組件名,HD.Shared.Logging enrich;新資料才有)→專區「服務」下拉+/api/services+服務欄;②per-app 保留期=retention_per_app 設定(設定頁產品列「保留(日)」),Archive 每輪掃描清 hot/std(warn/audit 不動);③RBAC app_scope 進 claims("app"),產品卡過濾+專區守門;④金鑰治理=四把綁產品金鑰上崗(HDPacs→.191 /etc/hd/logplatform.env、HDDicomWeb→/etc/hd-pacs-dicomweb、HDExport→.199 /etc/hd-export;ViewerStation 那把待站台側換裝→之後才可停 ingest 的 INGEST_API_KEY fallback);ApiKeys 頁=建立改彈窗+複製鈕 hdCopyText http fallback(原 clipboard API 在 http 下炸 Blazor 電路)、金鑰可 Reveal 再看(key_enc)。Export 定案只裝 .199(.191 試裝品已移除)
metadata: 
  node_type: memory
  type: project
  originSessionId: 13e6b6ed-984d-4c27-aed8-2170077bfa02
  modified: 2026-08-10T08:52:46.155Z
---

**背景(2026-08-06):** 使用者定位 LoggingPlatform=服務人員**排障第一站**(任何產品出事先來這按產品看);原本只有單一「日誌查詢」頁靠 filter,亂。大改成**按產品分區**。

**✅ P1 已上線 .195(2026-08-06,commits `341123c`→`8d2e315`,部署驗證通過,畫面到位):**
- **產品總覽(新首頁 `/`)**:一產品一卡(24h 錯誤數/日誌量/最近錯誤/「無日誌」偵測=橘色);登入直接落在這(原導 /logs)。實戰即抓到 HDPacs 23 錯誤(ExecuteStore Critical Error,值得追)。
- **產品專區 `/product/{App}`**:24h 摘要+錯誤分佈 spark bar+籤(錯誤/警告以上/全部)+「開進階查詢」→ `/logs?app=X`(Logs.razor 支援 query 預選)。
- 技術眉角:**scoped CSS(.razor.css)要在 App.razor 掛 `HD.LoggingPlatform.Web.styles.css`**(此專案原本沒掛,樣式會全失效);Razor 屬性內 lambda 不能含插值字串引號。
- **產品識別定案**:`HDPacs`(主 PACS,DICOM 勾選)/`HDDicomWeb`(原誤送 HDPacs 撞名,已改 DicomWeb `24a015d` 部署)/`HDExport`/`HDDicomViewerStation`(未接,佔位)。ProductService.Default+Settings fallback 同步此四值;**.195 DB 產品清單使用者已改**(移除舊 Gateway/WebViewer)。
- **新產品接入流程**:接 HD.Shared.Logging 取好 App 名→送 log→總覽 30 天自動探索長卡(零設定);要固定順序/勾 DICOM 去「系統設定→產品清單」。
- 部署方式(單服務更新):本機 `podman machine start`→publish+`podman build -t hdlog-web:v1.0.0`+save tar→scp .195→`podman load && cd /home/hdadmin/hdlog-v1.0.0 && podman compose up -d --no-deps --force-recreate web`。

**✅ P2 連線紀錄已上線(2026-08-08/09 部署+TESTSCU 驗證):** 慣例=結構化屬性 `Category=connection`+`CommType`(ASSOCIATE-OPEN/CLOSE/REJECT/ABORT、C-ECHO/C-STORE/C-FIND/C-MOVE/MWL-FIND/MPPS)+`Outcome`(success/failure)+`ClientIp`/`User`/`CallingAET`/`CalledAET`(全對齊平台既有契約);共用發送器 **`HD.Shared.Logging.ConnectionLog`**(靜態 Serilog `ForContext` 鏈,`d95400b`→`fbcc59d` 訊息去引號);主 PACS DicomPACSService+WorklistDicomService 全生命週期掛事件、**C-STORE 成功只彙總進 CLOSE 不逐筆**(音量控制,HD.Net10 `8c2aa45`);Web 專區「連線紀錄」籤=`props @> {"Category":"connection"}`(GIN jsonb_path_ops 索引,**Query 服務零改動**,`b728293`);籤只在 DICOM 產品(`dicom_apps` 設定)顯示。定位:**儀器 DICOM 連線**;DicomWeb/Export 的 HTTP 面走既有 access log 不另發。主控台事件表的 connection 分類無來源,要管理視圖再議。

**⏭ 待做:**
- **P3 治理**:HDDicomViewerStation 量大→per-app 保留期(tiered retention 有地基);各來源 log 零散收斂。
- RBAC `app_scope`(user_roles 有欄)未進 Web claims→產品卡未按人過濾(P1 全員可見)。

**✅ ExecuteStore Critical Error 結案(2026-08-09,匯出 CSV 功能首戰):** 30 筆=20 筆 server_login_retry(測試期 DB 重啟)+6 筆舊 DicomWeb 誤名殘留+**1 筆真 bug**:`HandleStorageError(dynamic info)` 對 ValueTuple 取欄位必炸(tuple 欄位名只在編譯期,dynamic 看不到)→儲存錯誤處理整包炸、錯誤資料集沒入 DB。修=具名 tuple 簽章(HD.Net10 `e3cb1ef`)。**匯出 CSV 功能同日上線**(Query `/api/logs/export` 串流+Web `/export/logs` 代理+進階查詢按鈕;tier 走 claims 防越權;query_audit 標 [export];HD.LoggingPlatform `9e96aa7` 部署 .195)。

**分工(定案)**:LoggingPlatform=排障(服務人員);[[project_hd_admin_console]]=管理視圖(API Key/Export job/使用者),log 檢視不重工。相關 [[project_shared_logging]]、[[project_req003_export_webapi]]。
