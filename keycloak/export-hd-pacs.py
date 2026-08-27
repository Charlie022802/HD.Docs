#!/usr/bin/env python3
r"""把 realm hd 裡「屬於我們」的 Keycloak 設定匯出成版控產物。

為什麼不用 Keycloak 內建的 realm 匯出：
  1. realm `hd` 是跟同事的訂閱平台共用的。整份匯出會把他的 client 一起抄走，
     那是別人的東西，不該進我們的 repo，也會讓 diff 充滿跟我們無關的變動。
  2. partial-export 端點要 `manage-realm`，我們的 service account 沒有
     （也不該有——那把權限大到可以改整個 realm）。

所以這支只抓我們自己的：`hd-pacs*` 三個 client、hd-pacs 底下的角色與 composite
展開結果、我們的群組、以及 user profile 的屬性定義。這些就是重建時真正要照抄的東西。

輸出是**穩定排序**的 JSON：key 排序、陣列排序、時間戳不寫進檔案，
所以 `git diff` 只會顯示真正被人改動的設定。

用法（PowerShell，在你自己的終端機跑，secret 不會經過任何人）：

    $env:KC_AUTHORITY  = 'https://sso.hdtech.tw/realms/hd'
    $env:KC_CLIENT_ID  = 'hd-pacs-identity-admin'
    $env:KC_CLIENT_SECRET = '<貼上 secret>'
    python D:\Dev\HyperDigital\docs\keycloak\export-hd-pacs.py

跑完 `git -C D:\Dev\HyperDigital\docs status` 就看得到差異。

需要的 service account 角色（realm-management）：
    view-realm, view-clients, query-groups
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# 我們自己的 client。realm 共用，前綴就是唯一的邊界，不要放非 hd-pacs 開頭的。
OUR_CLIENTS = ["hd-pacs", "hd-pacs-identity-admin", "hd-pacs-client"]

# 角色容器：scope 與職務 composite 都掛在這個 client 底下。
ROLE_CLIENT = "hd-pacs"

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "realm-hd")

# 每次讀都不一樣、或者換一台機器就不同的欄位。留著只會製造假的 diff。
VOLATILE_KEYS = {
    "secret",
    "registrationAccessToken",
    "clientAuthenticatorType_secretRotated",
}


def die(msg):
    print(f"錯誤：{msg}", file=sys.stderr)
    sys.exit(1)


def parse_authority(authority):
    """把 {server}/realms/{realm} 拆開。用最後一個 /realms/ 切，
    因為 server 本身的路徑裡也可能有 realms 這個字。"""
    authority = authority.rstrip("/")
    marker = "/realms/"
    idx = authority.rfind(marker)
    if idx < 0:
        die(f"KC_AUTHORITY 格式不對：'{authority}'，預期形如 https://host/realms/hd")
    server = authority[:idx]
    realm = authority[idx + len(marker):]
    if not server or not realm or "/" in realm:
        die(f"KC_AUTHORITY 格式不對：'{authority}'，預期形如 https://host/realms/hd")
    return server, realm


def get_token(authority, client_id, client_secret):
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode()
    req = urllib.request.Request(
        f"{authority.rstrip('/')}/protocol/openid-connect/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)["access_token"]
    except urllib.error.HTTPError as e:
        die(f"取 token 失敗 {e.code}：{e.read().decode('utf-8', 'replace')[:400]}")


def api(admin_base, token, path):
    req = urllib.request.Request(
        f"{admin_base}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        # 權限不足時 Keycloak 常常回 200 加空陣列而不是 403，所以會走到這裡的
        # 多半是路徑錯或 realm 錯，值得原樣印出來。
        die(f"GET {path} 失敗 {e.code}：{e.read().decode('utf-8', 'replace')[:400]}")


def scrub(obj):
    """遞迴移除易變欄位，並把「順序不具意義」的字串陣列排序。"""
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in sorted(obj.items()) if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        cleaned = [scrub(v) for v in obj]
        if all(isinstance(v, str) for v in cleaned):
            return sorted(cleaned)
        return cleaned
    return obj


def write_json(rel_path, data):
    path = os.path.join(OUT_DIR, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(scrub(data), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"  寫入 {os.path.relpath(path, OUT_DIR)}（{len(text)} 位元組）")


def main():
    authority = os.environ.get("KC_AUTHORITY", "").strip()
    client_id = os.environ.get("KC_CLIENT_ID", "").strip()
    client_secret = os.environ.get("KC_CLIENT_SECRET", "").strip()
    if not authority or not client_id or not client_secret:
        die("需要環境變數 KC_AUTHORITY / KC_CLIENT_ID / KC_CLIENT_SECRET，用法見本檔開頭。")

    server, realm = parse_authority(authority)
    admin_base = f"{server}/admin/realms/{realm}"
    print(f"realm：{realm} @ {server}")

    token = get_token(authority, client_id, client_secret)

    # 1) 我們的 client。用 clientId 查詢字串精準取，不要撈全部再過濾——
    #    撈全部會連同事的一起拿到，沒必要。
    print("client：")
    client_uuid = {}
    for cid in OUR_CLIENTS:
        found = api(admin_base, token, f"/clients?clientId={urllib.parse.quote(cid)}")
        if not found:
            # 空陣列有兩種可能：真的沒這個 client，或者 service account 缺
            # view-clients。兩者長得一模一樣，所以訊息要把兩種都講出來。
            print(f"  略過 {cid}：查不到（不存在，或 service account 缺 view-clients）")
            continue
        rep = found[0]
        client_uuid[cid] = rep["id"]
        write_json(f"clients/{cid}.json", rep)

    # 2) hd-pacs 底下的角色。composite 要展開存下來——
    #    composite 的成員才是「這個職務實際給了哪些權限」，
    #    而那正是別的地方（ScopeCatalog）要對得起來的東西。
    if ROLE_CLIENT in client_uuid:
        print("角色：")
        uid = client_uuid[ROLE_CLIENT]

        # composite 成員的 containerId 是 client 的**內部 UUID**，重建 realm 之後會變成
        # 另一串。直接寫下去等於這份檔案照抄不了、diff 也讀不出來，所以換成 clientId。
        name_cache = {v: k for k, v in client_uuid.items()}

        def container_name(container_id):
            if container_id not in name_cache:
                rep = api(admin_base, token, f"/clients/{urllib.parse.quote(container_id)}")
                name_cache[container_id] = rep.get("clientId", container_id)
            return name_cache[container_id]

        roles = api(admin_base, token, f"/clients/{uid}/roles")
        detailed = []
        for r in sorted(roles, key=lambda x: x["name"]):
            entry = {
                "name": r["name"],
                "description": r.get("description"),
                "composite": r.get("composite", False),
            }
            if r.get("composite"):
                comps = api(
                    admin_base, token,
                    f"/clients/{uid}/roles/{urllib.parse.quote(r['name'])}/composites")
                entry["composites"] = sorted(
                    f"{container_name(c['containerId'])}:{c['name']}" if c.get("clientRole")
                    else f"realm:{c['name']}"
                    for c in comps)
            detailed.append(entry)
        write_json(f"roles/{ROLE_CLIENT}.json", {
            "client": ROLE_CLIENT,
            "roleCount": len(detailed),
            "roles": detailed,
        })

    # 3) 群組。只寫名稱與路徑，不寫成員——成員是活資料，投影表才是查它的地方。
    print("群組：")
    groups = api(admin_base, token, "/groups")

    def flatten(gs, acc):
        for g in gs:
            acc.append({"name": g["name"], "path": g["path"]})
            flatten(g.get("subGroups", []), acc)
        return acc

    write_json("groups.json", {"groups": sorted(flatten(groups, []),
                                                key=lambda x: x["path"])})

    # 4) user profile。hdUserUuid / siteCode 的「只有 admin 能改」就宣告在這裡，
    #    那是安全性質不是外觀設定，掉了不會有任何錯誤訊息。
    print("user profile：")
    write_json("user-profile.json", api(admin_base, token, "/users/profile"))

    print("完成。接著跑 git diff 看有什麼被改過。")


if __name__ == "__main__":
    main()
