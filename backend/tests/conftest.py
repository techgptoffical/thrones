"""Unit tests run against a throwaway data directory, never the user's database."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="thrones_test_", dir=os.environ.get("THRONES_TEST_TMP")))
os.environ["THRONES_DATA"] = str(_TMP / "data")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from thrones import db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    db.close()
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db.config.DB_PATH) + suffix)
        if p.exists():
            p.unlink()
    yield
    db.close()
