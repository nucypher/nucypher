import pytest
from marshmallow import ValidationError

from nucypher.policy.conditions.json.base import JSONPathField


def test_jsonpath_field_valid():
    field = JSONPathField()
    valid_jsonpath = "$.store.book[0].price"
    result = field.deserialize(valid_jsonpath)
    assert result == valid_jsonpath


def test_jsonpath_field_invalid():
    field = JSONPathField()
    invalid_jsonpath = "invalid jsonpath"
    with pytest.raises(
        ValidationError,
        match=f"'{invalid_jsonpath}' is not a valid JSONPath expression",
    ):
        field.deserialize(invalid_jsonpath)
