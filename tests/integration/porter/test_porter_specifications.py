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
import os
from base64 import b64encode

import pytest

from nucypher.characters.control.specifications.fields import TreasureMap
from nucypher.control.specifications.exceptions import InvalidArgumentCombo, InvalidInputData
from nucypher.crypto.powers import DecryptingPower
from nucypher.crypto.umbral_adapter import SecretKey
from nucypher.policy.maps import AuthorizedKeyFrag
from nucypher.policy.orders import WorkOrder as WorkOrderClass
from nucypher.utilities.porter.control.specifications.fields import UrsulaInfoSchema
from nucypher.utilities.porter.control.specifications.porter_schema import (
    AliceGetUrsulas,
    AlicePublishTreasureMap,
    BobGetTreasureMap,
    BobExecWorkOrder
)
from nucypher.utilities.porter.porter import Porter


def test_alice_get_ursulas_schema(get_random_checksum_address):
    #
    # Input i.e. load
    #

    # no args
    with pytest.raises(InvalidInputData):
        AliceGetUrsulas().load({})

    quantity = 10
    required_data = {
        'quantity': quantity,
        'duration_periods': 4,
    }

    # required args
    AliceGetUrsulas().load(required_data)

    # missing required args
    updated_data = {k: v for k, v in required_data.items() if k != 'quantity'}
    with pytest.raises(InvalidInputData):
        AliceGetUrsulas().load(updated_data)

    updated_data = {k: v for k, v in required_data.items() if k != 'duration_periods'}
    with pytest.raises(InvalidInputData):
        AliceGetUrsulas().load(updated_data)

    # optional components

    # only exclude
    updated_data = dict(required_data)
    exclude_ursulas = []
    for i in range(2):
        exclude_ursulas.append(get_random_checksum_address())
    updated_data['exclude_ursulas'] = exclude_ursulas
    AliceGetUrsulas().load(updated_data)

    # only include
    updated_data = dict(required_data)
    include_ursulas = []
    for i in range(3):
        include_ursulas.append(get_random_checksum_address())
    updated_data['include_ursulas'] = include_ursulas
    AliceGetUrsulas().load(updated_data)

    # both exclude and include
    updated_data = dict(required_data)
    updated_data['exclude_ursulas'] = exclude_ursulas
    updated_data['include_ursulas'] = include_ursulas
    AliceGetUrsulas().load(updated_data)

    # list input formatted as ',' separated strings
    updated_data = dict(required_data)
    updated_data['exclude_ursulas'] = ','.join(exclude_ursulas)
    updated_data['include_ursulas'] = ','.join(include_ursulas)
    data = AliceGetUrsulas().load(updated_data)
    assert data['exclude_ursulas'] == exclude_ursulas
    assert data['include_ursulas'] == include_ursulas

    # single value as string cast to list
    updated_data = dict(required_data)
    updated_data['exclude_ursulas'] = exclude_ursulas[0]
    updated_data['include_ursulas'] = include_ursulas[0]
    data = AliceGetUrsulas().load(updated_data)
    assert data['exclude_ursulas'] == [exclude_ursulas[0]]
    assert data['include_ursulas'] == [include_ursulas[0]]

    # invalid include entry
    updated_data = dict(required_data)
    updated_data['exclude_ursulas'] = exclude_ursulas
    updated_data['include_ursulas'] = list(include_ursulas)  # make copy to modify
    updated_data['include_ursulas'].append("0xdeadbeef")
    with pytest.raises(InvalidInputData):
        AliceGetUrsulas().load(updated_data)

    # invalid exclude entry
    updated_data = dict(required_data)
    updated_data['exclude_ursulas'] = list(exclude_ursulas)  # make copy to modify
    updated_data['exclude_ursulas'].append("0xdeadbeef")
    updated_data['include_ursulas'] = include_ursulas
    with pytest.raises(InvalidInputData):
        AliceGetUrsulas().load(updated_data)

    # too many ursulas to include
    updated_data = dict(required_data)
    too_many_ursulas_to_include = []
    while len(too_many_ursulas_to_include) <= quantity:
        too_many_ursulas_to_include.append(get_random_checksum_address())
    updated_data['include_ursulas'] = too_many_ursulas_to_include
    with pytest.raises(InvalidArgumentCombo):
        # number of ursulas to include exceeds quantity to sample
        AliceGetUrsulas().load(updated_data)

    # include and exclude addresses are not mutually exclusive - include has common entry
    updated_data = dict(required_data)
    updated_data['exclude_ursulas'] = exclude_ursulas
    updated_data['include_ursulas'] = list(include_ursulas)  # make copy to modify
    updated_data['include_ursulas'].append(exclude_ursulas[0])  # one address that overlaps
    with pytest.raises(InvalidArgumentCombo):
        # 1 address in both include and exclude lists
        AliceGetUrsulas().load(updated_data)

    # include and exclude addresses are not mutually exclusive - exclude has common entry
    updated_data = dict(required_data)
    updated_data['exclude_ursulas'] = list(exclude_ursulas)  # make copy to modify
    updated_data['exclude_ursulas'].append(include_ursulas[0])  # on address that overlaps
    updated_data['include_ursulas'] = include_ursulas
    with pytest.raises(InvalidArgumentCombo):
        # 1 address in both include and exclude lists
        AliceGetUrsulas().load(updated_data)

    #
    # Output i.e. dump
    #
    ursulas_info = []
    expected_ursulas_info = []
    port = 11500
    for i in range(3):
        ursula_info = Porter.UrsulaInfo(get_random_checksum_address(),
                                        f"https://127.0.0.1:{port+i}",
                                        SecretKey.random().public_key())
        ursulas_info.append(ursula_info)

        # use schema to determine expected output (encrypting key gets changed to hex)
        expected_ursulas_info.append(UrsulaInfoSchema().dump(ursula_info))

    output = AliceGetUrsulas().dump(obj={'ursulas': ursulas_info})
    assert output == {"ursulas": expected_ursulas_info}


