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


def test_timelock_condition_schema_validation(timelock_condition):
    condition_dict = timelock_condition.to_dict()

    # no issues here
    TimeCondition.validate(condition_dict)

    # no issues with optional name
    condition_dict["name"] = "my_time_machine"
    TimeCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # no method
        condition_dict = timelock_condition.to_dict()
        del condition_dict["method"]
        TimeCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # no returnValueTest defined
        condition_dict = timelock_condition.to_dict()
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
