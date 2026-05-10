# ref-downloader Open-Source Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor a copied-but-untouched-original Python skill into a GitHub-ready open-source project: replace all private/institutional info with config-driven values, add bilingual docs, license, issue templates, and verification gates — without modifying the source skill at `<original-skill-dir>\`.

**Architecture:** Three-layer config (env vars > `config.local.toml` > `config.example.toml` > built-in fallback), loaded once at wrapper entry and threaded through all four scripts via a `_config.py` dataclass. Personal/institution-specific strings — both at module-level constants and at five inline checks scattered through `download_refs.py` — read from config instead.

**Tech Stack:** Python 3.11, stdlib `tomllib`, dataclasses; existing dependencies unchanged (Playwright, Crossref, optional PyMuPDF).

**Working dir:** `<this-repo>\` (pre-populated with original code copied from `<original-skill-dir>\` minus `__pycache__/` and `temp_*.py`).

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `_config.py` | **create** | Loads TOML + env vars; exposes `Config` dataclass with `crossref`, `zotero`, `browser`, `institution` sections |
| `config.example.toml` | **create** | Committed template documenting all options; safe defaults |
| `config.local.toml` | **create (gitignored)** | User's actual values; empty in fresh checkout |
| `run_ref_downloader.py` | **modify** | Read config, pass through; add `--config`, `--yes` |
| `extract_refs.py` | **modify** | Mailto from config; non-tty input handling |
| `validate_refs.py` | **modify** | Mailto from config |
| `download_refs.py` | **modify** | 11 line-level edits: lazy-load EDGE_USER_DATA, replace 5 institution-config constant blocks + 5 inline string checks with config reads, rename auth_redirect reason |
| `SKILL.md` | **rewrite** | Trim to agent-mode runbook; remove personal paths; cross-link README |
| `LICENSE` | **create** | MIT |
| `README.md` | **create** | English; primary documentation |
| `README.zh.md` | **create** | Chinese mirror |
| `CONTRIBUTING.md` | **create** | How to add publisher / report bug; documents auth_loading_titles ambiguity |
| `SECURITY.md` | **create** | Edge-profile-cookie warning; recommend dedicated browser profile |
| `CHANGELOG.md` | **create** | v0.1.0 entry |
| `requirements.txt` | **create** | playwright, pymupdf (optional marker) |
| `.gitignore` | **create** | __pycache__/, *.pyc, config.local.toml, runs/, *_refs/ |
| `docs/SUPPORTED_PUBLISHERS.md` | **create** | Extracted publisher table + tier explanation from old SKILL.md |
| `tests/README.md` | **create** | Manual smoke-test recipe |
| `.github/ISSUE_TEMPLATE/bug-report.md` | **create** | Forces user to attach: DOI, publisher, env, events.jsonl excerpt |
| `.github/ISSUE_TEMPLATE/new-publisher.md` | **create** | DOI prefix, sample article URL, PDF selector |

---

## Task 1: Initialize git + .gitignore

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Initialize git repo**

```powershell
git init
git branch -M main
```

- [ ] **Step 2: Create .gitignore**

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/
.venv/
venv/

# Local config (user-specific)
config.local.toml

# Runtime artifacts
runs/
*_refs/
test_smoke/
events.jsonl

# Editor
.vscode/
.idea/
*.swp
*.swo
.DS_Store
Thumbs.db

# Output reports
download_report.csv
postmortem.md
```

- [ ] **Step 3: Initial commit (the copied-but-not-yet-refactored state)**

```powershell
git add .
git status
git commit -m "Initial import: copy from personal skill, drop temp files and pycache"
```

Expected `git status` after commit: clean working tree.

---

## Task 2: Config loader module (`_config.py`)

**Files:**
- Create: `_config.py`

- [ ] **Step 1: Write `_config.py`**

```python
"""Config loader for ref-downloader.

Resolution order (highest priority first):
    1. Environment variables (REF_DOWNLOADER_*)
    2. TOML file pointed to by --config or REF_DOWNLOADER_CONFIG
    3. config.local.toml in this package directory
    4. config.example.toml in this package directory
    5. Built-in fallback (empty / placeholder)

Used by run_ref_downloader.py, extract_refs.py, validate_refs.py, download_refs.py.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import List, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore

PACKAGE_DIR = Path(__file__).resolve().parent
EXAMPLE_TOML = PACKAGE_DIR / "config.example.toml"
LOCAL_TOML = PACKAGE_DIR / "config.local.toml"
PLACEHOLDER_MAILTO = "your.email@example.com"


@dataclass
class CrossrefConfig:
    mailto: str = PLACEHOLDER_MAILTO


@dataclass
class ZoteroConfig:
    db_path: str = ""


@dataclass
class BrowserConfig:
    edge_profile_dir: str = ""
    disable_extensions: bool = False


@dataclass
class InstitutionConfig:
    auth_hosts: List[str] = field(default_factory=list)
    auth_url_fragments: List[str] = field(default_factory=list)
    auth_page_titles: List[str] = field(default_factory=list)
    auth_loading_titles: List[str] = field(default_factory=list)
    ignored_access_dois: List[str] = field(default_factory=list)


@dataclass
class Config:
    crossref: CrossrefConfig = field(default_factory=CrossrefConfig)
    zotero: ZoteroConfig = field(default_factory=ZoteroConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    institution: InstitutionConfig = field(default_factory=InstitutionConfig)
    source_files: List[str] = field(default_factory=list)


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _merge_dict(base: dict, overlay: dict) -> dict:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _merge_dict(dict(base[key]), value)
        else:
            base[key] = value
    return base


def _build_from_dict(data: dict, source_files: List[str]) -> Config:
    crossref = data.get("crossref", {}) or {}
    zotero = data.get("zotero", {}) or {}
    browser = data.get("browser", {}) or {}
    institution = data.get("institution", {}) or {}
    return Config(
        crossref=CrossrefConfig(
            mailto=str(crossref.get("mailto", PLACEHOLDER_MAILTO)),
        ),
        zotero=ZoteroConfig(
            db_path=str(zotero.get("db_path", "")),
        ),
        browser=BrowserConfig(
            edge_profile_dir=str(browser.get("edge_profile_dir", "")),
            disable_extensions=bool(browser.get("disable_extensions", False)),
        ),
        institution=InstitutionConfig(
            auth_hosts=list(institution.get("auth_hosts", []) or []),
            auth_url_fragments=list(institution.get("auth_url_fragments", []) or []),
            auth_page_titles=list(institution.get("auth_page_titles", []) or []),
            auth_loading_titles=list(institution.get("auth_loading_titles", []) or []),
            ignored_access_dois=list(institution.get("ignored_access_dois", []) or []),
        ),
        source_files=source_files,
    )


def _apply_env_overrides(cfg: Config) -> Config:
    mailto = os.environ.get("REF_DOWNLOADER_MAILTO")
    zotero = os.environ.get("REF_DOWNLOADER_ZOTERO_DB")
    edge = os.environ.get("REF_DOWNLOADER_EDGE_PROFILE")
    disable_ext = os.environ.get("REF_DOWNLOADER_DISABLE_EXTENSIONS")

    if mailto:
        cfg = replace(cfg, crossref=replace(cfg.crossref, mailto=mailto))
    if zotero is not None:
        cfg = replace(cfg, zotero=replace(cfg.zotero, db_path=zotero))
    if edge is not None:
        cfg = replace(cfg, browser=replace(cfg.browser, edge_profile_dir=edge))
    if disable_ext is not None:
        flag = disable_ext.strip().lower() in ("1", "true", "yes", "on")
        cfg = replace(cfg, browser=replace(cfg.browser, disable_extensions=flag))
    return cfg


def load_config(explicit_path: Optional[Path] = None) -> Config:
    """Load config from TOML files + env vars, return frozen Config dataclass.

    explicit_path: if provided (e.g. from --config CLI arg), used as the highest-
    priority TOML; else REF_DOWNLOADER_CONFIG env var; else local.toml; else example.toml.
    """
    chain: List[Path] = []
    chain.append(EXAMPLE_TOML)
    if LOCAL_TOML.exists():
        chain.append(LOCAL_TOML)

    env_path = os.environ.get("REF_DOWNLOADER_CONFIG")
    if env_path:
        chain.append(Path(env_path).expanduser())
    if explicit_path:
        chain.append(explicit_path.expanduser())

    merged: dict = {}
    used: List[str] = []
    for path in chain:
        if not path.exists():
            continue
        data = _load_toml(path)
        merged = _merge_dict(merged, data)
        used.append(str(path))

    cfg = _build_from_dict(merged, used)
    cfg = _apply_env_overrides(cfg)
    return cfg


def user_agent_from(cfg: Config, app: str = "RefDownloader/1.0") -> str:
    return f"{app} (mailto:{cfg.crossref.mailto})"


def warn_if_placeholder_mailto(cfg: Config) -> None:
    if cfg.crossref.mailto == PLACEHOLDER_MAILTO:
        print(
            "WARNING: crossref.mailto is the placeholder. "
            "Edit config.local.toml (copy from config.example.toml) or set "
            "REF_DOWNLOADER_MAILTO to enter the Crossref polite pool.",
            file=sys.stderr,
        )
```

