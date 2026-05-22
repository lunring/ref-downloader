# Agent Runbook — Extended Manual Flow

> This is the **expanded** version of [../SKILL.md](../SKILL.md): the 8-step manual
> three-script flow, full DOI-resolution fallback chain, and `PUBLISHER_MAP`
> extension procedure. SKILL.md covers the slim happy path; this file covers
> "what to do when the happy path breaks".
>
> Audience: agent mode (or human contributor) needing to debug or extend.

`<SKILL_DIR>` = this skill's folder (`skills/ref-downloader/` in source, or
`~/.claude/skills/ref-downloader/` etc. after install). Python scripts live in
`<SKILL_DIR>/scripts/`; config files (`config.example.toml`,
`config.local.toml`) live at `<SKILL_DIR>/`. All commands below assume the
user has installed prereqs once (`pip install playwright pymupdf &&
playwright install msedge`).

---

## Complete execution flow

```
用户提供 PDF 路径 OR DOI 字符串
        │
        ▼
Step 1  解析输入 → 获取 DOI
        │
        ▼
Step 2  确认 DOI 正确 + Edge 已关闭
        │
        ▼
Step 3  确定 OUTPUT_DIR 和 PROJECT_NAME
        │
        ├─ refs_raw.json 不存在 ──▶ Step 4  extract_refs.py <DOI>
        │
        ▼
Step 5  validate_refs.py <PROJECT_NAME>
        │
        ├─ 有 unknown publisher ──▶ 更新 PUBLISHER_MAP ──▶ 重跑
        │
        ▼
Step 6  download_refs.py <PROJECT_NAME>
        │
        ▼
Step 7  展示 download_report.csv 摘要
        │
        ▼
Step 8  清理 OUTPUT_DIR 旧脚本
```

---

## Step 1 — Resolve DOI

### Case A: User provides a DOI directly

Recognition rule: input starts with `10.` (e.g. `10.1021/jacs.5c05017`). Use as-is, skip to Step 2.

### Case B: User provides a local PDF path

**B.1 Try Zotero database first** (fast + most accurate metadata). Only attempt if `[zotero].db_path` is configured and the file exists:

```python
# Read db_path from config — do NOT hardcode
import sqlite3, shutil, os, sys, tempfile
from _config import load_config

cfg = load_config()
db_path = cfg.zotero.db_path  # Empty string if not configured
pdf_path = sys.argv[1]

if not db_path or not os.path.exists(db_path):
    print("")  # Caller falls back to fitz
else:
    # Copy to tmp to avoid locking the live Zotero DB
    tmp_db = tempfile.mktemp(suffix=".sqlite")
    shutil.copy2(db_path, tmp_db)
    try:
        conn = sqlite3.connect(tmp_db)
        basename = os.path.basename(pdf_path)
        row = conn.execute("""
            SELECT dv.value
            FROM itemData id
            JOIN fields f ON id.fieldID = f.fieldID
            JOIN itemDataValues dv ON id.valueID = dv.valueID
            WHERE f.fieldName = 'DOI'
              AND id.itemID IN (
                  SELECT parentItemID FROM itemAttachments
                  WHERE path LIKE ?
              )
            LIMIT 1
        """, (f"%{basename}%",)).fetchone()
        conn.close()
        print(row[0] if row else "")
    finally:
        os.remove(tmp_db)
```

**B.2 Fall back to PDF text extraction** if Zotero returned empty:

```python
import fitz, re, sys
doc = fitz.open(sys.argv[1])
text = "".join(doc[i].get_text() for i in range(min(3, len(doc))))
m = re.search(r'10\.\d{4,9}/[^\s"<>]+', text)
print(m.group(0).rstrip(".,;)") if m else "")
```

**B.3 Both methods failed** — ask the user explicitly:

> "无法自动识别该 PDF 的 DOI，请手动提供（格式：10.xxxx/xxxxx）"

---

## Step 2 — Confirm preconditions

Before running any script, confirm with the user:

