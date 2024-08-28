from unittest.mock import ANY, Mock

from web3.exceptions import ExtraDataLengthError
from web3.middleware import geth_poa_middleware
from web3.types import RPCEndpoint, RPCResponse

from nucypher.blockchain.middleware.poa import create_poa_error_redundancy_middleware


def test_request_with_poa_issues():
    make_request = Mock()
    w3 = Mock()
    middleware_onion = Mock()
    w3.middleware_onion = middleware_onion

    poa_name = "poa_test"

    poa_redundancy_middleware = create_poa_error_redundancy_middleware(
        existing_poa_middleware_name=poa_name
    )

    valid_response = RPCResponse(
        jsonrpc="2.0", id=1, result="Geth/v1.14.8-stable-a9523b64/linux-amd64/go1.22.6"
    )

    redundant_middleware = poa_redundancy_middleware(make_request, w3)

    # 1. no poa error, simply return response
    make_request.side_effect = [valid_response]
    response = redundant_middleware(RPCEndpoint("web3_clientVersion"), None)

    assert response == valid_response
    middleware_onion.get.assert_not_called()
    middleware_onion.remove.assert_not_called()
    middleware_onion.inject.assert_not_called()

    # 2. poa error; no prior poa middleware
    make_request.side_effect = [ExtraDataLengthError(), valid_response]
    middleware_onion.get.return_value = None

    response = redundant_middleware(RPCEndpoint("web3_clientVersion"), None)

    assert response == valid_response
    middleware_onion.get.assert_called_once_with(poa_name)
    middleware_onion.remove.assert_not_called()
    middleware_onion.inject.assert_called_once_with(ANY, layer=0, name=poa_name)

    # 3. poa error; prior poa middleware
    make_request.side_effect = [ExtraDataLengthError(), valid_response]
    middleware_onion.get.return_value = geth_poa_middleware
    response = redundant_middleware(RPCEndpoint("web3_clientVersion"), None)

    assert response == valid_response
    assert middleware_onion.get.call_count == 2
    middleware_onion.get.assert_called_with(poa_name)
    middleware_onion.remove.assert_called_once_with(poa_name)
    assert middleware_onion.inject.call_count == 2
    middleware_onion.inject.assert_called_with(ANY, layer=0, name=poa_name)
