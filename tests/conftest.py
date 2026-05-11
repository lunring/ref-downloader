"""pytest configuration: put the repo root on sys.path so tests can import the
top-level modules (`_config`, `extract_refs`, `validate_refs`,
`run_ref_downloader`) without an install step.

`download_refs.py` is intentionally NOT imported here — its module-level
`from playwright.async_api import ...` would force `playwright` as a hard
test dependency. The offline unit tests in this directory cover the four
modules listed above; browser-driven behavior lives in the manual smoke
recipe in `tests/README.md`.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
