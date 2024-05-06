import pytest

from nucypher.policy.conditions.address import AddressMatchCondition
from nucypher.policy.conditions.exceptions import InvalidCondition
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest
from tests.constants import TESTERCHAIN_CHAIN_ID


def test_invalid_address_condition():
    # invalid condition type
    with pytest.raises(InvalidCondition, match=ConditionType.ADDRESS.value):
        _ = AddressMatchCondition(
            condition_type=ConditionType.COMPOUND.value,
            return_value_test=ReturnValueTest(
                "==", "0xaDD9D957170dF6F33982001E4c22eCCdd5539118"
            ),
            chain=TESTERCHAIN_CHAIN_ID,
            method=AddressMatchCondition.METHOD,
            parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        )

    # invalid method
    with pytest.raises(InvalidCondition):
        _ = AddressMatchCondition(
            return_value_test=ReturnValueTest(
                "==", "0xaDD9D957170dF6F33982001E4c22eCCdd5539118"
            ),
            chain=TESTERCHAIN_CHAIN_ID,
            method="wrong_address_match",
            parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        )

    # chain id not permitted
    with pytest.raises(InvalidCondition):
        _ = AddressMatchCondition(
            return_value_test=ReturnValueTest(
                "==", "0xaDD9D957170dF6F33982001E4c22eCCdd5539118"
            ),
            chain=90210,  # Beverly Hills Chain :)
            method=AddressMatchCondition.METHOD,
            parameters=["0xaDD9D957170dF6F33982001E4c22eCCdd5539118"],
        )


def test_address_condition_schema_validation(address_condition):
    condition_dict = address_condition.to_dict()

    # no issues here
    AddressMatchCondition.validate(condition_dict)

    # no issues with optional name
    condition_dict["name"] = "my_address_condition"
    AddressMatchCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # no method
        condition_dict = address_condition.to_dict()
        del condition_dict["method"]
        AddressMatchCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # no returnValueTest defined
        condition_dict = address_condition.to_dict()
        del condition_dict["returnValueTest"]
        AddressMatchCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # invalid method name
        condition_dict["method"] = "my_address_match"
        AddressMatchCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # chain id not an integer
        condition_dict["chain"] = str(TESTERCHAIN_CHAIN_ID)
        AddressMatchCondition.validate(condition_dict)

    with pytest.raises(InvalidCondition):
        # chain id not a permitted chain
        condition_dict["chain"] = 90210  # Beverly Hills Chain :)
        AddressMatchCondition.validate(condition_dict)


@pytest.mark.parametrize("invalid_value", [10.15, [1], [1, 2, 3], [True, [1, 2]]])
def test_time_condition_invalid_comparator_value_type(invalid_value, address_condition):
    with pytest.raises(InvalidCondition, match="must be a string"):
        _ = AddressMatchCondition(
            chain=address_condition.chain,
            method=address_condition.method,
            parameters=address_condition.parameters,
            return_value_test=ReturnValueTest(
                comparator=address_condition.return_value_test.comparator,
                value=invalid_value,
            ),
        )
