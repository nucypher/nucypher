from nucypher.characters.control.specifications import fields
from nucypher.characters.control.specifications.base import BaseSchema


class JoinPolicy(BaseSchema):

    label = fields.Label(load_only=True, required=True)
    alice_verifying_key = fields.Key(load_only=True, required=True)

    policy_encrypting_key = fields.String(dump_only=True)
    # this should be a Key Field
    # but bob.join_policy outputs {'policy_encrypting_key': 'OK'}


class Retrieve(BaseSchema):
    label = fields.Label(required=True, load_only=True)
    policy_encrypting_key = fields.Key(required=True, load_only=True)
    alice_verifying_key = fields.Key(required=True, load_only=True, )
    message_kit = fields.UmbralMessageKit(required=True, load_only=True)

    cleartexts = fields.List(fields.Cleartext(), dump_only=True)


class PublicKeys(BaseSchema):
    bob_encrypting_key = fields.Key(dump_only=True)
    bob_verifying_key = fields.Key(dump_only=True)
