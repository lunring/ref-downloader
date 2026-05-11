# Testing

Two layers:

1. **Offline pytest** — fast, no network, no Playwright. Run on every PR.
2. **Manual smoke** — full pipeline against a live publisher; covers what unit tests can't.

## Offline pytest

```powershell
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

Coverage:

| File | What it tests |
|---|---|
| `test_config.py` | TOML loader: chain merge order, env-var overrides, malformed-TOML exit code, schema validation (non-string filter, scalar-where-table) |
| `test_validate_refs.py` | `detect_publisher` — DOI-prefix primary path + journal-name fallback |
| `test_run_ref_downloader.py` | `looks_like_doi` + project-name sanitization (Windows-illegal chars) |

Roughly 10 tests; runs in well under a second. `download_refs.py` is NOT
imported by the test suite (it pulls in Playwright); that flow is covered
by the manual smoke recipe below.

## Manual smoke-test recipe

Before submitting a PR that changes publisher logic, run a manual smoke test
for the publisher you touched.

## Per-publisher smoke test

Pick a sample DOI for the publisher (suggestions in
[../docs/SUPPORTED_PUBLISHERS.md](../docs/SUPPORTED_PUBLISHERS.md)) and run:

```powershell
python run_ref_downloader.py <PARENT_DOI_THAT_CITES_YOUR_PUBLISHER> --output-dir test_smoke
```

Watch the console for refs in your target publisher:

| Status | Meaning |
|---|---|
| `downloaded (X KB)` | success — PDF saved |
| `already_exists` | previously downloaded, skipped |
| `manual_pending (...)` | needs human / paywall / SSO |
| `failed (...)` | automatic download failed |
| `ignored` | listed in `[institution].ignored_access_dois` |

For deeper inspection, open
`test_smoke/<project>/runs/<timestamp>-round-03/events.jsonl` and grep for
your publisher / DOI / failure reason.

Clean up after testing:

```powershell
Remove-Item -Recurse -Force test_smoke
```

## Empty-config smoke test

This verifies the wrapper still runs against vanilla open-internet defaults
(no `config.local.toml`):

```powershell
Move-Item config.local.toml config.local.toml.bak
python run_ref_downloader.py 10.1021/jacs.5c05017 --output-dir test_smoke
Move-Item config.local.toml.bak config.local.toml
```

Expected:
- Console prints `WARNING: crossref.mailto is the placeholder.`
- `extract_refs.py` succeeds (Crossref reachable without auth)
- `validate_refs.py` succeeds (per-DOI metadata fetch works)
- `download_refs.py` may or may not succeed for individual refs — paywalled
  refs without institutional access will paywall, that's acceptable

What MUST NOT happen:
- `ImportError` / `NameError` / `AttributeError` traceable to `_config.py`
- `KeyError` / `NoneType` from a missing config field
- Personal paths (e.g. `C:\Users\<you>\...`) appearing in any traceback

## Malformed-config robustness test

The config layer should warn and degrade gracefully on malformed TOML, never
crash mid-run. Create a `bad-config.toml`:

```toml
[crossref]
mailto = "test@example.com"

[institution]
auth_hosts = ["valid", 123, true, "another"]   # mixed types — non-strings dropped
auth_page_titles = "should_be_list_not_string"  # wrong type — ignored entirely
```

Run:

```powershell
python run_ref_downloader.py 10.1021/jacs.5c05017 --config bad-config.toml --output-dir test_smoke
```

Expected stderr WARNINGs (one per malformed field), then normal extract+validate
flow. The script should NOT raise `TypeError: 'in <string>' requires string`
mid-download — that was a pre-fix bug.

## --auto / --yes flag round-trip

The wrapper's `--auto` and `--yes` should propagate to the right child scripts:

```powershell
python run_ref_downloader.py 10.1021/jacs.5c05017 --yes --auto --output-dir test_smoke
```

Expected:
- `extract_refs.py` receives `--yes` (visible in the `>>> Running:` log line)
- `download_refs.py` receives `--auto` (visible in the `>>> Running:` log line)
- No `unrecognized arguments` error

## Cross-platform: macOS / Linux

Currently UNTESTED. The script will refuse to run `download_refs.py` on
non-Windows without an explicit `[browser].edge_profile_dir` setting:

```
ERROR: No Edge profile directory configured.
  This tool's auto-default for the Edge profile only works on Windows.
  ...
```

If you run on macOS / Linux and the error is unclear, please file an issue.

## Quick import-only check

If you've changed structure and want to verify without running a full
download:

```powershell
python -c "import _config, run_ref_downloader, extract_refs, validate_refs, download_refs; print('imports OK')"
```

This catches `SyntaxError`, `ImportError`, `NameError` early.

## Future automated tests

When pytest scaffolding lands, target:

- `_config.py`: TOML merge order, env override behavior, missing files
- `extract_refs.py`: argument parsing, non-tty input handling
- `download_refs.py` (unit-testable parts only): URL construction, status
  classification, label generation

Network-dependent integration tests (Crossref, Edge automation) likely stay
manual or behind an opt-in marker.
