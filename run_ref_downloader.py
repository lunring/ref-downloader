#!/usr/bin/env python3
"""
Single-entry wrapper for the ref-downloader skill.

Primary use:
  python run_ref_downloader.py <doi_or_pdf_path> [--output-dir PATH]

Behavior:
- DOI input: defaults OUTPUT_DIR to "<cwd>/<project_name>_refs" unless overridden
- PDF input: defaults OUTPUT_DIR to "<pdf_dir>/<pdf_stem>_refs" unless overridden
- Runs extract_refs.py -> validate_refs.py -> download_refs.py in sequence
- Performs a narrow cleanup pass in OUTPUT_DIR root after the pipeline finishes
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from _config import load_config, warn_if_placeholder_mailto


SKILL_DIR = Path(__file__).resolve().parent
LEGACY_ROOT_FILENAMES = (
    "fetch_refs.py",
    "fetch_refs_playwright.py",
    "fetch_refs_v2.py",
)
SEVEN_DAYS_SECONDS = 7 * 24 * 60 * 60
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+")


def looks_like_doi(value: str) -> bool:
    return value.strip().startswith("10.")


def doi_to_project_name(doi: str) -> str:
    suffix = doi.split("/")[-1]
    return re.sub(r'[<>:"/\\|?*]+', "_", suffix).strip(" .") or "unnamed_project"


def resolve_doi_from_zotero(pdf_path: Path, zotero_db: Path) -> str:
    if not zotero_db or not zotero_db.exists():
        return ""
    tmp_db = Path(tempfile.mktemp(suffix=".sqlite"))
    try:
        shutil.copy2(zotero_db, tmp_db)
        conn = sqlite3.connect(tmp_db)
        try:
            row = conn.execute(
                """
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
                """,
                (f"%{pdf_path.name}%",),
            ).fetchone()
        finally:
            conn.close()
        return (row[0] or "").strip() if row else ""
    except Exception:
        return ""
    finally:
        try:
            tmp_db.unlink(missing_ok=True)
        except Exception:
            pass


def resolve_doi_from_pdf_text(pdf_path: Path) -> str:
    try:
        import fitz  # type: ignore
    except Exception:
        return ""
    try:
        doc = fitz.open(pdf_path)
        try:
            text = "".join(doc[i].get_text() for i in range(min(3, len(doc))))
        finally:
            doc.close()
        match = DOI_RE.search(text)
        return match.group(0).rstrip(".,;)") if match else ""
    except Exception:
        return ""


def resolve_input(input_value: str, output_dir_arg: str, zotero_db: Path) -> tuple[str, Path, str]:
    raw = input_value.strip()
    if looks_like_doi(raw):
        doi = raw
        project_name = doi_to_project_name(doi)
        output_dir = Path(output_dir_arg).expanduser().resolve() if output_dir_arg else (Path.cwd() / f"{project_name}_refs")
        return doi, output_dir, project_name

    pdf_path = Path(raw).expanduser().resolve()
    if not pdf_path.exists() or pdf_path.suffix.lower() != ".pdf":
        raise SystemExit(f"ERROR: Input is neither a DOI nor an existing PDF path:\n  {raw}")

    doi = resolve_doi_from_zotero(pdf_path, zotero_db) or resolve_doi_from_pdf_text(pdf_path)
    if not doi:
        raise SystemExit(
            "ERROR: Unable to resolve DOI automatically from the PDF.\n"
            "Please rerun with a DOI directly, or provide a PDF that exists in Zotero with DOI metadata."
        )

    project_name = doi_to_project_name(doi)
    output_dir = Path(output_dir_arg).expanduser().resolve() if output_dir_arg else (pdf_path.parent / f"{pdf_path.stem}_refs")
    return doi, output_dir, project_name


def run_step(script_name: str, args: list[str], cwd: Path) -> None:
    cmd = [sys.executable, str(SKILL_DIR / script_name), *args]
    print(f"\n>>> Running: {' '.join(cmd)}")
    print(f"    cwd: {cwd}")
    subprocess.run(cmd, cwd=str(cwd), check=True)


def cleanup_output_dir_root(output_dir: Path) -> None:
    for name in LEGACY_ROOT_FILENAMES:
        target = output_dir / name
        if target.exists() and target.is_file():
            target.unlink()

    now = time.time()
    for path in output_dir.glob("*.log"):
        try:
            if not path.is_file():
                continue
            age = now - path.stat().st_mtime
            if age > SEVEN_DAYS_SECONDS:
                path.unlink()
        except Exception:
            continue


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
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Forward to download_refs.py: skip the 'press Enter to confirm Edge is closed' prompt and use shorter challenge wait. Pairs naturally with --yes for fully unattended runs.",
    )
    return parser.parse_args()


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

    extract_extra_args = ["--yes"] if args.yes else []
    download_extra_args = ["--auto"] if args.auto else []

    if raw_path.exists():
        print(f"\n>>> Reusing existing raw refs: {raw_path}")
    else:
        run_step("extract_refs.py", [doi, *extract_extra_args], output_dir)

    run_step("validate_refs.py", [project_name], output_dir)
    run_step("download_refs.py", [project_name, *download_extra_args], output_dir)

    cleanup_output_dir_root(output_dir)
    print("\n✓ Wrapper finished.")
    print(f"  Project dir : {project_dir}")
    print(f"  Run artifacts: {output_dir / 'runs'}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        raise SystemExit(e.returncode)
