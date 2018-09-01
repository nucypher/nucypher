from click.testing import CliRunner

from nucypher_cli.main import cli


def test_stake_init():
    runner = CliRunner()
    result = runner.invoke(cli, ['stake', 'init'], catch_exceptions=False)


def test_stake_resume():
    runner = CliRunner()
    result = runner.invoke(cli, ['stake', 'resume'], catch_exceptions=False)


def test_stake_info():
    runner = CliRunner()
    result = runner.invoke(cli, ['stake', 'info'], catch_exceptions=False)


def test_stake_list():
    runner = CliRunner()
    result = runner.invoke(cli, ['stake', 'list'], catch_exceptions=False)


def test_stake_confirm():
    runner = CliRunner()
    result = runner.invoke(cli, ['stake', 'confirm-activity'], catch_exceptions=False)


def test_stake_divide():
    runner = CliRunner()
    result = runner.invoke(cli, ['stake', 'divide-stake'], catch_exceptions=False)
