---
name: project_viewer_settings_ui
description: "看片端設定頁的區塊樣式統一(SettingsPanelTheme)+舊工具列格式轉換;過程修掉三個既有地雷"
metadata: 
  node_type: memory
  type: project
  originSessionId: 13e6b6ed-984d-4c27-aed8-2170077bfa02
  modified: 2026-08-14T10:05:31.264Z
---

**看片端設定頁樣式統一(2026-08-14 完成,`ee157f6`+`9a383f0`+`c571782`)**。共用樣式在 `Configurations/SettingForms/SettingsPanelTheme.cs`(色碼 + `MakeSectionPanel`/`MakeSectionHeader`/`MakeSmallButton`)。**抽出來的理由就是這次需求本身**:使用者要「快捷工具長得跟工具列一樣」,而原本兩頁各留一份色碼與版面碼,只改一邊就會慢慢長歪。

**改法一律是「只換容器」**:Designer 的控制項與事件處理全部沿用、操作方式不變,只把外框換成深色面板+標題列。快捷工具因此從「浮動 TopMost 的可用工具視窗」變成三欄嵌入(那個浮動視窗會蓋住自己頁面的對話框,所以原本新增/刪除 modality 時要先 `Hide()` 再 `Show()` 去閃它)。標題列設定則是把三個 `GroupBox` 換掉(它的蝕刻外框在深色主題下像沒套樣式)。

**「框中框」的真正成因**:整頁**沒有任何 `BorderStyle`**。是 resx 給三欄固定尺寸,底下剩一塊空白露出外層容器 `panelForm`(17,39,52)的中間色調,那條帶子的上緣看起來就像框線。解法=三欄 `Dock=Fill` 填滿高度 + 頁面底色設成 `SettingsPanelTheme.PAGE`(與 panelForm 同色)。

**舊工具列格式轉換**:舊版存 `ToolBarSettings`(分組),新版是 `ToolBarSettingsFlat`(攤平+分隔線),而 `UserConfig` 已無舊屬性 → 舊使用者那段 JSON 被反序列化忽略 → **升級後工具列整條空白**(`IsConfigUsable` 沒檢查工具列,不會被擋)。**優先轉換不是套預設**(使用者調過的要保住):**每組最後一個工具標分隔線**=等價轉換。真的什麼都沒有才用內建預設(照 `.163` 現場那組 21 個抄的)。**補值放 `GetUserConfig()` 不是 `RefreshConfigs()`** —— `SettingsForm` 會自己再跟 DB 要一份,放錯層的症狀是「畫面上的工具列是好的、設定頁裡卻是空的」。**要去重**:`ViewerTool.Parse` 對認不得的名稱一律回 `None`(選擇箭頭),舊設定裡每個已移除的工具都會變一顆箭頭。舊格式**留在 DB 不刪**(轉換有誤還救得回)。13 項機制測試 + `.163` 真實舊帳號 `DX05`(45 工具/5 組)實測。

**順手修掉的既有地雷(原本的版面剛好躲過)**
1. **`ContextToolControl.CreateGrid()` 重建 `Items` 會清掉已放好的工具,而 `OnResize` 會呼叫它** → **改變視窗大小就會讓快捷工具消失**,使用者只看到「按鈕不見了」完全聯想不到縮放。改成重建後從 `contextTool` 還原。
2. `ApplyData` 先 `Items.Clear()` 再設 `GridX/GridY`,格數沒變時 setter 不重建 → 對著空清單塞工具;順帶把「工具數>格子數」從 `IndexOutOfRange` 改成取較少者。
3. 清單搬進新容器後 handle 重建,`Items[0].Selected = true` **不見得觸發 `SelectedIndexChanged`** → 反白有、內容空,要再點一次。改成直接呼叫載入,不依賴事件時機。

**版面小坑**:`TableLayoutPanel` 格子裡的按鈕用 `Dock=Fill` 會被撐到與容器等高、文字被邊緣切掉 → 固定尺寸 + `Anchor=None` 置中。

**直式螢幕的三個坑(2026-08-14 追出來,`0bd4c32`)**。症狀都是「設定頁沒鋪滿、關閉鈕卡半空中、右半邊按不到」,但成因互相獨立,**而且全部無聲**(畫面只是怪,不會有任何錯誤):
1. **Designer 的 `WindowState=Maximized`** 讓嵌入式表單永遠停在**主螢幕的最大化尺寸**(實測 1723×1035,容器是 1080×1920)。機制:`TopLevel=false` 會重建 handle,底層視窗仍帶 `WS_MAXIMIZE` → `Form.UpdateWindowState()` 收到 `WM_WINDOWPOSCHANGED` 把狀態寫回 Maximized → **Maximized 的表單設 `Size` 只會存進 restore bounds**,`Dock=Fill` 與程式指定尺寸都不生效。**單獨寫測試程式重現不出來**(那裡的表單在 `TopLevel=false` 前還沒建 handle),我因此誤判過一次;是靠在 `ShowSettingsPage` 加逐層 log 才定位。
2. **`AutoScroll` 不把停靠的子控制項算進捲動範圍** → 子頁只要 `Dock=Fill` 就永遠等於可視區、捲軸不出現;**加 `MinimumSize` 也沒用**(只是不被壓扁)。要改成不 Dock、自己給尺寸=max(設計尺寸, 可視區)。三種寫法都實測比較過。
3. **`Control.Scale()` 會連表單自己的 Bounds 一起縮** —— 獨立視窗時正確,嵌入式表單則每滾一格 ×0.909 縮成畫面一角。縮放後要還原成容器尺寸。

順帶:自動字體倍率原本用**螢幕高度**估密度,直立擺放的螢幕(醫院常見)會被誤判 1.78 倍 → 改取**短邊**;`GetAutoScale` 也要由呼叫端傳 MainForm(建構當下表單還沒掛進容器,`Screen.FromControl` 一律回主螢幕)。**捲動容器不要有 Padding**(子頁座標原點就不是 0,0),留白掛外層 `panelRight`。

**排障手法**:五層容器底色一樣,看截圖分不出誰縮了 → 在 `ShowSettingsPage` 留一行逐層尺寸 log(表單→table→panelRight→panelForm→子頁),已保留在程式裡。

相關:[[project_viewer_install]]、[[project_viewer_license]]
