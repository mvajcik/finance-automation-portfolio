"""pytest: `tmpdir` = pathlib.Path (testy s ním pracujú ako s Path) a dáta vyrobené generátorom pred testami."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def tmpdir(tmp_path):
    return tmp_path


def pytest_sessionstart(session):
    data = ROOT / "profiles" / "papiernictvo2" / "data" / "clean"
    if not data.is_dir():
        subprocess.run([sys.executable, str(ROOT / "tools" / "gen_papiernictvo2.py")], check=True)
