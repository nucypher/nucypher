import json

import pytest
from nucypher_core import Conditions

from nucypher.characters.lawful import Ursula
from nucypher.policy.conditions.lingo import ConditionLingo
from tests.utils.middleware import MockRestMiddleware


def _policy_info_kwargs(enacted_policy):
    return dict(
        encrypted_treasure_map=enacted_policy.treasure_map,
        alice_verifying_key=enacted_policy.publisher_verifying_key,
    )


def test_single_retrieve_with_truthy_conditions(
    enacted_blockchain_policy, blockchain_bob, blockchain_ursulas, mocker
):
    from nucypher_core import MessageKit

    reencrypt_spy = mocker.spy(Ursula, '_reencrypt')

    blockchain_bob.remember_node(blockchain_ursulas[0])
    blockchain_bob.start_learning_loop()

    conditions = [
        {'returnValueTest': {'value': '0', 'comparator': '>'}, 'method': 'timelock'},
        {'operator': 'and'},
        {'returnValueTest': {'value': '99999999999999999', 'comparator': '<'}, 'method': 'timelock'},
    ]
    json_conditions = json.dumps(conditions)
    rust_conditions = Conditions(json_conditions)
    message_kits = [
        MessageKit(enacted_blockchain_policy.public_key, b"lab", rust_conditions)
    ]

    cleartexts = blockchain_bob.retrieve_and_decrypt(
        message_kits=message_kits,
        **_policy_info_kwargs(enacted_blockchain_policy),
    )

    assert b'lab' in cleartexts
    assert reencrypt_spy.call_count == enacted_blockchain_policy.threshold


def test_single_retrieve_with_falsy_conditions(
    enacted_blockchain_policy, blockchain_bob, blockchain_ursulas, mocker
):
    from nucypher_core import MessageKit

    reencrypt_spy = mocker.spy(Ursula, '_reencrypt')
    mocker.patch.object(ConditionLingo, 'eval', return_value=False)
    reencrypt_http_spy = mocker.spy(MockRestMiddleware, 'reencrypt')

    # not actually used for eval, but satisfies serializers
    conditions = Conditions(json.dumps(
        [{'returnValueTest': {'value': '0', 'comparator': '>'}, 'method': 'timelock'}]
    ))

    blockchain_bob.start_learning_loop()

    message_kits = [
        MessageKit(enacted_blockchain_policy.public_key, b"radio", conditions)
    ]

    with pytest.raises(Ursula.NotEnoughUrsulas):
        blockchain_bob.retrieve_and_decrypt(
            message_kits=message_kits,
            **_policy_info_kwargs(enacted_blockchain_policy),
        )

    reencrypt_spy.assert_not_called()
    assert isinstance(reencrypt_http_spy.spy_exception, MockRestMiddleware.Unauthorized)
