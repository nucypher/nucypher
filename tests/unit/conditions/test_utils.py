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
from dataclasses import dataclass
from http import HTTPStatus
from typing import List, Optional, Tuple, Type
from unittest.mock import Mock, patch

import pytest
from marshmallow import fields
from web3 import Web3

from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.policy.conditions.base import Condition
from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT
from nucypher.policy.conditions.evm import ContractCondition, RPCCondition
from nucypher.policy.conditions.exceptions import (
    ConditionEvaluationFailed,
    ContextVariableVerificationFailed,
    InvalidCondition,
    InvalidConditionLingo,
    InvalidContextVariableData,
    NoConnectionToChain,
    RequiredContextVariable,
    ReturnValueEvaluationError,
)
from nucypher.policy.conditions.json.api import JsonApiCondition
from nucypher.policy.conditions.json.json import JsonCondition
from nucypher.policy.conditions.json.rpc import JsonRpcCondition
from nucypher.policy.conditions.jwt import JWTCondition
from nucypher.policy.conditions.lingo import (
    CompoundCondition,
    ConditionLingo,
    ConditionVariable,
    IfThenElseCondition,
    ReturnValueTest,
    SequentialCondition,
)
from nucypher.policy.conditions.signing.base import (
    AbiCallValidation,
    AbiParameterValidation,
    SigningObjectAbiAttributeCondition,
    SigningObjectAttributeCondition,
)
from nucypher.policy.conditions.time import TimeCondition
from nucypher.policy.conditions.utils import (
    DEBUG_CONDITION_LOGICAL_CHECK,
    DEBUG_CONDITION_NOT_EVALUATED,
    CamelCaseSchema,
    ConditionEvalError,
    ConditionProviderManager,
    camel_case_to_snake,
    check_and_convert_big_int_string_to_int,
    evaluate_condition_lingo,
    extract_condition_failure_details,
    to_camelcase,
)
from tests.constants import INT256_MIN, TESTERCHAIN_CHAIN_ID, UINT256_MAX
from tests.unit.conditions.test_jwt_condition import TEST_ECDSA_PUBLIC_KEY

FAILURE_CASE_EXCEPTION_CODE_MATCHING = [
    # (exception, constructor parameters, expected status code)
    (ReturnValueEvaluationError, None, HTTPStatus.BAD_REQUEST),
    (InvalidConditionLingo, None, HTTPStatus.BAD_REQUEST),
    (InvalidCondition, None, HTTPStatus.BAD_REQUEST),
    (RequiredContextVariable, None, HTTPStatus.BAD_REQUEST),
    (InvalidContextVariableData, None, HTTPStatus.BAD_REQUEST),
    (ContextVariableVerificationFailed, None, HTTPStatus.FORBIDDEN),
    (NoConnectionToChain, [1], HTTPStatus.NOT_IMPLEMENTED),
    (ConditionEvaluationFailed, None, HTTPStatus.BAD_REQUEST),
    (Exception, None, HTTPStatus.INTERNAL_SERVER_ERROR),
]


@pytest.mark.parametrize("failure_case", FAILURE_CASE_EXCEPTION_CODE_MATCHING)
def test_evaluate_condition_exception_cases(
    failure_case: Tuple[Type[Exception], Optional[List], int]
):
    exception_class, exception_constructor_params, expected_status_code = failure_case
    exception_constructor_params = exception_constructor_params or []

    condition_lingo = Mock()
    condition_lingo.eval.side_effect = exception_class(*exception_constructor_params)

    with patch(
        "nucypher.policy.conditions.lingo.ConditionLingo.from_dict"
    ) as mocked_from_dict:
        mocked_from_dict.return_value = condition_lingo

        with pytest.raises(ConditionEvalError) as eval_error:
            evaluate_condition_lingo(
                condition_lingo=condition_lingo
            )  # provider and context default to empty dicts
        assert eval_error.value.status_code == expected_status_code


