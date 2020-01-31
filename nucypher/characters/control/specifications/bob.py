import click
from nucypher.cli import options
from nucypher.characters.control.specifications import fields
from nucypher.characters.control.specifications.base import BaseSchema


class JoinPolicy(BaseSchema):  #TODO:  this doesn't have a cli implementation

    label = fields.Label(
        load_only=True, required=True,
        click=options.option_label(required=True))
    alice_verifying_key = fields.Key(
        load_only=True, required=True,
        click=click.option(
            '--alice-verifying-key',
            help="Alice's verifying key as a hexadecimal string",
            required=True, type=click.STRING,))

    policy_encrypting_key = fields.String(dump_only=True)
    # this should be a Key Field
    # but bob.join_policy outputs {'policy_encrypting_key': 'OK'}


class Retrieve(BaseSchema):
    label = fields.Label(
        required=True, load_only=True,
        click=options.option_label(required=True))
    policy_encrypting_key = fields.Key(
        required=True,
        load_only=True,
        click=options.option_policy_encrypting_key(required=True))
    alice_verifying_key = fields.Key(
        required=True, load_only=True,
        click=click.option(
            '--alice-verifying-key',
            help="Alice's verifying key as a hexadecimal string",
            type=click.STRING,
            required=True))
    message_kit = fields.UmbralMessageKit(
        required=True, load_only=True,
        click=options.option_message_kit(required=True))

    cleartexts = fields.List(fields.Cleartext(), dump_only=True)


class PublicKeys(BaseSchema):
    bob_encrypting_key = fields.Key(dump_only=True)
    bob_verifying_key = fields.Key(dump_only=True)
