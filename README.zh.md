# ref-downloader

> 输入一篇论文的 DOI，自动批量下载它的全部参考文献；用你真实的 Microsoft Edge
> 配置文件，机构权限自然可用。
>
> Batch-download every reference of a paper from a single DOI, using your real
> Microsoft Edge profile so institutional access just works.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
![Verified on Windows + Edge](https://img.shields.io/badge/verified%20on-Windows%20+%20Edge-success)

[English full version](README.md)

---

## 亮点 / Highlights

每行结构：**给你的价值** —— *靠什么差异化做到的*。

| 中文 | English |
|---|---|
| **一个 DOI 输入，全部参考文献输出。** 不用逐篇手动点 —— *内置 17+ 家出版商专用路径（Wiley PDFDirect、Elsevier viewer、AIP 加载页等待），不是通用爬虫。* | **One DOI in, every reference out.** No manual click-through 50 PDFs — *17+ publisher-specific download paths (Wiley PDFDirect, Elsevier viewer, AIP loading-page wait), not generic scraping.* |
| **机构付费内容免配置直接可下** —— *直接驱动你真实的 Microsoft Edge 配置文件，Edge 里登录过的会话自然继承。不需要 API key、代理、或逆向工程。* | **Paywalled refs work out of the box** — *driven by your real Microsoft Edge profile, so any institutional login already in your browser carries through. No API keys, no proxies, no reverse engineering.* |
| **失败的条目和原因一目了然。** *`download_report.csv` 给每篇参考文献状态 + 原因（`manual_pending (auth_redirect)`、`failed (challenge_timeout)`、`ignored`），`events.jsonl` 留每篇的事件流。* | **You always know which refs failed and why.** *`download_report.csv` gives every ref a status + reason (`manual_pending (auth_redirect)`, `failed (challenge_timeout)`, `ignored`); `events.jsonl` keeps the per-ref event trace.* |
| **断点续跑**：VPN 断、浏览器崩、`Ctrl+C` 后都能继续。 *状态按项目目录持久化；重跑自动跳过已下载、只重试失败。* | **Pick up where you left off** after a VPN drop, browser crash, or `Ctrl+C`. *State persists per project; rerunning skips already-downloaded refs and retries only the failures.* |
| **贴合你的机构，无需改代码。** *`[institution]` 配置位让你把 SSO 主机、认证页标题、已知无权限的 DOI 告诉工具 —— 机构相关的知识留在你本地 TOML，不进源代码。* | **Adapts to your institution without touching code.** *A `[institution]` config slot lets you teach SSO hosts, auth-page titles, and known-paywalled DOIs — institution-bound knowledge stays in your local TOML, not in source.* |

---

## 它做什么

提供一篇论文的 DOI，工具会从 Crossref 拉取它的参考文献列表（化学/物理论文通常 30-80 篇），
逐条验证 DOI、按出版商分类，然后驱动 Microsoft Edge 用各出版商对应的策略下载主文 PDF
（部分出版商也下载 SI）。

输出：每篇论文一个目录，里面是各参考文献 PDF + `download_report.csv` 状态摘要。
失败的下载会标注原因（如 `manual_pending (auth_redirect)` / `failed (challenge_timeout)`），
方便你定位需要手动处理的条目。

## 为什么用

写综述时手动一篇篇下太费劲。本工具：

- **按出版商选对的策略**：能直链就直链（Springer / RSC / ACS），需要点击流程就跑（Wiley
  PDFDirect / Elsevier viewer）
- **认得机构 SSO 跳转**：撞到学校认证页时不会崩，标 `manual_pending` 让你交互登录后重跑
- **支持增量恢复**：同一个项目目录重跑会自动跳过已下载的条目

它**不是**绕过付费墙的工具。需要机构权限的文章，仍需你处于有访问权的网络环境，
或在 Edge profile 里登录过学校 SSO。

## 系统要求

- **操作系统**：Windows 10/11（已验证）。macOS / Linux 未测试，欢迎 PR。
- **浏览器**：Microsoft Edge（Stable channel）。脚本会接管你的持久 Edge profile，
  运行前请关闭所有 Edge 窗口。
- **Python**：3.11 或更新（用了标准库 `tomllib`）。
- **可选**：Zotero 安装（自动从 PDF 文件名查 DOI，速度比文本提取快很多）。
- **可选**：PyMuPDF（`pip install pymupdf`），用于 Zotero 不可用时从 PDF 文本提取 DOI。

## 安装

```powershell
git clone <REPO_URL>
cd ref-downloader

pip install -r requirements.txt
playwright install msedge

cp config.example.toml config.local.toml
# 在你顺手的编辑器里编辑 config.local.toml，至少改 [crossref].mailto
# Windows: notepad config.local.toml
# macOS / Linux: $EDITOR config.local.toml   (或 vim / nano / code 等)
```

## 快速开始

### 输入：一个 DOI

```powershell
python run_ref_downloader.py 10.1021/jacs.5c05017
```

默认输出到 `<cwd>/jacs.5c05017_refs/jacs.5c05017/`

### 输入：本地 PDF（metadata 中含 DOI 或 PDF 文本中可识别 DOI）

```powershell
python run_ref_downloader.py "C:\path\to\your_paper.pdf"
```

默认输出到 `<pdf_dir>/your_paper_refs/<根据 DOI 派生的目录名>/`

### 自定义输出目录

```powershell
python run_ref_downloader.py 10.1021/jacs.5c05017 --output-dir refs/
```

### 非交互模式（CI / 批处理）

```powershell
python run_ref_downloader.py 10.1021/jacs.5c05017 --yes --auto
```

### 使用备选配置文件

```powershell
python run_ref_downloader.py 10.1021/jacs.5c05017 --config ./alt.toml
```

## 配置

所有配置写在 `config.local.toml`（gitignored）。从 `config.example.toml` 拷贝出来后编辑。

| 段 | 字段 | 用途 |
|---|---|---|
| `[crossref]` | `mailto` | 你的邮箱 — 进入 Crossref polite pool 用 |
| `[zotero]` | `db_path` | 可选：`zotero.sqlite` 路径，用于从 PDF 文件名查 DOI |
| `[browser]` | `edge_profile_dir` | Edge profile 目录；空 = OS 默认 |
| `[browser]` | `disable_extensions` | 设 `true` 启动时加 `--disable-extensions` |
| `[institution]` | `auth_hosts` | 表示"被弹到 SSO"的主机名（例如 `["sso.your-uni.edu"]`） |
| `[institution]` | `auth_url_fragments` | 表示 SSO 的 URL 片段（如 `["oauth", "saml"]`） |
| `[institution]` | `auth_page_titles` | SSO 页面 `<title>` 文本（用于检测 HTML 当 PDF 返回的情况） |
| `[institution]` | `auth_loading_titles` | 加载页 title（同时被 AIP/AVS 出版商加载页检测复用） |
| `[institution]` | `ignored_access_dois` | 已知机构无法访问的 DOI 列表，跳过不重试 |

环境变量优先级高于文件：

| 变量 | 映射 |
|---|---|
| `REF_DOWNLOADER_MAILTO` | `crossref.mailto` |
| `REF_DOWNLOADER_ZOTERO_DB` | `zotero.db_path` |
| `REF_DOWNLOADER_EDGE_PROFILE` | `browser.edge_profile_dir` |
| `REF_DOWNLOADER_DISABLE_EXTENSIONS` | `browser.disable_extensions`（`1`/`true` 启用） |
| `REF_DOWNLOADER_CONFIG` | 备选 TOML 路径 |

完整文档参考 [`config.example.toml`](config.example.toml)。

## 架构

三阶段流水线 + 一个 wrapper：

```
run_ref_downloader.py   # 入口：加载配置、解析 DOI、串行调度
  └─> extract_refs.py     (1) Crossref API：抓取主论文的参考文献列表
  └─> validate_refs.py    (2) Crossref API：逐条 metadata + 出版商分类
  └─> download_refs.py    (3) Playwright/Edge：按出版商策略下主文 PDF + SI
```

也可以单独运行三个脚本调试或局部重跑。手动流程见 [SKILL.md](SKILL.md)。

## 已支持出版商

ACS、Nature、Science、Elsevier、Wiley、RSC、Springer、PNAS、ECS、IOP、AIP、
AVS、IEEE、OSA、KPS、Beilstein、APS、Annual Reviews、Taylor & Francis。
成熟度因出版商而异，详细分级表与已知问题见
[`docs/SUPPORTED_PUBLISHERS.md`](docs/SUPPORTED_PUBLISHERS.md)。

## 已知限制

- **仅在 Windows + Edge 验证过**：macOS / Linux / Chromium 未测试。如果你尝试了，
  欢迎在 issues 里反馈结果。
- **必须 headed 模式**：实测 `headless=True` 时 Wiley / ACS 的 SI 下载会返空结果。默认 headed。
- **运行前 Edge 必须完全关闭**：Playwright 需独占持久 profile。任务管理器里
  `msedge.exe` 后台进程也要 kill。
- **SSO 跳转能识别但不会自动登录**：撞到学校 SSO 时该篇标 `manual_pending`，需要你
  交互登录。配置 `[institution]` 段告诉脚本你学校的 SSO 特征。
- **SI 下载是最脆弱的路径**：主文 PDF 比较稳；SI 路径每个出版商不一样，是最容易因
  出版商页面更新而需要调整的地方。
- **付费内容需要机构访问权**：本工具不绕过付费墙。
- **依赖 Crossref 的 reference 数据**：如果某出版商没有把参考列表存进 Crossref，工具无法自动处理。

## 贡献

参见 [CONTRIBUTING.md](CONTRIBUTING.md)，包含：
- 添加新出版商（DOI 前缀 → 下载策略）
- 添加机构 SSO 配置
- 报 bug 时附上有用的日志

## 安全

工具会启动你的真实 Edge profile，含所有 cookie 和已登录会话。在用日常浏览的 profile
跑之前请阅读 [SECURITY.md](SECURITY.md)。

## License

MIT — 见 [LICENSE](LICENSE)。