```
即将开始下载参考文献：
  DOI：<DOI>
  输出目录：<OUTPUT_DIR>   (see Step 3)

请确认：
1. 以上 DOI 是否正确？
2. Microsoft Edge 是否已完全关闭？（脚本需要独占 Edge 配置文件）
```

---

## Step 3 — Decide OUTPUT_DIR and PROJECT_NAME

```
Case A: input is a PDF path
  OUTPUT_DIR = PDF parent dir + "/" + PDF stem + "_refs"
    Example: <path/to/paper>_refs/

Case B: input is a DOI (no original PDF path)
  OUTPUT_DIR default = current working directory + "/" + PROJECT_NAME + "_refs"
    Example: <cwd>/<project_name>_refs/
  Override with --output-dir
```

`PROJECT_NAME` = the segment after the last `/` in the DOI, with special characters replaced by `_`.

Project data lands in: `<OUTPUT_DIR>/<PROJECT_NAME>/`

**Incremental mode**: if `<OUTPUT_DIR>/<PROJECT_NAME>/refs_raw.json` already exists, **skip Step 4** and continue from Step 5.

Create `OUTPUT_DIR` if missing:

```bash
mkdir "<OUTPUT_DIR>"
```

Notes:
- `download_refs.py` writes run artifacts to `<OUTPUT_DIR>/runs/`.
- For manual three-script mode, `cd "<OUTPUT_DIR>"` first to keep output paths consistent.

---

## Step 4 — Run `extract_refs.py`

```bash
cd "<OUTPUT_DIR>"
python "<SKILL_DIR>/scripts/extract_refs.py" <DOI>
```

**Expected**: `<PROJECT_NAME>/refs_raw.json` created; console prints reference count.

**Error handling**:

| Error | Fix |
|---|---|
| `DOI not found in Crossref` | DOI may be wrong; confirm with user |
| `No references found` | Crossref didn't deposit references for that publisher; tool can't auto-extract |
| Network timeout | Retry once |
| `Overwrite? [y/N]` prompt | Should be skipped via Step 3's existing-file check; if non-interactive context, add `--yes` |

---

## Step 5 — Run `validate_refs.py`

```bash
cd "<OUTPUT_DIR>"
python "<SKILL_DIR>/scripts/validate_refs.py" <PROJECT_NAME>
```

**Expected**: `refs_validated.json` created; console shows `Verified: X / Failed: Y / No DOI: Z`.

### Extending `PUBLISHER_MAP` when unknown prefixes appear

After validation, scan `refs_validated.json` for `publisher == "unknown"` entries with DOIs:

```python
import json, urllib.request

data = json.loads(open("<OUTPUT_DIR>/<PROJECT_NAME>/refs_validated.json").read())
unknowns = [r for r in data["references"] if r.get("publisher") == "unknown" and r.get("doi")]

# Get unique prefixes
prefixes = {}
for r in unknowns:
    prefix = r["doi"].split("/")[0]
    if prefix not in prefixes:
        prefixes[prefix] = r["doi"]

print(f"Unknown prefixes: {list(prefixes.keys())}")
```

For each prefix, look up the publisher via Crossref:

```python
from _config import load_config, user_agent_from
cfg = load_config()
ua = user_agent_from(cfg)

url = f"https://api.crossref.org/works/{urllib.request.quote(doi, safe='')}"
req = urllib.request.Request(url, headers={"User-Agent": ua})
with urllib.request.urlopen(req, timeout=15) as r:
    msg = json.loads(r.read())["message"]
    publisher_name = msg.get("publisher", "").lower()
    print(f"  {prefix} → {publisher_name}")
```

Map publisher name to the internal key (see table) and update `PUBLISHER_MAP` in `<SKILL_DIR>/scripts/validate_refs.py`:

