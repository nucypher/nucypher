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

import time
from typing import Callable, Any, Union

from requests import HTTPError
from web3 import Web3
from web3.types import RPCEndpoint, RPCResponse

from nucypher.utilities.logging import Logger


class RetryRequestMiddleware:
    """
    Automatically retries rpc requests whenever a 429 status code is returned.
    """
    def __init__(self,
                 make_request: Callable[[RPCEndpoint, Any], RPCResponse],
                 w3: Web3,
                 retries: int = 3,
                 exponential_backoff: bool = True):
        self.w3 = w3
        self.make_request = make_request
        self.retries = retries
        self.exponential_backoff = exponential_backoff
        self.logger = Logger(self.__class__.__name__)

    def is_request_result_retry(self, result: Union[RPCResponse, Exception]) -> bool:
        # default retry functionality - look for 429 codes
        # override for additional checks
        if isinstance(result, HTTPError):
            # HTTPError 429
            status_code = result.response.status_code
            if status_code == 429:
                return True
        elif not isinstance(result, Exception):
            # must be RPCResponse
            if 'error' in result:
                error = result['error']
                # either instance of RPCError or str
                if not isinstance(error, str) and error.get('code') == 429:
                    return True

        # not retry result
        return False

    def __call__(self, method, params):
        result = None
        num_iterations = 1 + self.retries  # initial call and subsequent retries
        for i in range(num_iterations):
            try:
                response = self.make_request(method, params)
            except Exception as e:  # type: ignore
                result = e
            else:
                result = response

            # completed request
            if not self.is_request_result_retry(result):
                if i > 0:
                    # not initial call and retry was actually performed
                    self.logger.debug(f'Retried rpc request completed after {i} retries')
                break

            # max retries with no completion
            if i == self.retries:
                self.logger.warn(f'RPC request retried {self.retries} times but was not completed')
                break

            # backoff before next call
            if self.exponential_backoff:
                time.sleep(2 ** (i + 1))  # exponential back-off - 2^(retry number)

        if isinstance(result, Exception):
            raise result
        else:
            # RPCResponse
            return result


class AlchemyRetryRequestMiddleware(RetryRequestMiddleware):
    """
    Automatically retries rpc requests whenever a 429 status code or Alchemy-specific error message is returned.
    """

    def is_request_result_retry(self, result: Union[RPCResponse, Exception]) -> bool:
        """
        Check Alchemy request result for Alchemy-specific retry message.
        """
        # perform additional Alchemy-specific checks
        # - Websocket result:
        #   {'code': -32000,
        #    'message': 'Your app has exceeded its compute units per second capacity. If you have retries enabled, you
        #              can safely ignore this message. If not, check out https://docs.alchemyapi.io/guides/rate-limits'}
        #
        #
        # - HTTP result: is a requests.exception.HTTPError with status code 429
        # (will be checked in original `is_request_result_retry`)

        if super().is_request_result_retry(result):
            return True

        if not isinstance(result, Exception):
            # RPCResponse
            if 'error' in result:
                error = result['error']
                if isinstance(error, str):
                    return 'retries' in error
                else:
                    # RPCError TypeDict
                    return 'retries' in error.get('message')
        # else
        #     exception already checked by superclass - no need to check here

        # not a retry result
        return False


class InfuraRetryRequestMiddleware(RetryRequestMiddleware):
    """
    Automatically retries rpc requests whenever a 429 status code or Infura-specific error message is returned.
    """

    def is_request_result_retry(self, result: Union[RPCResponse, Exception]) -> bool:
        """
        Check Infura request result for Infura-specific retry message.
        """
        # see https://infura.io/docs/ethereum/json-rpc/ratelimits
        # {
        #   "jsonrpc": "2.0",
        #   "id": 1,
        #   "error": {
        #     "code": -32005,
        #     "message": "project ID request rate exceeded",
        #     "data": {
        #       "see": "https://infura.io/docs/ethereum/jsonrpc/ratelimits",
        #       "current_rps": 13.333,
        #       "allowed_rps": 10.0,
        #       "backoff_seconds": 30.0,
        #     }
        #   }
        # }
        if super().is_request_result_retry(result):
            return True

        if not isinstance(result, Exception):
            # RPCResponse
            if 'error' in result:
                error = result['error']
                if not isinstance(error, str):
                    # RPCError TypeDict
                    # TODO should we utilize infura's backoff_seconds value in response?
                    return error.get('code') == -32005 and 'rate exceeded' in error.get('message')
        # else
        #     exceptions already checked by superclass - no need to check here

        # not a retry result
        return False
