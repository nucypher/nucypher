from nucypher.cli.main import nucypher_cli
from nucypher.utilities.sandbox.constants import MOCK_URSULA_STARTING_PORT


def test_alice_control_starts(click_runner):

    init_args = ('alice', 'start-controller', '--rest-port',
                 MOCK_URSULA_STARTING_PORT, '-x')
    result = click_runner.invoke(nucypher_cli, init_args)
    assert result.exit_code == 0
    assert 'Alice character controller starting' in result.output
