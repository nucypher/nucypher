from click.testing import CliRunner

from cli.main import cli


def test_finnegans_wake_demo():
    runner = CliRunner()
    result = runner.invoke(cli, ['simulate', 'demo', '--federated-only'], catch_exceptions=False)

    pass