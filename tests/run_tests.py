"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
from pathlib import Path

import maya
import os
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
