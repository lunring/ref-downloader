---
name: ref-downloader
description: >
  批量下载一篇论文的所有参考文献 PDF。接受 Zotero PDF 路径或 DOI 字符串作为输入，
  自动从 Zotero 数据库或 PDF 文本中查找 DOI，并通过单入口脚本串起
  extract_refs → validate_refs → download_refs 流水线。
  对 PDF 输入，输出到原论文同级目录下的 {文件名}_refs/ 子文件夹；
  对 DOI 输入，默认输出到当前工作目录下的 {PROJECT_NAME}_refs/。
  wrapper 结束后会在输出目录根部执行一次窄范围旧文件清理。
  触发场景：用户说"帮我下载这篇文献的参考文献"、"批量下载引用文献"、"把这篇论文的
  所有引用都下载下来"、或提供 PDF 路径/DOI 要求下载全部参考文献。
---

# Ref Downloader — Claude Code Skill Runbook

> **This file is primarily an agent runbook for Claude Code.**
> If you're a human reading this for the first time, see [README.md](README.md)
> for setup, configuration, and usage. This file documents the step-by-step flow
> Claude Code's agent mode follows when invoked as `/ref-downloader`.

推荐通过单入口 wrapper 使用；底层仍保留三脚本流水线，便于调试和增量重跑。

---

## 配置

本 skill 从 `<SKILL_DIR>/config.local.toml`（gitignored，用户私有）读取个人配置，
并以 `<SKILL_DIR>/config.example.toml` 作为兜底默认值。schema 详见
[config.example.toml](config.example.toml)。安装与覆盖机制说明见 [README.md](README.md)。

环境变量可覆盖文件值：`REF_DOWNLOADER_MAILTO`、`REF_DOWNLOADER_ZOTERO_DB`、
`REF_DOWNLOADER_EDGE_PROFILE`、`REF_DOWNLOADER_DISABLE_EXTENSIONS`、
`REF_DOWNLOADER_CONFIG`（指定备选 TOML 路径）。

本 runbook 中的 `<SKILL_DIR>` 表示 skill 文件所在目录（agent 通过任一脚本里的
`Path(__file__).resolve().parent` 解析）。

---

## 推荐入口

优先使用：

```bash
python "<SKILL_DIR>/run_ref_downloader.py" <DOI 或 PDF 路径>
```

可选参数：

```bash
python "<SKILL_DIR>/run_ref_downloader.py" <DOI 或 PDF 路径> --output-dir <path/to/custom_refs>
python "<SKILL_DIR>/run_ref_downloader.py" <DOI> --config <path/to/alt-config.toml>
python "<SKILL_DIR>/run_ref_downloader.py" <DOI> --yes  # 非交互（CI / 批处理）
```

wrapper 会负责：

- 解析 DOI（PDF 输入时先查 Zotero（若 `[zotero].db_path` 已配置且存在），再回退到 PDF 文本）
- 计算 `OUTPUT_DIR`
- 在 `OUTPUT_DIR` 里顺序运行三脚本
- 结束后只在 `OUTPUT_DIR` 根目录做一次窄范围清理

只有在你需要单独调试某一步时，才按下面的"三脚本手动流程"逐步执行。

---

## 完整执行流程（底层手动模式）

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

## Step 1：解析输入，获取 DOI

### 情况 A：用户直接给出 DOI
识别规则：输入以 `10.` 开头（如 `10.1021/jacs.5c05017`）。直接使用，跳到 Step 2。

### 情况 B：用户给出 PDF 文件路径
若 `[zotero].db_path` 已配置且文件存在，优先查 Zotero 数据库（速度快、元数据最准）：

