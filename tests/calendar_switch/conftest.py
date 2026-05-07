"""Pytest import setup for the calendar switch study tests."""
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
IMPORT_PATHS = (
    REPO_ROOT / "calendar_scheduler" / "python",
    REPO_ROOT / "workloads" / "calendar_study",
    REPO_ROOT / "scripts",
)


for import_path in reversed(IMPORT_PATHS):
    absolute_path = str(import_path.resolve())
    if absolute_path not in sys.path:
        sys.path.insert(0, absolute_path)
