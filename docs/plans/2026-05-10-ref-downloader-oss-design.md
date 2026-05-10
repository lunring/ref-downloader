# ref-downloader Open-Sourcing Design

**Date**: 2026-05-10
**Source skill**: `<original-skill-dir>\` (untouched)
**Working copy**: `<this-repo>\` (this repo, freshly copied)

---

## 1. Goal

Convert the personal `ref-downloader` Claude Code skill into a self-contained,
shareable, GitHub-ready open-source project, **without modifying the original**.

Original skill at `<original-skill-dir>\` stays intact;
the user keeps using it locally. This new folder is the open-source variant —
it can be developed, refactored, tested, and eventually `git init` + pushed
without affecting the user's working setup.

## 2. Locked-in decisions

| Topic | Choice | Rationale |
|---|---|---|
| Form factor | Standalone copy in new folder (not in-place) | User keeps original untouched as a safety net |
| Refactor scope | **Light**: sanitize private info + config layer + docs; do NOT restructure `download_refs.py` (3440 lines) | Minimize risk of regressing battle-tested download flow |
| Open-source profile | **P2 — GitHub-ready bilingual** | English README primary, Chinese README mirror, minimal `.github/` templates |
| License | **MIT** | Standard, permissive; no friction for academic users |
| Configuration mechanism | `config.local.toml` (gitignored) > env vars (`REF_DOWNLOADER_*`) > `config.example.toml` (committed) > built-in fallbacks | File for desktop users, env vars for CI/container users |
| Backup of original | **Not needed** — original is untouched by definition | Implicit safety: nothing in the original tree changes |

## 3. Review-driven sanitization map

Two parallel reviews (Plan-agent + Kimi-supervision) found these private
information leaks. Plan-agent caught the structural issues + main institution-specific block;
Kimi found 3 institution-specific strings scattered outside the obvious block; self-grep
confirmed no other drive-letter paths or personal identifiers.

### 3.1 institutional signals (HIGH-PRIORITY — PII-adjacent)

All in `download_refs.py`, will be replaced with reads from
`config.institution.*` (5 fields, see §4.2):

For privacy, the original literal values (institution domain, ignored-access
DOIs, auth-page titles, paths) are redacted to placeholders below. The
maintainer's actual values lived in `config.local.toml` (gitignored) when this
plan was executed.

| Line | Original code shape | Reads from |
|---|---|---|
| 119–122 | `IGNORED_INSTITUTION_ACCESS_DOIS = {"<institution-paywalled-DOI>"}` | `config.institution.ignored_access_dois` |
| 736 | `"<chinese-loading-title>" in last_title or "<other-loading-title>" in last_title` | `any(t in last_title for t in cfg.auth_loading_titles)` |
| 1122–1124 | `AUTH_HOST_PATTERNS = ("<institution-sso-host>",)` | `tuple(cfg.auth_hosts)` |
| 1126–1129 | `AUTH_URL_PATTERNS = ("<sso-url-fragment>", "oauth.jsp")` | `tuple(cfg.auth_url_fragments)` |
| 1131–1134 | `AUTH_TITLE_PATTERNS = ("<institution-sso-page-title>", "<generic-sso-title>")` | `tuple(cfg.auth_page_titles)` |
| 1251 / 1260 | `reason="<institution>_auth_redirect"` | hardcoded `"institution_auth_redirect"` (no config needed) |
| 1509 | `if "<sso-page-title>" in decoded:` | `any(t in decoded for t in cfg.auth_page_titles)` |
| 2205 | `or "<sso-page-title>" in head` | `any(t in head for t in cfg.auth_page_titles)` |
| 2714 / 2717 | `"<chinese-loading-title-fragment>" in title` | `any(t in title for t in cfg.auth_loading_titles)` |

**Ambiguity to document in CONTRIBUTING.md**: `auth_loading_titles` is read by
both the institution SSO detection path AND the AIP/AVS publisher loading-page
detection path. The same Chinese loading-text fragment legitimately appears in
both contexts. Future contributors must not "clean up" by splitting these.

### 3.2 Other private hardcodes

| File:line | Original (redacted) | Action |
|---|---|---|
| `run_ref_downloader.py:31` | `ZOTERO_DB = Path(r"<personal-zotero-sqlite-path>")` | Read from `config.zotero.db_path`; if empty/missing → silently skip Zotero |
| `download_refs.py:78` | `EDGE_USER_DATA = os.path.expandvars(...)` (module-level) | Convert to lazy: read inside `launch_edge_context()` from `config.browser.edge_profile_dir` (empty → OS default) |
| `extract_refs.py:24` | `USER_AGENT = "RefDownloader/1.0 (mailto:academic-tool@example.com)"` | Build at runtime from `config.crossref.mailto`; warn at startup if still placeholder |
| `validate_refs.py:27` | (same as above) | Same |
| `extract_refs.py:112` | `input("Overwrite? [y/N] ")` | Add `--yes` flag; if non-tty (`not sys.stdin.isatty()`) → default to abort |
| `SKILL.md` (multiple) | maintainer's personal Windows Python interpreter path, skill install dir under user home, Zotero SQLite absolute path, drive-letter PDF examples | Replace with `<SKILL_DIR>` placeholder; cross-link to README |

### 3.3 Files to delete

Already removed during initial copy (verified): `__pycache__/`, `temp_extract_doi.py`, `temp_check.py`.

## 4. Configuration architecture

### 4.1 Lookup priority

```
env var REF_DOWNLOADER_<KEY>
  > config.local.toml at SKILL_DIR (or path from --config or REF_DOWNLOADER_CONFIG)
    > config.example.toml at SKILL_DIR
      > built-in fallback (empty / placeholder)
