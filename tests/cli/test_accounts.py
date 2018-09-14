from click.testing import CliRunner

from cli.main import cli


def test_list():
    runner = CliRunner()
    result = runner.invoke(cli, ['accounts', 'list'], catch_exceptions=False)


def test_lock():
    runner = CliRunner()
    result = runner.invoke(cli, ['accounts', 'lock'], catch_exceptions=False)


def test_unlock():
    runner = CliRunner()
    result = runner.invoke(cli, ['accounts', 'unlock'], catch_exceptions=False)


def test_balance():
    runner = CliRunner()
    result = runner.invoke(cli, ['accounts', 'balance'], catch_exceptions=False)
