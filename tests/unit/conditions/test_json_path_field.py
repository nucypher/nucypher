import pytest
from marshmallow import ValidationError

from nucypher.policy.conditions.json.base import JSONPathField


def test_jsonpath_field_valid():
    field = JSONPathField()
    valid_jsonpath = "$.store.book[0].price"
    result = field.deserialize(valid_jsonpath)
    assert result == valid_jsonpath


@pytest.mark.parametrize(
    "invalid_jsonpath",
    [
        "invalid jsonpath",
        "}{[]$%",
        12,
        12.25,
        True,
    ],
)
def test_jsonpath_field_invalid(invalid_jsonpath):
    field = JSONPathField()
    with pytest.raises(ValidationError):
        field.deserialize(invalid_jsonpath)
