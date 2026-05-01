from jsonpath_ng.ext import parse

from nucypher.policy.conditions.json.utils import parse_jsonpath


def test_json_path_parse_utility_caching():
    expr = "$.store.book[0].price"

    # First call - should parse and cache
    json_path_1 = parse_jsonpath(expr)
    # Second call - should retrieve from cache
    json_path_2 = parse_jsonpath(expr)
    assert json_path_1 is json_path_2  # Both results should be the same cached object

    other_expr = "$.store.book[1].price"
    json_path_3 = parse_jsonpath(other_expr)
    assert (
        json_path_3 is not json_path_1
    )  # Different expressions should yield different objects

    direct_json_path = parse(
        other_expr
    )  # call jsonpath library directly to get a new object
    assert (
        direct_json_path is not json_path_3
    )  # Direct parse should yield a different object than the cached one
    assert (
        direct_json_path == json_path_3
    )  # The parser should be "equivalent" in terms of content, even if not the same object
