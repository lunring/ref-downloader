# ref-downloader

> **Stop spending 3 hours hunting 50 PDFs for your literature review.**
> One DOI in, every reference PDF out — using your existing institutional access.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
![Verified on Windows + Edge](https://img.shields.io/badge/verified%20on-Windows%20+%20Edge-success)

[中文完整文档 / Full Chinese version](README.zh.md)

> **Heads up — not a paywall bypass.** ref-downloader uses _your_ institutional access. If your university or organization subscribes to a journal, those refs work. If they don't, those refs become `manual_pending` for you to follow up on by hand.

## Demo (30-second console preview)

```text
$ python run_ref_downloader.py 10.1021/jacs.5c05017

=== Ref Downloader Wrapper ===
DOI:         10.1021/jacs.5c05017
PROJECT:     jacs.5c05017
Config:      config.example.toml + config.local.toml

>>> extract_refs.py
  Title: Designing Natural Cell-Inspired Heme-Spurred Membrane...
  References found: 38

>>> validate_refs.py
  Total: 38  Verified: 38  Failed: 0  No DOI: 0

>>> download_refs.py
  [ 1] downloaded (842 KB)        Lee2016_NatEnergy.pdf
  [ 2] downloaded (1.2 MB)        Wang2018_AdvMater.pdf
  [ 3] manual_pending (auth_redirect)
  [ 4] downloaded (655 KB)        Chen2019_JACS.pdf
  ... 33 more refs processed ...
  [38] downloaded (956 KB)        Park2024_JElectrochemSoc.pdf

========== Download report ==========
Total references:  38
Main PDFs:         33 downloaded · 4 manual_pending · 1 ignored
SI files:          12 captured
PDFs land in:      ./jacs.5c05017_refs/jacs.5c05017/
=====================================
```

## Contents

- [What you get](#what-you-get)
- [Why this and not Zotero / scihub / generic scrapers?](#why-this-and-not-zotero--scihub--generic-scrapers)
- [Quick start](#quick-start) · [Requirements](#requirements) · [Install](#install) · [Usage examples](#usage-examples)
- [Configuration](#configuration) · [Architecture](#architecture) · [Supported publishers](#supported-publishers)
- [Known limitations](#known-limitations) · [Contributing](#contributing) · [Security](#security) · [License](#license)

## What you get

- **Paywalled refs work without setup.** _Drives your real Microsoft Edge profile, so any institutional login already in your browser carries through. No API keys, no proxies, no reverse engineering._
- **One DOI in, every reference PDF out.** _Crossref-driven extraction + 17+ publisher-specific download paths (Wiley PDFDirect, Elsevier viewer, AIP loading-page wait — see [per-publisher reliability tier](docs/SUPPORTED_PUBLISHERS.md)), not generic scraping._
- **You always know which refs failed and why.** _`download_report.csv` gives every ref a status + reason (`manual_pending (auth_redirect)`, `failed (challenge_timeout)`, `ignored`); `events.jsonl` keeps the per-ref event trace._
- **Pick up where you left off** after a VPN drop, browser crash, or `Ctrl+C`. _State persists per project; rerunning skips already-downloaded refs and retries only the failures._

## Why this and not Zotero / scihub / generic scrapers?

- **vs. Zotero's _Find Available PDF_** — walks one paper at a time and silently gives up at SSO redirects. ref-downloader walks the whole reference list at once and treats SSO as a configurable step instead of a dead end.
- **vs. scihub-style tools** — don't carry your institutional license, so paywalled refs you _legitimately_ have access to just fail. ref-downloader uses your authenticated browser session, so subscriptions you already pay for actually count.
- **vs. generic web scrapers** — don't know Wiley needs PDFDirect, Elsevier needs a viewer click, or AIP serves a Chinese loading page first. ref-downloader has 17+ publisher-specific paths plus hot-session retry for Elsevier.

## Quick start

```powershell
git clone <REPO_URL> && cd ref-downloader
pip install -r requirements.txt && playwright install msedge
cp config.example.toml config.local.toml      # then set [crossref].mailto
python run_ref_downloader.py 10.1021/jacs.5c05017
```

That's the happy path. Details below.

## Requirements

- **OS**: Windows 10/11 (verified). macOS / Linux untested — PRs welcome.
- **Browser**: Microsoft Edge (Stable channel). The script claims your persistent Edge profile, so close all Edge windows before running.
- **Python**: 3.11 or newer (uses stdlib `tomllib`).
- **Optional**: A Zotero installation (auto-detects DOI from a PDF's filename via Zotero's SQLite database — much faster than text extraction).
- **Optional**: PyMuPDF (`pip install pymupdf`) for DOI extraction from PDF text when Zotero lookup is unavailable.

## Install

```powershell
git clone <REPO_URL>
cd ref-downloader

pip install -r requirements.txt
playwright install msedge

cp config.example.toml config.local.toml
# Edit config.local.toml in your preferred editor — at minimum set [crossref].mailto.
# Windows: notepad config.local.toml
# macOS / Linux: $EDITOR config.local.toml   (or vim / nano / code / ...)
```

## Usage examples

### Input: a DOI

```powershell
python run_ref_downloader.py 10.1021/jacs.5c05017
```

Default output: `<cwd>/jacs.5c05017_refs/jacs.5c05017/`

### Input: a local PDF (with DOI in metadata or in PDF text)

```powershell
python run_ref_downloader.py "C:\path\to\your_paper.pdf"
```

Default output: `<pdf_dir>/your_paper_refs/<doi-derived-name>/`

### Custom output directory

```powershell
python run_ref_downloader.py 10.1021/jacs.5c05017 --output-dir refs/
```

### Non-interactive (CI / batch)

```powershell
python run_ref_downloader.py 10.1021/jacs.5c05017 --yes --auto
```

### Alternate config file

```powershell
python run_ref_downloader.py 10.1021/jacs.5c05017 --config ./alt.toml
```

## Configuration

All configuration lives in `config.local.toml` (gitignored). Copy `config.example.toml` to bootstrap.

| Section | Key | Purpose |
|---|---|---|
| `[crossref]` | `mailto` | Your email — entry into Crossref polite pool |
| `[zotero]` | `db_path` | Optional path to `zotero.sqlite` for DOI lookup from PDF filename |
| `[browser]` | `edge_profile_dir` | Edge profile directory; empty = OS default |
| `[browser]` | `disable_extensions` | Set `true` to launch with `--disable-extensions` |
| `[institution]` | `auth_hosts` | Hostnames that mean "you got bounced to SSO" (e.g. `["sso.your-uni.edu"]`) |
| `[institution]` | `auth_url_fragments` | URL substrings indicating SSO (e.g. `["oauth", "saml"]`) |
| `[institution]` | `auth_page_titles` | `<title>` text for SSO pages (catches HTML served as PDF) |
| `[institution]` | `auth_loading_titles` | Loading-page titles (also reused for AIP/AVS publisher loading detection) |
| `[institution]` | `ignored_access_dois` | DOIs you know are paywalled at your institution; skipped without retry |

Environment variables override file values:

| Variable | Maps to |
|---|---|
| `REF_DOWNLOADER_MAILTO` | `crossref.mailto` |
| `REF_DOWNLOADER_ZOTERO_DB` | `zotero.db_path` |
| `REF_DOWNLOADER_EDGE_PROFILE` | `browser.edge_profile_dir` |
| `REF_DOWNLOADER_DISABLE_EXTENSIONS` | `browser.disable_extensions` (`1`/`true` to enable) |
| `REF_DOWNLOADER_CONFIG` | Path to alternate TOML file |

See [`config.example.toml`](config.example.toml) for full documentation.

## Architecture

Three-stage pipeline + a wrapper:

```
run_ref_downloader.py   # entry point — config loading, DOI resolution, sequencing
  └─> extract_refs.py     (1) Crossref API: fetch parent paper's reference list
  └─> validate_refs.py    (2) Crossref API: per-ref metadata + publisher classify
  └─> download_refs.py    (3) Playwright/Edge: download main PDF + SI per publisher
```

You can also run the three scripts manually for debugging or partial restarts. See [SKILL.md](SKILL.md) for the manual flow.

## Supported publishers

ACS, Nature, Science, Elsevier, Wiley, RSC, Springer, PNAS, ECS, IOP, AIP, AVS, IEEE, OSA, KPS, Beilstein, APS, Annual Reviews, Taylor & Francis. Maturity varies — see [`docs/SUPPORTED_PUBLISHERS.md`](docs/SUPPORTED_PUBLISHERS.md) for the per-publisher tier table and known issues.

## Known limitations

- **Windows + Microsoft Edge only**: that's the verified path. macOS / Linux / Chromium support has not been tested. If you try, please open an issue with results.
- **Headed mode required**: empirically, `headless=True` yields empty results for Wiley / ACS supplementary downloads. The default is headed.
- **Edge must be fully closed before running**: Playwright needs exclusive access to the persistent profile. Check Task Manager for any background `msedge.exe` processes.
- **SSO redirects are detected, not solved**: when the script bounces to your institution's SSO, the ref becomes `manual_pending` so you can sign in interactively. Configure `[institution]` to teach it which redirects to recognize.
- **SI download is the most fragile path**: main PDFs are reliable; SI lookup varies by publisher and is the area most likely to need a tweak when a publisher updates their site.
- **Paywalled content needs institutional access**: this is not a bypass tool.
- **Crossref dependency**: papers with no reference list deposited at Crossref can't be processed automatically.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidance on:
- Adding a new publisher (DOI prefix → strategy)
- Adding institutional SSO patterns
- Reporting download failures with useful logs

## Security

This tool launches your real Edge profile, with all your cookies and saved sessions. Read [SECURITY.md](SECURITY.md) before running it against a profile you also use for daily browsing.

## License

MIT — see [LICENSE](LICENSE).
