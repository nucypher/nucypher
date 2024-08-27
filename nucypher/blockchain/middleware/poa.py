from typing import Any, Callable

from web3 import Web3
from web3.exceptions import ExtraDataLengthError
from web3.middleware import geth_poa_middleware
from web3.types import RPCEndpoint, RPCResponse

from nucypher.utilities.logging import Logger


class POAErrorRedundancyMiddleware:
    """
    Redundant middleware for replacing already added named poa middleware if ExtraDataLengthError
    still encountered. Extra layer of defense in case random POA error is observed
    """

    POA_MIDDLEWARE_NAME = "poa"

    def __init__(
        self,
        make_request: Callable[[RPCEndpoint, Any], RPCResponse],
        w3: Web3,
        existing_poa_middleware_name: str = POA_MIDDLEWARE_NAME,
    ):
        self.w3 = w3
        self.make_request = make_request
        self.existing_poa_middleware_name = existing_poa_middleware_name
        self.logger = Logger(self.__class__.__name__)

    def __call__(self, method, params) -> RPCResponse:
        try:
            response = self.make_request(method, params)
        except ExtraDataLengthError:
            self.logger.warn(
                "RPC request failed due to extraData error; re-injecting poa middleware and retrying"
            )
            # add / replace existing poa middleware; replacement seems unlikely but just in case
            if self.w3.middleware_onion.get(self.existing_poa_middleware_name):
                # we can't have > 1 geth_poa_middleware added (event with different names) so the
                # removal-then-add is just for safety.
                self.w3.middleware_onion.remove(self.existing_poa_middleware_name)
            self.w3.middleware_onion.inject(
                geth_poa_middleware, layer=0, name=self.existing_poa_middleware_name
            )

            # try again
            response = self.make_request(method, params)

        return response
