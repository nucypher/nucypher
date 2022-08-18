import json
import pytest

from nucypher.policy.conditions.lingo import ConditionLingo
from tests.integration.characters.test_bob_handles_frags import _make_message_kits


def test_erc20_evm_condition_evaluation(testerchain, evm_condition):
    result, value = evm_condition.verify(provider=testerchain.provider, user_address=testerchain.unassigned_accounts[0])
    assert result is True
    result, value = evm_condition.verify(provider=testerchain.provider, user_address=testerchain.etherbase_account)
    assert result is False


@pytest.mark.skip('Need a way to handle user inputs like HRAC as context variables')
def test_subscription_manager_condition_evaluation(testerchain, subscription_manager_condition):
    hrac = None  # TODO
    result, value = subscription_manager_condition.verify(provider=testerchain.provider, user_address=testerchain.unassigned_accounts[0], hrac=hrac)
    assert result is True
    result, value = subscription_manager_condition.verify(provider=testerchain.provider, user_address=testerchain.etherbase_account)
    assert result is False


def test_rpc_condition_evaluation(testerchain, rpc_condition):
    address = testerchain.unassigned_accounts[0]
    result, value = rpc_condition.verify(provider=testerchain.provider, user_address=address)
    assert result is True


def test_time_condition_evaluation(testerchain, timelock_condition):
    address = testerchain.unassigned_accounts[0]
    result, value = timelock_condition.verify(provider=testerchain.provider, user_address=address)
    assert result is True


def test_simple_compound_conditions_evaluation(testerchain):
    # TODO Improve internals of evaluation here (natural vs recursive approach)
    conditions = [
        {'returnValueTest': {'value': '0', 'comparator': '>'}, 'method': 'timelock'},
        {'operator': 'and'},
        {'returnValueTest': {'value': '99999999999999999', 'comparator': '<'}, 'method': 'timelock'},
        {'operator': 'and'},
        {'returnValueTest': {'value': '0', 'comparator': '>'}, 'method': 'timelock'}
    ]
    conditions = json.dumps(conditions)
    lingo = ConditionLingo.from_json(conditions)
    result = lingo.eval()
    assert result is True


def test_onchain_conditions_lingo_evaluation(testerchain, timelock_condition, rpc_condition, evm_condition, lingo):
    result = lingo.eval(provider=testerchain.provider, user_address=testerchain.etherbase_account)
    assert result is True


def test_single_retrieve_with_onchain_conditions(enacted_blockchain_policy, blockchain_bob, blockchain_ursulas):
    blockchain_bob.start_learning_loop()
    messages, message_kits = _make_message_kits(enacted_blockchain_policy.public_key)
    conditions = [
        {'returnValueTest': {'value': '0', 'comparator': '>'}, 'method': 'timelock'},
        {'operator': 'and'},
        {"chain": "testerchain",
         "method": "eth_getBalance",
         "parameters": [
             blockchain_bob.checksum_address,
             "latest"
         ],
         "returnValueTest": {
             "comparator": ">=",
             "value": "10000000000000"
         }
         }

    ]
    for mk in message_kits:
        mk.lingo = ConditionLingo.from_json(json.dumps(conditions))

    policy_info_kwargs = dict(
        encrypted_treasure_map=enacted_blockchain_policy.treasure_map,
        alice_verifying_key=enacted_blockchain_policy.publisher_verifying_key,
    )

    cleartexts = blockchain_bob.retrieve_and_decrypt(
        message_kits=message_kits,
        **policy_info_kwargs,
    )

    assert cleartexts == messages
