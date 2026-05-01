import pytest

from nucypher.blockchain.eth.utils import (
    _truncate_response_text,
    obfuscate_rpc_url,
)


@pytest.mark.parametrize(
    "url,expected",
    [
        # Infura-style URLs with API key
        (
            "https://base-sepolia.infura.io/v3/25c3f47d58494214b9cbb7bdc3db99e0",
            "https://base-sepolia.infura.io/v3/25c***",
        ),
        # Alchemy-style URLs with API key
        (
            "https://eth-mainnet.alchemyapi.io/v2/abcdef1234567890abcdef1234567890",
            "https://eth-mainnet.alchemyapi.io/v2/abc***",
        ),
        # URLs without API keys should remain unchanged
        ("https://rpc.ankr.com/eth", "https://rpc.ankr.com/eth"),
        ("https://cloudflare-eth.com", "https://cloudflare-eth.com"),
        # Short path segments preserved
        ("https://example.com/v3/short", "https://example.com/v3/short"),
        # query parameters preserved but API key obfuscated
        (
            "https://eth-mainnet.rpcfast.com?api_key=xbhWBI1Wkguk8SNMu1bvvLurPGLXmgwYeC4S6g2H7WdwFigZSmPWVZRxrskEQwIf",
            "https://eth-mainnet.rpcfast.com?api_key=xbh***",
        ),
        (
            "https://andromeda.metis.io/?owner=1088",
            "https://andromeda.metis.io/?owner=1088",
        ),  # no change since no API key
        (
            "https://andromeda.metis.io/?owner=1088&extra=param",
            "https://andromeda.metis.io/?owner=1088&extra=param",
        ),  # no change since no API key
        (
            "https://andromeda.metis.io/?nokeyvaluepair",
            "https://andromeda.metis.io/?nokeyvaluepair",
        ),  # no change since no API key
        (
            "https://andromeda.metis.io/?nokeyvaluepair&othervalue",
            "https://andromeda.metis.io/?nokeyvaluepair&othervalue",
        ),  # no change since no API key
        (
            "https://andromeda.metis.io/?owner=1088&api_key=abcdef1234567890",
            "https://andromeda.metis.io/?owner=1088&api_key=abc***",
        ),
        (
            "https://api-gateway.skymavis.com/rpc?apikey=9aqYLBbxSC6LROynQJBvKkEIsioqwHmr",
            "https://api-gateway.skymavis.com/rpc?apikey=9aq***",
        ),
        (
            "https://andromeda.metis.io/?api_key=abcdef1234567890&owner=1088",
            "https://andromeda.metis.io/?api_key=abc***&owner=1088",
        ),
        (
            "https://andromeda.metis.io/?owner=1088&api_key=abcdef1234567890&extra=param",
            "https://andromeda.metis.io/?owner=1088&api_key=abc***&extra=param",
        ),
        # ridiculous example of both path and query API keys obfuscated
        (
            "https://eth-mainnet.alchemyapi.io/v2/abcdef1234567890abcdef1234567890?alternative_key_to_use=1234567890abcdef",
            "https://eth-mainnet.alchemyapi.io/v2/abc***?alternative_key_to_use=123***",
        ),
        # Invalid input falls back to placeholder
        (123, "<RPC endpoint>"),
    ],
)
def test_obfuscate_rpc_url(url, expected):
    assert obfuscate_rpc_url(url) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        # Short text unchanged
        ("Short error", "Short error"),
        # Exactly 200 chars unchanged
        ("x" * 200, "x" * 200),
        # Long text truncated with ellipsis
        ("x" * 250, "x" * 200 + "..."),
        # Empty string unchanged
        ("", ""),
    ],
)
def test_truncate_response_text(text, expected):
    assert _truncate_response_text(text) == expected
