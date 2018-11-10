"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import time

import pytest
import pytest_twisted
from click.testing import CliRunner
from twisted.internet import threads
from twisted.internet.error import CannotListenError

from nucypher.cli import cli
from nucypher.characters.base import Learner
from nucypher.utilities.sandbox.constants import TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD


@pytest.mark.skip()
@pytest_twisted.inlineCallbacks
def test_run_lone_federated_default_ursula():

    args = ['--dev',
            '--federated-only',
            'ursula', 'run',
            '--rest-port', '9999',  # TODO: use different port to avoid premature ConnectionError with many test runs?
            '--no-reactor'
            ]

    runner = CliRunner()
    result = yield threads.deferToThread(runner.invoke, cli, args, catch_exceptions=False, input=TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD+'\n')

    alone = "WARNING - Can't learn right now: Need some nodes to start learning from."
    time.sleep(Learner._SHORT_LEARNING_DELAY)
    assert alone in result.output
    assert result.exit_code == 0

    # Cannot start another Ursula on the same REST port
    with pytest.raises(CannotListenError):
        _result = runner.invoke(cli, args, catch_exceptions=False, input=TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD)
