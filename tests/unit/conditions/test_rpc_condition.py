from unittest.mock import ANY

import pytest
from web3 import HTTPProvider

from nucypher.policy.conditions.evm import RPCCall, RPCCondition
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    InvalidConditionLingo,
)
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest
from tests.constants import TESTERCHAIN_CHAIN_ID


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

    # no method
    with pytest.raises(InvalidCondition, match="Undefined method name"):
        _ = RPCCondition(
            method=None,
            chain=TESTERCHAIN_CHAIN_ID,
            return_value_test=ReturnValueTest("==", 0),
            parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        )

    # no eth_ prefix for method
    with pytest.raises(InvalidCondition, match="is not a permitted RPC endpoint"):
        _ = RPCCondition(
            method="no_eth_prefix_eth_getBalance",
            chain=TESTERCHAIN_CHAIN_ID,
            return_value_test=ReturnValueTest("==", 0),
            parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        )

    # non-existent method
    with pytest.raises(InvalidCondition, match="is not a permitted RPC endpoint"):
        _ = RPCCondition(
            method="eth_randoMethod",
            chain=TESTERCHAIN_CHAIN_ID,
            return_value_test=ReturnValueTest("==", 0),
            parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        )

    # unsupported chain id
    with pytest.raises(InvalidCondition, match="90210 is not a permitted blockchain"):
        _ = RPCCondition(
            method="eth_getBalance",
            chain=90210,  # Beverly Hills Chain :)
            return_value_test=ReturnValueTest("==", 0),
            parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        )

    # invalid chain type provided
    with pytest.raises(ValueError, match="invalid literal for int"):
        _ = RPCCondition(
            method="eth_getBalance",
            chain="chainId",  # should be int not str.
            return_value_test=ReturnValueTest("==", 0),
            parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        )


def test_rpc_condition_schema_validation(rpc_condition):
    condition_dict = rpc_condition.to_dict()

    # no issues here
    RPCCondition.from_dict(condition_dict)

    # no issues with optional name
    condition_dict["name"] = "my_rpc_condition"
    RPCCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo):
        # no chain defined
        condition_dict = rpc_condition.to_dict()
        del condition_dict["chain"]
        RPCCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo):
        # no method defined
        condition_dict = rpc_condition.to_dict()
        del condition_dict["method"]
        RPCCondition.from_dict(condition_dict)

    # no issue with no parameters
    condition_dict = rpc_condition.to_dict()
    del condition_dict["parameters"]
    RPCCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo):
        # no returnValueTest defined
        condition_dict = rpc_condition.to_dict()
        del condition_dict["returnValueTest"]
        RPCCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo):
        # chain id not an integer
        condition_dict["chain"] = str(TESTERCHAIN_CHAIN_ID)
        RPCCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo):
        # chain id not a permitted chain
        condition_dict["chain"] = 90210  # Beverly Hills Chain :)
        RPCCondition.from_dict(condition_dict)


def test_rpc_condition_repr(rpc_condition):
    rpc_condition_str = f"{rpc_condition}"
    assert rpc_condition.__class__.__name__ in rpc_condition_str
    assert f"function={rpc_condition.method}" in rpc_condition_str
    assert f"chain={rpc_condition.chain}" in rpc_condition_str


@pytest.mark.parametrize(
    "invalid_value", ["0x123456", 10.15, [1], [1, 2, 3], [True, [1, 2], "0x0"]]
)
def test_rpc_condition_invalid_comparator_value_type(invalid_value, rpc_condition):
    with pytest.raises(
        InvalidCondition, match=f"should be '{int}' and not '{type(invalid_value)}'"
    ):
        _ = RPCCondition(
            chain=rpc_condition.chain,
            method=rpc_condition.method,
            parameters=rpc_condition.parameters,
            return_value_test=ReturnValueTest(
                comparator=rpc_condition.return_value_test.comparator,
                value=invalid_value,
            ),
        )


def test_rpc_condition_uses_provided_endpoint(mocker):
    # Spy HTTPProvider
    mock_http_provider_spy = mocker.spy(HTTPProvider, "__init__")

    # Mock eth module
    mock_w3 = mocker.Mock()
    mock_w3.eth.get_balance.return_value = 0
    mock_w3.eth.chain_id = 8453

    # Patch RPCCall._configure_w3 method
    mocker.patch(
        "nucypher.policy.conditions.evm.RPCCall._configure_w3", return_value=mock_w3
    )

    # Mock _next_endpoint method
    next_endpoint_spy = mocker.spy(RPCCall, "_next_endpoint")

    rpc_endpoint = "https://base.example.com"
    condition = RPCCondition(
        method="eth_getBalance",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest("==", 0),
        parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        rpc_endpoint=rpc_endpoint,
    )

    providers = {}
    condition.verify(providers=providers)

    # Verify the endpoint was used
    mock_http_provider_spy.assert_called_once_with(ANY, rpc_endpoint)
    next_endpoint_spy.assert_not_called()


def test_rpc_condition_execution_priority(mocker):
    # Mock HTTPProvider
    mock_http_provider_spy = mocker.spy(HTTPProvider, "__init__")

    # Mock eth module with successful response
    mock_eth = mocker.Mock()
    mock_eth.get_balance.return_value = 100  # Set a non-zero balance
    mock_eth.chain_id = TESTERCHAIN_CHAIN_ID

    mock_w3 = mocker.Mock()
    mock_w3.eth = mock_eth
    mock_w3.middleware_onion = mocker.Mock()

    mocker.patch("nucypher.policy.conditions.evm.Web3", return_value=mock_w3)

    # Test Case 1: Chain in providers - should use local provider only
    local_provider = HTTPProvider("https://local-provider.example.com")
    providers = {TESTERCHAIN_CHAIN_ID: {local_provider}}

    condition = RPCCondition(
        method="eth_getBalance",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest("==", 100),  # Match the mock response
        parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        rpc_endpoint="https://fallback.example.com",
    )

    condition.verify(providers=providers)
    mock_http_provider_spy.assert_called_once_with(
        ANY, "https://local-provider.example.com"
    )
    mock_http_provider_spy.reset_mock()

    # Test Case 2: Unsupported chain - should use rpc_endpoint
    unsupported_chain = 99999  # Chain not in _CONDITION_CHAINS
    condition = RPCCondition(
        method="eth_getBalance",
        chain=unsupported_chain,
        return_value_test=ReturnValueTest("==", 0),
        parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        rpc_endpoint="https://fallback.example.com",
    )

    condition.verify(providers=providers)
    mock_http_provider_spy.assert_called_once_with(ANY, "https://fallback.example.com")

    # Test Case 3: Unsupported chain with no rpc_endpoint - should raise error
    with pytest.raises(InvalidCondition):
        condition = RPCCondition(
            method="eth_getBalance",
            chain=unsupported_chain,
            return_value_test=ReturnValueTest("==", 0),
            parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        )