def test_alice_publish_treasure_map_schema_federated_context(enacted_federated_policy, federated_bob):
    # since federated, schema's context must be set - so create one schema
    # and reuse (it doesn't hold state other than the context)
    alice_publish_treasure_map_schema = AlicePublishTreasureMap()
    alice_publish_treasure_map_schema.context[TreasureMap.IS_FEDERATED_CONTEXT_KEY] = True

    # no args
    with pytest.raises(InvalidInputData):
        alice_publish_treasure_map_schema.load({})

    treasure_map_b64 = b64encode(bytes(enacted_federated_policy.treasure_map)).decode()
    bob_encrypting_key = federated_bob.public_keys(DecryptingPower)
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

    # setting federated context to False fails
    alice_publish_treasure_map_schema.context[TreasureMap.IS_FEDERATED_CONTEXT_KEY] = False
    with pytest.raises(InvalidInputData):
        # failed because non-federated (blockchain) treasure map expected, but instead federated treasure map provided
        alice_publish_treasure_map_schema.load(required_data)


def test_alice_revoke():
    pass  # TODO


def test_bob_get_treasure_map(enacted_federated_policy, federated_alice, federated_bob):
    #
    # Input i.e. load
    #

    # no args
    with pytest.raises(InvalidInputData):
        BobGetTreasureMap().load({})

    treasure_map_id = federated_bob.construct_map_id(federated_alice.stamp, enacted_federated_policy.label)
    bob_encrypting_key = federated_bob.public_keys(DecryptingPower)
    bob_encrypting_key_hex = bytes(bob_encrypting_key).hex()

    required_data = {
        'treasure_map_id': treasure_map_id,
        'bob_encrypting_key': bob_encrypting_key_hex
    }

    # required args
    BobGetTreasureMap().load(required_data)

    # random 16-byte length map id
    updated_data = dict(required_data)
    updated_data['treasure_map_id'] = "93a9482bdf3b4f2e9df906a35144ca93"
    BobGetTreasureMap().load(updated_data)

    # missing required args
    updated_data = {k: v for k, v in required_data.items() if k != 'treasure_map_id'}
    with pytest.raises(InvalidInputData):
        BobGetTreasureMap().load(updated_data)

    updated_data = {k: v for k, v in required_data.items() if k != 'bob_encrypting_key'}
    with pytest.raises(InvalidInputData):
        BobGetTreasureMap().load(updated_data)

    # invalid treasure map id
    updated_data = dict(required_data)
    updated_data['treasure_map_id'] = b'fake_id'.hex()
    with pytest.raises(InvalidInputData):
        BobGetTreasureMap().load(updated_data)

    # invalid encrypting key
    updated_data = dict(required_data)
    updated_data['bob_encrypting_key'] = b'123456'.hex()
    with pytest.raises(InvalidInputData):
        BobGetTreasureMap().load(updated_data)

    #
    # Output i.e. dump
    #
    treasure_map = enacted_federated_policy.treasure_map
    result = {'treasure_map': treasure_map}
    output = BobGetTreasureMap().dump(obj=result)
    assert output == {'treasure_map': b64encode(bytes(treasure_map)).decode()}


def test_bob_exec_work_order(mock_ursula_reencrypts,
                             federated_ursulas,
                             get_random_checksum_address,
                             federated_bob,
                             federated_alice,
                             random_policy_label):
    # Setup
    ursula = list(federated_ursulas)[0]
    tasks = [mock_ursula_reencrypts(ursula) for _ in range(3)]
    material = [(task.capsule, task.signature, task.cfrag, task.cfrag_signature) for task in tasks]
    capsules, signatures, cfrags, cfrag_signatures = zip(*material)

    mock_kfrag = os.urandom(AuthorizedKeyFrag.ENCRYPTED_SIZE)

    # Test construction of WorkOrders by Bob
    work_order = WorkOrderClass.construct_by_bob(encrypted_kfrag=mock_kfrag,
                                                 bob=federated_bob,
                                                 publisher_verifying_key=federated_alice.stamp.as_umbral_pubkey(),
                                                 alice_verifying_key=federated_alice.stamp.as_umbral_pubkey(),
                                                 ursula=ursula,
                                                 capsules=capsules,
                                                 label=random_policy_label)

    # Test Work Order
    work_order_bytes = work_order.payload()

    # no args
    with pytest.raises(InvalidInputData):
        BobExecWorkOrder().load({})

    work_order_b64 = b64encode(work_order_bytes).decode()
    required_data = {
        'ursula': ursula.checksum_address,
        'work_order_payload': work_order_b64
    }

    # required args
    BobExecWorkOrder().load(required_data)

    # missing required args
    updated_data = {k: v for k, v in required_data.items() if k != 'ursula'}
    with pytest.raises(InvalidInputData):
        BobExecWorkOrder().load(updated_data)

    updated_data = {k: v for k, v in required_data.items() if k != 'work_order_payload'}
    with pytest.raises(InvalidInputData):
        BobExecWorkOrder().load(updated_data)

    # invalid ursula checksum address
    updated_data = dict(required_data)
    updated_data['ursula'] = "0xdeadbeef"
    with pytest.raises(InvalidInputData):
        BobExecWorkOrder().load(updated_data)
