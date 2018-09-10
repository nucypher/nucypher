import os
from tempfile import NamedTemporaryFile

from click.testing import CliRunner

from cli.main import cli
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, DEFAULT_INI_FILEPATH, APP_DIRS, PROJECT_ROOT


def test_config():
    runner = CliRunner()

    result = runner.invoke(cli, ['config', 'init', '--dev'], input='Y', catch_exceptions=False)
    assert DEFAULT_CONFIG_ROOT in result.output
    assert result.exit_code == 0

    assert os.path.isfile(DEFAULT_INI_FILEPATH)
    with open(DEFAULT_INI_FILEPATH, 'r') as ini_file:
        assert ini_file.read()
        config_payload = ini_file.read()
        assert '[nucypher]' in config_payload

    result = runner.invoke(cli, ['config', 'destroy'], input='Y', catch_exceptions=False)
    assert DEFAULT_CONFIG_ROOT in result.output
    assert result.exit_code == 0
    assert not os.path.isfile(DEFAULT_INI_FILEPATH)


def test_validate():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ['config', 'validate'], catch_exceptions=False)
        # assert 'Valid'.casefold() in result.output
        assert result.exit_code == 0

