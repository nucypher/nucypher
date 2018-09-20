import pytest
from click.testing import CliRunner

from cli.main import cli


@pytest.mark.skip
def test_init():
    runner = CliRunner()
    result = runner.invoke(cli, ['simulate', 'init'], catch_exceptions=False)

    assert result.exit_code == 0
    # assert 'Debug mode is on' in result.output


@pytest.mark.skip
def test_deploy():
    runner = CliRunner()
    result = runner.invoke(cli, ['simulate', 'deploy'], catch_exceptions=False)
    assert result.exit_code == 0


@pytest.mark.skip
def test_swarm():
    runner = CliRunner()
    result = runner.invoke(cli, ['simulate', 'swarm'], catch_exceptions=False)
    assert result.exit_code == 0


@pytest.mark.skip
def test_status():
    runner = CliRunner()
    result = runner.invoke(cli, ['simulate', 'status'], catch_exceptions=False)
    assert result.exit_code == 0


@pytest.mark.skip
def test_stop():
    runner = CliRunner()
    result = runner.invoke(cli, ['simulate', 'stop'], catch_exceptions=False)
    assert result.exit_code == 0
