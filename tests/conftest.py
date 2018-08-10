"""Set default curve for tests"""

from umbral.config import set_default_curve
from umbral.curve import SECP256K1

"""NOTICE:  Depends on fixture modules; do not delete"""
from .fixtures import *

"""Pytest configuration"""
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
