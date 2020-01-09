from nucypher.characters.control.specifications import fields
from nucypher.characters.control.specifications.base import BaseSchema


class PolicyBaseSchema(BaseSchema):

    bob_encrypting_key = fields.Key(
        required=True, load_only=True,
        click=fields.click(
            '--bob-encrypting-key',
            help="Bob's encrypting key as a hexadecimal string"))
    bob_verifying_key = fields.Key(
        required=True, load_only=True,
        click=fields.click(
            '--bob-verifying-key',
            help="Bob's verifying key as a hexadecimal string"))
    m = fields.M(
        required=True, load_only=True,
        click=fields.click(
            '--m', help="M-Threshold KFrags"))
    n = fields.N(
        required=True, load_only=True,
        click=fields.click(
            '--n', help="N-Total KFrags"))
    expiration = fields.DateTime(
        required=True, load_only=True,
        click=fields.click(
            '--expiration', help="Expiration Datetime of a policy"))

    # optional input
    value = fields.Wei(
        load_only=True,
        click=fields.click('--value', help="Total policy value (in Wei)"))
    rate = fields.Wei(
        load_only=True,
        click=fields.click('--rate', help="Policy value (in Wei) per period"))

    # output
    policy_encrypting_key = fields.Key(dump_only=True)


class CreatePolicy(PolicyBaseSchema):

    label = fields.Label(
        required=True,
        click=fields.click(
            '--label', help="The label for a policy"))


class GrantPolicy(PolicyBaseSchema):

    label = fields.Label(
        load_only=True, required=True,
        click=fields.click(
            '--label', help="The label for a policy"))

    # output fields
    treasure_map = fields.TreasureMap(dump_only=True)
    alice_verifying_key = fields.Key(dump_only=True)


class DerivePolicyEncryptionKey(BaseSchema):

    label = fields.Label(required=True)
    policy_encrypting_key = fields.Key(dump_only=True)


class Revoke(BaseSchema):

    label = fields.Label(required=True, load_only=True)
    bob_verifying_key = fields.Key(required=True, load_only=True)

    failed_revocations = fields.Integer(dump_only=True)


class Decrypt(BaseSchema):
    label = fields.Label(required=True, load_only=True)
    message_kit = fields.UmbralMessageKit(load_only=True)
    cleartexts = fields.List(fields.Cleartext(), dump_only=True)


class PublicKeys(BaseSchema):

    alice_verifying_key = fields.Key(dump_only=True)


grant = GrantPolicy()
