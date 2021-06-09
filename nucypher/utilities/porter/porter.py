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
from constant_sorrow.constants import NO_CONTROL_PROTOCOL
from flask import request, Response

from nucypher.blockchain.eth.registry import BaseContractRegistry, InMemoryContractRegistry
from nucypher.control.controllers import WebController, JSONRPCController
from nucypher.network.nodes import Learner
from nucypher.utilities.logging import Logger
from nucypher.utilities.porter.control.controllers import PorterCLIController
from nucypher.utilities.porter.control.interfaces import PorterInterface


class Porter(Learner):

    BANNER = r"""

 ______
(_____ \           _
 _____) )__   ____| |_  ____  ____
|  ____/ _ \ / ___)  _)/ _  )/ ___)
| |   | |_| | |   | |_( (/ /| |
|_|    \___/|_|    \___)____)_|

the Pipe for nucypher network operations
"""

    APP_NAME = "Porter"

    _SHORT_LEARNING_DELAY = 2
    _LONG_LEARNING_DELAY = 30
    _ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN = 25

    DEFAULT_PORTER_HTTP_PORT = 9155

    _interface_class = PorterInterface

    def __init__(self,
                 domain: str = None,
                 registry: BaseContractRegistry = None,
                 controller: bool = True,
                 *args, **kwargs):
        self.federated_only = False  # TODO Start with non-federated for now
        self.registry = registry or InMemoryContractRegistry.from_latest_publication(network=domain)

        super().__init__(save_metadata=True, domain=domain, *args, **kwargs)

        self.log = Logger(self.__class__.__name__)

        # Controller Interface
        self.interface = self._interface_class(porter=self)
        self.controller = NO_CONTROL_PROTOCOL
        if controller:
            # TODO need to understand this better - only made it analogous to what was done for characters
            self.make_cli_controller()
        self.log.info(self.BANNER)

    def make_cli_controller(self, crash_on_error: bool = False):
        controller = PorterCLIController(app_name=self.APP_NAME,
                                         crash_on_error=crash_on_error,
                                         interface=self.interface)
        self.controller = controller
        return controller

    def make_rpc_controller(self, crash_on_error: bool = False):
        controller = JSONRPCController(app_name=self.APP_NAME,
                                       crash_on_error=crash_on_error,
                                       interface=self.interface)

        self.controller = controller
        return controller

    def make_web_controller(self, crash_on_error: bool = False):
        controller = WebController(app_name=self.APP_NAME,
                                   crash_on_error=crash_on_error,
                                   interface=self._interface_class(porter=self))
        self.controller = controller

        # Register Flask Decorator
        porter_flask_control = controller.make_control_transport()

        #
        # Porter Control HTTP Endpoints
        #
        @porter_flask_control.route('/get_ursulas', methods=['GET'])
        def get_ursulas() -> Response:
            """Porter control endpoint for sampling Ursulas on behalf of Alice."""
            return controller(method_name='get_ursulas', control_request=request)

        @porter_flask_control.route("/publish_treasure_map", methods=['POST'])
        def publish_treasure_map() -> Response:
            """Porter control endpoint for publishing a treasure map on behalf of Alice."""
            response = controller(method_name='publish_treasure_map', control_request=request)
            return response

        @porter_flask_control.route("/revoke", methods=['POST'])
        def revoke():
            """Porter control endpoint for off-chain revocation of a policy on behalf of Alice."""
            response = controller(method_name='revoke', control_request=request)
            return response

        @porter_flask_control.route('/get_treasure_map', methods=['GET'])
        def get_treasure_map() -> Response:
            """Porter control endpoint for retrieving a treasure map on behalf of Bob."""
            response = controller(method_name='get_treasure_map', control_request=request)
            return response

        @porter_flask_control.route("/exec_work_order", methods=['POST'])
        def exec_work_order() -> Response:
            """Porter control endpoint for executing a PRE work order on behalf of Bob."""
            response = controller(method_name='exec_work_order', control_request=request)
            return response

        return controller
