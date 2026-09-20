from pathlib import Path

import pytest

from homeflow.io_utils import load_inventory


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def inventory():
    return load_inventory(ROOT / "data" / "sample_home.yaml")
