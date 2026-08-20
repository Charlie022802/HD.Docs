---
name: project_viewer_diagnostics
description: 看片端 log 調閱不到(REQ-016)—定案走 ViewerWebApi 上傳診斷包到院內 Linux 主機;細流/粗流兩管道;崩潰只留記號、下次啟動才傳
metadata: 
  node_type: memory
  type: project
  originSessionId: ea8648ec-751b-449c-aab0-36db86e8c1e2
  modified: 2026-08-17T04:24:21.127Z
---

**看片端的 log 全落在醫師個人電腦上,我們連不到那台機器**(與授權簽發 REQ-015 同一個限制)。正本 = docs `backlog.md` REQ-016。實查:`HDLogger` 只掛 `Serilog.Sinks.File`(安裝版 `{app}\logs`、Media 版 `%LocalAppData%`),**沒有任何網路 sink**;現場醫師機器**都開 Debug**(使用者刻意的:現場出問題是一次性事件,事後才調高等級請醫師重現,情況早就沒了)。

**🔑 傳輸通道定案(2026-08-17):上傳到院內 Linux 主機的 ViewerWebApi**(`HD.DicomImageViewer.Server`),工程師 VPN 進醫院看。**取代了 REQ-016 原本寫的「寫進醫院 DB」**——理由是看片端的目標架構本來就要「只對 ViewerWebApi + DicomWeb、不再直連 DB」(見 [[project_viewer_server]]),那支服務每間醫院都會裝(hdctl 元件 `viewerapi`),所以診斷包不必為自己另外爭取通道;而且服務端能直接落地成主機上的檔案,VPN 進去 `ls` 就看得到,不必從 bytea 撈。

**Debug 全量不能灌進 LoggingPlatform**(使用者自己先察覺的,方向正確)。除了封閉網路送不到 .195 之外,還有獨立理由:**兩者性質不同**——伺服器 log 是**訊號**(每筆都可能要處理),看片端 Debug 是**軌跡**(一台一天數十 MB,99.9% 是一切正常的流水帳)。混在一起會同時毀掉三件事:查詢被雜訊淹沒、保留期被迫縮短、LoggingPlatform「排障第一站」的定位失效。→ **兩條管道**:細流(Warning/Error+少量關鍵事件)即時送;粗流(Debug 全文)留本機、出事才整包上傳。

**⚠️ 程式當掉的處理(使用者追問的點):不要在崩潰當下上傳。** 程序正在死的時候能做的事極少,網路 IO 很可能來不及或再炸一次把原始錯誤蓋掉。拆兩段:①**當下只留記號**(掛 ThreadException/UnhandledException,只寫崩潰標記檔:例外、時間、當時 log 檔名,然後讓它死)②**下次啟動才打包上傳**。這樣順便解掉更難抓的一種:**程序被砍/當機/斷電**連 handler 都不會跑 → 啟動寫「執行中」標記、正常關閉清掉,下次啟動發現標記還在 = 上次不正常結束,一樣上傳(dirty-shutdown 偵測)。合起來覆蓋:未處理例外/程序被殺/藍屏斷電。

**觸發**:崩潰或不正常結束自動、醫師手動「回報問題」+填一句描述(**那句描述最值錢**,最難的是知道發生什麼事而不是拿到 log)、工程師遠端標記下次啟動上傳。**要控**:單包大小上限、保留期自動清、頻率限制(防壞掉的機器狂送)。

**⚠️ 個資決定架構**:log 必然帶 PatientID/AccessionNumber。**診斷包只停在醫院主機 = 資料沒出院**,跟工程師到現場看同一層級,阻力最小;**若要自動傳回公司就是資料外流**,需醫院同意+可能去識別化,難度完全不同。schema 要不要留遮蔽欄位取決於此。

**✅ 第一階段完成(2026-08-17,趕在 8/18 裝機前;已重新打包 `2.4.0+20260817-121900+0800`)。** 判斷是**先做「拿得到」、不做自動上傳**:那天要裝的是已實機驗證過的 2.4.0,再往啟動路徑塞伺服器端相依等於把驗證作廢,而**裝機當天出問題的代價遠大於少一套自動上傳**。交付兩項,都只寫本機檔案、不碰網路、不碰登入流程:①**「匯出診斷包」按鈕**(`Core/Diagnostics/DiagnosticPackage.cs`,掛關於視窗;環境資訊重用 AboutForm 既有的 `BuildReport()`,不另寫會走樣的第二套)②**事故標記**(`Core/Diagnostics/SessionMarker.cs`+`Program.HookCrashHandlers`)。**意外加分:三支(Viewer/Executer/LinkClient)安裝時共用同一個 log 目錄 ⇒ 診斷包自動涵蓋 Executer 紀錄**(連動問題最關鍵那份)。

**實作踩到/要記得的**:①今天的 log 檔正被 Serilog 開著寫,**必須明講 `FileShare.ReadWrite`** 才讀得到——而它正是最需要收的一個(`ZipFile.CreateFromDirectory` 直接不能用)②`localconfig.json` 有 DB 密碼,遮蔽用「**欄位名看起來像密碼就遮**」而非列舉已知欄位(設定檔會長新欄位,漏一個就是把密碼寄出去);連巢狀 apiKey 一起遮③**掛上 `Application.ThreadException` 後 WinForms 就不再顯示它內建的錯誤對話框**→自己叫出同一個 `ThreadExceptionDialog` 並照樣處理「結束」選擇,目的是多記一筆事故、不是改變使用者看到的行為④打包走背景執行緒(同步會凍住視窗,授權「重新檢查」踩過同一顆雷)⑤async void 的 finally 要檔 `IsDisposed`——打包幾秒間使用者可能已關掉視窗。**驗證**:機制測試 21 項全過、關於視窗版面截圖確認、**用實際出貨 binary 端到端跑過「啟動→強制砍掉→再啟動」**產生正確事故記錄。

相關:[[project_viewer_server]]、[[project_viewer_license]]、[[project_loggingplatform_product_zones]]、[[project_viewer_install]]。
