"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import click

from nucypher.cli.commands import (
    alice,
    bob,
    dao,
    enrico,
    felix,
    multisig,
    stake,
    status,
    ursula,
    worklock,
    cloudworkers,
    contacts
)
from nucypher.cli.painting.help import echo_version, echo_config_root_path, echo_logging_root_path


@click.group()
@click.option('--version', help="Echo the CLI version",
              is_flag=True, callback=echo_version, expose_value=False, is_eager=True)
@click.option('--config-path', help="Echo the configuration root directory path",
              is_flag=True, callback=echo_config_root_path, expose_value=False, is_eager=True)
@click.option('--logging-path', help="Echo the logging root directory path",
              is_flag=True, callback=echo_logging_root_path, expose_value=False, is_eager=True)
def nucypher_cli():
    """Top level command for all things nucypher."""


#
# Character CLI Entry Points (Fan Out Input)
#
#
#             ursula
#               |
#               |
#               |
#               |
# stdin --> cli.main --- alice
#               | \
#               |  \
#               |  bob
#               |
#             enrico
#
#
#
# New character CLI modules must be added here
# for the entry point to be attached to the nucypher base command.
#
# Inversely, commenting out an entry point here will disable it.
#

ENTRY_POINTS = (

    # Characters & Actors
    alice.alice,        # Author of Policies
    bob.bob,            # Builder of Capsules
    enrico.enrico,      # Encryptor of Data
    ursula.ursula,      # Untrusted Re-Encryption Proxy
    stake.stake,        # Stake Management
    worklock.worklock,  # WorkLock

    # Utility Commands
    status.status,      # Network Status
    dao.dao,            # NuCypher DAO
    multisig.multisig,  # MultiSig operations
    felix.felix,        # Faucet
    cloudworkers.cloudworkers,  # Remote Worker node management
    contacts.contacts,          # Character "card" management
)

for entry_point in ENTRY_POINTS:
    nucypher_cli.add_command(entry_point)