```

Single config-loader module at `_config.py` (new file, ~80 lines) provides:
- `load_config(path: Optional[Path] = None) -> Config`
- Dataclass `Config` with sections: `crossref`, `zotero`, `browser`, `institution`
- Each section has explicit fields with sensible empty defaults

### 4.2 `config.example.toml`

```toml
# Copy this file to config.local.toml and edit. config.local.toml is gitignored.

[crossref]
# Crossref polite-pool identifier. Replace with your email — helps API priority.
# If left as the placeholder, the wrapper prints a warning at startup.
mailto = "your.email@example.com"

[zotero]
# Optional: Zotero SQLite path. If set + file exists, wrapper resolves DOI
# from PDF filename via Zotero metadata (faster than fitz fallback).
# Leave empty "" to disable. fitz fallback still works for any PDF.
db_path = ""

[browser]
# Edge persistent profile directory.
# Empty = use OS default (Windows: %LOCALAPPDATA%\Microsoft\Edge\User Data\Default)
edge_profile_dir = ""
# Set to true to launch Edge with extensions disabled (debugging only)
disable_extensions = false

[institution]
# Optional: institutional SSO patterns. Leave empty for vanilla open-internet use.
# Adding your university's SSO host/title enables auth-redirect detection during downloads.
auth_hosts          = []   # e.g. ["sso.your-uni.edu"]
auth_url_fragments  = []   # e.g. ["oauth", "saml"]
auth_page_titles    = []   # e.g. ["University Single Sign-On"]
# auth_loading_titles is ALSO consumed by AIP/AVS publisher loading-page detection;
# safe defaults for AIP/AVS are baked in. Add institution-specific loading texts here.
auth_loading_titles = []
ignored_access_dois = []   # DOIs known to be paywalled at your institution
```

### 4.3 Environment variable overrides

| Variable | Maps to | Notes |
|---|---|---|
| `REF_DOWNLOADER_CONFIG` | path to alternate `.toml` | Highest precedence for file location |
| `REF_DOWNLOADER_MAILTO` | `crossref.mailto` | |
| `REF_DOWNLOADER_ZOTERO_DB` | `zotero.db_path` | |
| `REF_DOWNLOADER_EDGE_PROFILE` | `browser.edge_profile_dir` | |
| `REF_DOWNLOADER_DISABLE_EXTENSIONS` | `browser.disable_extensions` | "1"/"true" → true |

(Institution fields are intentionally not env-mapped; complex list values
deserve a config file.)

## 5. Final repository layout

```
ref-downloader/
├── .gitignore
├── LICENSE                          # MIT
├── README.md                        # English (primary)
├── README.zh.md                     # Chinese
├── CONTRIBUTING.md                  # Add publisher / report bug
├── SECURITY.md                      # Edge profile cookies; recommend dedicated profile
├── CHANGELOG.md                     # Optional, seed with v0.1.0 entry
├── SKILL.md                         # Trimmed: agent-mode runbook for Claude Code users
├── config.example.toml              # Committed template
├── config.local.toml                # Gitignored — user's actual values
├── requirements.txt                 # playwright, pymupdf (optional)
├── _config.py                       # Config loader (new file, ~80 lines)
├── run_ref_downloader.py            # Wrapper (sanitized + --yes / --config flags)
├── extract_refs.py                  # mailto from config + non-tty handling
├── validate_refs.py                 # mailto from config
├── download_refs.py                 # 10 line-level edits, no structural changes
├── docs/
│   ├── plans/
│   │   └── 2026-05-10-ref-downloader-oss-design.md   # this file
│   └── SUPPORTED_PUBLISHERS.md      # Extracted from SKILL.md
├── tests/
│   └── README.md                    # Manual smoke-test recipe (no automated tests yet)
└── .github/
    └── ISSUE_TEMPLATE/
        ├── bug-report.md
        └── new-publisher.md