```python
# 通过 _config 读取配置后的 db_path（不要硬编码）
import sqlite3, shutil, os, sys, tempfile
from _config import load_config

cfg = load_config()
db_path = cfg.zotero.db_path  # 来自 config.local.toml；未配置则跳过 Zotero
pdf_path = sys.argv[1]

if not db_path or not os.path.exists(db_path):
    print("")  # 让 caller fallback 到 fitz 文本提取
else:
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

如果 Zotero 返回空（或未配置），尝试从 PDF 文本提取：

```python
import fitz, re, sys
doc = fitz.open(sys.argv[1])
text = "".join(doc[i].get_text() for i in range(min(3, len(doc))))
m = re.search(r'10\.\d{4,9}/[^\s"<>]+', text)
print(m.group(0).rstrip(".,;)") if m else "")
```

如果两种方法都失败，停下来询问用户：
> "无法自动识别该 PDF 的 DOI，请手动提供（格式：10.xxxx/xxxxx）"

---

## Step 2：确认前置条件

在运行任何脚本前，向用户确认：

```
即将开始下载参考文献：
  DOI：<DOI>
  输出目录：<OUTPUT_DIR>（见 Step 3）

请确认：
1. 以上 DOI 是否正确？
2. Microsoft Edge 是否已完全关闭？（脚本需要独占 Edge 配置文件）
```

---

## Step 3：确定输出目录和项目名

```
情况 A：输入是 PDF 路径
  OUTPUT_DIR = PDF 所在目录 + "/" + PDF 文件名（去掉 .pdf）+ "_refs"
    示例：<path/to/your_paper>_refs/

情况 B：输入是 DOI（没有原始 PDF 路径）
  OUTPUT_DIR 默认 = 当前工作目录 + "/" + PROJECT_NAME + "_refs"
    示例：<cwd>/<project_name>_refs/
  也可以在 wrapper 里显式传 `--output-dir`

PROJECT_NAME = DOI 最后一个 "/" 之后的部分，特殊字符替换为 "_"

项目数据最终存放在：OUTPUT_DIR/PROJECT_NAME/
```

如果 `OUTPUT_DIR/PROJECT_NAME/refs_raw.json` 已存在，**跳过 Step 4**，直接从 Step 5 继续（增量模式）。

如果 OUTPUT_DIR 不存在，先创建：
```bash
mkdir "<OUTPUT_DIR>"
```

注意：
- `download_refs.py` 现在会把 run artifacts 固定写到 `OUTPUT_DIR/runs/`
- 但手动三步模式仍推荐先 `cd "<OUTPUT_DIR>"`，这样三脚本输出更一致、更不容易混淆

---

## Step 4：运行 extract_refs.py（提取 DOI 列表）

```bash
cd "<OUTPUT_DIR>"
python "<SKILL_DIR>/extract_refs.py" <DOI>
```

**预期输出**：`<PROJECT_NAME>/refs_raw.json` 创建成功，控制台显示参考文献总数。

**错误处理**：

| 错误 | 处理 |
|------|------|
| `DOI not found in Crossref` | DOI 可能有误，向用户确认 |
| `No references found` | Crossref 未收录该期刊参考列表，告知用户无法自动提取 |
| 网络超时 | 重试一次 |
| `Overwrite? [y/N]` 提示 | Step 3 已检测到已存在时跳过此步，此提示不应出现；非交互场景请加 `--yes` |

---

## Step 5：运行 validate_refs.py（验证 DOI，分类出版商）

```bash
cd "<OUTPUT_DIR>"
python "<SKILL_DIR>/validate_refs.py" <PROJECT_NAME>
```

**预期输出**：`refs_validated.json` 创建成功，显示 `Verified: X / Failed: Y / No DOI: Z`。

### 自动更新 PUBLISHER_MAP

验证完成后，读取 `refs_validated.json`，检查 `publisher == "unknown"` 且有 DOI 的条目：

```python
import json, urllib.request, re

data = json.loads(open("<OUTPUT_DIR>/<PROJECT_NAME>/refs_validated.json").read())
unknowns = [r for r in data["references"] if r.get("publisher") == "unknown" and r.get("doi")]

# 提取唯一 DOI 前缀
prefixes = {}
for r in unknowns:
    prefix = r["doi"].split("/")[0]
    if prefix not in prefixes:
        prefixes[prefix] = r["doi"]

