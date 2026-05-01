from functools import lru_cache
from typing import Any, Optional

from jsonpath_ng.exceptions import JsonPathLexerError, JsonPathParserError
from jsonpath_ng.ext import parse

from nucypher.policy.conditions.context import resolve_any_context_variables
from nucypher.policy.conditions.exceptions import ConditionEvaluationFailed


def query_json_data(data: Any, query: Optional[str], **context) -> Any:
    """
    Shared utility to query JSON data with a JSONPath expression.
    Handles context variable resolution and query execution.
    """
    if not query:
        return data  # no query, return raw data

    resolved_query = resolve_any_context_variables(query, **context)

    try:
        expression = parse_jsonpath(resolved_query)
        matches = expression.find(data)
        if not matches:
            message = f"No matches found for the JSONPath query: {resolved_query}"
            raise ConditionEvaluationFailed(message)
    except (JsonPathLexerError, JsonPathParserError) as jsonpath_err:
        raise ConditionEvaluationFailed(
            f"JSONPath error: {jsonpath_err}"
        ) from jsonpath_err

    if len(matches) > 1:
        result = [match.value for match in matches]
    else:
        result = matches[0].value

    return result


@lru_cache(maxsize=512)
def parse_jsonpath(expr: str):
    return parse(expr)
