# hd-web-server（同事維護的 Node 影像服務）

> ## 這不是我們的 repo，而且**已凍結**（2026-08-27）
>
> `hd-web-server` 由同事維護，不屬於 `D:\Dev\HyperDigital` 下那 11 個 repo。
> 工作副本放在 `D:\Dev\HyperDigital\hd-web-server`（2026-08-19 為排障而取），
> **不要在本地 commit**。處理方式同 [animal-proxy.md](animal-proxy.md) 的凍結慣例。
>
> **2026-08-27 決定：以現在的版本為主，不再更新。** 所以「請同事在那邊加一段」不再是
> 可用的解法——任何需求要嘛在我們這側解決，要嘛等看片端切到院內 Keycloak 之後，
> 那條路本身退場。
>
> 已知受此影響的一項：`loginCheck` 不檢查 `HD_USER.ENABLE`，所以**主控台的「停用」擋不住
> 看片端的帳密登入**。這不是待辦，是已知限制，UI 與交接文件都據實寫明
> （見 [../keycloak-user-provisioning.md](../keycloak-user-provisioning.md)）。
> 曾評估「停用時抽換密碼 hash、啟用時放回」讓它對看片端也生效，**不採用**：
> 那讓停用變成一個有隱藏副作用的操作、且賭在暫存值不會遺失上，而問題本身會隨切換消失。

## 為什麼這份文件必須存在

**桌面看片端的每一張影像都是這支服務送出來的**，不是看片端直連 DB 撈檔案。

看片端的資料流是分開的兩條：

| 用途 | 對象 |
|---|---|
| 查詢清單、study tree、DICOM tag（metadata）| PostgreSQL（`localconfig.json` 的 `Database.Host`）|
| **實際影像檔／JPEG／MP4／PDF** | **hd-web-server 的 `/api/v2.0/wado-uri`**（`localconfig.json` 的 `DownloadHost`）|

這兩個設定可以指向**不同主機**，而且實務上就是不同主機。所以「DB 查得到、影像調不出來」是完全正常的失敗形狀 ——
2026-08-19 那次排障繞了三小時，根源就是這支服務在我們的系統認知裡不存在，出問題時沒人能讀它的程式碼。

## 技術棧與部署

- Node + Fastify + `@fastify/postgres`（pg Pool）+ `@fastify/sensible` + pino。TypeScript。
- 以 **pkg** 打包成單一執行檔 `hd-web-server-linux-x64`（約 58 MB）。
  **JS 已編成 V8 bytecode** —— `strings` 撈不到任何原始碼字串，binary 裡只剩一條
  `/snapshot/hd-web-server/uglifiedTmp/index.js`。要讀邏輯只能拿原始碼 repo。
- 不只做 WADO：還有 gRPC 打 dicomSCU、腦波（ntuh-eeg）、光田 HIS callback、
  國泰 cathyCgh 客製、`public/` 前端（含 cornerstone 網頁看片）、kiosk、export、archive、device、group……
  **動它之前要清楚影響範圍**，這也是只讀不改的理由。

### 已知的部署點（透過 VPN 連線的院內網段）

| 主機 | 角色 | 備註 |
|---|---|---|
| `10.10.1.148` | 正式 | 同機還有 PostgreSQL／PgBouncer |
| `10.10.60.66` | 由 `.148` 複製過去的一份 | 已運行數月。**systemd unit 是 `disabled`，開機不會自動啟動** |

`.66` 的路徑：`/home/HD/service/hd-web-server/`（執行檔＋`config.json`）。

### config.json（啟動時讀一次）

`serverConfig` 是 `fse.readJSONSync("./config.json")`，在 module 載入時執行 ——
**改了設定不重啟服務，不會生效**。

`.66` 目前的關鍵設定：

```json
"pg": { "host": "10.10.1.148", "database": "HDPACS", "port": 6432 }
"authCtrl": { "mode": "intranet", "loginPwRequired": true, "tokenExpiresIn": "1w" }
```

**`port: 6432` 不是 PostgreSQL，是 PgBouncer。** 這點很重要：中間有連線池代理，
「每次查詢都是獨立交易、獨立快照」這種直連才成立的推理會失效。

