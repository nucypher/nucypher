from click.testing import CliRunner

from cli.main import cli


def test_list():
    runner = CliRunner()
    result = runner.invoke(cli, ['accounts', 'list'], catch_exceptions=False)
    assert result.exit_code == 0


def test_balance():
    runner = CliRunner()
    result = runner.invoke(cli, ['accounts', 'balance'], catch_exceptions=False)
    assert result.exit_code == 0
