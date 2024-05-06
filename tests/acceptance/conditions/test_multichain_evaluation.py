from collections import defaultdict

import pytest

from nucypher.policy.conditions.evm import RPCCondition
from nucypher.policy.conditions.lingo import (
    CompoundAccessControlCondition,
    ConditionLingo,
    ConditionType,
    ReturnValueTest,
)
from nucypher.policy.conditions.time import TimeCondition
from nucypher.utilities.logging import GlobalLoggerSettings
from tests.utils.policy import make_message_kits

GlobalLoggerSettings.start_text_file_logging()


def make_multichain_evm_conditions(bob, chain_ids):
    """This is a helper function to make a set of conditions that are valid on multiple chains."""
    operands = list()
    for chain_id in chain_ids:
        compound_and_condition = CompoundAccessControlCondition(
            operator="and",
            operands=[
                TimeCondition(
                    chain=chain_id,
                    return_value_test=ReturnValueTest(
                        comparator=">",
                        value=0,
                    ),
                ),
                RPCCondition(
                    chain=chain_id,
                    method="eth_getBalance",
                    parameters=[bob.checksum_address, "latest"],
                    return_value_test=ReturnValueTest(
                        comparator=">=",
                        value=10000000000000,
                    ),
                ),
            ],
        )
        operands.append(compound_and_condition.to_dict())

    _conditions = {
        "version": ConditionLingo.VERSION,
        "condition": {
            "conditionType": ConditionType.COMPOUND.value,
            "operator": "and",
            "operands": operands,
        },
    }
    return _conditions


@pytest.fixture(scope="module")
def conditions(bob, multichain_ids):
    _conditions = make_multichain_evm_conditions(bob, multichain_ids)
    return _conditions


def test_single_retrieve_with_multichain_conditions(
    enacted_policy, bob, multichain_ursulas, conditions, mock_rpc_condition
):
    bob.remember_node(multichain_ursulas[0])
    bob.start_learning_loop()

    messages, message_kits = make_message_kits(enacted_policy.public_key, conditions)
    policy_info_kwargs = dict(
        encrypted_treasure_map=enacted_policy.treasure_map,
        alice_verifying_key=enacted_policy.publisher_verifying_key,
    )

    cleartexts = bob.retrieve_and_decrypt(
        message_kits=message_kits,
        **policy_info_kwargs,
    )

    assert cleartexts == messages


@pytest.mark.skip("Will fix once things are cleaned up")
def test_single_decryption_request_with_faulty_rpc_endpoint(
    enacted_policy, bob, multichain_ursulas, conditions, mock_rpc_condition
):
    bob.remember_node(multichain_ursulas[0])
    bob.start_learning_loop()

    messages, message_kits = make_message_kits(enacted_policy.public_key, conditions)
    policy_info_kwargs = dict(
        encrypted_treasure_map=enacted_policy.treasure_map,
        alice_verifying_key=enacted_policy.publisher_verifying_key,
    )

    calls = defaultdict(int)
    original_execute_call = RPCCondition._execute_call

    def faulty_execute_call(*args, **kwargs):
        """Intercept the call to the RPC endpoint and raise an exception on the second call."""
        nonlocal calls
        rpc_call = args[0]
        calls[rpc_call.chain] += 1
        if (
            calls[rpc_call.chain] == 2
            and "tester://multichain.0" in rpc_call.provider.endpoint_uri
        ):
            # simulate a network error
            raise ConnectionError("Something went wrong with the network")
        elif calls[rpc_call.chain] == 3:
            # check the provider is the fallback
            this_uri = rpc_call.provider.endpoint_uri
            assert "fallback" in this_uri
        return original_execute_call(*args, **kwargs)

    RPCCondition._execute_call = faulty_execute_call
    cleartexts = bob.retrieve_and_decrypt(
        message_kits=message_kits,
        **policy_info_kwargs,
    )
    assert cleartexts == messages
    RPCCondition._execute_call = original_execute_call
