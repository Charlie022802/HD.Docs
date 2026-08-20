---
name: feedback_versioning_convention
description: HD 產品版控慣例 — 發布前語意版本固定、序號只在交付時 +1、build 靠自動時間戳;細節在 hd-versioning skill
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4955439c-e319-4882-9ff7-dc4be5c80843
  modified: 2026-07-27T03:51:49.291Z
---

使用者為所有 HD.* 產品定了一套版控規約,並做成 **user-level skill `hd-versioning`**(`~/.claude/skills/hd-versioning/SKILL.md`,跨對話可用)。

**Why:** 之前我一路 bump `1.0.1→1.0.2→…` 只為了讓每個 build 有區別,把「版本」和「build 識別」混在一起。使用者指正:產品還在 beta、沒發過正式版,不該一直加 patch。

**How to apply(幫他標版本時):**
- 格式 `主.次.修-階段.序號+build`,例 `1.0.0-alpha.1+20260727-144530`。
- **發布前語意版本固定**(通常停在 `1.0.0`);PATCH 是發布後才用。**別再每 build bump patch。**
- 階段 alpha(功能還在長)→ beta(功能凍結、抓 bug)→ rc → 拿掉後綴。內部同事試用仍算 alpha。
- 序號 `.N` **只在「交付一版給人測」時手動 +1**;平常自測不動。
- build 時間戳**自動**(Release build 才戳),負責區分每顆 build。序號≠時間戳(交付輪次 vs 實體 build)。

**已套用:** HD.Pacs.DicomWeb(`Directory.Build.props` Release 自動戳 + `Domain/AppVersion.cs` 拆 Version/Build + `/health` 回 version+build);repo 根有 `VERSIONING.md`。現行版本 `1.0.0-alpha.1`(從先前混亂的 1.0.x 重置)。詳見 [[project_dicomweb_impl_split]]。
