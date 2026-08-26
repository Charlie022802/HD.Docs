---
name: project_josef_site
description: "若瑟現場正式主機=10.10.1.148(HDPACS148):DB 2.0.22+已補刪除保護 hotfix、儲存三層位置與餘裕(nearline 約 320 天)、每晚 02:00 有 pg 備份;別跟測試機 .163 搞混"
metadata:
  node_type: memory
  type: project
---

**若瑟現場的正式 PACS 主機是 `10.10.1.148`(主機名 `HDPACS148`)。**
不是 `192.168.68.148`(不存在,我 2026-08-26 講錯過一次),也**不是 `192.168.68.163`**
——那是我們內網的測試機,只是形態相近。

**OS**:Red Hat Enterprise Linux **9.2**、glibc **2.34**(2026-08-26 實測)。
相當新,self-contained 的 .NET 10 在這裡沒有相容性疑慮。

**同機還有** PostgreSQL(5432)+PgBouncer(6432)+hd-web-server(見 docs/systems/hd-web-server.md 主機表)。

## DB
- 版本 **2.0.22** —— 正是 2026-08 掉資料的那一版。
- **2026-08-26 已單獨補上 2.0.27 的 `get_next_delete_study`**(nearline 保護),
  **刻意不動版本號**,所以 `HD_CONFIG` 仍回報 2.0.22。函式 md5 `bc9350e7…` → `1847728f…`。
- 正式升到 2.0.27 尚未規劃;2.0.23~2.0.26 動到進檔主幹,舊版 PACS 服務相容性要另評估。
- 實測「旗標說有 nearline、實際沒有」的檢查數 = **0**(靜止時旗標是準的,失效是競態)。

## 執行環境(2026-08-26 實測)
- **PostgreSQL 16.0** —— 很新,2.0.23~2.0.27 的語法不會有問題。
- **dotnet 只有 6.0.22**(ASP.NET Core 6 + NETCore 6),**沒有 8 也沒有 10**。
  而我們的原始碼現在是 **net10.0** → 若瑟跑的服務**必然是 net6 時代的 build**。
  **日後要在若瑟裝我們的新元件,一定得 self-contained**(glibc 2.34 沒問題),或先裝 .NET 10 runtime。
- SELinux **Permissive**。
- `/home/HD/service/` 下 17 個目錄,執行中 14 支:archive-manager / cache-delete /
  dicom-service-manager / dicom-to-image / dicom-to-video / dicom-transmit /
  dicom-transposition / media-package / pacs / web-dicom-scu / web-server /
  workflow-manager / worklist-modify / worklist-server。

**⚠️ 服務版本號判斷不了新舊。** `deps.json` 顯示一律 `HD.*/2.0.4`,但**原始碼的 csproj
現在也還是 `<Version>2.0.4</Version>`** —— 那個欄位自 net10 遷移後就沒動過
(實際在動的是 hdctl 元件版號,`.191` 是 `pacs 2.0.13`)。
所以「若瑟 2.0.4、我們也 2.0.4」**不代表一樣新**,只代表那個欄位沒人維護。
要判斷年份看檔案時間與 `runtimeconfig.json` 的 tfm。這是「版本說謊」的靜態版本。

## 儲存(2026-08-26 實測)
| 用途 | 路徑 | 實體 | 餘裕 |
|---|---|---|---|
| **線上快取** | `/home/HD/HDPACS_OCACHE01` | 本機 9.0T(`rhel-home`) | 920G,**90%＝正好在 redLine**,自動刪除持續運作 |
| 暫存 | `/home/HD/Cache_Temp` | `10.10.1.141` 的 25T(NCACHE01,**已退役**) | 1.4T,95% |
| **nearline** | `/home/HD/HDPACS_NCACHE02` | `//10.10.70.11` 的 27T | **3.7T**,87% |

- 線上是**穩態**(卡在 redLine,靠刪除維持),**真正只出不進的是 nearline**。
- 進檔日均 **≈11.8 GB**(平日 ≈14.7、週末 2~5)→ **nearline 約 320 天餘裕**。第三個空間申請中。
- `SQLBACK` 與 `NCACHE02` **是同一個 share**,但它不是滾動備份:散落約 137G 的手動 dump
  (2023~2026),**最新一份是 2026-04-02** —— 影像有 nearline 副本,但 **DB 本身四個多月沒備份**,
  這件事比容量更值得注意(metadata 沒了,影像還在也對不回去)。

## 待辦
規劃升到 2.0.27 以上;`insert_study_job` 的 NEARLINE_BACKUP gate 併那次一起改
(見 [[project_nearline_flag_race]])。預演環境待定:
- `.163` 曾整組消失過一次(hdctl 與整個元件目錄),同事說沒有 rollback 機制,**原因未明**;
  查過 cron 與 tmpfiles 都沒有清 `/usr/local` 的規則。當預演環境有「跑到一半被清掉且不會通知」的風險。
- **兩台環境不一樣**:`.163` 是 CentOS 8 / glibc 2.28、若瑟是 RHEL 9.2 / glibc 2.34。
  不過**要預演 DB 升級,該對齊的是 PostgreSQL 版本、DB 版本(2.0.22)與 PACS 服務版本,不是 OS**
  —— 2.0.23~2.0.26 動的是進檔主幹的 proc,風險在服務與 proc 的介面落差。

相關:[[project_nearline_flag_race]]、[[reference_pacs_db_schema]]、[[project_hd_web_server]]。
