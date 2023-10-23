import click

from nucypher.cli.literature import CHARACTER_DESTRUCTION
from nucypher.config.base import CharacterConfiguration


def confirm_destroy_configuration(config: CharacterConfiguration) -> bool:
    """Interactively confirm destruction of nucypher configuration files"""
    # TODO: This is a workaround for ursula - needs follow up
    confirmation = CHARACTER_DESTRUCTION.format(name=config.NAME,
                                                root=config.config_root,
                                                keystore=config.keystore_dir,
                                                config=config.filepath)
    click.confirm(confirmation, abort=True)
    return True

