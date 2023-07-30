import pytest

from nucypher.policy.conditions.evm import _CONDITION_CHAINS, RPCCondition
from nucypher.policy.conditions.lingo import ConditionLingo
from nucypher.utilities.logging import GlobalLoggerSettings
from tests.constants import TESTERCHAIN_CHAIN_ID, TEST_POLYGON_PROVIDER_URI
from tests.utils.policy import make_message_kits

GlobalLoggerSettings.start_text_file_logging()


def make_multichain_evm_conditions(bob, chain_ids):
    """This is a helper function to make a set of conditions that are valid on multiple chains."""
    operands = list()
    for chain_id in chain_ids:
        operand = [
            {
                "returnValueTest": {"value": "0", "comparator": ">"},
                "method": "blocktime",
                "chain": chain_id,
            },
            {
                "chain": chain_id,
                "method": "eth_getBalance",
                "parameters": [bob.checksum_address, "latest"],
                "returnValueTest": {"comparator": ">=", "value": "10000000000000"},
            },
        ]
        operands.extend(operand)

    _conditions = {
        "version": ConditionLingo.VERSION,
        "condition": {
            "operator": "and",
            "operands": operands,
        },
    }
    return _conditions


@pytest.fixture(scope="module")
def chain_ids(module_mocker):
    ids = [
        TESTERCHAIN_CHAIN_ID,
        TESTERCHAIN_CHAIN_ID + 1,
        TESTERCHAIN_CHAIN_ID + 2,
        123456789,
    ]
    module_mocker.patch.dict(
        _CONDITION_CHAINS, {cid: "fakechain/mainnet" for cid in ids}
    )
    return ids


@pytest.fixture(scope="module", autouse=True)
def multichain_ursulas(ursulas, chain_ids):
    base_uri = "tester://multichain.{}"
    provider_uris = [base_uri.format(i) for i in range(len(chain_ids))]
    mocked_condition_providers = {
        cid: {uri} for cid, uri in zip(chain_ids, provider_uris)
    }
    for ursula in ursulas:
        ursula.condition_providers = mocked_condition_providers
    return ursulas


@pytest.fixture(scope="module")
def conditions(bob, chain_ids):
    _conditions = make_multichain_evm_conditions(bob, chain_ids)
    return _conditions


@pytest.fixture(scope="module")
def mock_rpc_condition(module_mocker, testerchain):
    configure_mock = module_mocker.patch.object(
        RPCCondition, "_configure_w3", return_value=testerchain.w3
    )

    chain_id_check_mock = module_mocker.patch.object(RPCCondition, "_check_chain_id")
    return configure_mock, chain_id_check_mock


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