def test_evaluate_condition_invalid_lingo():
    with pytest.raises(ConditionEvalError) as eval_error:
        evaluate_condition_lingo(
            condition_lingo={
                "version": ConditionLingo.VERSION,
                "condition": {"dont_mind_me": "nothing_to_see_here"},
            }
        )  # provider and context default to empty dicts
    assert "Invalid condition grammar" in eval_error.value.message
    assert eval_error.value.status_code == HTTPStatus.BAD_REQUEST


def test_evaluate_condition_eval_returns_false():
    condition_lingo = Mock()
    condition_lingo.eval.return_value = False

    with patch(
        "nucypher.policy.conditions.lingo.ConditionLingo.from_dict"
    ) as mocked_from_dict:
        mocked_from_dict.return_value = condition_lingo

        with pytest.raises(ConditionEvalError) as eval_error:
            evaluate_condition_lingo(
                condition_lingo=condition_lingo,
                providers=ConditionProviderManager({}),
                context={"key": "value"},  # fake context
            )
        assert eval_error.value.status_code == HTTPStatus.FORBIDDEN


def test_evaluate_condition_eval_returns_true():
    condition_lingo = Mock()
    condition_lingo.eval.return_value = True

    with patch(
        "nucypher.policy.conditions.lingo.ConditionLingo.from_dict"
    ) as mocked_from_dict:
        mocked_from_dict.return_value = condition_lingo

        evaluate_condition_lingo(
            condition_lingo=condition_lingo,
            providers=ConditionProviderManager({}),
            context={
                "key1": "value1",
                "key2": "value2",
            },  # multiple values in fake context
        )


@pytest.mark.parametrize(
    "test_case",
    (
        ("nounderscores", "nounderscores"),
        ("one_underscore", "oneUnderscore"),
        ("two_under_scores", "twoUnderScores"),
    ),
)
def test_to_from_camel_case(test_case: Tuple[str, str]):
    # test to_camelcase()
    snake_case, camel_case = test_case
    result = to_camelcase(snake_case)
    assert result == camel_case

    # test camel_case_to_snake()
    result = camel_case_to_snake(camel_case)
    assert result == snake_case


def test_camel_case_schema():
    # test CamelCaseSchema
    @dataclass
    class Function:
        field_name_with_underscores: str

    class FunctionSchema(CamelCaseSchema):
        field_name_with_underscores = fields.Str()

    value = "field_name_value"
    function = Function(field_name_with_underscores=value)
    schema = FunctionSchema()
    output = schema.dump(function)
    assert output == {"fieldNameWithUnderscores": f"{value}"}

    reloaded_function = schema.load(output)
    assert reloaded_function == {"field_name_with_underscores": f"{value}"}


@pytest.mark.parametrize(
    "value, expectedValue",
    [
        # number string
        ("123132312", None),
        ("-1231231", None),
        # big int string of form "<number>n"
        (f"{UINT256_MAX}n", UINT256_MAX),
        (f"{INT256_MIN}n", INT256_MIN),
        (f"{UINT256_MAX*2}n", UINT256_MAX * 2),  # larger than uint256 max
        (f"{INT256_MIN*2}n", INT256_MIN * 2),  # smaller than in256 min
        ("9007199254740992n", 9007199254740992),  # bigger than max safe
        ("-9007199254740992n", -9007199254740992),  # smaller than min safe
        # regular strings
        ("Totally a number", None),
        ("Totally a number that ends with n", None),
        ("0xdeadbeef", None),
        ("fallen", None),
    ],
)
def test_conversion_from_big_int_string(value, expectedValue):
    result = check_and_convert_big_int_string_to_int(value)
    if expectedValue:
        assert result == expectedValue
    else:
        # value unchanged
        assert result == value


