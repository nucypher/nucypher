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

import json
from pathlib import Path

import pytest
from web3 import Web3

import tests.data
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    NucypherTokenAgent,
    SubscriptionManagerAgent,
)
from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT
from nucypher.policy.conditions.evm import ContractCondition, RPCCondition
from nucypher.policy.conditions.lingo import AND, OR, ConditionLingo, ReturnValueTest
from nucypher.policy.conditions.time import TimeCondition

VECTORS_FILE = Path(tests.__file__).parent / "data" / "test_conditions.json"

with open(VECTORS_FILE, 'r') as file:
    VECTORS = json.loads(file.read())


@pytest.fixture()
def ERC1155_balance_condition_data():
    data = json.dumps(VECTORS['ERC1155_balance'])
    return data


@pytest.fixture()
def ERC1155_balance_condition(ERC1155_balance_condition_data):
    data = ERC1155_balance_condition_data
    condition = ContractCondition.from_json(data)
    return condition


@pytest.fixture()
def ERC20_balance_condition_data():
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
        chain="testerchain",
        return_value_test=ReturnValueTest("==", Web3.toWei(1_000_000, "ether")),
        parameters=[USER_ADDRESS_CONTEXT],
    )
    return condition


@pytest.fixture
def erc20_evm_condition(test_registry, agency):
    token = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
    condition = ContractCondition(
        contract_address=token.contract.address,
        method="balanceOf",
        standard_contract_type="ERC20",
        chain="testerchain",
        return_value_test=ReturnValueTest("==", 0),
        parameters=[USER_ADDRESS_CONTEXT],
    )
    return condition


@pytest.fixture
def custom_context_variable_erc20_condition(test_registry, agency):
    token = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
    condition = ContractCondition(
        contract_address=token.contract.address,
        method="balanceOf",
        standard_contract_type="ERC20",
        chain="testerchain",
        return_value_test=ReturnValueTest("==", 0),
        parameters=[":addressToUse"],
    )
    return condition


@pytest.fixture
def erc721_evm_condition(test_registry):
    condition = ContractCondition(
        contract_address="0xaDD9D957170dF6F33982001E4c22eCCdd5539118",  # TODO not a valid ERC721 contract
        method="ownerOf",
        standard_contract_type="ERC721",
        chain="testerchain",
        return_value_test=ReturnValueTest("==", ":userAddress"),
        parameters=[
            5954,
        ],
    )
    return condition


@pytest.fixture
def subscription_manager_condition(test_registry, agency):
    subscription_manager = ContractAgency.get_agent(SubscriptionManagerAgent, registry=test_registry)
    condition = ContractCondition(
        contract_address=subscription_manager.contract.address,
        method='getPolicy',
        chain='testerchain',
        return_value_test=ReturnValueTest('==', 0),
        parameters=[
            ':hrac'
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
def lingo(timelock_condition, rpc_condition, erc20_evm_condition):
    lingo = ConditionLingo(
        conditions=[timelock_condition, OR, rpc_condition, AND, erc20_evm_condition]
    )
    return lingo
