import json

import pytest
from nucypher_core import Conditions

from nucypher.characters.lawful import Ursula
from nucypher.policy.conditions.exceptions import *
from nucypher.policy.conditions.lingo import ConditionLingo
from tests.utils.middleware import MockRestMiddleware


def _policy_info_kwargs(enacted_policy):
    return dict(
        encrypted_treasure_map=enacted_policy.treasure_map,
        alice_verifying_key=enacted_policy.publisher_verifying_key,
    )


def test_single_retrieve_with_truthy_conditions(enacted_policy, bob, ursulas, mocker):
    from nucypher_core import MessageKit

    reencrypt_spy = mocker.spy(Ursula, '_reencrypt')

    bob.remember_node(ursulas[0])
    bob.start_learning_loop()

    conditions = [
        {"returnValueTest": {"value": 0, "comparator": ">"}, "method": "timelock"},
        {"operator": "and"},
        {
            "returnValueTest": {"value": 99999999999999999, "comparator": "<"},
            "method": "timelock",
        },
    ]
    json_conditions = json.dumps(conditions)
    rust_conditions = Conditions(json_conditions)
    message_kits = [MessageKit(enacted_policy.public_key, b"lab", rust_conditions)]

    cleartexts = bob.retrieve_and_decrypt(
        message_kits=message_kits,
        **_policy_info_kwargs(enacted_policy),
    )

    assert b'lab' in cleartexts
    assert reencrypt_spy.call_count == enacted_policy.threshold


def test_single_retrieve_with_falsy_conditions(enacted_policy, bob, ursulas, mocker):
    from nucypher_core import MessageKit

    reencrypt_spy = mocker.spy(Ursula, '_reencrypt')
    mocker.patch.object(ConditionLingo, 'eval', return_value=False)
    reencrypt_http_spy = mocker.spy(MockRestMiddleware, 'reencrypt')

    # not actually used for eval, but satisfies serializers
    conditions = Conditions(
        json.dumps(
            [{"returnValueTest": {"value": 0, "comparator": ">"}, "method": "timelock"}]
        )
    )

    bob.start_learning_loop()

    message_kits = [MessageKit(enacted_policy.public_key, b"radio", conditions)]

    with pytest.raises(Ursula.NotEnoughUrsulas):
        bob.retrieve_and_decrypt(
            message_kits=message_kits,
            **_policy_info_kwargs(enacted_policy),
        )

    reencrypt_spy.assert_not_called()
    assert isinstance(reencrypt_http_spy.spy_exception, MockRestMiddleware.Unauthorized)


FAILURE_MESSAGE = "I’ve failed over and over and over again in my life. And that is why I succeed."  # -- Michael Jordan

FAILURE_CASE_EXCEPTION_CODE_MATCHING = [
    # (condition exception class, exception parameters, middleware exception class)
    (ReturnValueEvaluationError, MockRestMiddleware.BadRequest),
    (InvalidConditionLingo, MockRestMiddleware.BadRequest),
    (InvalidCondition, MockRestMiddleware.BadRequest),
    (RequiredContextVariable, MockRestMiddleware.BadRequest),
    (InvalidContextVariableData, MockRestMiddleware.BadRequest),
    (ContextVariableVerificationFailed, MockRestMiddleware.Unauthorized),
    (NoConnectionToChain, MockRestMiddleware.UnexpectedResponse),
    (ConditionEvaluationFailed, MockRestMiddleware.BadRequest),
    (ValueError, MockRestMiddleware.UnexpectedResponse),
]


@pytest.mark.parametrize(
    "eval_failure_exception_class, middleware_exception_class",
    FAILURE_CASE_EXCEPTION_CODE_MATCHING,
)
def test_middleware_handling_of_failed_condition_responses(
    eval_failure_exception_class,
    middleware_exception_class,
    mocker,
    enacted_policy,
    bob,
    mock_rest_middleware,
):
    # we use a failed condition for reencryption to test conversion of response codes to middleware exceptions
    from nucypher_core import MessageKit

    reencrypt_http_spy = mocker.spy(MockRestMiddleware, "reencrypt")

    # not actually used for eval, but satisfies serializers
    conditions = Conditions(
        json.dumps(
            [
                {
                    "returnValueTest": {"value": 0, "comparator": ">"},
                    "method": "timelock",
                }
            ]
        )
    )

    bob.start_learning_loop()

    message_kits = [MessageKit(enacted_policy.public_key, b"radio", conditions)]

    # use string message or chain id as exception parameter
    chain_id = 1
    exception_parameter = (
        FAILURE_MESSAGE
        if eval_failure_exception_class != NoConnectionToChain
        else chain_id
    )
    mocker.patch.object(
        ConditionLingo,
        "eval",
        side_effect=eval_failure_exception_class(exception_parameter),
    )

    with pytest.raises(Ursula.NotEnoughUrsulas):
        # failed retrieval because of failed exception
        bob.retrieve_and_decrypt(
            message_kits=message_kits,
            encrypted_treasure_map=enacted_policy.treasure_map,
            alice_verifying_key=enacted_policy.publisher_verifying_key,
        )

    actual_exception = reencrypt_http_spy.spy_exception
    assert type(actual_exception) == middleware_exception_class  # be specific
    # verify message is not in bytes form
    assert "b'" not in str(actual_exception)  # no byte string included in message
    assert str(exception_parameter) in str(actual_exception)