| Publisher name contains | Internal key |
|---|---|
| aip, american institute of physics | `aip` |
| ieee | `ieee` |
| osa, optica | `osa` |
| royal society of chemistry, rsc | `rsc` |
| american physical society | `aps` |
| taylor & francis | `tandfonline` |
| elsevier | `elsevier` |
| wiley | `wiley` |
| springer, nature portfolio | `springer` / `nature` |

After updating `PUBLISHER_MAP`, **re-run** `validate_refs.py` (incremental: only re-classifies the unknown entries):

```bash
cd "<OUTPUT_DIR>"
python "<SKILL_DIR>/scripts/validate_refs.py" <PROJECT_NAME>
```

Also: if `download_refs.py` lacks a `direct_pdf_url` template or `PDF_SELECTORS` entry for the new publisher, add reasonable defaults (use `doi.org/{doi}` for article URL, `a:has-text("PDF")` as a selector fallback). See [CONTRIBUTING.md](../../../CONTRIBUTING.md) for the full add-publisher workflow.

---

## Step 6 — Run `download_refs.py`

```bash
cd "<OUTPUT_DIR>"
python "<SKILL_DIR>/scripts/download_refs.py" <PROJECT_NAME>
```

**Default mode is interactive**. Pick `--auto` only when no one is watching the run (CI, overnight batch, sleep run); otherwise stay interactive so you can drive captchas and SSO yourself.

The `--auto` flag (v0.3.0+):
- Skips manual Enter-to-confirm.
- Uses 15s challenge wait (vs interactive 10s).
- **Manual-pending refs get queued for a single asynchronous retry attempt** ~60s later (gated by `is_auto_mode()` in `download_refs.py`). The main loop does not block — it keeps downloading other refs while the retry queue drains in the background. Up to 3 retries run concurrently, up to 8 pending. Refs that succeed on retry update the report to `downloaded`; refs that still fail keep their `manual_pending (...)` status.
- Suitable when you genuinely cannot click — and you accept that a captcha/SSO ref that needs human input will stay `manual_pending` permanently in this run.
- **Not suitable** when you _can_ click; interactive mode pauses for you and gets higher success rates on Elsevier / Wiley / institutional-SSO refs.

Behavioral details:
- Launches **real Microsoft Edge persistent profile** at `[browser].edge_profile_dir` (or `%LOCALAPPDATA%\Microsoft\Edge\User Data` default on Windows).
- Extensions stay enabled by default; set `[browser].disable_extensions = true` or env `REF_DOWNLOADER_DISABLE_EXTENSIONS=1` to disable.
- Interactive mode keeps `manual_pending` pages open for the retry loop.
- Main-loop "small-queue immediate flush" (interactive mode):
  - **Elsevier**: first `manual_pending` triggers an immediate prompt + retry, leveraging hot session.
  - After Elsevier challenge is solved, subsequent Elsevier transient states (`crasolve shell`, `viewer_capture_failed`) auto-retry once in the hot window.
  - **Other publishers**: accumulate to a small queue limit before prompting.
- Auto-mode async retry queue (separate mechanism, only active under `--auto`):
  - Drained at three points in `main`: before each `download_one`, after each `download_one`, and at end-of-run (with `wait=True`).
  - Cancelled on `restart_edge_context` (Edge session crash) so retries don't fire against a dead context.
  - `sync_report_with_existing_files` reconciles the in-memory report with files on disk before writing `download_report.csv`, picking up successes that finished mid-loop.
- If Edge session crashes mid-run, the script auto-restarts once and only retries the current ref.
- If a ref entered the PDF viewer but auto-save missed it, manual retry prefers the **current live page** over re-navigating to the article.

**Expected output**:
- PDF files saved to `<OUTPUT_DIR>/<PROJECT_NAME>/`
- Events stored at `<OUTPUT_DIR>/runs/<timestamp>-round-03/events.jsonl`
- Graceful completion regenerates `<OUTPUT_DIR>/<PROJECT_NAME>/download_report.csv`

**Status codes**:
- `downloaded (X KB)` — fresh download succeeded
- `already_exists` — previously downloaded, skipped
- `manual_pending` — needs institutional access or captcha
- `failed (...)` — automatic path failed
- `ignored` — DOI in `[institution].ignored_access_dois`

