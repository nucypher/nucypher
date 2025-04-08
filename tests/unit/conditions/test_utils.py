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
from web3.providers import BaseProvider

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
from nucypher.policy.conditions.lingo import ConditionLingo
from nucypher.policy.conditions.utils import (
    CamelCaseSchema,
    ConditionEvalError,
    ConditionProviderManager,
    camel_case_to_snake,
    check_and_convert_big_int_string_to_int,
    evaluate_condition_lingo,
    to_camelcase,
)
from tests.constants import INT256_MIN, UINT256_MAX

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
                providers=ConditionProviderManager(
                    {1: Mock(spec=BaseProvider)}
                ),  # fake provider
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
            providers=ConditionProviderManager(
                {
                    1: Mock(spec=BaseProvider),
                    2: Mock(spec=BaseProvider),
                }
            ),
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


def test_condition_provider_manager(mocker):
    # no condition to chain
    with pytest.raises(NoConnectionToChain, match="No connection to chain ID"):
        manager = ConditionProviderManager(
            providers={2: [mocker.Mock(spec=BaseProvider)]}
        )
        _ = list(manager.web3_endpoints(chain_id=1))

    # invalid provider chain
    manager = ConditionProviderManager(providers={2: [mocker.Mock(spec=BaseProvider)]})
    w3 = mocker.Mock()
    w3.eth.chain_id = (
        1  # make w3 instance created from provider have incorrect chain id
    )
    with patch.object(manager, "_configure_w3", return_value=w3):
        with pytest.raises(
            NoConnectionToChain, match="Problematic provider endpoints for chain ID"
        ):
            _ = list(manager.web3_endpoints(chain_id=2))

    # valid provider chain
    manager = ConditionProviderManager(providers={2: [mocker.Mock(spec=BaseProvider)]})
    with patch.object(manager, "_check_chain_id", return_value=None):
        assert len(list(manager.web3_endpoints(chain_id=2))) == 1

    # multiple providers
    manager = ConditionProviderManager(
        providers={2: [mocker.Mock(spec=BaseProvider), mocker.Mock(spec=BaseProvider)]}
    )
    with patch.object(manager, "_check_chain_id", return_value=None):
        w3_instances = list(manager.web3_endpoints(chain_id=2))
        assert len(w3_instances) == 2
        for w3_instance in w3_instances:
            assert w3_instance  # actual object returned
            assert w3_instance.middleware_onion.get("poa")  # poa middleware injected

    # specific w3 instances
    w3_1 = mocker.Mock()
    w3_1.eth.chain_id = 2
    w3_2 = mocker.Mock()
    w3_2.eth.chain_id = 2
    with patch.object(manager, "_configure_w3", side_effect=[w3_1, w3_2]):
        assert list(manager.web3_endpoints(chain_id=2)) == [w3_1, w3_2]


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
