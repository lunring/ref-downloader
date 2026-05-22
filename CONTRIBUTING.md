# Contributing

Thanks for considering a contribution! This project is small but the
publisher-specific logic in `download_refs.py` has accumulated real-world
edge cases. This document explains where to look and how to test.

## How the codebase fits together

```
_config.py              Config dataclass + TOML/env loader
run_ref_downloader.py   Entry wrapper: DOI resolution, sequencing
extract_refs.py         Stage 1: Crossref → refs_raw.json
validate_refs.py        Stage 2: per-DOI metadata + publisher classification
download_refs.py        Stage 3: Playwright/Edge → PDF + SI
```

All three stage scripts read configuration via `_config.load_config()`. The
download script also calls `init_institution_config()` once at startup to
make institution-specific patterns accessible from async helpers.

## Adding support for a new publisher

A "new publisher" means a DOI prefix the script doesn't currently recognize.
Adding one usually requires touching three places:

### 1. `validate_refs.py` — `PUBLISHER_MAP`

Map the DOI prefix to a short publisher key:

```python
PUBLISHER_MAP = {
    ...
    "10.XXXX": "your_publisher_key",
}
```

The script also tries journal-name hints (`JOURNAL_PUBLISHER_MAP`) when the
DOI prefix is ambiguous (e.g., shared by multiple imprints). Add an entry
there if your publisher's journal names are recognizable.

### 2. `download_refs.py` — `PUBLISHER_STRATEGIES`

Tell the script which strategy family the publisher belongs to:

```python
PUBLISHER_STRATEGIES: Dict[str, Dict[str, str]] = {
    ...
    "your_publisher_key": {
        "family": "generic_fallback",  # or "specialized_*"
        "support": "stable",           # or "weak" / "specialized"
        "min_test": "route_selector_smoke",
    },
}
```

Pick `generic_fallback` first — it covers the typical
`direct_pdf_url → article_url → PDF_SELECTORS → viewer fetch` path. Move to
`specialized_*` only if generic flow can't reach the PDF.

### 3. `download_refs.py` — URL templates and selectors

If the publisher exposes a direct-PDF URL pattern, add it:

```python
def direct_pdf_url(publisher: str, doi: str) -> Optional[str]:
    return {
        ...
        "your_publisher_key": f"https://example.com/articles/{doi}/pdf",
    }.get(publisher)
```

Add the article landing page (used as fallback):

```python
def article_url(publisher: str, doi: str) -> str:
    return {
        ...
        "your_publisher_key": f"https://example.com/articles/{doi}",
    }.get(publisher, f"https://doi.org/{doi}")
```

Add CSS selectors for the PDF download link on the article page:

```python
PDF_SELECTORS = {
    ...
    "your_publisher_key": [
        'a.pdf-download-link',
        'a[href*="/pdf"]',
    ],
}
```

### 4. Smoke test

Pick a sample DOI for the publisher and run:

```powershell
python run_ref_downloader.py <PARENT_DOI_THAT_CITES_YOUR_PUBLISHER> --output-dir test_smoke
```

Watch the console + `test_smoke/<project>/runs/<timestamp>/events.jsonl` for
your publisher's stage transitions. Attach this output to your PR.

## Adding institutional SSO patterns

Don't add your institution to source code. Edit your local
`config.local.toml`:

```toml
[institution]
auth_hosts          = ["sso.your-uni.edu"]
auth_url_fragments  = ["oauth", "saml"]
auth_page_titles    = ["Your University Single Sign-On"]
auth_loading_titles = []
ignored_access_dois = []
```

This stays local to your machine. The `config.example.toml` ships with all
institution lists empty, which is the right default for an unknown
contributor.

## ⚠ The `auth_loading_titles` ambiguity

The `auth_loading_titles` field is consumed by **two** code paths:

1. **Institution SSO loading-page detection** (e.g., your university's
   "Loading..." page that appears between login redirects)
2. **AIP/AVS publisher loading-page detection** — these publishers serve
   `请稍候` (Chinese for "Please wait") regardless of locale

The AIP/AVS path also has a hardcoded `"稍候"` substring check in
`download_refs.py`. **Do not remove that hardcoded string.** AIP/AVS literally
serve Chinese loading text, and removing the check would break their
download flow for everyone, including English-locale users.

If you're "cleaning up" loading-page detection, leave both mechanisms in
place. The hardcoded `"稍候"` is publisher behavior, not user-identifying
data.

## Reporting a download failure

Use the [bug report template](.github/ISSUE_TEMPLATE/bug-report.md). It
prompts you for the minimum useful info:

- Parent DOI + failing reference DOI
- Publisher (per `download_report.csv`)
- The last 30 lines of the relevant `events.jsonl` mentioning the failure
- Edge version + OS

**Redact institution-specific URLs** from logs before posting publicly.

## Code style

- Match existing style; no large reformats while adding a feature.
- `download_refs.py` is intentionally a single ~4,300 line file with
  carefully tuned timing/retry constants. Don't restructure it unilaterally;
  open an issue first if you think it needs splitting. A module split
  (`barriers.py` / `pdf_capture.py` / `publishers/elsevier.py` /
  `manual_retry.py` / `reporting.py`) is on the v0.4 candidate list.
- Keep public interfaces of `_config.py` stable — all four scripts depend on
  the `Config` dataclass shape.
- **Touching `--auto` mode** (v0.3.0+): the `is_auto_mode()` gate +
  `auto_manual_retry_*` helpers form a separate code path. Any new
  `manual_pending` site needs to decide explicitly whether to call
  `schedule_auto_manual_retry` (auto mode) or `preserve_manual_page`
  (interactive). Forgetting to wire one in means refs that hit that site
  in auto mode silently skip the retry queue. See `architecture.md`
  "Auto-mode manual-retry queue".

## CLI behavior nuances

A few things that look inconsistent on first read but are intentional:

- **Only `extract_refs.py` prompts on overwrite.** `validate_refs.py` and
  `download_refs.py` always overwrite their outputs (`refs_validated.json` and
  `download_report.csv` respectively) without asking — both are derived
  artifacts that should be safe to regenerate. The `--yes` flag is only
  meaningful for `extract_refs.py`. The wrapper exposes `--yes` (forwards to
  extract) and `--auto` (forwards to download for headless-like behavior) as
  the two non-interactive levers.

- **Running `extract_refs.py` standalone creates `<doi-suffix>/` next to your
  cwd without the `_refs` suffix.** The wrapper appends `_refs` itself; the
  underlying script doesn't. If you run `python extract_refs.py 10.x/y` from
  the repo root you'll get a bare `y/` directory there. `.gitignore` catches
  the JSON output files inside, but not the directory shell. Either run from a
  scratch dir, or use the wrapper.

## Testing

There's no automated test suite yet. See [tests/README.md](tests/README.md)
for the manual smoke-test recipe.

Any change to publisher logic in `download_refs.py` should include a
manually-verified smoke test for that publisher in the PR description.