Per-ref report also carries:
- `session_restarts` — auto session-recovery count for this ref
- `session_last_error` — most recent triggering browser error

**Important reality constraint**: `download_report.csv` is regenerated **only on graceful completion**. If you `Ctrl+C` / kill / crash mid-run, the root CSV may not reflect the latest state. In that case trust:
- The latest `<OUTPUT_DIR>/runs/<timestamp>-round-03/events.jsonl`
- Actual files that landed in `<OUTPUT_DIR>/<PROJECT_NAME>/`

---

## Step 7 — Show the report

Priority order:

1. **Run completed gracefully** → read `<OUTPUT_DIR>/<PROJECT_NAME>/download_report.csv` for the per-ref summary.
2. **Run interrupted** → don't trust the stale CSV. Read:
   - Latest `<OUTPUT_DIR>/runs/<timestamp>-round-03/events.jsonl`
   - Actual PDF / SI files in `<OUTPUT_DIR>/<PROJECT_NAME>/`

Graceful-completion summary template:

```
========== 下载报告 ==========
总参考文献：X 条
主文 PDF 成功：X 篇
主文 PDF 失败：X 篇（见下方列表）
需手动下载：X 篇
SI 文件成功：X 个
PDF 位置：<OUTPUT_DIR>/<PROJECT_NAME>/
==============================

未能自动下载（可尝试手动）：
  [7]  Wang2018_JPowerSources  https://doi.org/10.1016/j.jpowsour.2018.01.068
  ...
```

---

## Step 8 — Cleanup

If invoked via `run_ref_downloader.py`, the wrapper runs a narrow cleanup pass on `<OUTPUT_DIR>` root (not the `<PROJECT_NAME>` subdirectory):

```
Patterns cleaned (if present):
  fetch_refs.py
  fetch_refs_playwright.py
  fetch_refs_v2.py
  *.log  (last-modified > 7 days)
```

Cleanup rules:
- Only the `OUTPUT_DIR` itself, no recursion into subdirs
- `.bak` files are preserved (likely user backups)
- Nothing in `<SKILL_DIR>` is touched
- Manual three-script invocations skip this step by default

---

## Common issues (extended)

| Symptom | Resolution |
|---|---|
| `No references found` | Crossref didn't deposit reference metadata for that publisher's record; tool can't auto-extract. Tell user. |
| Edge won't launch | Make sure Edge is fully closed (including background `msedge.exe` in Task Manager); re-run Step 6 |
| Many `manual_pending` | VPN / campus network not connected, or publisher requires SSO. See [CONTRIBUTING.md](../../../CONTRIBUTING.md) `[institution]` section for SSO host configuration. |
| Root `download_report.csv` looks stale | If the run was interrupted, use the latest `runs/<timestamp>/events.jsonl` + the project directory's actual files. |
| Many `failed` in `validated.json` | Transient Crossref API failure; re-run Step 5 (incremental skips already-verified). |
| Zotero lookup returns nothing for a PDF | Confirm `[zotero].db_path` points to the right `zotero.sqlite`; fall back to fitz text extraction; if both fail, ask user for the DOI manually. |
| `WARNING: crossref.mailto is the placeholder` | Edit `<SKILL_DIR>/config.local.toml` and set `[crossref].mailto` to a real email to enter Crossref polite pool. |

## See also

- [../SKILL.md](../SKILL.md) — slim agent entry; trigger conditions and primary entry command
- [../../../README.md](../../../README.md) — human-facing setup and usage
- [../../../docs/SUPPORTED_PUBLISHERS.md](../../../docs/SUPPORTED_PUBLISHERS.md) — per-publisher download strategy + maturity tier
- [../../../CONTRIBUTING.md](../../../CONTRIBUTING.md) — adding a new publisher / institution SSO patterns
- [../config.example.toml](../config.example.toml) — full config schema (now at skill root)
