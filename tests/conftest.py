"""Set default curve for tests"""

"""NOTICE:  Depends on fixture modules; do not delete"""
from .fixtures import *


"""Pytest configuration"""
import pytest


def pytest_addoption(parser):
    parser.addoption("--runslow",
                     action="store_true",
                     default=False,
                     help="run tests even if they are marked as slow")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow"):
        # --runslow given in cli: do not skip slow tests
        return
    skip_slow = pytest.mark.skip(reason="need --runslow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
