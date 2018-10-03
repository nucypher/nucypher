import time

import pytest
import pytest_twisted
from click.testing import CliRunner
from twisted.internet import threads
from twisted.internet.error import CannotListenError

from cli.main import cli
from nucypher.characters.base import Learner
from nucypher.utilities.sandbox.constants import TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD


@pytest.mark.skip(reason="Handle second call to reactor.run, or use multiproc")
@pytest_twisted.inlineCallbacks
def test_run_lone_federated_default_ursula():

    args = ['--dev',
            '--federated-only',
            'ursula', 'run',
            '--rest-port', '9999',  # TODO: use different port to avoid premature ConnectionError with many test runs?
            ]

    runner = CliRunner()
    result = yield threads.deferToThread(runner.invoke(cli, args, catch_exceptions=False, input=TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD))
    # result = runner.invoke(cli, args, catch_exceptions=False)      # TODO: Handle second call to reactor.run
    alone = "WARNING - Can't learn right now: Need some nodes to start learning from."
    time.sleep(Learner._SHORT_LEARNING_DELAY)
    assert alone in result.output
    assert result.exit_code == 0

    # Cannot start another Ursula on the same REST port
    with pytest.raises(CannotListenError):
        _result = runner.invoke(cli, args, catch_exceptions=False, input=TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD)