驗證方式：查 `.148` 的 `pg_stat_activity`，`application_name = 'hd-web-server'` 的 backend
最舊不會超過 60 分鐘 —— 那是 PgBouncer `server_lifetime` 預設 3600 秒的特徵。

## 排障入口（重要）

| 要看什麼 | 去哪裡 |
|---|---|
| HTTP 請求／狀態碼（pino，JSON 逐行）| `/home/HD/logs/web-server.log` |
| **服務自己 `console.log` 的除錯訊息** | **`journalctl -u hd-web-server`** |

兩邊內容不重疊。`web-server.log` 只有 HTTP 層（`incoming request` / `request completed` / 錯誤 stack），
所有 `console.log` 都在 journald。2026-08-19 那次的關鍵訊息全在 journald，不在檔案裡。

### 重啟會清掉 web-server.log

實測：重啟後 `/home/HD/logs/web-server.log` 是新的 inode，舊內容消失，**也沒有輪替檔**。

> **出問題時先備份 log 再重啟**，否則證據就沒了：
> ```
> sudo cp /home/HD/logs/web-server.log /tmp/web-server-$(date +%H%M).log
> ```

## `wado-uri` 的兩套「存在性」判定

`src/routes/api/v2.0/wado-uri/wado-uri.ts` 只有 123 行，但有三處 `rep.notFound()`，語意完全不同：

| 行 | 情境 | 判斷依據 |
|---|---|---|
| 32 | **守門失敗** | `filterCheck()` → `qido_query`（讀 **DATASET jsonb**）|
| 58 | 檔案不存在 | `fse.exists(file)`，`file` 來自 `wadouri_query`（讀 **RC_* / RC_LOCATION**）|
| 71 | 從 DCM 抽 PDF 失敗 | `getRawPdfFromDcm` 回空 |

**守門和取檔用的是兩個不同的資料來源。** `RC_LOCATION` 有記錄、檔案也躺在磁碟上，
但只要 `DATASET` jsonb 那邊湊不出結果，第 32 行就先擋掉了 —— 根本走不到第 58 行。

### `filtered.length === 1` 是個地雷

`filterCheck` 的判定是這一行：

```ts
const filter = isShareUser(req) ? await getShareUserAccessFilter(req) : {};
const filtered = filterResults(qidoResult, filter);
return filtered.length === 1;
```

對**內部使用者**（`uuid !== SHARE_USER_UUID`）來說 `filter` 是空物件，而 `filterResults` 對空 filter
是 `[].every() === true`（全部放行）。所以整個守門退化成一句：

> `qido_query('Image', ...)` 對這組三個 UID 必須回**剛好一列**。

**0 列會擋，`>= 2` 列也會擋。** 而主 PACS 的 `store_dicom` 有 `allow_duplicate` 設定 ——
一旦某張影像出現重複的 SOP Instance UID，它就永久下載不了，而且回 404。這兩件事直接矛盾。

### 重現守門判定的診斷 SQL

```sql
SELECT o."SOP_INSTANCE_UID",
       (SELECT count(*) FROM qido_query('Image', jsonb_build_object(
          'search_filters', jsonb_build_object(
             '0020000D', jsonb_build_array(s."STUDY_INSTANCE_UID"),
             '0020000E', jsonb_build_array(se."SERIES_INSTANCE_UID"),
             '00080018', jsonb_build_array(o."SOP_INSTANCE_UID")),
          'includefield', jsonb_build_array('00080020','00080050','00100020')))) AS qido_rows
FROM public."RC_OBJECT" o
JOIN public."RC_SERIES" se ON se."SERIES_REF" = o."SERIES_REF"
JOIN public."RC_STUDY" s ON s."STUDY_REF" = o."STUDY_REF"
WHERE s."STUDY_INSTANCE_UID" = '<studyUID>'
ORDER BY o."INSTANCE_NUMBER";
```

`qido_rows` 不等於 1 的那幾張，看片端一定調不出來。

## `getInternetUserInfo` 是紅鯡魚

journald 裡每個 `wado-uri` 請求常伴隨這段輸出：

```
getInternetUserInfo /api/v2.0/wado-uri?...  undefined { uuid: '...', name: '...', share: undefined }
```

