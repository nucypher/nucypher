from typing import Any
from unittest.mock import Mock

import pytest
from requests import HTTPError
from web3.types import RPCResponse, RPCError, RPCEndpoint

from nucypher.blockchain.middleware.retry import (
    RetryRequestMiddleware,
    AlchemyRetryRequestMiddleware,
    InfuraRetryRequestMiddleware
)
from tests.constants import RPC_TOO_MANY_REQUESTS, RPC_SUCCESSFUL_RESPONSE

RETRY_REQUEST_CLASSES = (RetryRequestMiddleware, AlchemyRetryRequestMiddleware, InfuraRetryRequestMiddleware)


@pytest.mark.parametrize('retry_middleware_class', RETRY_REQUEST_CLASSES)
def test_is_request_result_retry(retry_middleware_class):
    # base checks
    retry_middleware = retry_middleware_class(make_request=Mock(), w3=Mock())

    assert retry_middleware.is_request_result_retry(result=RPC_TOO_MANY_REQUESTS)

    http_error = HTTPError(response=Mock(status_code=429))
    assert retry_middleware.is_request_result_retry(result=http_error)

    assert not retry_middleware.is_request_result_retry(result=RPC_SUCCESSFUL_RESPONSE)


@pytest.mark.parametrize('retry_middleware_class', RETRY_REQUEST_CLASSES)
def test_request_with_retry(retry_middleware_class):
    retries = 4
    make_request = Mock()
    retry_middleware = retry_middleware_class(make_request=make_request,
                                              w3=Mock(),
                                              retries=retries,
                                              exponential_backoff=False)

    # Retry Case - RPCResponse fails due to limits, and retry required
    make_request.return_value = RPC_TOO_MANY_REQUESTS

    retry_response = retry_middleware(method=RPCEndpoint('web3_client_version'), params=None)
    assert retry_response == RPC_TOO_MANY_REQUESTS
    assert make_request.call_count == (retries + 1)   # initial call, and then the number of retries


@pytest.mark.parametrize('retry_middleware_class', RETRY_REQUEST_CLASSES)
def test_request_with_non_retry_exception(retry_middleware_class):
    def forbidden_request(method: RPCEndpoint, params: Any):
        raise HTTPError(response=Mock(status_code=400))

    make_request = Mock()
    make_request.side_effect = forbidden_request
    retry_middleware = retry_middleware_class(make_request=make_request, w3=Mock(), exponential_backoff=False)
    with pytest.raises(HTTPError):
        retry_middleware(method=RPCEndpoint('web3_client_version'), params=None)

    assert make_request.call_count == 1  # only initial call, exception gets raised


@pytest.mark.parametrize('retry_middleware_class', RETRY_REQUEST_CLASSES)
def test_request_success_with_no_retry(retry_middleware_class):
    # Success Case - retry not needed
    make_request = Mock()
    make_request.return_value = RPC_SUCCESSFUL_RESPONSE

    retry_middleware = retry_middleware_class(make_request=make_request,
                                              w3=Mock(),
                                              retries=10,
                                              exponential_backoff=False)
    retry_response = retry_middleware(method=RPCEndpoint('web3_client_version'), params=None)
    assert retry_response == RPC_SUCCESSFUL_RESPONSE
    assert make_request.call_count == 1  # first call was successful, no need for retries


def test_alchemy_request_with_retry():
    retries = 4

    test_responses = [
        # alchemy-specific failures
        RPCResponse(error=RPCError(code=-32000,
                                   message='Your app has exceeded its compute units per second capacity. If you have '
                                           'retries enabled, you can safely ignore this message. If not, '
                                           'check out https://docs.alchemyapi.io/guides/rate-limits')),

        RPCResponse(error='Your app has exceeded its compute units per second capacity. If you have retries enabled, '
                          'you can safely ignore this message. If not, '
                          'check out https://docs.alchemyapi.io/guides/rate-limits')
    ]
    for test_response in test_responses:
        make_request = Mock()
        make_request.return_value = test_response
        retry_middleware = AlchemyRetryRequestMiddleware(make_request=make_request,
                                                         w3=Mock(),
                                                         retries=retries,
                                                         exponential_backoff=False)

        response = retry_middleware(method=RPCEndpoint('eth_call'), params=None)

        assert response == test_response
        assert make_request.call_count == (retries + 1)   # initial call, and then the number of retries


def test_infura_request_with_retry():
    retries = 4

    test_responses = [
        # infura-specific failures
        {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {
                "code": -32005,
                "message": "project ID request rate exceeded",
                "data": {
                   "see": "https://infura.io/docs/ethereum/jsonrpc/ratelimits",
                   "current_rps": 13.333,
                   "allowed_rps": 10.0,
                   "backoff_seconds": 30.0,
                }
            }
        },
    ]

    for test_response in test_responses:
        make_request = Mock()
        make_request.return_value = test_response
        retry_middleware = InfuraRetryRequestMiddleware(make_request=make_request,
                                                        w3=Mock(),
                                                        retries=retries,
                                                        exponential_backoff=False)

        response = retry_middleware(method=RPCEndpoint('eth_blockNumber'), params=None)

        assert response == test_response
        assert make_request.call_count == (retries + 1)  # initial call, and then the number of retries
