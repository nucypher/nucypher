import pytest
from click.testing import CliRunner

from cli.main import cli


@pytest.mark.skip
def test_finnegans_wake_demo():
    runner = CliRunner()
    result = runner.invoke(cli, ['simulate', 'demo', '--federated-only'], catch_exceptions=False)

    assert result.exit_code == 0
