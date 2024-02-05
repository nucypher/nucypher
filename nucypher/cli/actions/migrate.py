from pathlib import Path

import click

from nucypher.config.migrations import MIGRATIONS
from nucypher.config.migrations.common import (
    InvalidMigration,
    WrongConfigurationVersion,
)
from nucypher.utilities.emitters import StdoutEmitter


def migrate(emitter: StdoutEmitter, config_file: Path):
    for jump, migration in MIGRATIONS.items():
        old, new = jump
        emitter.message(f"Checking migration {old} -> {new}")
        if not migration:
            emitter.echo(
                f"Migration {old} -> {new} not found.",
                color="yellow",
                verbosity=1,
            )
            continue  # no migration script
        try:
            migration(config_file)
            emitter.echo(
                f"Successfully ran migration {old} -> {new}",
                color="green",
                verbosity=1,
            )

        except WrongConfigurationVersion:
            emitter.echo(
                f"Migration {old} -> {new} not required.",
                color="yellow",
                verbosity=1,
            )
            continue  # already migrated

        except InvalidMigration as e:
            emitter.error(f"Migration {old} -> {new} failed: {str(e)}")
            raise click.Abort()

    emitter.echo("Done! ✨", color="green", verbosity=1)
