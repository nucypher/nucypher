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

from base64 import b64encode

import pytest

from nucypher.characters.control.specifications.fields import TreasureMap
from nucypher.control.specifications.exceptions import InvalidInputData
from nucypher.crypto.powers import DecryptingPower
from nucypher.utilities.porter.control.specifications.porter_schema import AlicePublishTreasureMap


def test_alice_publish_treasure_map_schema_blockchain_context_default(enacted_blockchain_policy, blockchain_bob):
    alice_publish_treasure_map_schema = AlicePublishTreasureMap()  # default is decentralized
    run_publish_treasuremap_schema_tests(alice_publish_treasure_map_schema=alice_publish_treasure_map_schema,
                                         enacted_blockchain_policy=enacted_blockchain_policy,
                                         blockchain_bob=blockchain_bob)


def test_alice_publish_treasure_map_schema_blockchain_context_set_false(enacted_blockchain_policy, blockchain_bob):
    # since non-federated, schema's context doesn't have to be set, but set it anyway to ensure that setting to
    # False still works as expected.
    alice_publish_treasure_map_schema = AlicePublishTreasureMap()  # default is decentralized
    alice_publish_treasure_map_schema.context[TreasureMap.IS_FEDERATED_CONTEXT_KEY] = False
    run_publish_treasuremap_schema_tests(alice_publish_treasure_map_schema=alice_publish_treasure_map_schema,
                                         enacted_blockchain_policy=enacted_blockchain_policy,
                                         blockchain_bob=blockchain_bob)


def run_publish_treasuremap_schema_tests(alice_publish_treasure_map_schema, enacted_blockchain_policy, blockchain_bob):
    # no args
    with pytest.raises(InvalidInputData):
        alice_publish_treasure_map_schema.load({})

    treasure_map_b64 = b64encode(bytes(enacted_blockchain_policy.treasure_map)).decode()
    bob_encrypting_key = blockchain_bob.public_keys(DecryptingPower)
    bob_encrypting_key_hex = bytes(bob_encrypting_key).hex()

    required_data = {
        'treasure_map': treasure_map_b64,
        'bob_encrypting_key': bob_encrypting_key_hex
    }

    # required args
    alice_publish_treasure_map_schema.load(required_data)

    # missing required args
    updated_data = {k: v for k, v in required_data.items() if k != 'treasure_map'}
    with pytest.raises(InvalidInputData):
        alice_publish_treasure_map_schema.load(updated_data)

    updated_data = {k: v for k, v in required_data.items() if k != 'bob_encrypting_key'}
    with pytest.raises(InvalidInputData):
        alice_publish_treasure_map_schema.load(updated_data)

    # invalid treasure map
    updated_data = dict(required_data)
    updated_data['treasure_map'] = b64encode(b"testing").decode()
    with pytest.raises(InvalidInputData):
        alice_publish_treasure_map_schema.load(updated_data)

    # invalid encrypting key
    updated_data = dict(required_data)
    updated_data['bob_encrypting_key'] = b'123456'.hex()
    with pytest.raises(InvalidInputData):
        alice_publish_treasure_map_schema.load(updated_data)

    # Test Output - test only true since there is no false ever returned
    response_data = {'published': True}
    output = alice_publish_treasure_map_schema.dump(obj=response_data)
    assert output == response_data

    # setting federated context to True
    alice_publish_treasure_map_schema.context[TreasureMap.IS_FEDERATED_CONTEXT_KEY] = True
    with pytest.raises(InvalidInputData):
        # failed because federated treasure map expected, but instead non-federated (blockchain) treasure map provided
        alice_publish_treasure_map_schema.load(required_data)
