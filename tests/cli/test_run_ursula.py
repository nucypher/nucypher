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


import pytest
import pytest_twisted as pt
import time
from twisted.internet import threads
from twisted.internet.error import CannotListenError

from nucypher.characters.base import Learner
from nucypher.cli.main import nucypher_cli
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD, MOCK_URSULA_STARTING_PORT


@pytest.mark.skip('Results in exception "ReactorAlreadyRunning"')
@pt.inlineCallbacks
def test_run_lone_federated_default_development_ursula(click_runner):
    args = ('ursula', 'run', '--rest-port', MOCK_URSULA_STARTING_PORT, '--dev')

    result = yield threads.deferToThread(click_runner.invoke,
                                         nucypher_cli, args,
                                         catch_exceptions=False,
                                         input=INSECURE_DEVELOPMENT_PASSWORD + '\n')

    alone = "WARNING - Can't learn right now: Need some nodes to start learning from."
    time.sleep(Learner._SHORT_LEARNING_DELAY)
    assert alone in result.output
    assert result.exit_code == 0

    # Cannot start another Ursula on the same REST port
    with pytest.raises(CannotListenError):
        _result = click_runner.invoke(nucypher_cli, args, catch_exceptions=False, input=INSECURE_DEVELOPMENT_PASSWORD)
