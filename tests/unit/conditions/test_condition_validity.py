import pytest

from nucypher.policy.conditions.evm import ContractCondition, RPCCondition
from nucypher.policy.conditions.exceptions import InvalidCondition
from nucypher.policy.conditions.lingo import (
    CompoundAccessControlCondition,
    ConditionType,
    ReturnValueTest,
)
from nucypher.policy.conditions.time import TimeCondition
from tests.constants import TESTERCHAIN_CHAIN_ID


def test_invalid_time_condition():
    # invalid condition type
    with pytest.raises(InvalidCondition, match=ConditionType.TIME.value):
        _ = TimeCondition(
            condition_type=ConditionType.COMPOUND.value,
            return_value_test=ReturnValueTest(">", 0),
            chain=TESTERCHAIN_CHAIN_ID,
            method=TimeCondition.METHOD,
        )

    # invalid method
    with pytest.raises(InvalidCondition):
        _ = TimeCondition(
            return_value_test=ReturnValueTest('>', 0),
            chain=TESTERCHAIN_CHAIN_ID,
            method="time_after_time",
        )


def test_invalid_rpc_condition():
    # invalid condition type
    with pytest.raises(InvalidCondition, match=ConditionType.RPC.value):
        _ = RPCCondition(
            condition_type=ConditionType.TIME.value,
            method="eth_getBalance",
            chain=TESTERCHAIN_CHAIN_ID,
            return_value_test=ReturnValueTest("==", 0),
            parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        )

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

    # invalid chain type provided
    with pytest.raises(ValueError):
        _ = RPCCondition(
            method="eth_getBalance",
            chain=str(TESTERCHAIN_CHAIN_ID),  # should be int not str.
            return_value_test=ReturnValueTest("==", 0),
            parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        )


