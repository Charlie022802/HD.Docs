# DicomWeb 端點總覽（完整版）

> 正本：程式碼 `HD.Pacs.DicomWeb/src/HD.Pacs.DicomWeb.Api/Endpoints/`；線上互動文件 `/scalar/v1`。
> 本檔為人讀彙整（2026-08-08 對齊，Keycloak 切換後）。精簡版權限對照見 repo README。
> 生產站台：http://192.168.68.199:5080

## 認證方式速查

| 憑證 | 怎麼帶 | 適用 |
|---|---|---|
| **API Key**（`hdp_` 前綴，主控台 .191:5200 發） | `X-API-Key: hdp_…` 或 `Authorization: Bearer hdp_…` | 儀器／系統整合（首選；可綁 AE、匿名規則） |
| **Keycloak JWT**（人類） | `Authorization: Bearer <jwt>` | 帳號需同時存在 Keycloak＋`HD_USER`；scopes 由 `HD_ROLE.ACCESS` 解析；效期 15 分 |
| **Admin cookie** | 瀏覽器 `/admin` 登入（Keycloak SSO 導頁） | 只用於管理網頁 |

MultiScheme 分派：帶 `hdp_` 前綴 → API Key 驗證；其他 Bearer → Keycloak JWT 驗證。

---

## 1. QIDO-RS 查詢（scope `dicomweb.read`）

| Method | 路徑 | 說明 |
|---|---|---|
| GET | `/dicomweb/studies` | 查 study |
| GET | `/dicomweb/studies/{studyUid}/series` | 查該 study 的 series |
| GET | `/dicomweb/studies/{studyUid}/series/{seriesUid}/instances` | 查該 series 的 instance |
| GET | `/dicomweb/studies/{studyUid}/instances` | 跨 series 查該 study 的 instance |
| GET | `/dicomweb/series` | 全域查 series |
| GET | `/dicomweb/instances` | 全域查 instance |

共通查詢參數：
- **DICOM tag 過濾**：`PatientID=…`、`StudyDate=20260101-20260131`、`AccessionNumber=…` 等（keyword 或 8 碼 hex 皆可）
- `includefield`：額外回傳欄位（tag keyword / hex；`includefield=all` 回整份 metadata）
- `limit`（預設 100）/ `offset`：分頁
- `fuzzymatching`：模糊比對
- 回應含 transfer syntax `(0008,3002)`（STOW 併入 DATASET 的新資料才有）

回應：200 + `application/dicom+json` 陣列；無資料 204。

## 2. WADO-RS 取得（scope `dicomweb.read`）

| Method | 路徑 | 回應 |
|---|---|---|
| GET | `/dicomweb/studies/{s}/metadata` | study 全部 instance metadata（JSON） |
| GET | `…/series/{se}/metadata` | series metadata |
| GET | `…/instances/{i}/metadata` | 單張 metadata |
| GET | `…/instances/{i}` | 原始 DICOM（`multipart/related; type="application/dicom"`） |
| GET | `…/instances/{i}/frames/{frames}` | 指定幀（逗號分隔多幀；多幀影像逐格取用） |
| GET | `…/instances/{i}/rendered` | 渲染圖（JPEG；`Accept` 或 `?quality=`、`?viewport=` 控制） |
| GET | `…/frames/{frame}/rendered` | 指定幀渲染圖 |
| GET | `…/instances/{i}/thumbnail` | 縮圖（有記憶體快取，REQ-004） |

- **出口疊合**：檔案原始不動，取得時自動疊 `RC_OBJECT.DATASET` 校正（coerce-on-retrieve）。
- **金鑰綁匿名規則**：所有 WADO 取得＋QIDO 結果自動去識別（instance UID 決定性替換；client 無法選退）。

## 3. STOW-RS 上傳（scope `dicomweb.write`）

| Method | 路徑 |
|---|---|
| POST | `/dicomweb/studies` |
| POST | `/dicomweb/studies/{studyUid}`（限定 study） |

- Content-Type：`multipart/related; type="application/dicom"`（多檔可單一請求批次）
- **來源 AE**（儲存路徑會驗證登記於 `AE_MAIN` 且啟用）依序：`X-Calling-AE-Title` header → 金鑰綁定 AE → DICOM `(0002,0016)`
- 重複 SOP 回 1111（duplicate）；走與 C-STORE 相同的 `insert_dicom_info` 流程

## 4. 刪除（擴充，scope `dicomweb.delete`）

| Method | 路徑 |
|---|---|
| DELETE | `/dicomweb/studies/{studyUid}` |
| DELETE | `…/series/{seriesUid}` |
| DELETE | `…/instances/{sopUid}` |

委派 legacy `delete_dicom` 程序（軟刪，與主 PACS 同套）。

## 5. WADO-URI 舊版相容（scope `dicomweb.read`）

