from unittest.mock import Mock

import maya
from web3.types import RPCEndpoint

from nucypher.blockchain.middleware.retry import RetryRequestMiddleware
from tests.constants import RPC_TOO_MANY_REQUESTS


# TODO - since this test does exponential backoff it takes >= 2^1 = 2s, should we only run on CI?
def test_request_with_retry_exponential_backoff():
    retries = 1
    make_request = Mock()

    # Retry Case - RPCResponse fails due to limits, and retry required
    make_request.return_value = RPC_TOO_MANY_REQUESTS

    retry_middleware = RetryRequestMiddleware(make_request=make_request,
                                              w3=Mock(),
                                              retries=1,
                                              exponential_backoff=True)

    start = maya.now()
    retry_response = retry_middleware(RPCEndpoint('web3_client_version'), None)
    end = maya.now()

    assert retry_response == RPC_TOO_MANY_REQUESTS
    assert make_request.call_count == (retries + 1)  # initial call, and then the number of retries

    # check exponential backoff
    delta = end - start
    assert delta.total_seconds() >= 2**retries
