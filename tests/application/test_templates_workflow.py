"""Native object creation support through published workflow output."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def short_template_path():
    root = Path(__file__).resolve().parents[2] / "tmp" / "tc"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix="") as path:
        yield Path(path)
