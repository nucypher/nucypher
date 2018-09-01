from click.testing import CliRunner

from nucypher_cli.main import cli


def test_init():
    runner = CliRunner()
    result = runner.invoke(cli, ['config', 'init'], catch_exceptions=False)
    assert result.exit_code == 0


def test_validate():
    runner = CliRunner()
    result = runner.invoke(cli, ['config', 'validate'], catch_exceptions=False)
    assert result.exit_code == 0