print(f"Unknown prefixes: {list(prefixes.keys())}")
```

如果有未知前缀，对每个前缀查询 Crossref 获取 publisher 名称：

```python
from _config import load_config, user_agent_from
cfg = load_config()
ua = user_agent_from(cfg, "RefDownloader/1.0")

url = f"https://api.crossref.org/works/{urllib.request.quote(doi, safe='')}"
req = urllib.request.Request(url, headers={"User-Agent": ua})
with urllib.request.urlopen(req, timeout=15) as r:
    msg = json.loads(r.read())["message"]
    publisher_name = msg.get("publisher", "").lower()
    print(f"  {prefix} → {publisher_name}")
```

根据 publisher 名称判断映射值（参考下表），然后用 Read/Edit 工具更新 `<SKILL_DIR>/validate_refs.py` 中的 `PUBLISHER_MAP`：

| Publisher 名称包含 | 映射值 |
|-------------------|--------|
| aip, american institute of physics | aip |
| ieee | ieee |
| osa, optica | osa |
| royal society of chemistry, rsc | rsc |
| american physical society | aps |
| taylor & francis | tandfonline |
| elsevier | elsevier |
| wiley | wiley |
| springer, nature portfolio | springer/nature |

更新 `PUBLISHER_MAP` 后，**重跑 validate_refs.py**（增量模式，只重新分类 unknown 条目）：

```bash
cd "<OUTPUT_DIR>"
python "<SKILL_DIR>/validate_refs.py" <PROJECT_NAME>
```

同时，如果 download_refs.py 中对应出版商没有 `direct_pdf_url` 和 `PDF_SELECTORS` 条目，用 Edit 工具补充合理的默认值（用 `doi.org/{doi}` 做 article URL，用 `a:has-text("PDF")` 做选择器兜底）。

---

## Step 6：运行 download_refs.py（下载 PDF）

```bash
cd "<OUTPUT_DIR>"
python "<SKILL_DIR>/download_refs.py" <PROJECT_NAME>
```

默认推荐**交互模式**，不要先加 `--auto`。

`--auto` 标志仍可用：
- 跳过手动 Enter 确认
- challenge 等待使用 15 秒超时
- 更适合"先快速扫一遍看整体成功率"
- **不适合**作为需要你接管验证码/学校登录/热会话的主流程

注意：
- 脚本会打开**真实的 Microsoft Edge 持久 profile**，路径取自 `[browser].edge_profile_dir`，未配置则用 OS 默认（Windows: `%LOCALAPPDATA%\Microsoft\Edge\User Data`）
- 默认**保留 Edge profile 里的扩展**；若 `[browser].disable_extensions = true` 或 env `REF_DOWNLOADER_DISABLE_EXTENSIONS=1`，会以禁扩展方式启动
- 交互模式下，`manual_pending` 页面会保留并进入后续 retry loop
- 主循环包含"小队列即时 flush"：
  - `elsevier`：出现 `manual_pending` 时立刻提示并热重试
  - 其他出版商：积累到队列上限再提示
- 如果 Edge 会话意外关闭，脚本会自动重启一次会话并只重试当前篇
- 如果某篇已进入 PDF viewer 但自动保存没接住，manual retry 会优先复用 live page

**预期输出**：
- PDF 文件保存到 `<OUTPUT_DIR>/<PROJECT_NAME>/`
- 运行事件保存到 `<OUTPUT_DIR>/runs/<timestamp>-round-03/events.jsonl`
- graceful completion 时生成 / 刷新 `<OUTPUT_DIR>/<PROJECT_NAME>/download_report.csv`

**状态说明**：
- `downloaded (X KB)` — 新下载成功
- `already_exists` — 之前已下载，跳过
- `manual_pending` — 需要机构访问权限或验证码
- `failed (...)` — 自动下载失败
- `ignored` — 已知无法访问（来自 `[institution].ignored_access_dois`）

报告中还会额外保留：
- `session_restarts` — 当前 ref 在运行中经历过几次自动会话恢复
- `session_last_error` — 最近一次触发会话恢复的原始浏览器错误

**重要现实约束**：
- `download_report.csv` 在**运行正常结束时**统一写回项目目录
- 如果中途 `Ctrl+C`、强关终端或异常中断，旧 CSV 可能不反映最新状态。改看：
  - 最新 run 目录下的 `events.jsonl`
  - `<OUTPUT_DIR>/<PROJECT_NAME>/` 里已经真实落盘的文件

---

## Step 7：展示下载报告

优先顺序如下：

1. 如果本轮**正常结束**：
   读取 `<OUTPUT_DIR>/<PROJECT_NAME>/download_report.csv`，展示摘要
2. 如果本轮**中途中断**：
   不要盲信旧 `download_report.csv`
   应读取：
   - 最新 `<OUTPUT_DIR>/runs/<timestamp>-round-03/events.jsonl`
   - `<OUTPUT_DIR>/<PROJECT_NAME>/` 中已经存在的 PDF / SI 文件

正常结束时的摘要示例：

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

## Step 8：清理旧文件

如果使用 `run_ref_downloader.py`，wrapper 会在结束后自动检查 OUTPUT_DIR（注意：是 `_refs` 根目录，不是 `PROJECT_NAME` 子目录）并执行一次**窄范围清理**：

```
要清理的文件模式（仅当存在时）：
  fetch_refs.py
  fetch_refs_playwright.py
  fetch_refs_v2.py
  *.log（最后修改时间超过 7 天的）
