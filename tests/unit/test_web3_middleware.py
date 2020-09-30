"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

from typing import Any
from unittest.mock import Mock

import maya
import pytest
from requests import HTTPError
from web3.types import RPCResponse, RPCError, RPCEndpoint

from nucypher.blockchain.middleware.retry import RetryRequestMiddleware, AlchemyRetryRequestMiddleware, \
    InfuraRetryRequestMiddleware

TOO_MANY_REQUESTS = {
    "jsonrpc": "2.0",
    "error": {
        "code": 429,
        "message": "Too many concurrent requests"
    }
}

SUCCESSFUL_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": "Geth/v1.9.20-stable-979fc968/linux-amd64/go1.15"
}

RETRY_REQUEST_CLASSES = (RetryRequestMiddleware, AlchemyRetryRequestMiddleware, InfuraRetryRequestMiddleware)


@pytest.mark.parametrize('retry_middleware_class', RETRY_REQUEST_CLASSES)
def test_is_request_result_retry(retry_middleware_class):
    # base checks
    retry_middleware = retry_middleware_class(make_request=Mock(), w3=Mock())

    assert retry_middleware.is_request_result_retry(result=TOO_MANY_REQUESTS)

    http_error = HTTPError(response=Mock(status_code=429))
    assert retry_middleware.is_request_result_retry(result=http_error)

    assert not retry_middleware.is_request_result_retry(result=SUCCESSFUL_RESPONSE)


@pytest.mark.parametrize('retry_middleware_class', RETRY_REQUEST_CLASSES)
def test_request_with_retry(retry_middleware_class):
    retries = 4
    make_request = Mock()
    retry_middleware = retry_middleware_class(make_request=make_request,
                                              w3=Mock(),
                                              retries=retries,
                                              exponential_backoff=False)

    # Retry Case - RPCResponse fails due to limits, and retry required
    make_request.return_value = TOO_MANY_REQUESTS

    retry_response = retry_middleware(method=RPCEndpoint('web3_clientVersion'), params=None)
    assert retry_response == TOO_MANY_REQUESTS
    assert make_request.call_count == (retries + 1)   # initial call, and then the number of retries


@pytest.mark.parametrize('retry_middleware_class', RETRY_REQUEST_CLASSES)
def test_request_with_non_retry_exception(retry_middleware_class):
    def forbidden_request(method: RPCEndpoint, params: Any):
        raise HTTPError(response=Mock(status_code=400))

    make_request = Mock()
    make_request.side_effect = forbidden_request
    retry_middleware = retry_middleware_class(make_request=make_request, w3=Mock(), exponential_backoff=False)
    with pytest.raises(HTTPError):
        retry_middleware(method=RPCEndpoint('web3_clientVersion'), params=None)

    assert make_request.call_count == 1  # only initial call, exception gets raised


@pytest.mark.parametrize('retry_middleware_class', RETRY_REQUEST_CLASSES)
def test_request_success_with_no_retry(retry_middleware_class):
    # Success Case - retry not needed
    make_request = Mock()
    make_request.return_value = SUCCESSFUL_RESPONSE

    retry_middleware = retry_middleware_class(make_request=make_request,
                                              w3=Mock(),
                                              retries=10,
                                              exponential_backoff=False)
    retry_response = retry_middleware(method=RPCEndpoint('web3_clientVersion'), params=None)
    assert retry_response == SUCCESSFUL_RESPONSE
    assert make_request.call_count == 1  # first call was successful, no need for retries


# TODO - since this test does exponential backoff it takes >= 2^1 = 2s, should we only run on circleci?
def test_request_with_retry_exponential_backoff():
    retries = 1
    make_request = Mock()

    # Retry Case - RPCResponse fails due to limits, and retry required
    make_request.return_value = TOO_MANY_REQUESTS

    retry_middleware = RetryRequestMiddleware(make_request=make_request,
                                              w3=Mock(),
                                              retries=1,
                                              exponential_backoff=True)

    start = maya.now()
    retry_response = retry_middleware(RPCEndpoint('web3_clientVersion'), None)
    end = maya.now()

    assert retry_response == TOO_MANY_REQUESTS
    assert make_request.call_count == (retries + 1)  # initial call, and then the number of retries

    # check exponential backoff
    delta = end - start
    assert delta.total_seconds() >= 2**retries


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
