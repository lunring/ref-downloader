# Architecture

> Why ref-downloader is built the way it is. Non-obvious design choices and their
> trade-offs, for contributors trying to extend the tool without breaking it.
>
> Implementation-level details on individual publishers live in
> [SUPPORTED_PUBLISHERS.md](SUPPORTED_PUBLISHERS.md). Agent-mode entry lives in
> [../skills/ref-downloader/SKILL.md](../skills/ref-downloader/SKILL.md), with the
> expanded manual flow in
> [../skills/ref-downloader/references/agent-runbook.md](../skills/ref-downloader/references/agent-runbook.md).
> User-facing usage lives in [../README.md](../README.md).

---

## Goal

Given a parent DOI (or a PDF whose DOI is in metadata), download every
reference Crossref knows about — using the user's existing institutional
browser session, with per-publisher strategies, and producing a per-reference
status report so the user knows exactly which refs succeeded, which need
manual follow-up, and why.

The project is _not_ a paywall bypass; it is a UX shell around the user's
already-paid-for institutional access plus publisher-specific quirks
encoded in Python.

## Shape

Three-stage pipeline + a single-entry wrapper:

```
skills/ref-downloader/scripts/run_ref_downloader.py   # entry: DOI + sequencing
  └─ extract_refs.py    (1)   Crossref → refs_raw.json
  └─ validate_refs.py   (2)   per-DOI metadata + publisher classify → refs_validated.json
  └─ download_refs.py   (3)   Playwright/Edge → PDFs + SI + download_report.csv
```

The repository root is the Python project. The installable agent skill is kept
under `skills/ref-downloader/` so skill evaluators and agent runtimes can load a
small task-specific bundle instead of treating README files, source files, tests,
and changelog history as skill context.

Each stage:
- Reads from the previous stage's JSON output
- Writes its own JSON / CSV that the next stage (or a human) can inspect
- Is independently restartable for partial re-runs and debugging

