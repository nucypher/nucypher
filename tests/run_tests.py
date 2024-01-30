
from pathlib import Path

import maya
import pytest


class NucypherPytestRunner:
    TEST_PATH = Path('tests') / 'cli'
    PYTEST_ARGS = ['--verbose', TEST_PATH]

    def pytest_sessionstart(self):
        print("*** Running Nucypher CLI Tests ***")
        self.start_time = maya.now()

    def pytest_sessionfinish(self):
        duration = maya.now() - self.start_time
        print("*** Nucypher Test Run Report ***")
        print("""Run Duration ... {}""".format(duration))


def run():
    pytest.main(NucypherPytestRunner.PYTEST_ARGS, plugins=[NucypherPytestRunner()])
