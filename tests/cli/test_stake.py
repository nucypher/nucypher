import pytest
from click.testing import CliRunner

from cli.main import cli


@pytest.mark.skip
def test_stake_init():
    runner = CliRunner()
    result = runner.invoke(cli, ['stake', 'init'], catch_exceptions=False)


@pytest.mark.skip
def test_stake_info():
    runner = CliRunner()
    result = runner.invoke(cli, ['stake', 'info'], catch_exceptions=False)


@pytest.mark.skip
def test_stake_confirm():
    runner = CliRunner()
    result = runner.invoke(cli, ['stake', 'confirm-activity'], catch_exceptions=False)