This explicit-file-handoff shape (instead of a single in-memory pipeline)
was chosen so that:
- Crashes in stage 3 don't lose stage 2's verification work (which is rate-
  limited by Crossref's 0.35s/req polite-pool delay).
- Bug reports from contributors include the exact JSON that triggered the
  failure, not a stack trace requiring a re-run.
- The slowest stage (download) can be retried incrementally without
  re-validating 80 refs against Crossref.

## Configuration layering

Lookup priority (later wins):

```
built-in defaults (empty / placeholder)
  > config.example.toml             (committed template)
    > config.local.toml             (gitignored user values)
      > REF_DOWNLOADER_CONFIG       (env-pointed alternate TOML)
        > --config CLI arg          (run-time override)
          > REF_DOWNLOADER_*        (per-field env vars)
```

Reasoning:
- **File for desktop users**: the typical user fills `config.local.toml` once and forgets.
- **Env vars on top**: CI / container users avoid managing a TOML file.
- **Schema validation is forgiving**: malformed sections / lists emit a stderr
  WARNING and degrade to safe defaults rather than crashing mid-run. Bad config
  shouldn't lose hours of partial downloads.
- **`load_config()` is intentionally uncached**: a fresh read on every call means
  `cache_clear()` on the runtime-config getters is sufficient to pick up new values.

## Why drive a real Edge profile

The single most consequential decision. Alternatives considered:

| Approach | Why rejected |
|---|---|
| Fresh Chromium sandbox via Playwright | Loses your institutional cookies; paywalled refs all fail |
| Headless mode | Empirically returns empty SI for Wiley / ACS — publisher anti-bot heuristics |
| API keys per publisher | No such universal API exists; each publisher has different terms |
| Reverse-engineering authenticated requests | Brittle, breaks on every site update, ethically fraught |

Using the user's persistent Edge profile means:
- Whatever the user can read in their daily browser, the tool can download.
- Institutional SSO is solved once at user-login time, not per-tool.
- No credentials are stored, transmitted, or reverse-engineered.

Cost: the user must close Edge before runs (single-instance profile lock).
This is documented in SECURITY.md (recommend a dedicated Edge profile for
this tool, not your daily-driver).

## Per-publisher strategies

`download_refs.py` is one large file (~4,300 lines) with a strategy table
in `PUBLISHER_STRATEGIES`. Three tiers:

- **specialized** — Wiley PDFDirect, Elsevier viewer + crasolve hot-session
  retry, AIP/AVS Chinese-loading-page wait.
- **generic_fallback** — direct PDF URL → article URL → CSS selector → viewer fetch.
  Covers ACS, Nature, Science, RSC, Springer, PNAS, IEEE, OSA, KPS.
- **weak** — recognized publisher key but no validated specialized path
  (APS, Annual Reviews, Taylor & Francis, Beilstein).

Why one big file:
- Per-publisher constants (timeouts, selectors, retry windows) are
  tightly coupled to the orchestration logic that uses them.
- Splitting into `publishers/elsevier.py`, `publishers/wiley.py`, etc. was
  rejected because the publishers share hot-session / queue / session-restart
  state that would need to be passed through every interface.
- The current single-file design is "boring but battle-tested"; the cost of
  finding a publisher quirk is `Ctrl+F`, not a tour of the architecture.

A future refactor _may_ split this once the publishers' shapes are stable,
but only with full end-to-end smoke regression on every supported publisher.

## Auto-mode manual-retry queue (v0.3.0)

`--auto` mode has a fundamentally different shape from interactive mode for
`manual_pending` refs. Interactive mode pauses the main loop and asks the
user to click captcha / SSO; auto mode cannot pause, so instead it queues
the ref for a single asynchronous retry attempt and lets the main loop
continue.

Mechanism (all in `download_refs.py`):

- `is_auto_mode()` — single source of truth, checks `sys.argv` for `--auto`.
  Every callsite that needs to decide "queue vs preserve_manual_page" gates
  on this. Non-auto mode is bit-identical to v0.2.x.
- `CURRENT_REF: contextvars.ContextVar` — per-ref context that survives async
  hops, so retries attribute their events to the right ref in `events.jsonl`.
- Constants (top of file, intentional knobs):
  - `AUTO_MANUAL_RETRY_WAIT = 60_000` — wait before retrying (gives the
    publisher's transient state time to clear; e.g. Elsevier `crasolve_shell`
    typically transitions within 30-60s).
  - `AUTO_MANUAL_RETRY_TIMEOUT = 20_000` — single-try timeout. Short on
    purpose: if the second attempt also hangs, the ref stays
    `manual_pending` for the user to handle.
  - `AUTO_MANUAL_RETRY_MAX_CONCURRENT = 3` — async semaphore cap. Limits
    pressure on Edge / publisher when many refs queue at once.
  - `AUTO_MANUAL_RETRY_MAX_PENDING = 8` — backpressure cap. Beyond this,
    new manual_pending refs are not queued and stay as-is for the user.
- Drain points in `main()`:
  - Pre-`download_one`: drains any retries that have aged past their wait.
  - Post-`download_one`: same, plus catches the just-finished ref's possible
    queued retry siblings.
  - End-of-run with `wait=True`: blocks until all in-flight retries finish
    before reporting.
- `restart_edge_context` cancels pending retries first; firing a retry
  against a dead `BrowserContext` would crash mid-loop.
- `sync_report_with_existing_files` reconciles the in-memory report with
  PDFs that landed on disk during retries, immediately before writing
  `download_report.csv`. Without this, a ref that succeeded on retry could
  show as `manual_pending` in the CSV even though its PDF is sitting in
  the project directory.

Design tension: the queue duplicates some logic from the existing
interactive small-queue flush. Splitting them out into a single class
(`AutoManualRetryManager`) is a documented v0.4 candidate, gated on
real-world feedback that the current shape needs it.

## Institution-aware SSO detection

The `[institution]` config section is where each user teaches the tool
about their organization's authentication patterns:

- `auth_hosts` — hostnames that mean "you got bounced to SSO"
- `auth_url_fragments` — URL substrings indicating an auth redirect
- `auth_page_titles` — `<title>` text for SSO pages (catches HTML pretending to be PDF)
- `auth_loading_titles` — loading-page titles (also reused for AIP/AVS publisher loading detection)
- `ignored_access_dois` — DOIs known paywalled at the user's institution, skipped without retry

Refs that hit any of these become `manual_pending (institution_auth_redirect)`
in the report — the user signs in via the live Edge tab, then re-runs (the
incremental skip picks up where it left off).

The shared field `auth_loading_titles` deliberately couples two unrelated
detection paths (institution loading + AIP/AVS publisher loading) because both
look at the same `<title>` string in practice. CONTRIBUTING.md flags this
explicitly to prevent well-meaning "cleanup" PRs from breaking AIP/AVS.

## Runtime cache strategy

`download_refs.py` reads institution-config getters in hot loops (once per
ref × N refs). To avoid per-ref tuple/set rebuild:

- 5 institution getters + `get_edge_user_data_dir` are `@lru_cache(maxsize=1)`.
- `init_institution_config()` clears all 6 caches as a unit, so any future
  mid-run reload picks up new values atomically.
- A comment block in `download_refs.py` warns future maintainers that any
  new cached getter must be added to the `cache_clear()` set.

This is a defensive pattern: today there is no mid-run reload, but the
contract is explicit so the next contributor can add one safely.

## Out of scope (intentional)

- **Cross-platform**: Windows + Edge is the only verified path. macOS / Linux
  contributions welcome but not blockers for the v0.1.x line.
- **Headless mode**: documented as broken for Wiley / ACS SI. Re-enabling
  needs publisher-by-publisher regression.
- **Externalizing `PUBLISHER_MAP` / `PDF_SELECTORS` to TOML**: discussed and
  rejected; the strategy tables and orchestration logic are too tightly
  coupled to make external configuration worth the contributor surface area.
- **Automated browser-driven tests**: would need a private testbed of
  publisher accounts. Manual smoke test recipe is documented in
  [../tests/README.md](../tests/README.md).
- **Citation graph traversal / N-hop**: tool downloads one paper's direct
  references, not recursive citation networks.

## Files of interest for contributors

All Python sources live in `skills/ref-downloader/scripts/`:

- `_config.py` — config schema + loader (small, well-tested)
- `validate_refs.py:PUBLISHER_MAP` — DOI prefix → publisher key
- `download_refs.py:PUBLISHER_STRATEGIES` — strategy tier per publisher
- `download_refs.py:direct_pdf_url` / `article_url` / `PDF_SELECTORS` — per-publisher URL + selector data
- `download_refs.py:inspect_access_barrier` — SSO / captcha / Cloudflare detection

Other entry points:

- `tests/test_*.py` — offline unit tests covering config + DOI/publisher classification
- `skills/ref-downloader/SKILL.md` — installable agent entry
- `skills/ref-downloader/references/agent-runbook.md` — detailed manual/debug agent flow
