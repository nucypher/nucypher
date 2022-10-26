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
import base64
import random

import pytest
from nucypher_core import (
    MessageKit,
    TreasureMap as TreasureMapClass,
)
from nucypher_core.umbral import PublicKey
from nucypher_core.umbral import SecretKey

from nucypher.control.specifications.base import BaseSchema
from nucypher.control.specifications.exceptions import SpecificationError, InvalidInputData, InvalidArgumentCombo
from nucypher.crypto.powers import DecryptingPower
from nucypher.utilities.porter.control.specifications.fields import (
    RetrievalOutcomeSchema,
    UrsulaInfoSchema, Key,
)
from nucypher.utilities.porter.control.specifications.fields.treasuremap import TreasureMap
from nucypher.utilities.porter.control.specifications.porter_schema import (
    AliceGetUrsulas,
    BobRetrieveCFrags,
)
from nucypher.utilities.porter.porter import Porter
from tests.utils.policy import retrieval_request_setup


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
    }

    # required args
    AliceGetUrsulas().load(required_data)

    # missing required args
    updated_data = {k: v for k, v in required_data.items() if k != 'quantity'}
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


def test_alice_revoke():
    pass  # TODO


def test_bob_retrieve_cfrags(federated_porter,
                             enacted_federated_policy,
                             federated_bob,
                             federated_alice,
                             random_context,
                             get_random_checksum_address):
    bob_retrieve_cfrags_schema = BobRetrieveCFrags()

    # no args
    with pytest.raises(InvalidInputData):
        bob_retrieve_cfrags_schema.load({})

    # Setup - no context
    retrieval_args, _ = retrieval_request_setup(enacted_federated_policy,
                                                federated_bob,
                                                federated_alice,
                                                encode_for_rest=True)
    bob_retrieve_cfrags_schema.load(retrieval_args)

    # simple schema load w/ optional context
    retrieval_args, _ = retrieval_request_setup(
        enacted_federated_policy,
        federated_bob,
        federated_alice,
        encode_for_rest=True,
        context=random_context,
    )
    bob_retrieve_cfrags_schema.load(retrieval_args)

    # invalid context specified
    retrieval_args, _ = retrieval_request_setup(
        enacted_federated_policy,
        federated_bob,
        federated_alice,
        encode_for_rest=True,
        context=[1, 2, 3],  # list instead of dict
    )
    with pytest.raises(InvalidInputData):
        # invalid context type
        bob_retrieve_cfrags_schema.load(retrieval_args)

    # missing required argument
    updated_data = dict(retrieval_args)
    updated_data.pop("context")  # context is not a required param
    key_to_remove = random.choice(list(updated_data.keys()))
    del updated_data[key_to_remove]
    with pytest.raises(InvalidInputData):
        # missing arg
        bob_retrieve_cfrags_schema.load(updated_data)

    #
    # Retrieval output for 1 retrieval kit
    #
    non_encoded_retrieval_args, _ = retrieval_request_setup(
        enacted_federated_policy,
        federated_bob,
        federated_alice,
        encode_for_rest=False,
        context=random_context,
    )
    retrieval_outcomes = federated_porter.retrieve_cfrags(**non_encoded_retrieval_args)
    expected_retrieval_results_json = []
    retrieval_outcome_schema = RetrievalOutcomeSchema()

    assert len(retrieval_outcomes) == 1
    assert len(retrieval_outcomes[0].cfrags) > 0
    assert len(retrieval_outcomes[0].errors) == 0
    for outcome in retrieval_outcomes:
        data = retrieval_outcome_schema.dump(outcome)
        expected_retrieval_results_json.append(data)

    output = bob_retrieve_cfrags_schema.dump(
        obj={"retrieval_results": retrieval_outcomes}
    )
    assert output == {"retrieval_results": expected_retrieval_results_json}
    assert len(output["retrieval_results"]) == 1
    assert len(output["retrieval_results"][0]["cfrags"]) > 0
    assert len(output["retrieval_results"][0]["errors"]) == 0

    # now include errors
    errors = {
        get_random_checksum_address(): "Error Message 1",
        get_random_checksum_address(): "Error Message 2",
        get_random_checksum_address(): "Error Message 3",
    }
    new_retrieval_outcome = Porter.RetrievalOutcome(
        cfrags=retrieval_outcomes[0].cfrags, errors=errors
    )
    expected_retrieval_results_json = [
        retrieval_outcome_schema.dump(new_retrieval_outcome)
    ]
    output = bob_retrieve_cfrags_schema.dump(
        obj={"retrieval_results": [new_retrieval_outcome]}
    )
    assert output == {"retrieval_results": expected_retrieval_results_json}
    assert len(output["retrieval_results"]) == 1
    assert len(output["retrieval_results"][0]["cfrags"]) > 0
    assert len(output["retrieval_results"][0]["errors"]) == len(errors)

    #
    # Retrieval output for multiple retrieval kits
    #
    num_retrieval_kits = 4
    non_encoded_retrieval_args, _ = retrieval_request_setup(
        enacted_federated_policy,
        federated_bob,
        federated_alice,
        encode_for_rest=False,
        context=random_context,
        num_random_messages=num_retrieval_kits,
    )
    retrieval_outcomes = federated_porter.retrieve_cfrags(**non_encoded_retrieval_args)
    expected_retrieval_results_json = []
    retrieval_outcome_schema = RetrievalOutcomeSchema()

    assert len(retrieval_outcomes) == num_retrieval_kits
    for i in range(num_retrieval_kits):
        assert len(retrieval_outcomes[i].cfrags) > 0
        assert len(retrieval_outcomes[i].errors) == 0
    for outcome in retrieval_outcomes:
        data = retrieval_outcome_schema.dump(outcome)
        expected_retrieval_results_json.append(data)

    output = bob_retrieve_cfrags_schema.dump(
        obj={"retrieval_results": retrieval_outcomes}
    )
    assert output == {"retrieval_results": expected_retrieval_results_json}

    # now include errors
    error_message_template = "Retrieval Kit {} - Error Message {}"
    new_retrieval_outcomes_with_errors = []
    for i in range(num_retrieval_kits):
        specific_kit_errors = dict()
        for j in range(i):
            # different number of errors for each kit; 1 error for kit 1, 2 errors for kit 2 etc.
            specific_kit_errors[
                get_random_checksum_address()
            ] = error_message_template.format(i, j)
        new_retrieval_outcomes_with_errors.append(
            Porter.RetrievalOutcome(
                cfrags=retrieval_outcomes[i].cfrags, errors=specific_kit_errors
            )
        )

    expected_retrieval_results_json = []
    for outcome in new_retrieval_outcomes_with_errors:
        data = retrieval_outcome_schema.dump(outcome)
        expected_retrieval_results_json.append(data)

    output = bob_retrieve_cfrags_schema.dump(
        obj={"retrieval_results": new_retrieval_outcomes_with_errors}
    )
    assert output == {"retrieval_results": expected_retrieval_results_json}
    assert len(output["retrieval_results"]) == num_retrieval_kits
    for i in range(num_retrieval_kits):
        assert len(output["retrieval_results"][i]["cfrags"]) > 0
        # ensures errors are associated appropriately
        kit_errors = output["retrieval_results"][i]["errors"]
        assert len(kit_errors) == i
        values = kit_errors.values()  # ordered?
        for j in range(i):
            assert error_message_template.format(i, j) in values


