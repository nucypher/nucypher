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
from http import HTTPStatus
from typing import List, Tuple, Type
from unittest.mock import Mock

import pytest
from web3.providers import BaseProvider

from nucypher.policy.conditions._utils import evaluate_conditions
from nucypher.policy.conditions.exceptions import *

FAILURE_CASE_EXCEPTION_CODE_MATCHING = [
    # (exception, constructor parameters, expected status code)
    (ReturnValueEvaluationError, [], HTTPStatus.BAD_REQUEST),
    (InvalidCondition, [], HTTPStatus.BAD_REQUEST),
    (RequiredContextVariable, [], HTTPStatus.BAD_REQUEST),
    (InvalidContextVariableData, [], HTTPStatus.BAD_REQUEST),
    (ContextVariableVerificationFailed, [], HTTPStatus.FORBIDDEN),
    (NoConnectionToChain, [1], HTTPStatus.NOT_IMPLEMENTED),
    (ConditionEvaluationFailed, [], HTTPStatus.BAD_REQUEST),
    (Exception, [], HTTPStatus.INTERNAL_SERVER_ERROR),
]


@pytest.mark.parametrize("failure_case", FAILURE_CASE_EXCEPTION_CODE_MATCHING)
def test_evaluate_condition_exception_cases(
    failure_case: Tuple[Type[Exception], List, int]
):
    exception_class = failure_case[0]
    exception_constructor_params = failure_case[1]
    expected_status_code = failure_case[2]

    condition_lingo = Mock()
    condition_lingo.eval.side_effect = exception_class(*exception_constructor_params)

    eval_error = evaluate_conditions(
        lingo=condition_lingo
    )  # provider and context default to empty dicts
    assert eval_error
    assert eval_error.status_code == expected_status_code


def test_evaluate_condition_eval_returns_false():
    condition_lingo = Mock()
    condition_lingo.eval.return_value = False
    eval_error = evaluate_conditions(
        lingo=condition_lingo,
        providers={1: Mock(spec=BaseProvider)},  # fake provider
        context={"key": "value"},  # fake context
    )
    assert eval_error
    assert eval_error.status_code == HTTPStatus.FORBIDDEN


def test_evaluate_condition_eval_returns_true():
    condition_lingo = Mock()
    condition_lingo.eval.return_value = True
    eval_error = evaluate_conditions(
        lingo=condition_lingo,
        providers={
            1: Mock(spec=BaseProvider),
            2: Mock(spec=BaseProvider),
        },  # multiple fake provider
        context={"key1": "value1", "key2": "value2"},  # multiple values in fake context
    )

    assert not eval_error
