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


def test_single_retrieve_with_truthy_conditions(enacted_federated_policy, federated_bob, federated_ursulas, mocker):
    from nucypher_core import MessageKit

    reencrypt_spy = mocker.spy(Ursula, '_reencrypt')

    federated_bob.start_learning_loop()
    conditions = {
        'operator': 'and',
        "operands": [
            {'returnValueTest': {'value': '0', 'comparator': '>'}, 'method': 'timelock'},
            {'returnValueTest': {'value': '99999999999999999', 'comparator': '<'}, 'method': 'timelock'},
        ]
    }
    json_conditions = json.dumps(conditions)
    rust_conditions = Conditions(json_conditions)
    message_kits = [
        MessageKit(
            enacted_federated_policy.public_key,
            b'lab',
            rust_conditions
        )
    ]

    cleartexts = federated_bob.retrieve_and_decrypt(
        message_kits=message_kits,
        **_policy_info_kwargs(enacted_federated_policy),
    )

    assert b'lab' in cleartexts
    assert reencrypt_spy.call_count == 3


def test_single_retrieve_with_falsy_conditions(enacted_federated_policy, federated_bob, federated_ursulas, mocker):
    from nucypher_core import MessageKit

    reencrypt_spy = mocker.spy(Ursula, '_reencrypt')
    mocker.patch.object(ConditionLingo, 'eval', return_value=False)
    reencrypt_http_spy = mocker.spy(MockRestMiddleware, 'reencrypt')

    # not actually used for eval, but satisfies serializers
    conditions = Conditions(json.dumps(
        [{'returnValueTest': {'value': '0', 'comparator': '>'}, 'method': 'timelock'}]
    ))

    federated_bob.start_learning_loop()

    message_kits = [
        MessageKit(
            enacted_federated_policy.public_key,
            b'radio',
            conditions
        )
    ]

    with pytest.raises(Ursula.NotEnoughUrsulas):
        federated_bob.retrieve_and_decrypt(
            message_kits=message_kits,
            **_policy_info_kwargs(enacted_federated_policy),
        )

    reencrypt_spy.assert_not_called()
    assert isinstance(reencrypt_http_spy.spy_exception, MockRestMiddleware.Unauthorized)