def make_header(brand: bytes, major: int, minor: int) -> bytes:
    # Hardcoding this since it's too much trouble to expose it all the way from Rust
    assert len(brand) == 4
    major_bytes = major.to_bytes(2, 'big')
    minor_bytes = minor.to_bytes(2, 'big')
    header = brand + major_bytes + minor_bytes
    return header


def test_treasure_map_validation(enacted_federated_policy,
                                 federated_bob):
    class UnenncryptedTreasureMapsOnly(BaseSchema):
        tmap = TreasureMap()

    # this will raise a base64 error
    with pytest.raises(SpecificationError) as e:
        UnenncryptedTreasureMapsOnly().load({'tmap': "your face looks like a treasure map"})

    # assert that field name is in the error message
    assert "Could not parse tmap" in str(e)
    assert "Invalid base64-encoded string" in str(e)

    # valid base64 but invalid treasuremap
    bad_map = make_header(b'TMap', 1, 0) + b"your face looks like a treasure map"
    bad_map_b64 = base64.b64encode(bad_map).decode()

    with pytest.raises(InvalidInputData) as e:
        UnenncryptedTreasureMapsOnly().load({'tmap': bad_map_b64})

    assert "Could not convert input for tmap to a TreasureMap" in str(e)
    assert "Failed to deserialize" in str(e)

    # a valid treasuremap
    decrypted_treasure_map = federated_bob._decrypt_treasure_map(enacted_federated_policy.treasure_map,
                                                                 enacted_federated_policy.publisher_verifying_key)
    tmap_bytes = bytes(decrypted_treasure_map)
    tmap_b64 = base64.b64encode(tmap_bytes).decode()
    result = UnenncryptedTreasureMapsOnly().load({'tmap': tmap_b64})
    assert isinstance(result['tmap'], TreasureMapClass)


def test_key_validation(federated_bob):

    class BobKeyInputRequirer(BaseSchema):
        bobkey = Key()

    with pytest.raises(InvalidInputData) as e:
        BobKeyInputRequirer().load({'bobkey': "I am the key to nothing"})
    assert "non-hexadecimal number found in fromhex()" in str(e)
    assert "bobkey" in str(e)

    with pytest.raises(InvalidInputData) as e:
        BobKeyInputRequirer().load({'bobkey': "I am the key to nothing"})
    assert "non-hexadecimal number found in fromhex()" in str(e)
    assert "bobkey" in str(e)

    with pytest.raises(InvalidInputData) as e:
        # lets just take a couple bytes off
        BobKeyInputRequirer().load({'bobkey': "02f0cb3f3a33f16255d9b2586e6c56570aa07bbeb1157e169f1fb114ffb40037"})
    assert "Could not convert input for bobkey to an Umbral Key" in str(e)
    assert "xpected 33 bytes, got 32" in str(e)

    result = BobKeyInputRequirer().load(dict(bobkey=bytes(federated_bob.public_keys(DecryptingPower)).hex()))
    assert isinstance(result['bobkey'], PublicKey)