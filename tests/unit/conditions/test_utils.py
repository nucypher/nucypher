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

from nucypher.policy.conditions.exceptions import *
from nucypher.policy.conditions.utils import (
    CamelCaseSchema,
    camel_case_to_snake,
    evaluate_condition_lingo,
    to_camelcase,
    validate_condition_lingo,
)
from tests.constants import TESTERCHAIN_CHAIN_ID

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

        eval_error = evaluate_condition_lingo(
            condition_lingo=condition_lingo
        )  # provider and context default to empty dicts
        assert eval_error
        assert eval_error.status_code == expected_status_code


def test_evaluate_condition_eval_returns_false():
    condition_lingo = Mock()
    condition_lingo.eval.return_value = False

    with patch(
        "nucypher.policy.conditions.lingo.ConditionLingo.from_dict"
    ) as mocked_from_dict:
        mocked_from_dict.return_value = condition_lingo

        eval_error = evaluate_condition_lingo(
            condition_lingo=condition_lingo,
            providers={1: Mock(spec=BaseProvider)},  # fake provider
            context={"key": "value"},  # fake context
        )
        assert eval_error
        assert eval_error.status_code == HTTPStatus.FORBIDDEN


def test_evaluate_condition_eval_returns_true():
    condition_lingo = Mock()
    condition_lingo.eval.return_value = True

    with patch(
        "nucypher.policy.conditions.lingo.ConditionLingo.from_dict"
    ) as mocked_from_dict:
        mocked_from_dict.return_value = condition_lingo

        eval_error = evaluate_condition_lingo(
            condition_lingo=condition_lingo,
            providers={
                1: Mock(spec=BaseProvider),
                2: Mock(spec=BaseProvider),
            },  # multiple fake provider
            context={
                "key1": "value1",
                "key2": "value2",
            },  # multiple values in fake context
        )

        assert eval_error is None


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


def test_condition_lingo_validation(compound_lingo):
    # valid compound lingo; no issues here
    compound_lingo_dict = compound_lingo.to_dict()
    validate_condition_lingo(compound_lingo_dict)

    invalid_operator_lingo = {
        "operator": "AND_OPERATOR",
        "operands": [
            {
                "returnValueTest": {"value": 0, "comparator": ">"},
                "method": "blocktime",
                "chain": TESTERCHAIN_CHAIN_ID,
            },
            {
                "returnValueTest": {"value": 99999999999999999, "comparator": "<"},
                "method": "blocktime",
                "chain": TESTERCHAIN_CHAIN_ID,
            },
        ],
    }
    with pytest.raises(InvalidCondition):
        validate_condition_lingo(invalid_operator_lingo)

    # invalid condition
    with pytest.raises(InvalidConditionLingo):
        validate_condition_lingo({"dont_mind_me": "nothing_to_see_here"})
