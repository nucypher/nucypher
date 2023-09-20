import shutil
from pathlib import Path

import pytest

import tests
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.migrations import MIGRATIONS
from nucypher.config.migrations.common import WrongConfigurationVersion


def _copy_config_file(src_test_file_name, dst_filepath):
    src_filepath = (
        Path(tests.__file__).parent
        / "integration"
        / "config"
        / "data"
        / src_test_file_name
    )
    shutil.copy(src=src_filepath, dst=dst_filepath)


def _do_migration(config_file: Path):
    for jump, migration in MIGRATIONS.items():
        if not migration:
            continue  # no migration script
        try:
            migration(config_file)
        except WrongConfigurationVersion:
            continue


@pytest.fixture(scope="function")
def ursula_v4_config_filepath(tempfile_path):
    # v4 is the latest public release (from v6.1.0)
    _copy_config_file("ursula_v4.json", tempfile_path)

    return tempfile_path


@pytest.mark.usefixtures("test_registry_source_manager")
def test_migrate_v4_to_latest(ursula_v4_config_filepath):
    _do_migration(config_file=ursula_v4_config_filepath)

    # file changed in place
    migrated_ursula_config_filepath = ursula_v4_config_filepath
    ursula_config = UrsulaConfiguration.from_configuration_file(
        migrated_ursula_config_filepath, dev_mode=True
    )

    # successfully produce an ursula based on latest config
    _ = ursula_config.produce()
