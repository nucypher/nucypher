import json
from pathlib import Path

import pytest
from web3 import Web3

import nucypher
import tests
from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT
from nucypher.policy.conditions.evm import ContractCondition, RPCCondition
from nucypher.policy.conditions.lingo import AND, OR, ConditionLingo, ReturnValueTest
from nucypher.policy.conditions.time import TimeCondition
from tests.constants import TESTERCHAIN_CHAIN_ID

VECTORS_FILE = Path(tests.__file__).parent / "data" / "test_conditions.json"

with open(VECTORS_FILE, 'r') as file:
    VECTORS = json.loads(file.read())


@pytest.fixture(autouse=True)
def mock_condition_blockchains(mocker):
    """adds testerchain to permitted conditional chains"""
    mocker.patch.object(
        nucypher.policy.conditions.evm, "_CONDITION_CHAINS", tuple([131277322940537])
    )


@pytest.fixture()
def condition_providers(testerchain):
    providers = {testerchain.client.chain_id: testerchain.provider}
    return providers


@pytest.fixture()
def condition_bug_data():
    return json.dumps(VECTORS["bugCondition"])


@pytest.fixture()
def t_staking_data():
    return json.dumps(VECTORS["TStaking"])


# ERC1155

@pytest.fixture()
def ERC1155_balance_condition_data():
    VECTORS['ERC1155_balance']['chain'] = TESTERCHAIN_CHAIN_ID
    data = json.dumps(VECTORS['ERC1155_balance'])
    return data


@pytest.fixture()
def ERC1155_balance_condition(ERC1155_balance_condition_data):
    data = ERC1155_balance_condition_data
    condition = ContractCondition.from_json(data)
    return condition


# ERC20

@pytest.fixture()
def ERC20_balance_condition_data():
    VECTORS['ERC20_balance']['chain'] = TESTERCHAIN_CHAIN_ID
    data = json.dumps(VECTORS['ERC20_balance'])
    return data


@pytest.fixture()
def ERC20_balance_condition(ERC20_balance_condition_data):
    data = ERC20_balance_condition_data
    condition = ContractCondition.from_json(data)
    return condition


@pytest.fixture
def rpc_condition():
    condition = RPCCondition(
        method="eth_getBalance",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest("==", Web3.to_wei(1_000_000, "ether")),
        parameters=[USER_ADDRESS_CONTEXT],
    )
    return condition


@pytest.fixture
def erc20_evm_condition(test_registry):
    condition = ContractCondition(
        contract_address="0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
        method="balanceOf",
        standard_contract_type="ERC20",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest("==", 0),
        parameters=[
            USER_ADDRESS_CONTEXT,
        ],
    )
    return condition


@pytest.fixture
def erc721_evm_condition(test_registry):
    condition = ContractCondition(
        contract_address="0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
        method="ownerOf",
        standard_contract_type="ERC721",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest("==", ":userAddress"),
        parameters=[
            5954,
        ]
    )
    return condition


@pytest.fixture
def timelock_condition():
    condition = TimeCondition(
        return_value_test=ReturnValueTest('>', 0)
    )
    return condition


@pytest.fixture()
def lingo(timelock_condition, rpc_condition, erc20_evm_condition, erc721_evm_condition):
    lingo = ConditionLingo(
        conditions=[
            erc721_evm_condition,
            OR,
            timelock_condition,
            OR,
            rpc_condition,
            AND,
            erc20_evm_condition,
        ]
    )
    return lingo
