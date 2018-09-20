import pytest_twisted
import time

import pytest
from click.testing import CliRunner
from twisted.internet import threads
from twisted.internet.error import CannotListenError

from cli.main import cli
from nucypher.characters.base import Teacher
from nucypher.config.characters import UrsulaConfiguration


@pytest_twisted.inlineCallbacks
def test_run_lone_federated_default_ursula():

    args = ['run_ursula',
            '--dev',
            '--federated-only',
            '--rest-port', '9999',  # TODO: use different port to avoid premature ConnectionError?
            ]

    runner = CliRunner()
    result = yield threads.deferToThread(runner.invoke(cli, args, catch_exceptions=False))
    # result = runner.invoke(cli, args, catch_exceptions=False)      # TODO: Handle second call to reactor.run
    alone = "WARNING - Can't learn right now: Need some nodes to start learning from."
    time.sleep(Teacher._SHORT_LEARNING_DELAY)
    assert alone in result.output
    assert result.exit_code == 0

    # Cannot start another Ursula on the same REST port
    with pytest.raises(CannotListenError):
        _result = runner.invoke(cli, args, catch_exceptions=False)


@pytest.mark.skip(reason="Handle second call to reactor.run, or multiproc")
def test_federated_ursula_with_manual_teacher_uri():
    args = ['run_ursula',
            '--dev',
            '--federated-only',
            '--rest-port', '9091',  # TODO: Test Constant?
            '--teacher-uri', 'localhost:{}'.format(UrsulaConfiguration.DEFAULT_REST_PORT)]

    # TODO: Handle second call to reactor.run
    runner = CliRunner()
    result_with_teacher = runner.invoke(cli, args, catch_exceptions=False)
    assert result_with_teacher.exit_code == 0