```

## 6. Code change inventory

11 files touched (5 modify + 6 create) + 1 new helper:

| Action | File | Approx LoC delta |
|---|---|---|
| Create | `_config.py` | +80 |
| Modify | `run_ref_downloader.py` | ~+30 / -5 |
| Modify | `extract_refs.py` | ~+15 / -5 |
| Modify | `validate_refs.py` | ~+10 / -3 |
| Modify | `download_refs.py` | ~+25 / -25 (10 line-level edits, function-shape unchanged) |
| Modify | `SKILL.md` | rewrite to ~50% size, no personal paths |
| Create | `.gitignore` | +20 |
| Create | `LICENSE` | +21 (MIT boilerplate) |
| Create | `README.md` | ~250 lines |
| Create | `README.zh.md` | ~250 lines |
| Create | `CONTRIBUTING.md` | ~100 lines |
| Create | `SECURITY.md` | ~30 lines |
| Create | `CHANGELOG.md` | ~15 lines |
| Create | `requirements.txt` | 5 lines |
| Create | `config.example.toml` | ~40 lines |
| Create | `docs/SUPPORTED_PUBLISHERS.md` | ~80 lines (from SKILL.md) |
| Create | `tests/README.md` | ~40 lines |
| Create | `.github/ISSUE_TEMPLATE/bug-report.md` | ~30 lines |
| Create | `.github/ISSUE_TEMPLATE/new-publisher.md` | ~30 lines |

## 7. Verification gates

After all edits:

### Gate 1 — Sanitization grep (must be zero hits except in README/CHANGELOG examples)

```powershell
$patterns = @(
  '(Link|ltc\.z|gmail|pku|PKU|北大|北京大学|iaaa|ding|@[a-z]+\.edu)',
  '统一身份认证|请稍候|请稍后',
  '[DEFG]:\\'
)
foreach ($p in $patterns) {
  Get-ChildItem -Recurse -Include *.py,*.md,*.toml | Select-String -Pattern $p
}
```

### Gate 2 — Empty-config smoke test

Temporarily rename `config.local.toml`, then:

```powershell
python run_ref_downloader.py 10.1021/jacs.5c05017 --output-dir test_smoke
```

Expected:
- mailto WARNING printed
- extract_refs runs (Crossref reachable)
- validate_refs runs
- download phase may paywall — that's fine; no `KeyError` / `NoneType` / `AttributeError` from the config layer

### Gate 3 — `engineering:code-review` skill on the diff

Focus areas:
- Path handling (no shell injection in `subprocess.run`)
- Error swallowing in `_config.py` and `resolve_doi_from_zotero`
- Edge profile leak (don't log full path)

### Gate 4 — `engineering:deploy-checklist` skill before any git push

Specifically: rerun Gate 1 grep, eyeball `git diff --stat`, confirm
`config.local.toml` is in `.gitignore`.

## 8. Out of scope (intentional)

- **Cross-platform**: Windows + Edge stays the only verified path.
  README documents this as a Known Limitation. macOS/Linux contributions welcome
  but not blockers for v0.1.0.
- **Headless mode**: README documents that `headless=True` empirically returns
  empty SI for Wiley/ACS — keep `headed` as the default.
- **Externalizing `PUBLISHER_MAP` / `PDF_SELECTORS` to TOML**: Reviewed and
  rejected. These are tightly coupled to per-publisher logic in
  `download_refs.py`; externalizing one without the other doesn't reduce the
  contributor surface. Revisit in a separate "medium-scope" iteration.
- **Automated tests**: `tests/README.md` is a placeholder. Real pytest
  scaffolding deferred.

## 9. Two-route review provenance

| Reviewer | Findings unique to them |
|---|---|
| Plan-agent | Symlink discovery; institution PII at 1123/1132/1251/1260 + 119-122; EDGE_USER_DATA module-level (line 78); blocking `input()` at extract_refs.py:112; env var fallback recommendation; SECURITY.md recommendation; "if you can change one thing" → sanitize PKU |
| Kimi (narrow) | Three additional institution-specific strings at 736 / 1509 / 2205 (outside the main block); confirmed no other module-level constants need lazy-load; flagged auth_loading_titles ambiguity (institution + AIP/AVS share the string) |
| Self-grep | Confirmed no Drive-letter paths beyond known ones; no personal email/username in `.py`; identified additional URL fragment `iaaa/oauth` at 1127 and `oauth.jsp` at 1128 |

All findings consolidated into §3 above.