- [ ] **Step 2: Smoke test that the loader imports**

Run:
```powershell
python -c "from _config import load_config; c = load_config(); print(c.crossref.mailto, c.zotero.db_path)"
```

Expected before Task 3 creates the example.toml: `your.email@example.com` (placeholder).
Expected after Task 3 also runs: same — empty source files yield placeholder.

(Skip running until after Task 3, since example.toml doesn't exist yet — but the file should still import without error since `_load_toml` returns `{}` for missing paths.)

- [ ] **Step 3: Commit**

```powershell
git add _config.py
git commit -m "Add config loader with env+toml resolution"
```

---

## Task 3: Config templates

**Files:**
- Create: `config.example.toml`
- Create: `config.local.toml` (gitignored — should NOT show up in `git status`)

- [ ] **Step 1: Write `config.example.toml`**

```toml
# Copy this file to config.local.toml and edit. config.local.toml is gitignored.
# Environment variables (REF_DOWNLOADER_*) override these values.

[crossref]
# Crossref polite-pool identifier. Replace with your email — helps API priority.
# If left as the placeholder, the wrapper prints a warning at startup.
mailto = "your.email@example.com"

[zotero]
# Optional: Zotero SQLite path. If set + file exists, the wrapper resolves DOI
# from a PDF filename via Zotero metadata (faster than the fitz fallback).
# Leave empty "" to disable. fitz fallback still works for any PDF.
# Examples:
#   Windows: db_path = "D:\\YourName\\Documents\\Zotero\\zotero.sqlite"
#   macOS:   db_path = "/Users/you/Zotero/zotero.sqlite"
#   Linux:   db_path = "/home/you/Zotero/zotero.sqlite"
db_path = ""

[browser]
# Edge persistent profile directory.
# Empty = OS default (Windows: %LOCALAPPDATA%\Microsoft\Edge\User Data)
# This tool launches that profile, so close all Edge windows before running.
edge_profile_dir = ""
# Set to true to launch Edge with extensions disabled (useful for debugging
# extension-induced page-load issues).
disable_extensions = false

[institution]
# Optional: institutional SSO patterns.
# Leave all lists empty for vanilla open-internet use (no SSO at your org).
# Adding your university's SSO host/title enables auth-redirect detection during
# downloads, so the script knows when a paywalled link bounced you to login
# instead of treating that as a failed PDF.
#
# Example for a university with SSO:
#   auth_hosts          = ["sso.your-uni.edu", "idp.your-uni.edu"]
#   auth_url_fragments  = ["oauth", "saml", "shibboleth"]
#   auth_page_titles    = ["Your University Single Sign-On"]
#   auth_loading_titles = []
#   ignored_access_dois = ["10.xxxx/yyyyy"]   # DOIs you know are paywalled
#
# NOTE: auth_loading_titles is ALSO consumed by the AIP/AVS publisher
# loading-page detection path (it shares the same Chinese "Please wait" string
# detection as Chinese-locale SSO loading pages). The script bakes safe AIP/AVS
# defaults in code, so you only need to add anything here if your institution
# has SSO loading text not already covered.
auth_hosts          = []
auth_url_fragments  = []
auth_page_titles    = []
auth_loading_titles = []
ignored_access_dois = []
```

- [ ] **Step 2: Write `config.local.toml` (user's actual values, gitignored)**

The original maintainer's config (institution-specific values redacted to placeholders for the public repo). Each user fills in their own values; this file never reaches git.

```toml
# config.local.toml — gitignored. Personal values for this machine.

[crossref]
mailto = "<your-email@example.com>"

[zotero]
db_path = "<path-to-your-zotero.sqlite>"   # e.g. "D:\\YourName\\Documents\\Zotero\\zotero.sqlite"

[browser]
edge_profile_dir = ""
disable_extensions = false

[institution]
# Fill in your own institution's SSO patterns; leave empty if no institution-bound access
auth_hosts          = ["<sso-host.your-uni.edu>"]
auth_url_fragments  = ["<oauth-fragment>"]
auth_page_titles    = ["<Your University Single Sign-On title>"]
auth_loading_titles = []
ignored_access_dois = []
```

- [ ] **Step 3: Verify `config.local.toml` is gitignored**

```powershell
git status
```

Expected: `config.local.toml` does NOT appear (it's in .gitignore from Task 1).

- [ ] **Step 4: Verify the loader picks up both files**

```powershell
python -c "from _config import load_config; c = load_config(); print('mailto:', c.crossref.mailto); print('zotero:', c.zotero.db_path); print('institution.auth_hosts:', c.institution.auth_hosts); print('source_files:', c.source_files)"
```

Expected: `mailto: <your configured email>`, zotero non-empty, auth_hosts non-empty, source_files lists both example + local.

- [ ] **Step 5: Commit only the example template**

```powershell
git add config.example.toml
git commit -m "Add config.example.toml template"
```

(`config.local.toml` is gitignored and stays only on the local machine.)

---

## Task 4: Refactor `run_ref_downloader.py`

**Files:**
- Modify: `run_ref_downloader.py`

- [ ] **Step 1: Replace ZOTERO_DB hardcode + add config plumbing + flags**

Edit the top of `run_ref_downloader.py`. Replace lines 30–38 (current SKILL_DIR, ZOTERO_DB, etc.) with:

```python
SKILL_DIR = Path(__file__).resolve().parent
LEGACY_ROOT_FILENAMES = (
    "fetch_refs.py",
    "fetch_refs_playwright.py",
    "fetch_refs_v2.py",
)
SEVEN_DAYS_SECONDS = 7 * 24 * 60 * 60
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+")
```

(i.e., delete the `ZOTERO_DB = Path(...)` line entirely.)

Add an import for the config loader at the top of the imports block:

```python
from _config import load_config, warn_if_placeholder_mailto
```

- [ ] **Step 2: Replace `resolve_doi_from_zotero` to take db_path as argument**

Current signature:
```python
def resolve_doi_from_zotero(pdf_path: Path) -> str:
    if not ZOTERO_DB.exists():
        return ""
    tmp_db = Path(tempfile.mktemp(suffix=".sqlite"))
    try:
        shutil.copy2(ZOTERO_DB, tmp_db)
        ...
```

Replace with:
```python
def resolve_doi_from_zotero(pdf_path: Path, zotero_db: Path) -> str:
    if not zotero_db or not zotero_db.exists():
        return ""
    tmp_db = Path(tempfile.mktemp(suffix=".sqlite"))
    try:
        shutil.copy2(zotero_db, tmp_db)
        ...
```

(Only the function signature and the first two lines change; the rest is identical, just replacing `ZOTERO_DB` references inside with `zotero_db`.)

- [ ] **Step 3: Update `resolve_input` to thread db_path through**

Current `resolve_input` calls `resolve_doi_from_zotero(pdf_path)`. Change signature to:

```python
def resolve_input(input_value: str, output_dir_arg: str, zotero_db: Path) -> tuple[str, Path, str]:
    ...
    doi = resolve_doi_from_zotero(pdf_path, zotero_db) or resolve_doi_from_pdf_text(pdf_path)
    ...
```

- [ ] **Step 4: Add `--config` and `--yes` to `parse_args`**

Replace `parse_args` body:

```python
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full ref-downloader pipeline from a DOI or a parent PDF path.",
    )
    parser.add_argument("input", help="DOI string or local PDF path")
    parser.add_argument(
        "--output-dir",
        default="",
        help="Override OUTPUT_DIR. By default: DOI -> <cwd>/<project_name>_refs, PDF -> sibling <pdf_stem>_refs",
    )
    parser.add_argument(
        "--config",
        default="",
        help="Path to alternate TOML config file (overrides config.local.toml).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Non-interactive mode: assume yes to overwrite prompts. Use for CI / batch runs.",
    )
    return parser.parse_args()
```

- [ ] **Step 5: Update `main()` to load config and pass db_path through**

Replace `main()`:

```python
def main() -> None:
    args = parse_args()

    config_path = Path(args.config) if args.config else None
    cfg = load_config(config_path)
    warn_if_placeholder_mailto(cfg)

    zotero_db = Path(cfg.zotero.db_path).expanduser() if cfg.zotero.db_path else Path("")
    doi, output_dir, project_name = resolve_input(args.input, args.output_dir, zotero_db)
    output_dir.mkdir(parents=True, exist_ok=True)

    project_dir = output_dir / project_name
    raw_path = project_dir / "refs_raw.json"

    print("=== Ref Downloader Wrapper ===")
    print(f"DOI:         {doi}")
    print(f"OUTPUT_DIR:  {output_dir}")
    print(f"PROJECT:     {project_name}")
    print(f"Python:      {sys.executable}")
    if cfg.source_files:
        print(f"Config:      {' + '.join(cfg.source_files)}")

    extra_args = ["--yes"] if args.yes else []

    if raw_path.exists():
        print(f"\n>>> Reusing existing raw refs: {raw_path}")
    else:
        run_step("extract_refs.py", [doi, *extra_args], output_dir)

    run_step("validate_refs.py", [project_name], output_dir)
    run_step("download_refs.py", [project_name], output_dir)

    cleanup_output_dir_root(output_dir)
    print("\n✓ Wrapper finished.")
    print(f"  Project dir : {project_dir}")
    print(f"  Run artifacts: {output_dir / 'runs'}")
```

- [ ] **Step 6: Verify it imports and `--help` works**

```powershell
python run_ref_downloader.py --help
```

Expected output: usage text mentioning `--config` and `--yes`.

- [ ] **Step 7: Commit**

```powershell
git add run_ref_downloader.py
git commit -m "Wire wrapper to config loader; add --config and --yes flags"
```

---

## Task 5: Refactor `extract_refs.py`

**Files:**
- Modify: `extract_refs.py`

- [ ] **Step 1: Add config import + USER_AGENT from config + `--yes` flag**

Replace the import + constants section (lines 14–24) with:

```python
import sys
import json
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

from _config import load_config, user_agent_from, warn_if_placeholder_mailto


API_BASE = "https://api.crossref.org/works"
```

Note: USER_AGENT becomes a function-local string, built from config inside `main()`.

- [ ] **Step 2: Update `fetch_crossref` to take user_agent as argument**

Replace `fetch_crossref` signature:

```python
def fetch_crossref(doi: str, user_agent: str) -> dict:
    """Fetch metadata for a single DOI from Crossref API."""
    url = f"{API_BASE}/{urllib.request.quote(doi, safe='')}"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())["message"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  ERROR: DOI not found in Crossref: {doi}")
            return {}
        raise
```

- [ ] **Step 3: Update `extract_references` to thread user_agent through**

```python
def extract_references(parent_doi: str, user_agent: str) -> dict:
    """Extract reference list from a parent paper's Crossref entry."""
    print(f"Fetching parent paper: {parent_doi}")
    parent = fetch_crossref(parent_doi, user_agent)
    ...
```

(Only the signature + the first `fetch_crossref` call need updating; rest of function unchanged.)

- [ ] **Step 4: Replace `main()` with config-aware + non-tty handling**

```python
def main():
    parser = argparse.ArgumentParser(description="Extract reference DOIs via Crossref.")
    parser.add_argument("parent_doi", help="Parent paper DOI (e.g. 10.1021/jacs.5c05017)")
    parser.add_argument("--yes", action="store_true",
                        help="Non-interactive: overwrite refs_raw.json without asking.")
    args = parser.parse_args()

    cfg = load_config()
    warn_if_placeholder_mailto(cfg)
    user_agent = user_agent_from(cfg, "RefDownloader/1.0")

    parent_doi = args.parent_doi.strip()
    project_name = doi_to_project_name(parent_doi)
    project_dir = Path(project_name)
    output_path = project_dir / "refs_raw.json"

    if output_path.exists():
        if args.yes:
            print(f"WARNING: {output_path} exists; --yes given, overwriting.")
        elif not sys.stdin.isatty():
            print(f"ERROR: {output_path} exists and stdin is not a TTY; refusing to overwrite. Pass --yes to force.")
            sys.exit(2)
        else:
            print(f"WARNING: {output_path} already exists.")
            answer = input("  Overwrite? [y/N] ").strip().lower()
            if answer != "y":
                print("Aborted.")
                sys.exit(0)

    project_dir.mkdir(exist_ok=True)
    print(f"Project directory: {project_dir}/\n")

    result = extract_references(parent_doi, user_agent)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Saved to {output_path}")
    print(f"  Next step: python validate_refs.py {project_name}")
```

- [ ] **Step 5: Verify the script imports and `--help` works**

```powershell
python extract_refs.py --help
```

Expected: usage text with positional `parent_doi` and `--yes` flag.

- [ ] **Step 6: Commit**

```powershell
git add extract_refs.py
git commit -m "Read mailto from config; add --yes for non-tty environments"
```

---

## Task 6: Refactor `validate_refs.py`

**Files:**
- Modify: `validate_refs.py`

- [ ] **Step 1: Add config import + replace USER_AGENT constant with function call**

Replace lines 18–28 (imports + constants):

```python
import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

from _config import load_config, user_agent_from, warn_if_placeholder_mailto

API_BASE = "https://api.crossref.org/works"
RATE_LIMIT_DELAY = 0.35  # seconds between API calls (Crossref polite pool)
```

(Delete `USER_AGENT = "RefDownloader/1.0 ..."` constant.)

- [ ] **Step 2: Find every reference to `USER_AGENT` in this file and route through user_agent**

```powershell
python -c "import re; print(re.findall(r'USER_AGENT', open('validate_refs.py', encoding='utf-8').read()))"
```

For each hit, change the function signature to take a `user_agent: str` argument and pass it through. Typically there's one `urllib.request.Request(url, headers={\"User-Agent\": USER_AGENT})` call.

- [ ] **Step 3: Build user_agent in `main()` from config**

Add at the start of `main()`:

```python
def main():
    cfg = load_config()
    warn_if_placeholder_mailto(cfg)
    user_agent = user_agent_from(cfg, "RefDownloader/1.0")
    # ... existing main() body, but pass user_agent to any function that hits Crossref
```

- [ ] **Step 4: Verify the script imports**

```powershell
python -c "import validate_refs"
```

Expected: no error.

- [ ] **Step 5: Commit**

```powershell
git add validate_refs.py
git commit -m "Read Crossref mailto from config in validate_refs"
```

---

## Task 7: Refactor `download_refs.py` — institution config wiring (10 edits)

**Files:**
- Modify: `download_refs.py`

This is the heaviest task. We make 10 line-level edits + 1 module-level constant deletion. **Do NOT touch any other lines**, especially the 3000+ lines of business logic.

**Strategy:** Load config once at the top of `main()` (or wherever the entrypoint is), then thread either the `cfg.institution` dataclass or its individual lists through to the call sites that need them. Most uses are inside async functions, so we make the institution config a module-level mutable holder set at startup.

- [ ] **Step 1: Add config import and a runtime holder**

After the existing imports, before the first `STATUS_*` constant, add:

```python
from _config import load_config, InstitutionConfig

# Mutable holder set by `init_institution_config()` from `main()`.
# Default = empty (no SSO patterns configured).
_INSTITUTION: InstitutionConfig = InstitutionConfig()


def init_institution_config(cfg_institution: InstitutionConfig) -> None:
    """Called once at startup from main(); makes config visible to async helpers."""
    global _INSTITUTION
    _INSTITUTION = cfg_institution
```

- [ ] **Step 2: Replace `EDGE_USER_DATA` module-level constant (line 78) with a getter**

Delete line 78 (`EDGE_USER_DATA = os.path.expandvars(...)`).

Add this helper function right after the `env_flag` function:

```python
def get_edge_user_data_dir() -> str:
    """Resolve Edge profile dir at call time (after config is loaded).

    Lookup order:
        1. config.browser.edge_profile_dir if non-empty
        2. %LOCALAPPDATA%\\Microsoft\\Edge\\User Data (Windows default)
    """
    cfg = load_config()
    if cfg.browser.edge_profile_dir:
        return cfg.browser.edge_profile_dir
    return os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data")
```

Find every reference to `EDGE_USER_DATA` in the file and replace it with `get_edge_user_data_dir()`:

```powershell
python -c "import re; lines = open('download_refs.py', encoding='utf-8').read().splitlines(); print('\n'.join(f'{i+1}: {l}' for i,l in enumerate(lines) if 'EDGE_USER_DATA' in l))"
```

- [ ] **Step 3: Replace `IGNORED_INSTITUTION_ACCESS_DOIS` constant (lines 119–122)**

Delete lines 119–122 (the constant block).

Add a getter after the `env_flag` / `get_edge_user_data_dir` block:

```python
def ignored_institution_access_dois() -> set:
    return set(_INSTITUTION.ignored_access_dois)
```

Find every reference to `IGNORED_INSTITUTION_ACCESS_DOIS` and replace with `ignored_institution_access_dois()`:

```powershell
python -c "import re; lines = open('download_refs.py', encoding='utf-8').read().splitlines(); print('\n'.join(f'{i+1}: {l}' for i,l in enumerate(lines) if 'IGNORED_INSTITUTION_ACCESS_DOIS' in l))"
```

(Per Plan reviewer: lines 119, 393, 2977. Confirm via the command above.)

- [ ] **Step 4: Replace AUTH_HOST_PATTERNS (1122–1124), AUTH_URL_PATTERNS (1126–1129), AUTH_TITLE_PATTERNS (1131–1134)**

Delete lines 1121–1134 (the three constant tuples + comment header).

Replace with:

```python
# ── Captcha / challenge detection ────────────────────────────────────────────
# Auth patterns are read from `_INSTITUTION` set by init_institution_config().
# See config.example.toml [institution] section.
def _auth_hosts():            return tuple(_INSTITUTION.auth_hosts)
def _auth_url_fragments():    return tuple(_INSTITUTION.auth_url_fragments)
def _auth_page_titles():      return tuple(_INSTITUTION.auth_page_titles)
def _auth_loading_titles():   return tuple(_INSTITUTION.auth_loading_titles)
```

Then update the **uses** at lines 1250–1260 (inside `inspect_access_barrier`) and lines 1509 / 2205 / 736 / 2714 / 2717.

- [ ] **Step 5: Update `inspect_access_barrier` (around line 1250)**

Find the lines:

```python
    if any(host in url for host in AUTH_HOST_PATTERNS) or any(pat in url for pat in AUTH_URL_PATTERNS):
        return {"kind": "auth_redirect", "reason": "<institution>_auth_redirect", "url": page.url}

    title = ""
    try:
        title = (await page.title()).strip()
    except Exception:
        pass

    if title and any(pat in title for pat in AUTH_TITLE_PATTERNS):
        return {"kind": "auth_redirect", "reason": "<institution>_auth_redirect", "url": page.url}
```

Replace with:

```python
    if any(host in url for host in _auth_hosts()) or any(pat in url for pat in _auth_url_fragments()):
        return {"kind": "auth_redirect", "reason": "institution_auth_redirect", "url": page.url}

    title = ""
    try:
        title = (await page.title()).strip()
    except Exception:
        pass

    if title and any(pat in title for pat in _auth_page_titles()):
        return {"kind": "auth_redirect", "reason": "institution_auth_redirect", "url": page.url}
```

- [ ] **Step 6: Update inline `"统一身份认证"` checks at lines 1509 + 2205**

**Line 1509** — currently:
```python
    if "统一身份认证" in decoded:
        return False, "auth_page_instead_of_pdf"
```

Replace with:
```python
    if any(t in decoded for t in _auth_page_titles()):
        return False, "auth_page_instead_of_pdf"
```

**Line 2205** — currently:
```python
def body_looks_like_html(body: bytes) -> bool:
    head = body[:2048].decode("utf-8", errors="ignore").lower()
    return "<html" in head or "<!doctype" in head or "统一身份认证" in head
```

Replace with:
```python
def body_looks_like_html(body: bytes) -> bool:
    head = body[:2048].decode("utf-8", errors="ignore").lower()
    if "<html" in head or "<!doctype" in head:
        return True
    return any(t in head for t in _auth_page_titles())
```

- [ ] **Step 7: Update inline `"请稍候/请稍后/稍候"` checks at 736, 2714, 2717**

**Line 736** — currently:
```python
        loading_title = (not last_title) or ("请稍候" in last_title) or ("请稍后" in last_title) or title_lower in ("loading", "loading...")
```

Replace with:
```python
        loading_title = (
            (not last_title)
            or any(t in last_title for t in _auth_loading_titles())
            or title_lower in ("loading", "loading...")
        )
```

**Lines 2714 / 2717** — currently:
```python
                    title = (await page.title()).strip()
                    if "稍候" in title or title in ("", "Loading..."):
                        log_event(stage, "aip_loading_wait", "start", page.url, f"title={title!r}")
                        await page.wait_for_function(
                            "() => !document.title.includes('稍候') && document.title.length > 2",
                            timeout=20_000,
                        )
```

This block is AIP/AVS publisher-specific and uses `"稍候"` as a substring. It is reached only when `publisher in ("aip", "avs")`. Per Plan + Kimi guidance, AIP/AVS legitimately depend on this Chinese loading-page title and we don't have a non-Chinese alternative for these publishers' pages. **Action:** add a small AIP-AVS-specific fallback list (English `"loading"` already covered; `"稍候"` stays bake-in) but ALSO check institution loading titles. Replace with:

```python
                    title = (await page.title()).strip()
                    inst_loading = any(t in title for t in _auth_loading_titles())
                    is_aip_loading = "稍候" in title  # AIP/AVS server-side rendered Chinese loading text
                    if inst_loading or is_aip_loading or title in ("", "Loading..."):
                        log_event(stage, "aip_loading_wait", "start", page.url, f"title={title!r}")
                        await page.wait_for_function(
                            "() => !document.title.includes('稍候') && document.title.length > 2",
                            timeout=20_000,
                        )
```

(The hardcoded `"稍候"` here is publisher behavior, not user-identifying — it's what AIP/AVS literally serves. We document this in CONTRIBUTING.md.)

- [ ] **Step 8: Wire `init_institution_config` into the script entry**

Find `if __name__ == "__main__":` near the end of `download_refs.py` and the function it calls (typically `main()` or `asyncio.run(...)`). At the very top of that flow, before any download work begins, add:

```python
    cfg = load_config()
    init_institution_config(cfg.institution)
```

If the entry is `asyncio.run(main(...))`, add the two lines right before the `asyncio.run` call.

- [ ] **Step 9: Verify the script imports and basic shape**

```powershell
python -c "import download_refs"
```

Expected: no `SyntaxError`, no `NameError`, no `ImportError`.

```powershell
python -c "import download_refs as d; print('AUTH_HOST_PATTERNS' in dir(d))"
```

Expected: `False` (the constant has been removed).

```powershell
python -c "import download_refs as d; print('init_institution_config' in dir(d))"
```

Expected: `True`.

- [ ] **Step 10: Commit**

```powershell
git add download_refs.py
git commit -m "Wire institution + Edge profile to config; rename auth_redirect reason"
```

---

## Task 8: Sanitize `SKILL.md`

**Files:**
- Rewrite: `SKILL.md`

- [ ] **Step 1: Open the existing SKILL.md and identify replacements needed**

Personal hardcodes to remove (the maintainer's specifics; redacted here to placeholders):
- `<personal Windows Python interpreter absolute path>` → `python`
- `<personal SKILL install dir, both .agents and .claude path variants>` → `<SKILL_DIR>` (where the user installs this skill)
- `<personal Zotero SQLite absolute path>` → `<configured zotero.db_path or empty>`
- `<personal example PDF paths>` → generic `<path/to/your.pdf>`

- [ ] **Step 2: Add a header explaining the dual purpose**

At the very top, insert before any other content:

```markdown
# Ref Downloader — Claude Code Skill Runbook

> **This file is primarily an agent runbook for Claude Code.**
> If you're a human reading this for the first time, see [README.md](README.md)
> for setup and usage. This file documents the step-by-step flow Claude Code's
> agent mode follows when invoked as `/ref-downloader`.

Recommended entry: the single-entry wrapper. Backstop: the three-script pipeline
for debugging and incremental restarts.
```

- [ ] **Step 3: Replace the "固定常量" block with a config pointer**

Old block (around lines 7–17): three lines of literal absolute paths
(maintainer's personal Windows Python interpreter, skill install dir, and
Zotero SQLite path).

Replace with:
```markdown
## Configuration

This skill reads config from `<SKILL_DIR>/config.local.toml` (gitignored,
user-specific) and falls back to `<SKILL_DIR>/config.example.toml`. See
[README.md](README.md) for setup and [config.example.toml](config.example.toml)
for the schema.

Environment variables override the file: `REF_DOWNLOADER_MAILTO`,
`REF_DOWNLOADER_ZOTERO_DB`, `REF_DOWNLOADER_EDGE_PROFILE`, etc.

Throughout this runbook, `<SKILL_DIR>` is wherever the skill files live (the
agent should resolve it via `Path(__file__).resolve().parent` from any of the
scripts).
```

- [ ] **Step 4: Replace personal Python invocations**

Throughout the file, replace:
- `"{PYTHON}"` → `python` (or `<PYTHON>` if the agent needs the variable)
- `"{SKILL_DIR}"` → `<SKILL_DIR>`
- `"{PROJECT_NAME}"` and `"{OUTPUT_DIR}"` already exist as placeholders; keep them.

- [ ] **Step 5: Replace personal example paths**

Find any maintainer-specific absolute paths (e.g. drive-letter PDF paths,
personal directory examples) and replace with generic `<path/to/your.pdf>` or
`<path/to/output_dir>`.

- [ ] **Step 6: Add cross-link section at end**

```markdown
## See also

- [README.md](README.md) — human-facing setup and usage
- [docs/SUPPORTED_PUBLISHERS.md](docs/SUPPORTED_PUBLISHERS.md) — publisher tier table
- [CONTRIBUTING.md](CONTRIBUTING.md) — adding a new publisher / institution SSO
```

- [ ] **Step 7: Verify with grep that personal paths are gone**

```powershell
Get-Content SKILL.md | Select-String -Pattern '(C:\\Users\\Link|D:\\Link|E:\\北大|\.agents\\skills)'
```

Expected: empty output.

- [ ] **Step 8: Commit**

```powershell
git add SKILL.md
git commit -m "Sanitize SKILL.md: remove personal paths, add README cross-link"
```

---

## Task 9: License + requirements.txt

**Files:**
- Create: `LICENSE`
- Create: `requirements.txt`

- [ ] **Step 1: Write `LICENSE` (MIT)**

```
MIT License

Copyright (c) 2026 ref-downloader contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Write `requirements.txt`**

```
# Required
playwright>=1.40

# Optional (PDF text fallback for DOI extraction when Zotero lookup unavailable)
pymupdf>=1.23
```

(`tomllib` is stdlib in Python 3.11+; no entry needed.)

- [ ] **Step 3: Commit**

```powershell
git add LICENSE requirements.txt
git commit -m "Add MIT LICENSE and requirements.txt"
```

---

## Task 10: README.md (English)

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README.md** (~250 lines)

Required sections:

1. **Title + tagline** — "Batch-download all references of a paper from a DOI."
2. **Status badge line** — language: Python; license: MIT; verified-on: Windows + Edge
3. **What it does** — one paragraph: input a parent paper's DOI (or a PDF that has a DOI in metadata), output PDFs of every reference Crossref knows about, plus SI files where supported.
4. **Why use this** — one paragraph: alternative to manual click-through; especially useful for literature reviews. Honest about paywall limits.
5. **Requirements**
   - Windows 10/11 (other OS untested; PRs welcome)
   - Microsoft Edge (channel: Stable; the script uses your real Edge profile)
   - Python 3.11+
   - Optional: Zotero (auto-detects DOI from PDF filename)
   - Optional: PyMuPDF (`pip install pymupdf`) for DOI text fallback
6. **Install**
   - `git clone <repo>` / cd
   - `pip install -r requirements.txt`
   - `playwright install msedge` (uses Edge channel rather than Chromium)
   - `cp config.example.toml config.local.toml` and edit
7. **Quick start**
   - Three example invocations: DOI input, PDF input, custom output dir
   - Show expected console output snippet
8. **Configuration** — link to config.example.toml + env var table
9. **Supported publishers** — link to docs/SUPPORTED_PUBLISHERS.md
10. **Architecture** — three-script pipeline diagram (extract → validate → download), describe wrapper role
11. **Known limitations**
    - Windows + Edge only (verified)
    - Headed mode required (headless empirically returns empty SI for Wiley/ACS)
    - Edge must be fully closed before invoke (the script claims the profile)
    - Paywalled content needs institutional access; SSO redirects are detected but not resolved automatically
    - SI download is the most fragile path; main PDFs are reliable
12. **Contributing** — link to CONTRIBUTING.md
13. **Security** — link to SECURITY.md
14. **License** — MIT, link to LICENSE

Code examples must include real DOIs (e.g., `10.1021/jacs.5c05017`) and show the wrapper command:

```powershell
python run_ref_downloader.py 10.1021/jacs.5c05017
python run_ref_downloader.py "C:\path\to\paper.pdf" --output-dir refs/
```

Environment variable table:

| Variable | Maps to | Example |
|---|---|---|
| `REF_DOWNLOADER_MAILTO` | crossref.mailto | `you@uni.edu` |
| `REF_DOWNLOADER_ZOTERO_DB` | zotero.db_path | `D:\you\Zotero\zotero.sqlite` |
| `REF_DOWNLOADER_EDGE_PROFILE` | browser.edge_profile_dir | (empty = OS default) |
| `REF_DOWNLOADER_CONFIG` | path to alternate TOML | `./ci-config.toml` |

- [ ] **Step 2: Commit**

```powershell
git add README.md
git commit -m "Add English README"
```

---

## Task 11: README.zh.md (Chinese)

**Files:**
- Create: `README.zh.md`

- [ ] **Step 1: Write `README.zh.md`** — Chinese mirror of README.md with same section structure

Use the same outline as Task 10 but in Chinese. Open with:

```markdown
# Ref Downloader

> 输入一篇论文的 DOI，自动批量下载它的所有参考文献 PDF（以及部分出版商的 SI）。
>
> [English README](README.md)
```

Then mirror the English structure section by section.

- [ ] **Step 2: Commit**

```powershell
git add README.zh.md
git commit -m "Add Chinese README"
```

---

## Task 12: CONTRIBUTING.md

**Files:**
- Create: `CONTRIBUTING.md`

- [ ] **Step 1: Write `CONTRIBUTING.md`**

Required sections:

1. **Welcome** — one paragraph
2. **Adding a new publisher** — concrete steps:
   - Add DOI prefix to `PUBLISHER_MAP` in `validate_refs.py`
   - Add publisher key to `PUBLISHER_STRATEGIES` in `download_refs.py:123`
   - Add direct PDF URL template to `direct_pdf_url` map (around line 880)
   - Add article URL template (around line 901)
   - Add PDF selectors to `PDF_SELECTORS` (around line 926)
   - Test with a sample DOI; share the events.jsonl output in your PR
3. **Adding institution SSO patterns** — point to `[institution]` section in `config.example.toml`
4. **The `auth_loading_titles` ambiguity** (HIGH IMPORTANCE):
   ```
   The auth_loading_titles config field is consumed by TWO code paths:
     1. Institution SSO loading-page detection (e.g., your university's "Loading..." page)
     2. AIP/AVS publisher loading-page detection (which serves "请稍候")
   
   The AIP/AVS path also has a hardcoded "稍候" check that should NOT be removed —
   AIP/AVS literally serves Chinese "Please wait" text, regardless of locale.
   
   Do not "consolidate" these into one mechanism without testing both flows.
   ```
5. **Reporting a download failure** — link to `.github/ISSUE_TEMPLATE/bug-report.md`
6. **Code style** — match existing; no breaking refactors of `download_refs.py` without discussion
7. **Testing** — link to `tests/README.md`; manual smoke test required for any publisher change

- [ ] **Step 2: Commit**

```powershell
git add CONTRIBUTING.md
git commit -m "Add CONTRIBUTING with publisher / institution / ambiguity guidance"
```

---

## Task 13: SECURITY.md

**Files:**
- Create: `SECURITY.md`

- [ ] **Step 1: Write `SECURITY.md`**

```markdown
# Security Considerations

## Browser profile access

`download_refs.py` launches Microsoft Edge with your **persistent user profile**
(`%LOCALAPPDATA%\Microsoft\Edge\User Data\Default` by default, or the path in
`config.browser.edge_profile_dir`). This profile contains:

- Cookies (including authenticated sessions)
- Saved passwords (if you've stored any in Edge)
- Browsing history
- Extensions and their data

**Recommendation**: create a **dedicated Edge profile** for this tool. Don't
point it at your daily-driver profile.

To create a separate profile:

1. Open Edge → click your profile picture (top-right) → "Add profile"
2. Note the new profile's directory under `%LOCALAPPDATA%\Microsoft\Edge\User Data\Profile N`
3. Set `browser.edge_profile_dir` in `config.local.toml` to that directory.

## Credentials in config files

`config.local.toml` is gitignored — DO NOT commit it. The `mailto` field is
public-by-design (Crossref publishes it); the `zotero.db_path` reveals your
local filesystem layout, and the `[institution]` section may identify your
employer/university.

If you fork this repo and accidentally commit `config.local.toml`, treat any
contained values as compromised: rotate any related credentials and force-push
a clean history.

## Reporting a vulnerability

Open a private security advisory on GitHub or email the maintainer (see
repository metadata). Do not file a public issue for unpatched
vulnerabilities.
```

- [ ] **Step 2: Commit**

```powershell
git add SECURITY.md
git commit -m "Add SECURITY.md: dedicated Edge profile + credential hygiene"
```

---

## Task 14: CHANGELOG.md

**Files:**
- Create: `CHANGELOG.md`

- [ ] **Step 1: Write seed CHANGELOG**

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-05-10

Initial open-source release.

### Added
- Three-script pipeline (`extract_refs.py`, `validate_refs.py`, `download_refs.py`)
- Single-entry wrapper (`run_ref_downloader.py`)
- Config layer: TOML + env vars (`_config.py`, `config.example.toml`)
- Bilingual documentation (English + Chinese READMEs)
- Issue templates for bug reports and new-publisher requests
- Publisher coverage: ACS, Nature, Science, Elsevier, Wiley, RSC, Springer,
  PNAS, ECS, IOP, AIP, AVS, IEEE, OSA, KPS, Beilstein, APS (varying maturity;
  see docs/SUPPORTED_PUBLISHERS.md)
- Institutional SSO detection via configurable `[institution]` section

### Known limitations
- Windows + Microsoft Edge only (verified); other browsers / OSes untested
- Headed mode required for Wiley / ACS supplementary downloads
- SI download is the most fragile code path
```

- [ ] **Step 2: Commit**

```powershell
git add CHANGELOG.md
git commit -m "Add CHANGELOG.md with v0.1.0 entry"
```

---

## Task 15: docs/SUPPORTED_PUBLISHERS.md

**Files:**
- Create: `docs/SUPPORTED_PUBLISHERS.md`

- [ ] **Step 1: Extract publisher table + tier explanation from old SKILL.md**

Sections:
1. **DOI prefix → publisher table** (16 entries, taken from `validate_refs.py:PUBLISHER_MAP`)
2. **Three-tier strategy explanation** (specialized / generic_fallback / weak — taken from `download_refs.py:PUBLISHER_STRATEGIES`)
3. **Per-publisher notes** — Wiley specialized PDFDirect, Elsevier crasolve hot-window, AIP/AVS loading-wait, IOP barrier-aware, etc.
4. **Adding a new publisher** — link back to CONTRIBUTING.md

This is reference documentation, not narrative; tabular layout preferred.

- [ ] **Step 2: Commit**

```powershell
git add docs/SUPPORTED_PUBLISHERS.md
git commit -m "Extract publisher matrix from SKILL.md to dedicated doc"
```

---

## Task 16: tests/README.md

**Files:**
- Create: `tests/README.md`

- [ ] **Step 1: Write a manual smoke-test recipe**

```markdown
# Manual smoke test recipe

This project has no automated tests yet. Before submitting a PR, manually
verify the publisher you touched.

## Per-publisher smoke test

Pick a sample DOI for the publisher (suggestions in
[docs/SUPPORTED_PUBLISHERS.md](../docs/SUPPORTED_PUBLISHERS.md)) and run:

```powershell
python run_ref_downloader.py <PARENT_DOI> --output-dir test_smoke
```

Watch the console for the publisher in question:
- `downloaded (X KB)` — pass
- `manual_pending (...)` — needs human / paywall
- `failed (...)` — investigate

Cross-check `test_smoke\<project>\runs\<timestamp>\events.jsonl` for the
specific stage failures.

## Empty-config smoke test

Verify the wrapper still runs against vanilla open-internet defaults:

```powershell
Move-Item config.local.toml config.local.toml.backup
python run_ref_downloader.py 10.1021/jacs.5c05017 --output-dir test_smoke
Move-Item config.local.toml.backup config.local.toml
```

Expected:
- WARNING about placeholder mailto
- `extract_refs.py` succeeds (Crossref reachable without auth)
- `validate_refs.py` succeeds
- `download_refs.py` may auth-redirect or paywall — that's acceptable

What MUST NOT happen:
- `KeyError` / `NoneType` / `AttributeError` from the config layer
- Any reference to your personal paths (`C:\Users\<you>\...`) in stack traces
```

- [ ] **Step 2: Commit**

```powershell
git add tests/README.md
git commit -m "Add manual smoke-test recipe under tests/"
```

---

## Task 17: .github/ISSUE_TEMPLATE/

**Files:**
- Create: `.github/ISSUE_TEMPLATE/bug-report.md`
- Create: `.github/ISSUE_TEMPLATE/new-publisher.md`

- [ ] **Step 1: Write `bug-report.md`**

```markdown
---
name: Bug report
about: Something doesn't download or fails unexpectedly
title: "[BUG] "
labels: bug
---

## Environment

- OS: (e.g. Windows 11 24H2)
- Edge version: (Edge → Settings → About)
- Python version: `python --version`
- Project version / commit: 

## What happened

Run command:
```
python run_ref_downloader.py <DOI> ...
```

## Expected behavior

## Actual behavior

## Reference details

- Parent DOI:
- Failing reference DOI / index:
- Publisher (per `download_report.csv`):
- Status from report (e.g. `manual_pending (auth_redirect)`):

## Logs

Paste the LAST 30 lines of `<output_dir>/runs/<timestamp>-round-03/events.jsonl`
that mention the failing ref. **Redact any institution-specific URLs** before
posting.

```jsonl
(events.jsonl excerpt here)
```

## What you've already tried
```

- [ ] **Step 2: Write `new-publisher.md`**

```markdown
---
name: New publisher request
about: Add support for a publisher not currently covered
title: "[publisher: ] "
labels: new-publisher
---

## Publisher

- Name: (e.g. Cambridge University Press)
- DOI prefix: (e.g. 10.1017)
- Sample article DOI:
- Sample article URL:

## Access

- [ ] I have institutional access to this publisher
- [ ] Articles are open-access only
- [ ] I'm asking on behalf of someone with access

## PDF download path

If you've inspected the page, paste the CSS selector of the PDF download link
or the URL pattern of the direct-PDF route.

```
PDF selector: a.pdf-download-link
Or direct URL pattern: https://example.com/articles/{doi}/pdf
```

## SI / Supplementary

- [ ] Supplementary downloads needed
- [ ] Supplementary URLs follow a predictable pattern (describe below)
```

- [ ] **Step 3: Commit**

```powershell
git add .github/
git commit -m "Add issue templates for bug reports and new-publisher requests"
```

---

## Task 18: Verification Gate 1 — Sanitization grep

- [ ] **Step 1: Run the three patterns**

```powershell
$patterns = @(
  '(Link|ltc\.z|gmail|pku|PKU|北大|北京大学|iaaa|ding|@[a-z]+\.edu)',
  '统一身份认证|请稍候|请稍后',
  '[DEFG]:\\'
)
foreach ($p in $patterns) {
  Write-Output "=== Pattern: $p ==="
  Get-ChildItem -Recurse -Include *.py,*.md,*.toml,*.txt -Exclude config.local.toml |
    Select-String -Pattern $p
}
```

Expected hits (acceptable, document why each is OK):
- `download_refs.py:1168-1169`: `"请稍候" / "请稍后"` inside `CLOUDFLARE_TITLE_PATTERNS` — generic Chinese loading text, kept for Chinese-locale Cloudflare detection. Not personal info.
- `download_refs.py:2714, 2717`: `"稍候"` in AIP/AVS branch — publisher-served Chinese, not user-identifying.
- `README.md` and `README.zh.md`: example DOI / generic terms, no personal info.
- `CHANGELOG.md`: any mentions of Chinese language are description, not personal.

Unacceptable (must fix immediately):
- Any maintainer-specific home directory or drive-letter path in committed files
- Any maintainer-specific personal email in committed files
- Any institution-specific SSO host or authentication-page title outside of `config.local.toml` (the gitignored personal config)

- [ ] **Step 2: If any unacceptable hit appears, stop and fix it before continuing**

Document each acceptable hit briefly in this plan's commit message.

- [ ] **Step 3: Commit any fixes**

```powershell
git add -p
git commit -m "Sanitization gate: clean up residual personal info"
```

---

## Task 19: Verification Gate 2 — Empty-config smoke test

- [ ] **Step 1: Move `config.local.toml` aside**

```powershell
Move-Item config.local.toml config.local.toml.bak
```

- [ ] **Step 2: Run wrapper on a known-good public DOI**

```powershell
python run_ref_downloader.py 10.1021/jacs.5c05017 --output-dir test_smoke
```

Expected:
- WARNING line about placeholder mailto
- `extract_refs.py` runs and creates `test_smoke/jacs.5c05017/refs_raw.json`
- `validate_refs.py` runs without crashing
- `download_refs.py` may attempt downloads (most refs paywalled at vanilla internet — that's fine)

What MUST NOT happen:
- `ImportError`, `NameError` (any config-layer regression)
- Personal path appearing in any stack trace

- [ ] **Step 3: Restore config.local.toml**

```powershell
Move-Item config.local.toml.bak config.local.toml
Remove-Item -Recurse -Force test_smoke
```

- [ ] **Step 4: No commit needed (no files changed); but log result in this plan as a comment**

If the smoke test crashes with a config-related error, fix the relevant Task (4–7) before continuing.

---

## Task 20: Verification Gate 3 — code-review skill

- [ ] **Step 1: Invoke the code-review skill**

Run: `/code-review` (or use the `engineering:code-review` skill via Skill tool).

Scope: the diff from `git log --oneline` since the initial commit.

Focus areas to mention to the reviewer:
- `_config.py` — error swallowing? path traversal in `--config`? injection in env?
- `run_ref_downloader.py` — subprocess call argument quoting; Zotero DB temp file cleanup
- `download_refs.py` — institution config holder thread-safety (it's mutated globally; document in comment that it's set-once at startup)

- [ ] **Step 2: Apply review findings as a follow-up commit (or commits)**

```powershell
git commit -m "Address code-review findings: <summary>"
```

---

## Task 21: Verification Gate 4 — deploy-checklist skill

- [ ] **Step 1: Invoke the deploy-checklist skill**

Run: `/deploy-checklist` (or `engineering:deploy-checklist` via Skill tool).

This is the "release readiness" gate before any `git push origin main` or
GitHub repo creation.

The skill will check:
- All hardcoded paths gone
- `LICENSE` present
- `README.md` accurate (test install on a fresh path if requested)
- `.gitignore` catches local config
- `SKILL.md` doesn't leak personal info
- `git status` clean
- Commit history reasonable

- [ ] **Step 2: Tag v0.1.0**

```powershell
git tag -a v0.1.0 -m "Initial open-source release"
```

(Don't push — that's a user decision.)

- [ ] **Step 3: Final summary**

Report to user: what's in this repo, what's still to do (e.g. push to GitHub,
create release notes), and where the design + plan docs live.

---

## Self-review checklist (run by author after writing this plan)

**Spec coverage**:
- [x] institution sanitization (8 hardcoded sites: 119, 736, 1122-1124, 1126-1129, 1131-1134, 1251, 1260, 1509, 2205) — Task 7
- [x] EDGE_USER_DATA lazy load (line 78) — Task 7 step 2
- [x] AIP/AVS `稍候` ambiguity documented — CONTRIBUTING.md Task 12
- [x] Zotero DB hardcode (run_ref_downloader.py:31) — Task 4
- [x] mailto placeholders + warning — `_config.py` + Task 4
- [x] env var fallback (REF_DOWNLOADER_*) — `_config.py`
- [x] non-tty input handling (extract_refs.py:112) — Task 5
- [x] Bilingual README — Tasks 10, 11
- [x] LICENSE + .gitignore — Tasks 1, 9
- [x] SECURITY.md (Edge profile cookie risk) — Task 13
- [x] SUPPORTED_PUBLISHERS.md extracted — Task 15
- [x] Issue templates — Task 17
- [x] code-review + deploy-checklist gates — Tasks 20, 21
- [x] Original skill untouched (cwd is `<this-repo>\`, not `.agents`)

**Placeholder scan**: No "TBD", "TODO", "implement later", "appropriate error handling", etc. in this plan.

**Type consistency**:
- `Config` dataclass: `crossref` / `zotero` / `browser` / `institution` — used consistently
- `_INSTITUTION` module global: type `InstitutionConfig` — set by `init_institution_config(cfg.institution)` in download_refs.py
- `user_agent_from(cfg, app)` — same signature in extract_refs.py and validate_refs.py
- `load_config(explicit_path: Optional[Path])` — same call shape from all entry points
