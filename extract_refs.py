#!/usr/bin/env python3
"""
Script 1: Extract reference DOIs from a parent paper via Crossref API.

Usage:
  python extract_refs.py <parent_doi>

Example:
  python extract_refs.py 10.1021/jacs.5c05017

Output:
  {project_dir}/refs_raw.json
"""

import sys
import json
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

from _config import load_config, user_agent_from, warn_if_placeholder_mailto


API_BASE = "https://api.crossref.org/works"


def doi_to_project_name(doi: str) -> str:
    """Convert DOI to a safe directory name using the suffix after the last '/'."""
    return doi.split("/")[-1].replace(":", "_").replace("?", "_")


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


def extract_references(parent_doi: str, user_agent: str) -> dict:
    """Extract reference list from a parent paper's Crossref entry."""
    print(f"Fetching parent paper: {parent_doi}")
    parent = fetch_crossref(parent_doi, user_agent)

    if not parent:
        print("ERROR: Parent DOI not found in Crossref.")
        sys.exit(1)

    title = parent.get("title", ["(no title)"])[0]
    refs_raw = parent.get("reference", [])

    print(f"  Title: {title}")
    print(f"  References found: {len(refs_raw)}")

    if not refs_raw:
        print("ERROR: No references found. The publisher may not deposit reference metadata.")
        sys.exit(1)

    references = []
    no_doi_count = 0
    for i, ref in enumerate(refs_raw, 1):
        doi = ref.get("DOI")
        if not doi:
            no_doi_count += 1
            print(f"  WARNING: ref [{i}] has no DOI — {ref.get('unstructured', '(no info)')[:80]}")
        references.append({
            "id": i,
            "doi": doi,
            "key": ref.get("key", ""),
            "unstructured": ref.get("unstructured", ""),
            "author": ref.get("author", ""),
            "year": ref.get("year", ""),
            "journal": ref.get("journal-title", ""),
            "volume": ref.get("volume", ""),
            "first_page": ref.get("first-page", ""),
        })

    print(f"\n  Summary: {len(references)} refs total, "
          f"{len(references) - no_doi_count} with DOI, {no_doi_count} without DOI")

    return {
        "parent_doi": parent_doi,
        "parent_title": title,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(references),
        "with_doi": len(references) - no_doi_count,
        "without_doi": no_doi_count,
        "references": references,
    }


def main():
    parser = argparse.ArgumentParser(description="Extract reference DOIs via Crossref.")
    parser.add_argument("parent_doi", help="Parent paper DOI (e.g. 10.1021/jacs.5c05017)")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Non-interactive: overwrite refs_raw.json without asking.",
    )
    args = parser.parse_args()

    cfg = load_config()
    warn_if_placeholder_mailto(cfg)
    user_agent = user_agent_from(cfg)

    parent_doi = args.parent_doi.strip()
    project_name = doi_to_project_name(parent_doi)
    project_dir = Path(project_name)
    output_path = project_dir / "refs_raw.json"

    # Incremental: check if output already exists
    if output_path.exists():
        if args.yes:
            print(f"WARNING: {output_path} exists; --yes given, overwriting.")
        elif not sys.stdin.isatty():
            print(
                f"ERROR: {output_path} exists and stdin is not a TTY; "
                "refusing to overwrite. Pass --yes to force."
            )
            sys.exit(2)
        else:
            print(f"WARNING: {output_path} already exists.")
            answer = input("  Overwrite? [y/N] ").strip().lower()
            if answer != "y":
                print("Aborted.")
                sys.exit(0)

    # Create project directory
    project_dir.mkdir(exist_ok=True)
    print(f"Project directory: {project_dir}/\n")

    # Extract
    result = extract_references(parent_doi, user_agent)

    # Save
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Saved to {output_path}")
    print(f"  Next step: python validate_refs.py {project_name}")


if __name__ == "__main__":
    main()
