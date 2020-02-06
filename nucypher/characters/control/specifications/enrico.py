import click
from nucypher.cli import options
from nucypher.characters.control.specifications import fields
from nucypher.characters.control.specifications.base import BaseSchema


class EncryptMessage(BaseSchema):

    # input
    message = fields.Cleartext(
        required=True, load_only=True,
        click=click.option('--message', help="A unicode message to encrypt for a policy")
    )

    policy_encrypting_key = fields.Key(
        required=False,
        load_only=True,
        click=options.option_policy_encrypting_key())

    # output
    message_kit = fields.UmbralMessageKit(dump_only=True)
    signature = fields.String(dump_only=True) # maybe we need a signature field?
