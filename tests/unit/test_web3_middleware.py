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
from requests import HTTPError, Response
from web3.types import RPCResponse, RPCError, RPCEndpoint

from nucypher.blockchain.middleware.retry import RetryRequestMiddleware, AlchemyRetryRequestMiddleware, \
    InfuraRetryRequestMiddleware


def test_is_request_result_retry():
    retry_middleware = RetryRequestMiddleware(make_request=Mock(), w3=Mock())

    retry_response = RPCResponse(error=RPCError(code=429, message='Too many concurrent requests'))
    assert retry_middleware.is_request_result_retry(result=retry_response)

    response = Response()
    response.status_code = 429
    http_error = HTTPError(response=response)
    assert retry_middleware.is_request_result_retry(result=http_error)

    successful_response = RPCResponse(id=0, result='Geth/v1.9.20-stable-979fc968/linux-amd64/go1.15')
    assert not retry_middleware.is_request_result_retry(result=successful_response)


def test_request_with_retry():
    retries = 4
    make_request = Mock()
    retry_middleware = RetryRequestMiddleware(make_request=make_request,
                                              w3=Mock(),
                                              retries=retries,
                                              exponential_backoff=False)

    # Retry Case - RPCResponse fails due to limits, and retry required
    test_response = RPCResponse(error=RPCError(code=429, message='Too many concurrent requests'))
    make_request.return_value = test_response

    retry_response = retry_middleware(method=RPCEndpoint('eth_blockNumber'), params=None)
    assert retry_response == test_response
    assert make_request.call_count == (retries + 1)   # initial call, and then the number of retries


def test_request_with_non_retry_exception():
    def forbidden_request(method: RPCEndpoint, params: Any):
        response = Response()
        response.status_code = 400
        raise HTTPError(response=response)

    make_request = Mock()
    make_request.side_effect = forbidden_request
    retry_middleware = RetryRequestMiddleware(make_request=make_request, w3=Mock(), exponential_backoff=False)
    with pytest.raises(HTTPError):
        retry_middleware(method=RPCEndpoint('eth_blockNumber'), params=None)

    assert make_request.call_count == 1  # only initial call, exception gets raised


def test_request_success_with_no_retry():
    # Success Case - retry not needed
    make_request = Mock()
    successful_response = RPCResponse(id=0, result=12345678)
    make_request.return_value = successful_response

    retry_middleware = RetryRequestMiddleware(make_request=make_request,
                                              w3=Mock(),
                                              retries=10,
                                              exponential_backoff=False)
    retry_response = retry_middleware(method=RPCEndpoint('eth_blockNumber'), params=None)
    assert retry_response == successful_response
    assert make_request.call_count == 1  # first call was successful, no need for retries


# TODO - since this test does exponential backoff it takes >= 2^1 = 2s, should we only run on circleci?
def test_request_with_retry_exponential_backoff():
    retries = 1
    make_request = Mock()

    # Retry Case - RPCResponse fails due to limits, and retry required
    test_response = RPCResponse(error=RPCError(code=429, message='Too many concurrent requests'))
    make_request.return_value = test_response

    retry_middleware = RetryRequestMiddleware(make_request=make_request,
                                              w3=Mock(),
                                              retries=1,
                                              exponential_backoff=True)

    start = maya.now()
    retry_response = retry_middleware(RPCEndpoint('eth_blockNumber'), None)
    end = maya.now()

    assert retry_response == test_response
    assert make_request.call_count == (retries + 1)  # initial call, and then the number of retries

    # check exponential backoff
    delta = end - start
    assert delta.total_seconds() >= 2**retries


def test_alchemy_request_with_retry():
    retries = 4

    # Retry Case - RPCResponse fails due to limits, and retry required
    test_responses = [
        # failures
        (RPCResponse(error=RPCError(code=-32000,
                                   message='Your app has exceeded its compute units per second capacity. If you have '
                                           'retries enabled, you can safely ignore this message. If not, '
                                           'check out https://docs.alchemyapi.io/guides/rate-limits')),
         retries + 1),

        (RPCResponse(error='Your app has exceeded its compute units per second capacity. If you have retries enabled, '
                          'you can safely ignore this message. If not, '
                          'check out https://docs.alchemyapi.io/guides/rate-limits'),
         retries + 1),

        (RPCResponse(error=RPCError(code=429, message='Too many concurrent requests')),
         retries + 1), # on their website, but never observed in the wild

        # successes
        (RPCResponse(id=0, result='Geth/v1.9.20-stable-979fc968/linux-amd64/go1.15'),
         1)
    ]
    for test_response, num_calls in test_responses:
        make_request = Mock()
        make_request.return_value = test_response
        retry_middleware = AlchemyRetryRequestMiddleware(make_request=make_request,
                                                         w3=Mock(),
                                                         retries=retries,
                                                         exponential_backoff=False)

        response = retry_middleware(method=RPCEndpoint('eth_blockNumber'), params=None)

        assert response == test_response
        assert make_request.call_count == num_calls   # initial call, and then the number of retries


def test_infura_request_with_retry():
    retries = 4

    # Retry Case - RPCResponse fails due to limits, and retry required
    test_responses = [
        # failures
        (RPCResponse(error=RPCError(code=-32005,
                                    message='project ID request rate exceeded')),
         retries + 1),

        # successes
        (RPCResponse(id=0, result='Geth/v1.9.20-stable-979fc968/linux-amd64/go1.15'),
         1)
    ]

    for test_response, num_calls in test_responses:
        make_request = Mock()
        make_request.return_value = test_response
        retry_middleware = InfuraRetryRequestMiddleware(make_request=make_request,
                                                        w3=Mock(),
                                                        retries=retries,
                                                        exponential_backoff=False)

        response = retry_middleware(method=RPCEndpoint('eth_blockNumber'), params=None)

        assert response == test_response
        assert make_request.call_count == num_calls
