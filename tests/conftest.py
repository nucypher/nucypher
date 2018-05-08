from cryptography.hazmat.primitives.asymmetric import ec
from umbral.config import set_default_curve
from .eth_fixtures import *
from .fixtures import *

set_default_curve(ec.SECP256K1())


import pytest
def pytest_addoption(parser):
    parser.addoption("--runslow", action="store_true",
                     default=False, help="run slow tests")

def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow"):
        # --runslow given in cli: do not skip slow tests
        return
    skip_slow = pytest.mark.skip(reason="need --runslow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)