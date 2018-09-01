from click.testing import CliRunner

from nucypher_cli.main import cli


def test_run_ursula():
    runner = CliRunner()
    result = runner.invoke(cli, ['run_ursula'], catch_exceptions=False)
