---
name: reference_hdctl_preserve
description: "hdctl manifest 的 preserve 有三個容易忘的後果—退版不帶設定(已修)、跨版本改設定來源會炸、**它會遮住壞掉的設定檔讓只有新安裝才爆**"
metadata:
  node_type: memory
  type: reference
---

`preserve` 在升版時把**舊 release 的設定檔複製到新 release**，讓機器設定不被新版覆蓋。
立意正確,但 2026-08-26 一天內撞到它的三個後果:

**① 退版不會帶設定過去** —— hdctl **0.2.5 已修**。
目標 release 用的是它「當初被安裝時」那份設定,可能是幾個月前的。
實案:Keycloak 換 domain 改了 current 的 appsettings,退版後登入立刻壞,
症狀看起來像「退版沒解決問題」。現在會帶過去,目標版原檔留成 `.pre-rollback`(實測救得回來)。

**② 帶過去也可能出事:設定的來源跨版本改變時** —— hdctl **0.2.6 加警告**。
「設定是機器狀態、跟版本無關」這個前提,在「設定從 appsettings 搬到 env 檔」這種變更下不成立。
實案:alpha.5 把 `Keycloak:Authority` 搬進 env(appsettings 留空),退到 alpha.4 時空的
appsettings 被帶過去,但 **unit 是照目標版 manifest 重寫的**、alpha.4 沒有那個 env 檔
→ **服務 active 但每個請求都 500**。現在會比對兩版 `envFiles`,目標版少了就警告(不擋)。

**③ 它會遮住壞掉的設定檔 —— 最陰的一個。**
新版隨包附的 appsettings **永遠不會抵達既有安裝**(一律被舊的蓋掉)。
所以包裡的設定檔壞掉時,**既有安裝全部正常,只有全新安裝會炸**,也就是下一間新醫院。
實案:加註解時同一層多疊一個 `"_comment"` —— JSON 合法、編輯器與 python 都不抱怨,
但 .NET 的 `JsonConfigurationProvider` 對重複鍵直接 `InvalidDataException`。
`.191`/`.199` 升級後健檢 200、登入正常、JWT 也過,**而包是壞的**。

→ **`pack-*.sh` 現在會擋**:除了驗密碼沒漏進包,也驗每個 `appsettings*.json` 載得起來
(重點是重複鍵;python `json.load` 預設允許重複、後者覆蓋前者,要 `object_pairs_hook` 才抓得到)。
護欄本身先驗過會叫(壞的 exit=1、好的 exit=0)。

**推論(最該記住的一句)**:改過設定檔之後,「既有機器升級沒事」**不足以證明包是好的**。
要嘛靠打包時的檢查,要嘛真的做一次全新安裝。

相關:[[project_hdctl_hospital_host]]、[[project_main_pacs_deploy]]、[[project_hd_admin_console]]。
