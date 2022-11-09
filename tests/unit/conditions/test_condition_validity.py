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
import pytest

from nucypher.policy.conditions.evm import ContractCondition, RPCCondition
from nucypher.policy.conditions.exceptions import InvalidCondition
from nucypher.policy.conditions.lingo import ReturnValueTest
from nucypher.policy.conditions.time import TimeCondition
from tests.constants import TESTERCHAIN_CHAIN_ID


def test_invalid_time_condition():
    with pytest.raises(InvalidCondition):
        _ = TimeCondition(
            return_value_test=ReturnValueTest('>', 0),
            method="time_after_time",
        )


def test_invalid_rpc_condition():
    # no eth_ prefix for method
    with pytest.raises(InvalidCondition):
        _ = RPCCondition(
            method="no_eth_prefix_eth_getBalance",
            chain=TESTERCHAIN_CHAIN_ID,
            return_value_test=ReturnValueTest("==", 0),
            parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        )

    # non-existent method
    with pytest.raises(InvalidCondition):
        _ = RPCCondition(
            method="eth_randoMethod",
            chain=TESTERCHAIN_CHAIN_ID,
            return_value_test=ReturnValueTest("==", 0),
            parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        )

    # unsupported chain id
    with pytest.raises(InvalidCondition):
        _ = RPCCondition(
            method="eth_getBalance",
            chain=90210,  # Beverly Hills Chain :)
            return_value_test=ReturnValueTest("==", 0),
            parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        )


def test_invalid_contract_condition():
    # no abi or contract type
    with pytest.raises(InvalidCondition):
        _ = ContractCondition(
                contract_address="0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
                method="getPolicy",
                chain=TESTERCHAIN_CHAIN_ID,
                return_value_test=ReturnValueTest('!=', 0),
                parameters=[
                    ':hrac',
                ]
            )

    # invalid contract type
    with pytest.raises(InvalidCondition):
        _ = ContractCondition(
                contract_address="0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
                method="getPolicy",
                chain=TESTERCHAIN_CHAIN_ID,
                standard_contract_type="ERC90210",  # Beverly Hills contract type :)
                return_value_test=ReturnValueTest('!=', 0),
                parameters=[
                    ':hrac',
                ]
            )

    # invalid ABI
    with pytest.raises(InvalidCondition):
        _ = ContractCondition(
            contract_address="0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
            method="getPolicy",
            chain=TESTERCHAIN_CHAIN_ID,
            function_abi=["rando ABI"],
            return_value_test=ReturnValueTest("!=", 0),
            parameters=[
                ":hrac",
            ],
        )

    # method not in ABI
    with pytest.raises(ReencryptionCondition.InvalidCondition):
        _ = ContractCondition(
            contract_address="0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
            method="getPolicy",
            chain=TESTERCHAIN_CHAIN_ID,
            standard_contract_type="ERC20",  # Beverly Hills contract type :)
            return_value_test=ReturnValueTest("!=", 0),
            parameters=[
                ":hrac",
            ],
        )