```

**注意**：
- 只清理 OUTPUT_DIR 目录本身，不递归进子目录
- 不删除 `.bak` 文件（可能是用户手动备份）
- 不删除 `<SKILL_DIR>` 中的任何文件
- 如果是手动逐步运行三脚本，默认**不会**自动做这一步

---

## 出版商支持

详细的 DOI 前缀映射表 + 三层下载策略（specialized / generic_fallback / weak）+ 每个出版商的实现备注，见 [docs/SUPPORTED_PUBLISHERS.md](docs/SUPPORTED_PUBLISHERS.md)。

新出版商前缀遇到时，按 Step 5 描述的流程自动更新 `PUBLISHER_MAP`，并在 [CONTRIBUTING.md](CONTRIBUTING.md) 指引下补充 `download_refs.py` 中的策略条目。

---

## 常见问题

| 现象 | 处理 |
|------|------|
| `No references found` | Crossref 未收录该出版商参考列表 |
| Edge 无法启动 | 确认 Edge 已完全关闭（含后台进程），重跑 Step 6 |
| 大量 `manual_pending` | VPN/校园网未连接，或该出版商需登录；institutional SSO 配置见 `[institution]` 段 |
| 根目录 `download_report.csv` 看起来没更新 | 如果本轮中断过，请改看最新 `runs/<timestamp>/events.jsonl` 和项目目录里真实落盘的文件 |
| `validated.json` 中 `failed` 多 | Crossref API 偶发故障，重跑 Step 5（自动跳过已验证） |
| PDF 用 Zotero 找不到 DOI | 确认 `[zotero].db_path` 配置了正确路径；尝试 fitz 提取，仍失败则询问用户 |
| `WARNING: crossref.mailto is the placeholder` | 编辑 `<SKILL_DIR>/config.local.toml` 把 mailto 改成你的真实邮箱以进入 Crossref polite pool |

## See also

- [README.md](README.md) — 人类用户的安装与使用文档
- [docs/SUPPORTED_PUBLISHERS.md](docs/SUPPORTED_PUBLISHERS.md) — 出版商支持矩阵
- [CONTRIBUTING.md](CONTRIBUTING.md) — 添加新出版商 / institution SSO
- [SECURITY.md](SECURITY.md) — Edge profile cookie 风险声明
- [config.example.toml](config.example.toml) — 配置项 schema
