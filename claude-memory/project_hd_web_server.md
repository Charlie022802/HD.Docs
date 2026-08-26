---
name: project_hd_web_server
description: 看片端的影像其實由同事維護的 Node 服務 hd-web-server 送出，不是我們的 repo;排障入口與已知地雷
metadata: 
  node_type: memory
  type: project
  originSessionId: ea8648ec-751b-449c-aab0-36db86e8c1e2
  modified: 2026-08-19T09:12:18.793Z
---

**2026-08-26 起整支凍結**：以現在的版本為主、不再更新。所以「請同事在那邊加一段」不再是可用的解法——
需求要嘛在我方解決，要嘛等看片端切院內 Keycloak 之後那條路退場。
已知後果：`loginCheck` 不檢查 `HD_USER.ENABLE` → **主控台的「停用」擋不住看片端的帳密登入**（已知限制，非待辦）。

桌面看片端的**影像檔是 `hd-web-server` 送的** —— 同事維護的 Node/Fastify 服務，不是那 11 個 repo 之一。`localconfig.json` 裡 `Database.Host`（查 metadata）與 `DownloadHost`（抓影像，打 `/api/v2.0/wado-uri`）是**兩個獨立設定、實務上指向不同主機**，所以「清單查得到、影像調不出來」是正常的失敗形狀。

工作副本 `D:\Dev\HyperDigital\hd-web-server`（2026-08-19 為排障下載，不含 `.git`）—— **只讀不改**，同 [[project_hd_animal_proxy]] 的凍結慣例。

**Why:** 2026-08-19 一筆 MA study 全數 404，查了三小時，大部分時間耗在「這個元件在我們的系統認知裡不存在」。

**How to apply:**
- 排障看 **`journalctl -u hd-web-server`**，不是 `/home/HD/logs/web-server.log`（後者只有 HTTP 層，所有 `console.log` 在 journald）。**重啟會清掉 web-server.log，先備份再重啟。**
- `wado-uri.ts` 123 行有三處 `notFound()` 語意完全不同（守門／檔案不存在／PDF 抽取），全回同一狀態碼又不記原因 —— 這是繞路的根源。
- 地雷：`filterCheck` 判定是 `filtered.length === 1`，內部使用者 filter 為空（全放行），所以退化成「`qido_query` 必須回剛好一列」。**重複 SOP Instance UID 會讓影像永久 404**，與主 PACS 的 `allow_duplicate` 直接矛盾。
- 守門走 `qido_query`（讀 DATASET jsonb），取檔走 `wadouri_query`（讀 RC_*/RC_LOCATION）—— **兩套不同的存在性判定**。
- `pg.port` 是 **6432 = PgBouncer**，不是直連（`server_lifetime` 預設 3600 秒，backend 不會超過 60 分鐘）。DB 密碼寫死在 `src/utils/utils.initial.ts`。
- 那次 404 的根因**未定案**（重新匯入與重啟兩個變因分不開）。細節、時間軸、診斷 SQL、取樣順序全在正本 `docs/systems/hd-web-server.md`（見 [[reference_system_docs]]），backlog REQ-019。
