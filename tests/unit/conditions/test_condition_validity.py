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
            function_abi={"rando": "ABI"},
            return_value_test=ReturnValueTest("!=", 0),
            parameters=[
                ":hrac",
            ],
        )

    # method not in ABI
    with pytest.raises(InvalidCondition):
        _ = ContractCondition(
            contract_address="0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
            method="getPolicy",
            chain=TESTERCHAIN_CHAIN_ID,
            standard_contract_type="ERC20",
            return_value_test=ReturnValueTest("!=", 0),
            parameters=[
                ":hrac",
            ],
        )

    # standard contract type and function ABI
    with pytest.raises(InvalidCondition):
        _ = ContractCondition(
            contract_address="0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
            method="balanceOf",
            chain=TESTERCHAIN_CHAIN_ID,
            standard_contract_type="ERC20",
            function_abi={"rando": "ABI"},
            return_value_test=ReturnValueTest("!=", 0),
            parameters=[
                ":hrac",
            ],
        )
