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
from marshmallow import validates_schema

from nucypher.characters.control.specifications import fields
from nucypher.characters.control.specifications.base import BaseSchema
from nucypher.characters.control.specifications.exceptions import InvalidArgumentCombo
from nucypher.cli import options, types


class PolicyBaseSchema(BaseSchema):

    bob_encrypting_key = fields.Key(
        required=True, load_only=True,
        click=click.option(
            '--bob-encrypting-key',
            '-bek',
            help="Bob's encrypting key as a hexadecimal string",
            type=click.STRING, required=False))
    bob_verifying_key = fields.Key(
        required=True, load_only=True,
        click=click.option(
            '--bob-verifying-key',
            '-bvk',
            help="Bob's verifying key as a hexadecimal string",
            type=click.STRING, required=False))
    m = fields.M(
        required=True, load_only=True,
        click=options.option_m)
    n = fields.N(
        required=True, load_only=True,
        click=options.option_n)
    expiration = fields.DateTime(
        required=True, load_only=True,
        click=click.option(
            '--expiration',
            help="Expiration Datetime of a policy",
            type=click.DateTime())
    )

    # optional input
    value = fields.Wei(
        load_only=True,
        click=click.option('--value', help="Total policy value (in Wei)", type=types.WEI))

    rate = fields.Wei(
        load_only=True,
        required=False,
        click=options.option_rate
    )

    # output
    policy_encrypting_key = fields.Key(dump_only=True)

    @validates_schema
    def check_valid_n_and_m(self, data, **kwargs):
        # ensure that n is greater than or equal to m
        if not (0 < data['m'] <= data['n']):
            raise InvalidArgumentCombo(f"N and M must satisfy 0 < M ≤ N")

    @validates_schema
    def check_rate_or_value_not_both(self, data, **kwargs):

        if (data.get('rate') is not None) and (data.get('value') is not None):
            raise InvalidArgumentCombo("Choose either rate (per period in duration) OR value (total for duration)")

        # TODO: decide if we should inject config defaults before this validation
        # if not (data.get('rate', 0) ^ data.get('value', 0)):
            # raise InvalidArgumentCombo("Either rate or value must be greater than zero.")


class CreatePolicy(PolicyBaseSchema):

    label = fields.Label(
        required=True,
        click=options.option_label(required=True))


class GrantPolicy(PolicyBaseSchema):

    label = fields.Label(
        load_only=True, required=True,
        click=options.option_label(required=False))

    # output fields
    treasure_map = fields.TreasureMap(dump_only=True)
    alice_verifying_key = fields.Key(dump_only=True)


class DerivePolicyEncryptionKey(BaseSchema):

    label = fields.Label(
        required=True,
        click=options.option_label(required=True))

    # output
    policy_encrypting_key = fields.Key(dump_only=True)


class Revoke(BaseSchema):

    label = fields.Label(
        required=True, load_only=True,
        click=options.option_label(required=True))
    bob_verifying_key = fields.Key(
        required=True, load_only=True,
        click=click.option(
            '--bob-verifying-key',
            '-bvk',
            help="Bob's verifying key as a hexadecimal string", type=click.STRING,
            required=True))

    # output
    failed_revocations = fields.Integer(dump_only=True)


class Decrypt(BaseSchema):
    label = fields.Label(
        required=True, load_only=True,
        click=options.option_label(required=True))
    message_kit = fields.UmbralMessageKit(
        load_only=True,
        click=options.option_message_kit(required=True))

    # output
    cleartexts = fields.List(fields.Cleartext(), dump_only=True)


class PublicKeys(BaseSchema):

    alice_verifying_key = fields.Key(dump_only=True)
