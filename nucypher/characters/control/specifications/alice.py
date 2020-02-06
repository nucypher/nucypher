import click
from marshmallow import validates_schema

from nucypher.characters.control.specifications.exceptions import (
    InvalidInputData, InvalidArgumentCombo)
from nucypher.characters.control.specifications import fields
from nucypher.characters.control.specifications.base import BaseSchema
from nucypher.cli import options, types


class PolicyBaseSchema(BaseSchema):

    bob_encrypting_key = fields.Key(
        required=True, load_only=True,
        click=click.option(
            '--bob-encrypting-key',
            help="Bob's encrypting key as a hexadecimal string",
            type=click.STRING, required=True,))
    bob_verifying_key = fields.Key(
        required=True, load_only=True,
        click=click.option(
            '--bob-verifying-key', help="Bob's verifying key as a hexadecimal string",
            type=click.STRING, required=True))
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
            type=click.STRING))

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
        click=options.option_label(required=True))

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
