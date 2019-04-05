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

from ipaddress import ip_address

import click
from eth_utils import is_checksum_address

from nucypher.blockchain.eth.constants import (
    MIN_ALLOWED_LOCKED,
    MAX_MINTING_PERIODS,
    MIN_LOCKED_PERIODS,
    MAX_ALLOWED_LOCKED
)
from nucypher.blockchain.eth.token import NU


class ChecksumAddress(click.ParamType):
    name = 'checksum_public_address'

    def convert(self, value, param, ctx):
        if is_checksum_address(value):
            return value
        self.fail('{} is not a valid EIP-55 checksum address'.format(value, param, ctx))


class IPv4Address(click.ParamType):
    name = 'ipv4_address'

    def convert(self, value, param, ctx):
        try:
            _address = ip_address(value)
        except ValueError as e:
            self.fail(str(e))
        else:
            return value


# Staking
STAKE_DURATION = click.IntRange(min=MIN_LOCKED_PERIODS, max=MAX_MINTING_PERIODS, clamp=False)
STAKE_EXTENSION = click.IntRange(min=1, max=MAX_MINTING_PERIODS, clamp=False)
STAKE_VALUE = click.IntRange(min=NU(MIN_ALLOWED_LOCKED, 'NuNit').to_tokens(),
                             max=NU(MAX_ALLOWED_LOCKED, 'NuNit').to_tokens(), clamp=False)

# Filesystem
EXISTING_WRITABLE_DIRECTORY = click.Path(exists=True, dir_okay=True, file_okay=False, writable=True)
EXISTING_READABLE_FILE = click.Path(exists=True, dir_okay=False, file_okay=True, readable=True)

# Network
NETWORK_PORT = click.IntRange(min=0, max=65535, clamp=False)
IPV4_ADDRESS = IPv4Address()
EIP55_CHECKSUM_ADDRESS = ChecksumAddress()
