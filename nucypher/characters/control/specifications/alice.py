from .fields import fields
from .base import BaseSchema

class PolicyBaseSchema(BaseSchema):

    #required input fields
    bob_encrypting_key = fields.Key(required=True, load_only=True)
    bob_verifying_key = fields.Key(required=True, load_only=True)
    m = fields.Integer(required=True, load_only=True)
    n = fields.Integer(required=True, load_only=True)
    expiration = fields.DateTime(required=True, load_only=True)

    # optional input
    value = fields.Integer(load_only=True)
    first_period_reward = fields.Integer(load_only=True)
    rate = fields.Integer(load_only=True)

    #output
    policy_encrypting_key = fields.Key(dump_only=True)


class CreatePolicy(PolicyBaseSchema):

    label = fields.Label(required=True)


class GrantPolicy(PolicyBaseSchema):

    treasure_map = fields.TreasureMap(dump_only=True)
    alice_verifying_key = fields.Key(dump_only=True)
    label = fields.Label(load_only=True, required=True)


class DerivePolicyEncryptionKey(BaseSchema):

    label = fields.Label(required=True)
    policy_encrypting_key = fields.Key(dump_only=True)


class Revoke(BaseSchema):

    label = fields.Label(required=True, load_only=True)
    bob_verifying_key = fields.Key(required=True, load_only=True)

    failed_revocations = fields.Integer(dump_only=True)


class Decrypt(BaseSchema):
    label = fields.Label(required=True, load_only=True)
    message_kit = fields.MessageKit(load_only=True)
    cleartexts = fields.List(fields.Cleartext(), dump_only=True)


class PublicKeys(BaseSchema):

    alice_verifying_key = fields.Key(dump_only=True)


specifications = {
                    'create_policy': CreatePolicy(),
                    'derive_policy_encrypting_key': DerivePolicyEncryptionKey(),
                    'grant': GrantPolicy(),
                    'revoke': Revoke(),
                    'public_keys': PublicKeys(),
                    'decrypt': Decrypt(),
                    }