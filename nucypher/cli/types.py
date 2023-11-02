from decimal import Decimal, DecimalException
from ipaddress import ip_address
from pathlib import Path

import click
from eth_utils import to_checksum_address

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.token import TToken
from nucypher.policy.payment import PRE_PAYMENT_METHODS
from nucypher.utilities.networking import InvalidOperatorIP, validate_operator_ip


class ChecksumAddress(click.ParamType):
    name = 'checksum_address'

    def convert(self, value, param, ctx):
        try:
            value = to_checksum_address(value=value)
        except ValueError:
            self.fail("Invalid ethereum address")
        else:
            return value


class IPv4Address(click.ParamType):
    name = 'ipv4_address'

    def convert(self, value, param, ctx):
        try:
            _address = ip_address(value)
        except ValueError:
            self.fail("Invalid IP Address")
        else:
            return value


class OperatorIPAddress(IPv4Address):
    name = 'operator_ip'

    def convert(self, value, param, ctx):
        _ip = super().convert(value, param, ctx)
        try:
            validate_operator_ip(ip=_ip)
        except InvalidOperatorIP as e:
            self.fail(str(e))
        return value


class DecimalType(click.ParamType):
    name = 'decimal'

    def convert(self, value, param, ctx):
        try:
            return Decimal(value)
        except DecimalException:
            self.fail(f"'{value}' is an invalid decimal number")


class DecimalRange(DecimalType):
    name = 'decimal_range'

    def __init__(self, min=None, max=None, clamp=False):
        self.min = min
        self.max = max
        self.clamp = clamp

    def convert(self, value, param, ctx):
        rv = DecimalType.convert(self, value, param, ctx)
        if self.clamp:
            if self.min is not None and rv < self.min:
                return self.min
            if self.max is not None and rv > self.max:
                return self.max
        if self.min is not None and rv < self.min or \
           self.max is not None and rv > self.max:
            if self.min is None:
                self.fail(f'{rv} is bigger than the maximum valid value {self.max}')
            elif self.max is None:
                self.fail(f'{rv} is smaller than the minimum valid value {self.min}')
            else:
                self.fail(f'{rv} is not in the valid range of {self.min} to {self.max}')
        return rv


class NuCypherDomainName(click.ParamType):
    name = "nucypher_domain_name"

    def __init__(self, validate: bool = True):
        self.validate = bool(validate)

    def convert(self, value, param, ctx):
        if self.validate:
            domain = str(value).lower()
            if str(domain) not in domains.SUPPORTED_DOMAINS:
                self.fail(
                    f"'{value}' is not a recognized domain. Valid options are: {list(domains.SUPPORTED_DOMAINS)}"
                )
            else:
                return domain
        else:
            return value


# Ethereum
EIP55_CHECKSUM_ADDRESS = ChecksumAddress()
GWEI = DecimalRange(min=0)

__min_authorization = TToken(40_000, "T").to_tokens()  # TODO right spot for this?
MIN_AUTHORIZATION = Decimal(__min_authorization)
STAKED_TOKENS_RANGE = DecimalRange(min=__min_authorization)

# Filesystem
EXISTING_READABLE_FILE = click.Path(exists=True, dir_okay=False, file_okay=True, readable=True, path_type=Path)

# Network
NETWORK_PORT = click.IntRange(min=0, max=65535, clamp=False)
OPERATOR_IP = OperatorIPAddress()

PRE_PAYMENT_METHOD_CHOICES = click.Choice(list(PRE_PAYMENT_METHODS))