```
GET /wado?requestType=WADO&studyUID=…&seriesUID=…&objectUID=…
```
- `contentType`：`application/dicom`（原始檔）或 `image/jpeg`（渲染）
- `frameNumber`：指定幀（1 起算）
- `anonymize=yes`：**金鑰須綁匿名規則**，未綁回 403（fail-safe，絕不靜默回可識別資料）

## 6. UPS-RS 工作清單（scope `workitem.read` / `workitem.write`）

| Method | 路徑 | scope |
|---|---|---|
| POST | `/workitems` | write（建立） |
| GET | `/workitems?…` | read（搜尋，DICOM tag 過濾） |
| GET | `/workitems/{uid}` | read |
| PUT | `/workitems/{uid}/state` | write（IN PROGRESS/COMPLETED/CANCELED，txn 鎖） |
| POST | `/workitems/{uid}` | write（改屬性） |
| POST | `/workitems/{uid}/cancelrequest` | write |
| POST | `/workitems/{uid}/subscribers/{aetitle}` | write（訂閱） |
| DELETE | `/workitems/{uid}/subscribers/{aetitle}` | write |
| GET | `/workitems/subscribers/{aetitle}` | read（**WebSocket** 事件通道） |

資料在獨立 `UPS_WORKITEM` 表（public schema）。延後項：Progress Report 事件、suspend、deletion lock、瀏覽器 WS `?apikey=`。

## 7. 加值 API

### Import（scope `import.write`）
```
POST /api/v1/import/          （multipart/form-data）
```
| 欄位 | 說明 |
|---|---|
| `file` | JPEG / PNG / PDF（必填） |
| `studyUid` | 目標 study（必填；可新 UID＝建新 study） |
| `seriesUid` / `patientId` / `patientName` / `description` / `modality` | 選填 |
| AE | `X-Calling-AE-Title` header → 金鑰綁定 AE → form `aeTitle`（儲存路徑驗 AE_MAIN） |

JPEG/PNG → Secondary Capture；PDF → Encapsulated PDF。回 201 + 各層 UID + wado_uri。

### 稽核查詢（scope `admin.audit`）
```
GET /api/v1/audit/logs?from=&to=&actorId=&action=&resourceType=&resourceId=&status=&page=&pageSize=
```
回應含 `total`＋`X-Total-Count` header。（全產品事件的管理視圖在主控台 `/audit`。）

### 身分查詢（登入即可）
```
GET /api/v1/auth/me
```
回目前憑證的 `sub` / `preferred_username` / `email` / `tenant_id` / `roles` / `scopes`——排查 401/403 的第一站。

## 8. 公開端點（免認證）

| Method | 路徑 | 說明 |
|---|---|---|
| GET | `/health` | 狀態＋版本＋build 戳（systemd/監控用） |
| GET | `/health/live`、`/health/ready` | liveness / readiness |
| GET | `/dicomweb/conformance` | DICOMweb 能力宣告（支援的服務/傳輸語法/認證方式） |
| GET | `/scalar/v1` | 互動式 API 文件（OpenAPI UI） |
| GET | `/openapi/v1.json` | OpenAPI 規格 |

## 9. 內部／管理面（不對外開放）

| Method | 路徑 | 保護方式 |
|---|---|---|
| GET | `/api/v1/admin/status` | 限 **loopback ＋ X-Self-Call 祕鑰**（Blazor Admin UI 自呼叫；外部一律 403） |
| GET/PUT | `/api/v1/admin/settings` | 同上 |
| GET | `/api/v1/admin/logs`、`/logs/files` | 同上 |
| GET | `/api/v1/admin/access-logs` | 同上 |
| GET | `/api/v1/admin/audit-logs` | 同上 |
| GET | `/admin/auth/login` | 匿名（OIDC challenge 導 Keycloak） |
| POST | `/admin/auth/logout` | 匿名（RP-initiated 登出，清 cookie＋SSO 會話） |
| — | `/admin/*` 管理網頁（login / status / audit-logs / access-logs / log-viewer / settings） | Admin cookie（Keycloak SSO 登入） |
| GET | `/` | 匿名（導向 `/admin`） |

## 已退役端點（打到會 404）

| 端點 | 退役日 | 取代 |
|---|---|---|
| `POST /api/v1/auth/dev-token` | 2026-08-07 | Keycloak token 端點（`{Authority}/protocol/openid-connect/token`） |
| `GET/POST/PUT/DELETE /api/v1/api-keys*` | 2026-08-07 | HD 後端管理主控台 `/apikeys`（.191:5200，同一張 `HD_API_KEY` 表） |
| `POST /export/*`（媒體匯出薄殼） | 2026-08-06 | 獨立服務 HD.Export（.199:5090） |

相關：[dicomweb.md](dicomweb.md)（架構）、[identity.md](identity.md)（認證/坑）、[admin-console.md](admin-console.md)（金鑰/稽核管理面）。