def test_invalid_contract_condition():
    # invalid condition type
    with pytest.raises(InvalidCondition, match=ConditionType.CONTRACT.value):
        _ = ContractCondition(
            condition_type=ConditionType.RPC.value,
            contract_address="0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
            method="balanceOf",
            chain=TESTERCHAIN_CHAIN_ID,
            standard_contract_type="ERC20",
            return_value_test=ReturnValueTest("!=", 0),
            parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        )

    # no abi or contract type
    with pytest.raises(InvalidCondition):
        _ = ContractCondition(
            contract_address="0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
            method="getPolicy",
            chain=TESTERCHAIN_CHAIN_ID,
            return_value_test=ReturnValueTest("!=", 0),
            parameters=[
                ":hrac",
            ],
        )

    # invalid standard contract type
    with pytest.raises(InvalidCondition):
        _ = ContractCondition(
            contract_address="0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
            method="getPolicy",
            chain=TESTERCHAIN_CHAIN_ID,
            standard_contract_type="ERC90210",  # Beverly Hills contract type :)
            return_value_test=ReturnValueTest("!=", 0),
            parameters=[
                ":hrac",
            ],
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


def test_invalid_compound_condition(time_condition, rpc_condition):
    for operator in CompoundAccessControlCondition.OPERATORS:
        if operator == CompoundAccessControlCondition.NOT_OPERATOR:
            operands = [time_condition]
        else:
            operands = [time_condition, rpc_condition]

        # invalid condition type
        with pytest.raises(InvalidCondition, match=ConditionType.COMPOUND.value):
            _ = CompoundAccessControlCondition(
                condition_type=ConditionType.TIME.value,
                operator=operator,
                operands=operands,
            )

    # invalid operator - 1 operand
    with pytest.raises(InvalidCondition):
        _ = CompoundAccessControlCondition(operator="5True", operands=[time_condition])

    # invalid operator - 2 operands
    with pytest.raises(InvalidCondition):
        _ = CompoundAccessControlCondition(
            operator="5True", operands=[time_condition, rpc_condition]
        )

    # no operands
    with pytest.raises(InvalidCondition):
        _ = CompoundAccessControlCondition(operator=operator, operands=[])

    # > 1 operand for not operator
    with pytest.raises(InvalidCondition):
        _ = CompoundAccessControlCondition(
            operator=CompoundAccessControlCondition.NOT_OPERATOR,
            operands=[time_condition, rpc_condition],
        )

    # < 2 operands for or operator
    with pytest.raises(InvalidCondition):
        _ = CompoundAccessControlCondition(
            operator=CompoundAccessControlCondition.OR_OPERATOR,
            operands=[time_condition],
        )

    # < 2 operands for and operator
    with pytest.raises(InvalidCondition):
        _ = CompoundAccessControlCondition(
            operator=CompoundAccessControlCondition.AND_OPERATOR,
            operands=[rpc_condition],
        )


def test_time_condition_schema_validation(time_condition):
    condition_dict = time_condition.to_dict()

    # no issues here
    TimeCondition.validate(condition_dict)

    # no issues with optional name
    condition_dict["name"] = "my_time_machine"
    TimeCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # no method
        condition_dict = time_condition.to_dict()
        del condition_dict["method"]
        TimeCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # no returnValueTest defined
        condition_dict = time_condition.to_dict()
        del condition_dict["returnValueTest"]
        TimeCondition.validate(condition_dict)


def test_rpc_condition_schema_validation(rpc_condition):
    condition_dict = rpc_condition.to_dict()

    # no issues here
    RPCCondition.validate(condition_dict)

    # no issues with optional name
    condition_dict["name"] = "my_rpc_condition"
    RPCCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # no chain defined
        condition_dict = rpc_condition.to_dict()
        del condition_dict["chain"]
        RPCCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # no method defined
        condition_dict = rpc_condition.to_dict()
        del condition_dict["method"]
        RPCCondition.validate(condition_dict)

    # no issue with no parameters
    condition_dict = rpc_condition.to_dict()
    del condition_dict["parameters"]
    RPCCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # no returnValueTest defined
        condition_dict = rpc_condition.to_dict()
        del condition_dict["returnValueTest"]
        RPCCondition.validate(condition_dict)


def test_contract_condition_schema_validation():
    contract_condition = ContractCondition(
        contract_address="0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
        method="balanceOf",
        chain=TESTERCHAIN_CHAIN_ID,
        standard_contract_type="ERC20",
        return_value_test=ReturnValueTest("!=", 0),
        parameters=[
            ":hrac",
        ],
    )

    condition_dict = contract_condition.to_dict()

    # no issues here
    ContractCondition.validate(condition_dict)

    # no issues with optional name
    condition_dict["name"] = "my_contract_condition"
    ContractCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # no contract address defined
        condition_dict = contract_condition.to_dict()
        del condition_dict["contractAddress"]
        ContractCondition.validate(condition_dict)

    balanceOf_abi = {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    }

    with pytest.raises(InvalidCondition):
        # no function abi or standard contract type
        condition_dict = contract_condition.to_dict()
        del condition_dict["standardContractType"]
        ContractCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # provide both function abi and standard contract type
        condition_dict = contract_condition.to_dict()
        condition_dict["functionAbi"] = balanceOf_abi
        ContractCondition.validate(condition_dict)

    # remove standardContractType but specify function abi; no issues with that
    condition_dict = contract_condition.to_dict()
    del condition_dict["standardContractType"]
    condition_dict["functionAbi"] = balanceOf_abi
    ContractCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # no returnValueTest defined
        condition_dict = contract_condition.to_dict()
        del condition_dict["returnValueTest"]
        ContractCondition.validate(condition_dict)


@pytest.mark.parametrize("operator", CompoundAccessControlCondition.OPERATORS)
def test_compound_condition_schema_validation(operator, time_condition, rpc_condition):
    if operator == CompoundAccessControlCondition.NOT_OPERATOR:
        operands = [time_condition]
    else:
        operands = [time_condition, rpc_condition]

    compound_condition = CompoundAccessControlCondition(
        operator=operator, operands=operands
    )
    compound_condition_dict = compound_condition.to_dict()

    # no issues here
    CompoundAccessControlCondition.validate(compound_condition_dict)

    # no issues with optional name
    compound_condition_dict["name"] = "my_contract_condition"
    CompoundAccessControlCondition.validate(compound_condition_dict)

    with pytest.raises(InvalidCondition):
        # incorrect condition type
        compound_condition_dict = compound_condition.to_dict()
        compound_condition_dict["condition_type"] = ConditionType.RPC.value
        CompoundAccessControlCondition.validate(compound_condition_dict)

    with pytest.raises(InvalidCondition):
        # invalid operator
        compound_condition_dict = compound_condition.to_dict()
        compound_condition_dict["operator"] = "5True"
        CompoundAccessControlCondition.validate(compound_condition_dict)

    with pytest.raises(InvalidCondition):
        # no operator
        compound_condition_dict = compound_condition.to_dict()
        del compound_condition_dict["operator"]
        CompoundAccessControlCondition.validate(compound_condition_dict)

    with pytest.raises(InvalidCondition):
        # no operands
        compound_condition_dict = compound_condition.to_dict()
        del compound_condition_dict["operands"]
        CompoundAccessControlCondition.validate(compound_condition_dict)
