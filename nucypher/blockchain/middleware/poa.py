from typing import Any, Callable

from web3 import Web3
from web3.exceptions import ExtraDataLengthError
from web3.middleware import geth_poa_middleware
from web3.types import Middleware, RPCEndpoint, RPCResponse

from nucypher.utilities.logging import Logger


def create_poa_error_redundancy_middleware(
    existing_poa_middleware_name: str = "poa",
) -> Middleware:
    """
    Redundant middleware for replacing already added named poa middleware if ExtraDataLengthError
    still encountered. Extra layer of defense in case random POA error is observed.
    """

    def poa_error_redundancy_middleware(
        make_request: Callable[[RPCEndpoint, Any], RPCResponse], _w3: "Web3"
    ) -> Callable[[RPCEndpoint, Any], RPCResponse]:
        logger = Logger("POAErrorRedundancyMiddleware")

        def middleware(method: RPCEndpoint, params: Any) -> RPCResponse:
            try:
                response = make_request(method, params)
            except ExtraDataLengthError:
                logger.warn(
                    "RPC request failed due to extraData error; re-injecting poa middleware and retrying"
                )
                # add / replace existing poa middleware; replacement seems unlikely but just in case
                if _w3.middleware_onion.get(existing_poa_middleware_name):
                    # we can't have > 1 geth_poa_middleware added (event with different names) so the
                    # removal-then-add is just for safety.
                    _w3.middleware_onion.remove(existing_poa_middleware_name)
                _w3.middleware_onion.inject(
                    geth_poa_middleware, layer=0, name=existing_poa_middleware_name
                )

                # try again
                response = make_request(method, params)

            return response

        return middleware

    return poa_error_redundancy_middleware
