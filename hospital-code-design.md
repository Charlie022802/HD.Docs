# HOSPITAL_CODE 設計(動物醫院總主機)

狀態:設計中(2026-08-11)。Schema 基準:`Database/HDPACS_20260811.sql`(自 .191 拉,已核對 `store_dicom`/`get_ae_config`/`RC_STUDY` 與 20260720 版一致)。

## 背景與範圍

動物醫院總主機=單一新版 PACS、單一 HDPACS DB,儀器 C-STORE 直打總機(Proxy 退役)。本設計只處理**院別歸屬**:資料進來蓋 HOSPITAL_CODE、出去依院別過濾。WorklistInsert 擱置另案;Proxy 其餘特殊流程已盤點,新 PACS 皆有現成對應(AE 白名單/host 綁定/視訊 TS/進檔改寫 `dicomImportModified`+`dicomTagFilter`)。

## 定案原則

1. **`STUDY_INSTANCE_UID` 的 UNIQUE 不動**(單欄、全域唯一)。院別不參與唯一性——UID 依 DICOM 標準本就全球唯一,複合 UNIQUE 反而弄壞 QIDO/WADO/C-MOVE 的 UID 解析。
2. **歸屬在進檔當下凍結成實體欄**,不靠 AE_REF join 推導——AE 日後改掛院別不追溯改寫歷史;RLS/查詢不用 join。
3. 病患無主表(病患欄位攤平在 RC_STUDY),跨院病歷號相撞**不動約束**,靠查詢紀律:凡 PatientID 條件查詢必帶院別範圍。
4. 未歸戶(AE 未設院別)照收、HOSPITAL_CODE 留 NULL,管理 UI 認領。
5. 儲存路徑**不編院別目錄**,歸屬純靠 DB 欄位(免搬檔、改掛只改 DB)。

## DDL(migration 草案)

```sql
-- 院別登記表
CREATE TABLE public."HOSPITAL" (
    "HOSPITAL_CODE"      text PRIMARY KEY,
    "HOSPITAL_NAME"      text NOT NULL,
    "ENABLE"             boolean NOT NULL DEFAULT true,
    "DATE_TIME_CREATED"  timestamptz NOT NULL DEFAULT now(),
    "DATE_TIME_MODIFIED" timestamptz NOT NULL DEFAULT now()
);

-- 歸屬欄(NULL=未歸戶)
ALTER TABLE public."RC_STUDY"
    ADD COLUMN "HOSPITAL_CODE" text REFERENCES public."HOSPITAL"("HOSPITAL_CODE");

CREATE INDEX rc_study_hospital_code_index
    ON public."RC_STUDY" ("HOSPITAL_CODE", "STUDY_REF");
```

HOSPITAL_CODE=穩定代碼(改名只動 HOSPITAL_NAME)。Series/Object 不加欄(跟著 study)。索引尾掛 STUDY_REF 對齊既有 `accession_number_index` 慣例;若 Viewer 清單以日期為主可改 `("HOSPITAL_CODE","STUDY_DATE")`,等查詢模式確定再調。

## AE 掛院別(零 schema 變更)

per-AE 設定正本=`AE_CONFIG`(SECTION='NETWORK', KEY='DICOM')的 VALUE jsonb → **加 key `"hospitalCode"`**。`get_ae_config` 原樣通吃(jsonb 透傳),DB proc 與 C# 兩邊自動拿得到:

- DB:`store_dicom`/`insert_dicom_info` 讀 `config ->> 'hospitalCode'`。
- C#:`NetworkConfig`(HD.Net10/HD/Configuration/NetworkConfig.cs)加 `public string hospitalCode { get; set; }`——進檔蓋章用不到(全在 DB),但出口過濾(C-FIND/C-MOVE 查詢組建)會用。

## 進檔蓋章(兩條進檔路 + QC 複製)

**RC_STUDY 共四個 INSERT 點(20260811 版行號)**:

