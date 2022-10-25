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

from nucypher.characters.control.specifications import fields as character_fields
from nucypher.control.specifications import fields as base_fields
from nucypher.control.specifications.base import BaseSchema
from nucypher.control.specifications.exceptions import InvalidArgumentCombo
from nucypher.cli import options, types


class PolicyBaseSchema(BaseSchema):

    bob_encrypting_key = character_fields.Key(required=True, load_only=True)
    bob_verifying_key = character_fields.Key(required=True, load_only=True)
    threshold = base_fields.PositiveInteger(required=True, load_only=True)
    shares = base_fields.PositiveInteger(required=True, load_only=True)
    expiration = character_fields.DateTime(required=True, load_only=True)

    # optional input
    value = character_fields.Wei(load_only=True)
    rate = character_fields.Wei(load_only=True, required=False)

    # output
    policy_encrypting_key = character_fields.Key(dump_only=True)

    @validates_schema
    def check_valid_n_and_m(self, data, **kwargs):
        # ensure that n is greater than or equal to m
        if not (0 < data['threshold'] <= data['shares']):
            raise InvalidArgumentCombo(f"`shares` and `threshold` must satisfy 0 < threshold ≤ shares")

    @validates_schema
    def check_rate_or_value_not_both(self, data, **kwargs):

        if (data.get('rate') is not None) and (data.get('value') is not None):
            raise InvalidArgumentCombo("Choose either rate (per period in duration) OR value (total for duration)")

        # TODO: decide if we should inject config defaults before this validation
        # if not (data.get('rate', 0) ^ data.get('value', 0)):
            # raise InvalidArgumentCombo("Either rate or value must be greater than zero.")


class CreatePolicy(PolicyBaseSchema):
    label = character_fields.Label(required=True)


class GrantPolicy(PolicyBaseSchema):
    label = character_fields.Label(load_only=True, required=True)

    # output fields
    # treasure map only used for serialization so no need to provide federated/non-federated context
    treasure_map = character_fields.EncryptedTreasureMap(dump_only=True)
    alice_verifying_key = character_fields.Key(dump_only=True)


class DerivePolicyEncryptionKey(BaseSchema):
    label = character_fields.Label(required=True)

    # output
    policy_encrypting_key = character_fields.Key(dump_only=True)


class Revoke(BaseSchema):
    label = character_fields.Label(required=True, load_only=True)
    bob_verifying_key = character_fields.Key(required=True, load_only=True)

    # output
    failed_revocations = base_fields.Integer(dump_only=True)


class Decrypt(BaseSchema):
    label = character_fields.Label(required=True, load_only=True)
    message_kit = character_fields.MessageKit(load_only=True)

    # output
    cleartexts = base_fields.List(character_fields.Cleartext(), dump_only=True)


class PublicKeys(BaseSchema):

    alice_verifying_key = character_fields.Key(dump_only=True)
