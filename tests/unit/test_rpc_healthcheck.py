import requests

from nucypher.blockchain.eth.domains import EthChain, PolygonChain, TACoDomain
from nucypher.blockchain.eth.utils import (
    get_default_rpc_endpoints,
    get_healthy_default_rpc_endpoints,
    rpc_endpoint_health_check,
)


def test_rpc_endpoint_health_check(mocker):
    mock_time = mocker.patch("time.time", return_value=1625247600)
    mock_post = mocker.patch("requests.post")

    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"timestamp": hex(1625247600)},
    }
    mock_post.return_value = mock_response

    # Test a healthy endpoint
    assert rpc_endpoint_health_check("http://mockendpoint") is True

    # Test an unhealthy endpoint (drift too large)
    mock_time.return_value = 1625247600 + 100  # System time far ahead
    assert rpc_endpoint_health_check("http://mockendpoint") is False

    # Test request exception
    mock_post.side_effect = requests.exceptions.RequestException
    assert rpc_endpoint_health_check("http://mockendpoint") is False


def test_get_default_rpc_endpoints(mocker):
    mock_get = mocker.patch("requests.get")

    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "1": ["http://endpoint1", "http://endpoint2"],
        "2": ["http://endpoint3", "http://endpoint4"],
    }
    mock_get.return_value = mock_response

    test_domain = TACoDomain(
        name="test",
        eth_chain=EthChain.SEPOLIA,
        polygon_chain=PolygonChain.AMOY,
    )

    expected_result = {
        1: ["http://endpoint1", "http://endpoint2"],
        2: ["http://endpoint3", "http://endpoint4"],
    }
    assert get_default_rpc_endpoints(test_domain) == expected_result
    get_default_rpc_endpoints.cache_clear()

    # Mock a failed response
    mock_get.return_value.status_code = 500
    assert get_default_rpc_endpoints(test_domain) == {}


def test_get_healthy_default_rpc_endpoints(mocker):
    mock_get_endpoints = mocker.patch(
        "nucypher.blockchain.eth.utils.get_default_rpc_endpoints"
    )
    mock_get_endpoints.return_value = {
        1: ["http://endpoint1", "http://endpoint2"],
        2: ["http://endpoint3", "http://endpoint4"],
    }

    mock_health_check = mocker.patch(
        "nucypher.blockchain.eth.utils.rpc_endpoint_health_check"
    )
    mock_health_check.side_effect = (
        lambda endpoint: endpoint == "http://endpoint1"
        or endpoint == "http://endpoint3"
    )

    test_domain = TACoDomain(
        name="mainnet",
        eth_chain=EthChain.MAINNET,
        polygon_chain=PolygonChain.MAINNET,
    )

    healthy_endpoints = get_healthy_default_rpc_endpoints(test_domain)
    assert healthy_endpoints == {1: ["http://endpoint1"], 2: ["http://endpoint3"]}
