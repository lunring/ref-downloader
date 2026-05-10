# ref-downloader

> Batch-download every reference of a paper from a single DOI, using your real
> Microsoft Edge profile so institutional access just works.
>
> 输入一篇论文的 DOI，自动批量下载它的全部参考文献；用你真实的 Microsoft Edge
> 配置文件，机构权限自然可用。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
![Verified on Windows + Edge](https://img.shields.io/badge/verified%20on-Windows%20+%20Edge-success)

[中文完整文档 / Full Chinese version](README.zh.md)

---

## Highlights / 亮点

Each row: **what you get** — *the differentiator that delivers it*.

| English | 中文 |
|---|---|
| **One DOI in, every reference out.** No manual click-through 50 PDFs — *17+ publisher-specific download paths (Wiley PDFDirect, Elsevier viewer, AIP loading-page wait), not generic scraping.* | **一个 DOI 输入，全部参考文献输出。** 不用逐篇手动点 —— *内置 17+ 家出版商专用路径（Wiley PDFDirect、Elsevier viewer、AIP 加载页等待），不是通用爬虫。* |
| **Paywalled refs work out of the box** — *driven by your real Microsoft Edge profile, so any institutional login already in your browser carries through. No API keys, no proxies, no reverse engineering.* | **机构付费内容免配置直接可下** —— *直接驱动你真实的 Microsoft Edge 配置文件，Edge 里登录过的会话自然继承。不需要 API key、代理、或逆向工程。* |
| **You always know which refs failed and why.** *`download_report.csv` gives every ref a status + reason (`manual_pending (auth_redirect)`, `failed (challenge_timeout)`, `ignored`); `events.jsonl` keeps the per-ref event trace.* | **失败的条目和原因一目了然。** *`download_report.csv` 给每篇参考文献状态 + 原因（`manual_pending (auth_redirect)`、`failed (challenge_timeout)`、`ignored`），`events.jsonl` 留每篇的事件流。* |
| **Pick up where you left off** after a VPN drop, browser crash, or `Ctrl+C`. *State persists per project; rerunning skips already-downloaded refs and retries only the failures.* | **断点续跑**：VPN 断、浏览器崩、`Ctrl+C` 后都能继续。 *状态按项目目录持久化；重跑自动跳过已下载、只重试失败。* |
| **Adapts to your institution without touching code.** *A `[institution]` config slot lets you teach SSO hosts, auth-page titles, and known-paywalled DOIs — institution-bound knowledge stays in your local TOML, not in source.* | **贴合你的机构，无需改代码。** *`[institution]` 配置位让你把 SSO 主机、认证页标题、已知无权限的 DOI 告诉工具 —— 机构相关的知识留在你本地 TOML，不进源代码。* |

---

## What it does

You give it the DOI of one paper. It fetches that paper's reference list from
Crossref (~30–80 references for a typical chemistry/physics paper), validates
each DOI, classifies them by publisher, then drives Microsoft Edge to download
each PDF (and supplementary files where supported) using publisher-specific
strategies.

Output: one folder per parent paper, containing each reference's PDF + a
`download_report.csv` summarizing per-reference status. Failed downloads are
labeled with the failure reason (e.g. `manual_pending (auth_redirect)`,
`failed (challenge_timeout)`) so you know where to follow up by hand.

## Why use this

Manual reference downloading is tedious for literature reviews. This tool:

- **Tries the right thing per publisher**: direct PDF URL where available
  (Springer, RSC, ACS), JS-discovered click flow where required (Wiley
  PDFDirect, Elsevier viewer)
- **Handles institutional SSO redirects** without crashing — auth-redirect
  refs become `manual_pending`, ready for you to approve interactively
- **Resumes incrementally**: rerun on the same project and already-downloaded
  refs are skipped

It is **not** a paywall bypass. References that need institutional access
require you to be on a network with that access, or signed in to your
institution's SSO via the Edge profile.

## Requirements

- **OS**: Windows 10/11 (verified). macOS / Linux untested — PRs welcome.
- **Browser**: Microsoft Edge (Stable channel). The script claims your
  persistent Edge profile, so close all Edge windows before running.
- **Python**: 3.11 or newer (uses stdlib `tomllib`).
- **Optional**: A Zotero installation (auto-detects DOI from a PDF's filename
  via Zotero's SQLite database — much faster than text extraction).
- **Optional**: PyMuPDF (`pip install pymupdf`) for DOI extraction from PDF
  text when Zotero lookup is unavailable.

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

## Quick start

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

All configuration lives in `config.local.toml` (gitignored). Copy
`config.example.toml` to bootstrap.

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

You can also run the three scripts manually for debugging or partial restarts.
See [SKILL.md](SKILL.md) for the manual flow.

## Supported publishers

ACS, Nature, Science, Elsevier, Wiley, RSC, Springer, PNAS, ECS, IOP, AIP,
AVS, IEEE, OSA, KPS, Beilstein, APS, Annual Reviews, Taylor & Francis.
Maturity varies — see [`docs/SUPPORTED_PUBLISHERS.md`](docs/SUPPORTED_PUBLISHERS.md)
for the per-publisher tier table and known limitations.

## Known limitations

- **Windows + Microsoft Edge only**: that's the verified path. macOS / Linux /
  Chromium support has not been tested. If you try, please open an issue with
  results.
- **Headed mode required**: empirically, `headless=True` yields empty results
  for Wiley / ACS supplementary downloads. The default is headed.
- **Edge must be fully closed before running**: Playwright needs exclusive
  access to the persistent profile. Check Task Manager for any background
  `msedge.exe` processes.
- **SSO redirects are detected, not solved**: when the script bounces to your
  institution's SSO, the ref becomes `manual_pending` so you can sign in
  interactively. Configure `[institution]` to teach it which redirects to
  recognize.
- **SI download is the most fragile path**: main PDFs are reliable; SI lookup
  varies by publisher and is the area most likely to need a tweak when a
  publisher updates their site.
- **Paywalled content needs institutional access**: this is not a bypass tool.
- **Crossref dependency**: papers with no reference list deposited at Crossref
  can't be processed automatically.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidance on:
- Adding a new publisher (DOI prefix → strategy)
- Adding institutional SSO patterns
- Reporting download failures with useful logs

## Security

This tool launches your real Edge profile, with all your cookies and saved
sessions. Read [SECURITY.md](SECURITY.md) before running it against a profile
you also use for daily browsing.

## License

MIT — see [LICENSE](LICENSE).
