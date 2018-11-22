"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

from ipaddress import ip_address

import click
from eth_utils import is_checksum_address


class ChecksumAddress(click.ParamType):
    name = 'checksum_address'

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


IPV4_ADDRESS = IPv4Address()
CHECKSUM_ADDRESS = ChecksumAddress()


