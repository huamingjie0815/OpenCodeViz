from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture
def fixture_project(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parent.parent / "fixtures" / "ts_app"
    target = tmp_path / "project"
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(".codeviz", "__pycache__"))
    return target
