import pytest
from click.testing import CliRunner

from cli.main import cli


@pytest.mark.skip
def test_list():
    runner = CliRunner()
    result = runner.invoke(cli, ['accounts', 'list'], catch_exceptions=False)
    assert result.exit_code == 0


@pytest.mark.skip
def test_balance():
    runner = CliRunner()
    result = runner.invoke(cli, ['accounts', 'balance'], catch_exceptions=False)
    assert result.exit_code == 0
