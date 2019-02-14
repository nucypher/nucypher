import shutil

import click
from twisted.logger import Logger

from nucypher.config.constants import DEFAULT_CONFIG_ROOT


DESTRUCTION = '''
*Permanently and irreversibly delete all* nucypher files including
    - Private and Public Keys
    - Known Nodes
    - TLS certificates
    - Node Configurations
    - Log Files

Delete {}?'''


LOG = Logger('cli.actions')


def destroy_system_configuration(config_class,
                                 config_file=None,
                                 network=None,
                                 config_root=None,
                                 force=False,
                                 log=LOG):

    try:
        character_config = config_class.from_configuration_file(filepath=config_file, domains={network})

    except FileNotFoundError:
        config_root = config_root or DEFAULT_CONFIG_ROOT
        config_file_location = config_file or config_class.DEFAULT_CONFIG_FILE_LOCATION

        if not force:
            message = "No configuration file found at {}; \n" \
                      "Destroy top-level configuration directory: {}?".format(config_file_location, config_root)
            click.confirm(message, abort=True)  # ABORT

        shutil.rmtree(config_root, ignore_errors=False)

    else:
        if not force:
            click.confirm(DESTRUCTION.format(character_config.config_root), abort=True)

        try:
            character_config.destroy(force=force)
        except FileNotFoundError:
            message = 'Failed: No nucypher files found at {}'.format(character_config.config_root)
            click.secho(message, fg='red')
            log.debug(message)
            raise click.Abort()
        else:
            message = "Deleted configuration files at {}".format(character_config.config_root)
            click.secho(message, fg='green')
            log.debug(message)