class TestExtractConditionFailureDebugMode:
    """Tests for extracting condition failures for debug mode (only on lynx)."""

    @pytest.fixture(scope="function")
    def mock_conditions(self, mocker):
        cond_1 = mocker.Mock(spec=Condition)
        cond_1.verify.return_value = (True, 1)
        cond_1.to_dict.return_value = {"value": 1}

        cond_2 = mocker.Mock(spec=Condition)
        cond_2.verify.return_value = (True, 2)
        cond_2.to_dict.return_value = {"value": 2}

        cond_3 = mocker.Mock(spec=Condition)
        cond_3.verify.return_value = (True, 3)
        cond_3.to_dict.return_value = {"value": 3}

        return cond_1, cond_2, cond_3

    @classmethod
    def verify_simple_condition_failure_details(cls, condition, result):
        # FORMAT:
        # If "return_value_test" present, e.g.:
        # {
        #   "condition": "RPCCondition",
        #   "value_obtained": 12.0,
        #   "check_performed": {
        #     "comparator": "==",
        #     "value": 10.5
        #   }
        # }
        #
        # Else:
        # {
        #   "condition": "JWTCondition",
        #   "value_obtained": "<logical check>"
        # }
        failure_details = extract_condition_failure_details(condition, result)
        assert failure_details["condition"] == str(condition)
        if hasattr(condition, "return_value_test"):
            assert (
                failure_details["check_performed"]
                == condition.return_value_test.to_dict()
            )
        else:
            assert failure_details["check_performed"] == DEBUG_CONDITION_LOGICAL_CHECK

        if isinstance(condition, JWTCondition):
            assert "value_obtained" not in failure_details
        else:
            assert failure_details["value_obtained"] == result

    @pytest.mark.parametrize(
        "condition,result",
        [
            (
                RPCCondition(
                    method="eth_getBalance",
                    chain=TESTERCHAIN_CHAIN_ID,
                    return_value_test=ReturnValueTest(
                        "==", Web3.to_wei(1_000_000, "ether")
                    ),
                    parameters=[USER_ADDRESS_CONTEXT],
                ),
                1234567890,
            ),
            (
                TimeCondition(
                    chain=TESTERCHAIN_CHAIN_ID,
                    return_value_test=ReturnValueTest(">", 2000000000),
                ),
                1600000000,
            ),
            (
                ContractCondition(
                    contract_address="0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
                    method="ownerOf",
                    standard_contract_type="ERC721",
                    chain=TESTERCHAIN_CHAIN_ID,
                    return_value_test=ReturnValueTest("==", ":userAddress"),
                    parameters=[
                        5954,
                    ],
                ),
                NULL_ADDRESS,
            ),
            (
                JsonApiCondition(
                    endpoint="https://api.example.com/data",
                    query="$.store.book[0].title",
                    return_value_test=ReturnValueTest("==", "'Test Title'"),
                ),
                "Different Title",
            ),
            (
                JsonCondition(
                    data=":apiResult",
                    query="$.store.book[0].price",
                    return_value_test=ReturnValueTest("==", 10.5),
                ),
                12.0,
            ),
            (
                JsonRpcCondition(
                    endpoint="https://math.example.com/",
                    method="subtract",
                    params={
                        "value1": 42,
                        "value2": 23,
                    },
                    return_value_test=ReturnValueTest("==", 19),
                ),
                20,
            ),
            (
                JWTCondition(
                    jwt_token=":aContextVariableForJWTs",
                    public_key=TEST_ECDSA_PUBLIC_KEY,
                ),
                None,
            ),
            (
                SigningObjectAttributeCondition(
                    attribute_name="call_data",
                    return_value_test=ReturnValueTest("==", "0x1234567890abcdef"),
                ),
                "0xdeadbeef",
            ),
            (
                SigningObjectAbiAttributeCondition(
                    attribute_name="callData",
                    abi_validation=AbiCallValidation(
                        {
                            "execute(address,uint256,bytes)": [
                                AbiParameterValidation(
                                    parameter_index=2,
                                    nested_abi_validation=AbiCallValidation(
                                        {
                                            "transfer(address,uint256)": [],
                                        }
                                    ),
                                )
                            ],
                        }
                    ),
                ),
                None,
            ),
        ],
    )
    def test_simple_condition_extract_failure_details(self, condition, result):
        self.verify_simple_condition_failure_details(condition, result)

    @pytest.mark.usefixtures("mock_skip_schema_validation")
    def test_if_then_else_condition_extract_failure_details(self, mock_conditions):
        cond_1, cond_2, cond_3 = mock_conditions
        condition = IfThenElseCondition(
            if_condition=cond_1, then_condition=cond_2, else_condition=cond_3
        )
        # Simulate failure in the 'then' branch
        cond_1.verify.return_value = (True, 1)
        cond_2.verify.return_value = (False, 2)

        _, value = condition.verify()
        failure_details_then = extract_condition_failure_details(condition, value)

        # e.g.
        # {
        #     "condition": "IfThenElseCondition(if=Condition, then=Condition, else=Condition)",
        #     "check_performed": "<logical_check>",
        #     "sub_conditions": {
        #         "if_condition": {
        #             "condition": "<Mock spec='Condition' id='5044814768'>",
        #             "value_obtained": 1,
        #             "check_performed": "<logical_check>"
        #         },
        #         "then_condition": {
        #             "condition": "<Mock spec='Condition' id='5044840464'>",
        #             "value_obtained": 2,
        #             "check_performed": "<logical_check>"
        #         },
        #         "else_condition": {
        #             "condition": "<Mock spec='Condition' id='5044757488'>",
        #             "value_obtained": "<not_evaluated>",
        #             "check_performed": "<logical_check>"
        #         }
        #     }
        # }
        assert failure_details_then["condition"] == str(condition)
        assert failure_details_then["sub_conditions"]["if_condition"][
            "condition"
        ] == str(cond_1)
        assert (
            failure_details_then["sub_conditions"]["if_condition"]["value_obtained"]
            == 1
        )
        assert (
            failure_details_then["sub_conditions"]["if_condition"]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert failure_details_then["sub_conditions"]["then_condition"][
            "condition"
        ] == str(cond_2)
        assert (
            failure_details_then["sub_conditions"]["then_condition"]["value_obtained"]
            == 2
        )
        assert (
            failure_details_then["sub_conditions"]["then_condition"]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert failure_details_then["sub_conditions"]["else_condition"][
            "condition"
        ] == str(cond_3)
        assert (
            failure_details_then["sub_conditions"]["else_condition"]["value_obtained"]
            == DEBUG_CONDITION_NOT_EVALUATED
        )
        assert (
            failure_details_then["sub_conditions"]["else_condition"]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        # Simulate failure in the 'else' branch
        cond_1.verify.return_value = (False, 1)
        cond_3.verify.return_value = (False, 3)
        _, value = condition.verify()
        failure_details_else = extract_condition_failure_details(condition, value)
        assert failure_details_else["condition"] == str(condition)

        assert failure_details_else["sub_conditions"]["if_condition"][
            "condition"
        ] == str(cond_1)
        assert (
            failure_details_else["sub_conditions"]["if_condition"]["value_obtained"]
            == 1
        )
        assert (
            failure_details_else["sub_conditions"]["if_condition"]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert failure_details_else["sub_conditions"]["then_condition"][
            "condition"
        ] == str(cond_2)
        assert (
            failure_details_else["sub_conditions"]["then_condition"]["value_obtained"]
            == DEBUG_CONDITION_NOT_EVALUATED
        )
        assert (
            failure_details_else["sub_conditions"]["then_condition"]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert failure_details_else["sub_conditions"]["else_condition"][
            "condition"
        ] == str(cond_3)
        assert (
            failure_details_else["sub_conditions"]["else_condition"]["value_obtained"]
            == 3
        )
        assert (
            failure_details_else["sub_conditions"]["else_condition"]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

    @pytest.mark.usefixtures("mock_skip_schema_validation")
    def test_if_then_else_where_else_is_boolean_extract_failure_details(
        self, mock_conditions
    ):
        cond_1, cond_2, _ = mock_conditions
        condition = IfThenElseCondition(
            if_condition=cond_1, then_condition=cond_2, else_condition=False
        )

        # else executed
        cond_1.verify.return_value = (False, 1)
        _, value = condition.verify()
        assert value == [1, None, False]

        failure_details_else_executed = extract_condition_failure_details(
            condition, value
        )
        assert failure_details_else_executed["condition"] == str(condition)

        assert failure_details_else_executed["sub_conditions"]["if_condition"][
            "condition"
        ] == str(cond_1)
        assert (
            failure_details_else_executed["sub_conditions"]["if_condition"][
                "value_obtained"
            ]
            == value[0]
        )
        assert (
            failure_details_else_executed["sub_conditions"]["if_condition"][
                "check_performed"
            ]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert failure_details_else_executed["sub_conditions"]["then_condition"][
            "condition"
        ] == str(cond_2)
        assert (
            failure_details_else_executed["sub_conditions"]["then_condition"][
                "value_obtained"
            ]
            == DEBUG_CONDITION_NOT_EVALUATED
        )
        assert (
            failure_details_else_executed["sub_conditions"]["then_condition"][
                "check_performed"
            ]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert failure_details_else_executed["sub_conditions"]["else_condition"][
            "condition"
        ] == str(False)

        # else not executed
        cond_1.verify.return_value = (True, 1)
        cond_2.verify.return_value = (False, 2)
        _, value = condition.verify()
        assert value == [1, 2]
        failure_details_else_not_executed = extract_condition_failure_details(
            condition, value
        )
        assert failure_details_else_not_executed["condition"] == str(condition)

        assert failure_details_else_not_executed["sub_conditions"]["if_condition"][
            "condition"
        ] == str(cond_1)
        assert (
            failure_details_else_not_executed["sub_conditions"]["if_condition"][
                "value_obtained"
            ]
            == value[0]
        )
        assert (
            failure_details_else_not_executed["sub_conditions"]["if_condition"][
                "check_performed"
            ]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert failure_details_else_not_executed["sub_conditions"]["then_condition"][
            "condition"
        ] == str(cond_2)
        assert (
            failure_details_else_not_executed["sub_conditions"]["then_condition"][
                "value_obtained"
            ]
            == value[1]
        )
        assert (
            failure_details_else_not_executed["sub_conditions"]["then_condition"][
                "check_performed"
            ]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert failure_details_else_not_executed["sub_conditions"]["else_condition"][
            "condition"
        ] == str(False)
        assert (
            failure_details_else_not_executed["sub_conditions"]["else_condition"][
                "value_obtained"
            ]
            == DEBUG_CONDITION_NOT_EVALUATED
        )

    @pytest.mark.usefixtures("mock_skip_schema_validation")
    def test_compound_condition_extract_failure_details(
        self, mock_conditions, time_condition
    ):
        cond_1, cond_2, cond_3 = mock_conditions
        condition = CompoundCondition(
            operator="and", operands=[cond_1, cond_2, time_condition]
        )

        # Simulate and failing after 2nd condition
        cond_1.verify.return_value = (True, 1)
        cond_2.verify.return_value = (False, 2)

        _, value = condition.verify()
        assert value == [1, 2]
        and_failure_details = extract_condition_failure_details(condition, value)
        # e.g.
        # {
        #     "condition": "Operator=and (NumOperands=3), id=565f46)",
        #     "check_performed": "<logical_check>",
        #     "operator": "and",
        #     "sub_conditions": {
        #         "0": {
        #             "condition": "<Mock spec='Condition' id='5045030256'>",
        #             "value_obtained": 1,
        #             "check_performed": "<logical_check>"
        #         },
        #         "1": {
        #             "condition": "<Mock spec='Condition' id='5045042064'>",
        #             "value_obtained": 2,
        #             "check_performed": "<logical_check>"
        #         },
        #         "2": {
        #             "condition": "TimeCondition(timestamp=0, chain=131277322940537)",
        #             "value_obtained": "<not_evaluated>",
        #             "check_performed": {
        #                 "comparator": ">",
        #                 "value": 0
        #             }
        #         }
        #     }
        #
        # }

        assert and_failure_details["condition"] == str(condition)
        assert and_failure_details["operator"] == "and"

        assert and_failure_details["sub_conditions"][0]["condition"] == str(cond_1)
        assert and_failure_details["sub_conditions"][0]["value_obtained"] == value[0]
        assert (
            and_failure_details["sub_conditions"][0]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert and_failure_details["sub_conditions"][1]["condition"] == str(cond_2)
        assert and_failure_details["sub_conditions"][1]["value_obtained"] == value[1]
        assert (
            and_failure_details["sub_conditions"][1]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert and_failure_details["sub_conditions"][2]["condition"] == str(
            time_condition
        )
        assert (
            and_failure_details["sub_conditions"][2]["value_obtained"]
            == DEBUG_CONDITION_NOT_EVALUATED
        )
        assert (
            and_failure_details["sub_conditions"][2]["check_performed"]
            == time_condition.return_value_test.to_dict()
        )

        # or where all conditions were executed
        cond_1.verify.return_value = (False, 1)
        cond_2.verify.return_value = (False, 2)
        cond_3.verify.return_value = (False, 3)

        condition = CompoundCondition(operator="or", operands=[cond_1, cond_2, cond_3])
        _, value = condition.verify()
        assert value == [1, 2, 3]

        or_failure_details = extract_condition_failure_details(condition, value)
        assert or_failure_details["condition"] == str(condition)
        assert or_failure_details["operator"] == "or"

        assert or_failure_details["sub_conditions"][0]["condition"] == str(cond_1)
        assert or_failure_details["sub_conditions"][0]["value_obtained"] == value[0]
        assert (
            or_failure_details["sub_conditions"][0]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert or_failure_details["sub_conditions"][1]["condition"] == str(cond_2)
        assert or_failure_details["sub_conditions"][1]["value_obtained"] == value[1]
        assert (
            or_failure_details["sub_conditions"][1]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert or_failure_details["sub_conditions"][2]["condition"] == str(cond_3)
        assert or_failure_details["sub_conditions"][2]["value_obtained"] == value[2]
        assert (
            or_failure_details["sub_conditions"][2]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

    @pytest.mark.usefixtures("mock_skip_schema_validation")
    def test_sequential_condition_extract_failure_details(
        self, mock_conditions, rpc_condition
    ):
        cond_1, cond_2, cond_3 = mock_conditions

        var_1 = ConditionVariable("var1", cond_1)
        var_2 = ConditionVariable("var2", cond_2)
        var_3 = ConditionVariable("var3", cond_3)
        var_4 = ConditionVariable("var4", rpc_condition)

        condition = SequentialCondition(
            condition_variables=[var_1, var_2, var_3, var_4],
        )

        # failure on 3rd condition
        cond_1.verify.return_value = (True, 1)
        cond_2.verify.return_value = (True, 2)
        cond_3.verify.return_value = (False, 3)

        _, value = condition.verify(providers=ConditionProviderManager({}))
        sequential_failure_details = extract_condition_failure_details(condition, value)
        # e.g.
        # {
        #     "condition": "SequentialCondition(num_condition_variables=4)",
        #     "check_performed": "<logical_check>",
        #     "sub_conditions": {
        #         "0": {
        #             "condition": "<Mock spec='Condition' id='5013771264'>",
        #             "value_obtained": 1,
        #             "check_performed": "<logical_check>",
        #             "var_name": "var1"
        #         },
        #         "1": {
        #             "condition": "<Mock spec='Condition' id='5013817296'>",
        #             "value_obtained": 2,
        #             "check_performed": "<logical_check>",
        #             "var_name": "var2"
        #         },
        #         "2": {
        #             "condition": "<Mock spec='Condition' id='5013817584'>",
        #             "value_obtained": 3,
        #             "check_performed": "<logical_check>",
        #             "var_name": "var3"
        #         },
        #         "3": {
        #             "condition": "RPCCondition(function=eth_getBalance, chain=131277322940537)",
        #             "value_obtained": "<not_evaluated>",
        #             "check_performed": {
        #                 "comparator": "==",
        #                 "value": 1000000000000000000000000
        #             },
        #             "var_name": "var4"
        #         }
        #     }
        # }

        assert value == [1, 2, 3]

        assert sequential_failure_details["condition"] == str(condition)

        assert sequential_failure_details["sub_conditions"][0]["var_name"] == "var1"
        assert sequential_failure_details["sub_conditions"][0]["condition"] == str(
            cond_1
        )
        assert (
            sequential_failure_details["sub_conditions"][0]["value_obtained"]
            == value[0]
        )
        assert (
            sequential_failure_details["sub_conditions"][0]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert sequential_failure_details["sub_conditions"][1]["var_name"] == "var2"
        assert sequential_failure_details["sub_conditions"][1]["condition"] == str(
            cond_2
        )
        assert (
            sequential_failure_details["sub_conditions"][1]["value_obtained"]
            == value[1]
        )
        assert (
            sequential_failure_details["sub_conditions"][1]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert sequential_failure_details["sub_conditions"][2]["var_name"] == "var3"
        assert sequential_failure_details["sub_conditions"][2]["condition"] == str(
            cond_3
        )
        assert (
            sequential_failure_details["sub_conditions"][2]["value_obtained"]
            == value[2]
        )
        assert (
            sequential_failure_details["sub_conditions"][2]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert sequential_failure_details["sub_conditions"][3]["var_name"] == "var4"
        assert sequential_failure_details["sub_conditions"][3]["condition"] == str(
            rpc_condition
        )
        assert (
            sequential_failure_details["sub_conditions"][3]["value_obtained"]
            == DEBUG_CONDITION_NOT_EVALUATED
        )
        assert (
            sequential_failure_details["sub_conditions"][3]["check_performed"]
            == rpc_condition.return_value_test.to_dict()
        )

    @pytest.mark.usefixtures("mock_skip_schema_validation")
    def test_nested_multicondition_extract_failure_details(
        self, mock_conditions, time_condition
    ):
        cond_1, cond_2, cond_3 = mock_conditions

        inner_compound = CompoundCondition(
            operator="and", operands=[cond_2, time_condition]
        )

        condition = SequentialCondition(
            condition_variables=[
                ConditionVariable(var_name="var1", condition=cond_1),
                ConditionVariable(var_name="var2", condition=inner_compound),
                ConditionVariable(var_name="var3", condition=cond_3),
            ]
        )

        # Simulate failure in the inner 'and' compound condition
        cond_1.verify.return_value = (True, 1)
        cond_2.verify.return_value = (False, 2)
        cond_3.verify.return_value = (False, 3)

        _, value = condition.verify(providers=ConditionProviderManager({}))
        nested_failure_details = extract_condition_failure_details(condition, value)

        assert value == [1, [2]]

        assert nested_failure_details["condition"] == str(condition)

        assert nested_failure_details["sub_conditions"][0]["var_name"] == "var1"
        assert nested_failure_details["sub_conditions"][0]["condition"] == str(cond_1)
        assert nested_failure_details["sub_conditions"][0]["value_obtained"] == value[0]
        assert (
            nested_failure_details["sub_conditions"][0]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        inner_details = nested_failure_details["sub_conditions"][1]
        assert inner_details["var_name"] == "var2"
        assert inner_details["condition"] == str(inner_compound)
        assert inner_details["operator"] == "and"

        assert inner_details["sub_conditions"][0]["condition"] == str(cond_2)
        assert inner_details["sub_conditions"][0]["value_obtained"] == value[1][0]
        assert (
            inner_details["sub_conditions"][0]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert inner_details["sub_conditions"][1]["condition"] == str(time_condition)
        assert (
            inner_details["sub_conditions"][1]["value_obtained"]
            == DEBUG_CONDITION_NOT_EVALUATED
        )
        assert (
            inner_details["sub_conditions"][1]["check_performed"]
            == time_condition.return_value_test.to_dict()
        )

        assert nested_failure_details["sub_conditions"][2]["var_name"] == "var3"
        assert nested_failure_details["sub_conditions"][2]["condition"] == str(cond_3)
        assert (
            nested_failure_details["sub_conditions"][2]["value_obtained"]
            == DEBUG_CONDITION_NOT_EVALUATED
        )
        assert (
            nested_failure_details["sub_conditions"][2]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

    @pytest.mark.usefixtures("mock_skip_schema_validation")
    def test_nested_multiple_if_then_else_extract_failure_details(
        self, mock_conditions
    ):
        cond_1, cond_2, cond_3 = mock_conditions

        inner_if_then_else = IfThenElseCondition(
            if_condition=cond_2, then_condition=cond_3, else_condition=cond_1
        )

        condition = IfThenElseCondition(
            if_condition=cond_1,
            then_condition=inner_if_then_else,
            else_condition=cond_2,
        )

        # Simulate failure in the inner 'then' branch
        cond_1.verify.return_value = (True, 1)
        cond_2.verify.return_value = (True, 2)
        cond_3.verify.return_value = (False, 3)

        _, value = condition.verify()
        nested_failure_details = extract_condition_failure_details(condition, value)

        assert nested_failure_details["condition"] == str(condition)

        assert nested_failure_details["sub_conditions"]["if_condition"][
            "condition"
        ] == str(cond_1)
        assert (
            nested_failure_details["sub_conditions"]["if_condition"]["value_obtained"]
            == 1
        )
        assert (
            nested_failure_details["sub_conditions"]["if_condition"]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        inner_details = nested_failure_details["sub_conditions"]["then_condition"]
        assert inner_details["condition"] == str(inner_if_then_else)

        assert inner_details["sub_conditions"]["if_condition"]["condition"] == str(
            cond_2
        )
        assert inner_details["sub_conditions"]["if_condition"]["value_obtained"] == 2
        assert (
            inner_details["sub_conditions"]["if_condition"]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert inner_details["sub_conditions"]["then_condition"]["condition"] == str(
            cond_3
        )
        assert inner_details["sub_conditions"]["then_condition"]["value_obtained"] == 3
        assert (
            inner_details["sub_conditions"]["then_condition"]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert inner_details["sub_conditions"]["else_condition"]["condition"] == str(
            cond_1
        )
        assert (
            inner_details["sub_conditions"]["else_condition"]["value_obtained"]
            == DEBUG_CONDITION_NOT_EVALUATED
        )
        assert (
            inner_details["sub_conditions"]["else_condition"]["check_performed"]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )

        assert nested_failure_details["sub_conditions"]["else_condition"][
            "condition"
        ] == str(cond_2)
        assert (
            nested_failure_details["sub_conditions"]["else_condition"]["value_obtained"]
            == DEBUG_CONDITION_NOT_EVALUATED
        )
        assert (
            nested_failure_details["sub_conditions"]["else_condition"][
                "check_performed"
            ]
            == DEBUG_CONDITION_LOGICAL_CHECK
        )
