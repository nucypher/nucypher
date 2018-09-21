from click.testing import CliRunner

from cli.main import cli


def test_help_message():
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'], catch_exceptions=False)

    assert result.exit_code == 0
    assert 'Usage: cli [OPTIONS] COMMAND [ARGS]' in result.output, 'Missing or invalid help text was produced.'