| 位置 | 路徑 | 處理 |
|---|---|---|
| `store_dicom`(L20956,INSERT L21147) | C-STORE(DicomStoreProcess.InsertToDatabase) | 讀 config 蓋章+護欄 |
| `insert_dicom_info`(L11744,INSERT L11943) | DicomWeb STOW(HdPacs Infrastructure) | 同上(它同樣解析 calling_ae_ref) |
| `study_split`(L22187,INSERT L22233) | QC 拆單(SELECT 複製自來源 study) | 複製欄位清單**加 "HOSPITAL_CODE"**(繼承來源) |
| QC Split(study_qc 類,INSERT L27818) | 同上 | 同上 |

蓋章改法(以 store_dicom 為例,insert_dicom_info 同構):

```sql
-- DECLARE 加
hospital_code text;
existing_hospital_code text;

-- 讀 DICOM settings 那段(既有 get_ae_config('NETWORK','DICOM',aeRef))一起讀
--   config ->> 'hospitalCode' INTO hospital_code

-- Insert Study 分支:欄位清單加 "HOSPITAL_CODE"、VALUES 加 hospital_code

-- Study 已存在分支(進 update 前,無論 allow_duplicate):
IF hospital_code IS NOT NULL THEN
    SELECT "HOSPITAL_CODE" INTO existing_hospital_code
    FROM "RC_STUDY" WHERE "STUDY_REF" = study_ref;

    IF existing_hospital_code IS NULL THEN
        -- 先前未歸戶、AE 後來掛好院別 → 補蓋
        UPDATE "RC_STUDY" SET "HOSPITAL_CODE" = hospital_code WHERE "STUDY_REF" = study_ref;
    ELSIF existing_hospital_code != hospital_code THEN
        -- 跨院同 UID:不靜默合併(真正需要的唯一性保護,取代複合 UNIQUE)
        RAISE EXCEPTION 'Cross-hospital study conflict: % owned by %, incoming from %',
            study_instance_uid, existing_hospital_code, hospital_code;
    END IF;
END IF;
```

RAISE EXCEPTION 的行為:C-STORE 端由 `DicomStoreProcess.HandleStorageError` 接手(檔案進 error 路徑+回非零狀態),不會靜默把 B 院資料併進 A 院;STOW 端回 HTTP 錯誤。

## 出口過濾(第二階段)

- 儀器 C-FIND/C-MOVE:院別=CallingAE 的 `NetworkConfig.hospitalCode` → 查詢強制 `WHERE "HOSPITAL_CODE" = ...`。
- DicomWeb QIDO/WADO(生產走 HdPacs* Dapper 版):依呼叫者(金鑰/登入者)院別過濾。
- Viewer:登入者帳號綁院別。
- **RLS 第二道護欄**:RC_STUDY 上 policy(pgbouncer 環境需 `SET LOCAL`,既知)。細節此階段再展開。

## 初始資料與管理

- 舊 Proxy 設定檔的各院 AE 清單=現成「AE→院別」登記來源:一次性匯入 AE_MAIN+AE_CONFIG(NETWORK/DICOM 含 hospitalCode)。
- 管理 UI(後續):HOSPITAL CRUD、AE 掛院別欄位、未歸戶清單+認領(認領=UPDATE 歷史 RC_STUDY.HOSPITAL_CODE)。

## 施工順序

1. **階段一(進檔就開始歸戶)**:migration(HOSPITAL+RC_STUDY 欄+索引)→ 改 `store_dicom`+`insert_dicom_info`+兩處 QC 複製 → NetworkConfig 加屬性 → AE 設定匯入。
2. **階段二**:出口過濾(C-FIND/C-MOVE/QIDO/WADO/Viewer)+RLS。
3. **階段三**:管理 UI(HOSPITAL/掛院別/認領)。

## 待議

- **對外 port 網路安全**:DICOM 無認證,防線=AE 白名單+來源 IP 綁定;各院 NAT/浮動 IP 下 host 只能 0.0.0.0 → 需防火牆限源/VPN/固定出口 IP,與網路規劃一起定。
- 病患複合顯示:Viewer 顯示 PatientID 時是否帶院別前綴(跨院同號的視覺區辨),UI 階段再議。
- Worklist 線(擱置中)回來後:HDM 表是否也加 HOSPITAL_CODE、物種中翻英(狗→Feline 對調,proxy 退役後由 hd-worklist-server 接手)一併處理。
