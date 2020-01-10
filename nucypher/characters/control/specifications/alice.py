from nucypher.characters.control.specifications import fields
from nucypher.characters.control.specifications.base import BaseSchema
import click
from nucypher.cli import common_options
from nucypher.cli.common_options import option_m


class PolicyBaseSchema(BaseSchema):

    bob_encrypting_key = fields.Key(
        required=True, load_only=True,
        click=click.option(
            '--bob-encrypting-key',
            help="Bob's encrypting key as a hexadecimal string"))
    bob_verifying_key = fields.Key(
        required=True, load_only=True,
        click=click.option(
            '--bob-verifying-key', help="Bob's verifying key as a hexadecimal string"))
    m = fields.M(
        required=True, load_only=True,
        click=common_options.option_m)
    n = fields.N(
        required=True, load_only=True,
        click=common_options.option_n)
    expiration = fields.DateTime(
        required=True, load_only=True,
        click=click.option(
            '--expiration',
            help="Expiration Datetime of a policy"))

    # optional input
    value = fields.Wei(
        load_only=True,
        click=click.option('--value', help="Total policy value (in Wei)"))

    # output
    policy_encrypting_key = fields.Key(dump_only=True)


class CreatePolicy(PolicyBaseSchema):

    label = fields.Label(
        required=True,
        click=common_options.option_label)


class GrantPolicy(PolicyBaseSchema):

    label = fields.Label(
        load_only=True, required=True,
        click=common_options.option_label)

    # output fields
    treasure_map = fields.TreasureMap(dump_only=True)
    alice_verifying_key = fields.Key(dump_only=True)


class DerivePolicyEncryptionKey(BaseSchema):

    label = fields.Label(
        required=True,
        click=common_options.option_label)
    policy_encrypting_key = fields.Key(dump_only=True)


class Revoke(BaseSchema):

    label = fields.Label(
        required=True, load_only=True,
        click=common_options.option_label)
    bob_verifying_key = fields.Key(
        required=True, load_only=True,
        click=click.option(
            '--bob-verifying-key', help="Bob's verifying key as a hexadecimal string"))

    failed_revocations = fields.Integer(dump_only=True)


class Decrypt(BaseSchema):
    label = fields.Label(
        required=True, load_only=True,
        click=common_options.option_label)
    message_kit = fields.UmbralMessageKit(load_only=True)
    cleartexts = fields.List(fields.Cleartext(), dump_only=True)


class PublicKeys(BaseSchema):

    alice_verifying_key = fields.Key(dump_only=True)