它**跟成敗無關**。`src/utils/auth/auth.ts:133` 起：沒有 HD token 就在第 135 行直接 return，
而那句 `console.log` 在第 165 行 —— 所以「有沒有印」只反映**請求帶不帶 HD token cookie**。
排障時很容易被它帶著走（2026-08-19 就被帶走了一輪）。

`share: undefined` 也不代表異常；只有 `uuid === SHARE_USER_UUID`（`6390a483-afb8-47c9-866c-5802cd9d9f40`）
才會走分享使用者的授權過濾。

## 2026-08-19 事件記錄：一筆 MA study 全部 404（根因未定案）

**症狀**：某位病人的一筆 MG/MA study（4 張），看片端從 `.66` 抓，DICOM 與 JPEG 兩種 contentType
全部 404（43 次請求 0 成功）；同一時間同一台看片端抓另一筆 CT 完全正常。

**已排除**（各有實證，不是猜的）：

- 不是看片端的問題 —— 每個請求都收到伺服器主動回的 404。
- 不是資料新舊 —— 同一天（2023-10-03）產生的另兩筆 study 都 200，2012／2020 的原生 UID study 也都 200。
  當天 `.66` 共 3693 次 200／43 次 404，涵蓋 59 筆 study，只有這一筆壞。
- 不是 nearline／歸檔 —— `RC_LOCATION` 齊全：`VOLUME_REF=1`、`DIRECTORY=2017/0415`、
  `OBJECT_LENGTH` 約 11.6 MB、`IS_CACHED=true`、`IS_ARCHIVED=false`。
- 不是身分解析錯誤 —— 失敗時解析出的使用者就是登入者本人（`DX05` = 董合恩）。
- 不是應用層快取 —— `filterCheck` 這條路徑每次都實打實 `pg.query`，程式碼裡沒有任何 cache。
- 不是連線凍結快照 —— 122 處全是 `pg.query`（pool 自動借還），沒有任何 `BEGIN`／`connect()`；
  事後查 `pg_stat_activity` 也沒有一列 `idle in transaction`。

**未解**：使用者重新匯入該 study、並重啟 `hd-web-server` 之後恢復正常，
之後從 `.66` 抓同一筆四張全數成功。使用者的判斷是**重啟才是解**。
但「重新匯入之後、重啟之前」那個時間點只送出過一個請求，而看片端在 1 秒後就被關閉，
**沒有任何回應被記錄下來** —— 所以「重新匯入是否已經修好」從未真正被測到。
兩個變因無法分離，根因懸而未決。

**下次發生時要做的事**（順序很重要）：

1. **先備份 `/home/HD/logs/web-server.log`**（重啟會清掉）。
2. 在 404 的當下跑上面那條診斷 SQL。
   - `qido_rows != 1` → 資料／`DATASET` 的問題，與進程無關。
   - `qido_rows == 1` 而 `.66` 仍 404 → 進程本身的問題，證據確鑿，交給同事。
3. 只有在取樣完成之後才重啟。

## 要跟同事提的四件事

1. **兩處 `notFound()` 要記原因**（第 32 行印 `qidoResult.length`，第 58 行印 `file` 路徑）。
   三種完全不同的失敗回同一個 404、一句原因都不留 —— 這是 2026-08-19 那三小時的根源。
   補這兩行，同樣的問題五分鐘就能定位。
2. **`filtered.length === 1` 與 `allow_duplicate` 的矛盾**（見上）。
3. **DB 密碼寫死在原始碼**：`src/utils/utils.initial.ts` 裡連 `user: "postgres"` 一起硬編碼，
   不在 `config.json`。所以改密碼要重新編譯，而且原始碼 repo 誰拿到就等於拿到生產 DB 的 superuser。
4. **`.66` 的 systemd unit 是 `disabled`** —— 開機不會自動起。若要正式承載看片必須 `enable`。

## 我們這邊可以做的保險

`.148` 的 `pg_stat_activity` 上有十幾條 pgAdmin 連線。設個上限，避免哪天忘記關的連線凍結快照：

```sql
ALTER DATABASE "HDPACS" SET idle_in_transaction_session_timeout = '60s';
```
