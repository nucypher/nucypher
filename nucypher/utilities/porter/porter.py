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
from typing import List, Optional, Sequence, NamedTuple

from constant_sorrow.constants import NO_CONTROL_PROTOCOL, NO_BLOCKCHAIN_CONNECTION
from eth_typing import ChecksumAddress
from flask import request, Response
from nucypher.crypto.umbral_adapter import PublicKey

from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import BaseContractRegistry, InMemoryContractRegistry

from nucypher.characters.lawful import Ursula

from nucypher.control.controllers import WebController, JSONRPCController
from nucypher.crypto.powers import DecryptingPower
from nucypher.network.nodes import Learner
from nucypher.network import treasuremap
from nucypher.policy.policies import TreasureMapPublisher
from nucypher.policy.reservoir import (
    make_federated_staker_reservoir,
    make_decentralized_staker_reservoir,
    PrefetchStrategy
)
from nucypher.utilities.concurrency import WorkerPool
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

    DEFAULT_EXECUTION_TIMEOUT = 10  # 10s

    DEFAULT_PORT = 9155

    _interface_class = PorterInterface

    class UrsulaInfo(NamedTuple):
        """Simple object that stores relevant Ursula information resulting from sampling."""
        checksum_address: ChecksumAddress
        uri: str
        encrypting_key: PublicKey

    def __init__(self,
                 domain: str = None,
                 registry: BaseContractRegistry = None,
                 controller: bool = True,
                 federated_only: bool = False,
                 node_class: object = Ursula,
                 provider_uri: str = None,
                 *args, **kwargs):
        self.federated_only = federated_only

        if not self.federated_only:
            if not provider_uri:
                raise ValueError('Provider URI is required for decentralized Porter.')

            if not BlockchainInterfaceFactory.is_interface_initialized(provider_uri=provider_uri):
                BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri)

            self.registry = registry or InMemoryContractRegistry.from_latest_publication(network=domain)
            self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.registry)
        else:
            self.registry = NO_BLOCKCHAIN_CONNECTION.bool_value(False)
            node_class.set_federated_mode(federated_only)

        super().__init__(save_metadata=True, domain=domain, node_class=node_class, *args, **kwargs)

        self.log = Logger(self.__class__.__name__)

        # Controller Interface
        self.interface = self._interface_class(porter=self)
        self.controller = NO_CONTROL_PROTOCOL
        if controller:
            # TODO need to understand this better - only made it analogous to what was done for characters
            self.make_cli_controller()
        self.log.info(self.BANNER)

    def get_treasure_map(self, map_identifier: str, bob_encrypting_key: PublicKey):
        return treasuremap.get_treasure_map_from_known_ursulas(learner=self,
                                                               map_identifier=map_identifier,
                                                               bob_encrypting_key=bob_encrypting_key,
                                                               timeout=self.DEFAULT_EXECUTION_TIMEOUT)

    def publish_treasure_map(self, treasure_map_bytes: bytes, bob_encrypting_key: PublicKey) -> None:
        # TODO (#2516): remove hardcoding of 8 nodes
        self.block_until_number_of_known_nodes_is(8, timeout=self.DEFAULT_EXECUTION_TIMEOUT, learn_on_this_thread=True)
        target_nodes = treasuremap.find_matching_nodes(known_nodes=self.known_nodes,
                                                       bob_encrypting_key=bob_encrypting_key)
        treasure_map_publisher = TreasureMapPublisher(treasure_map_bytes=treasure_map_bytes,
                                                      nodes=target_nodes,
                                                      network_middleware=self.network_middleware,
                                                      timeout=self.DEFAULT_EXECUTION_TIMEOUT)
        treasure_map_publisher.start()  # let's do this
        treasure_map_publisher.block_until_success_is_reasonably_likely()

    def get_ursulas(self,
                    quantity: int,
                    duration_periods: int = None,  # optional for federated mode
                    exclude_ursulas: Optional[Sequence[ChecksumAddress]] = None,
                    include_ursulas: Optional[Sequence[ChecksumAddress]] = None) -> List[UrsulaInfo]:
        reservoir = self._make_staker_reservoir(quantity, duration_periods, exclude_ursulas, include_ursulas)
        value_factory = PrefetchStrategy(reservoir, quantity)

        def get_ursula_info(ursula_address) -> Porter.UrsulaInfo:
            if ursula_address not in self.known_nodes:
                raise ValueError(f"{ursula_address} is not known")

            ursula = self.known_nodes[ursula_address]
            try:
                # verify node is valid
                self.network_middleware.client.verify_and_parse_node_or_host_and_port(node_or_sprout=ursula,
                                                                                      host=None,
                                                                                      port=None)

                return Porter.UrsulaInfo(checksum_address=ursula_address,
                                         uri=f"{ursula.rest_interface.formal_uri}",
                                         encrypting_key=ursula.public_keys(DecryptingPower))
            except Exception as e:
                self.log.debug(f"Unable to obtain Ursula information ({ursula_address}): {str(e)}")
                raise

        self.block_until_number_of_known_nodes_is(quantity,
                                                  timeout=self.DEFAULT_EXECUTION_TIMEOUT,
                                                  learn_on_this_thread=True,
                                                  eager=True)

        worker_pool = WorkerPool(worker=get_ursula_info,
                                 value_factory=value_factory,
                                 target_successes=quantity,
                                 timeout=self.DEFAULT_EXECUTION_TIMEOUT,
                                 stagger_timeout=1,
                                 threadpool_size=quantity)
        worker_pool.start()
        successes = worker_pool.block_until_target_successes()
        ursulas_info = successes.values()
        return list(ursulas_info)

    def exec_work_order(self, ursula_address: ChecksumAddress, work_order_payload: bytes) -> bytes:
        self.block_until_specific_nodes_are_known(addresses={ursula_address}, learn_on_this_thread=True)
        ursula = self.known_nodes[ursula_address]
        ursula_rest_response = self.network_middleware.send_work_order_payload_to_ursula(
            ursula=ursula,
            work_order_payload=work_order_payload)
        result = ursula_rest_response.content
        return result

    def _make_staker_reservoir(self,
                               quantity: int,
                               duration_periods: int = None,  # optional for federated mode
                               exclude_ursulas: Optional[Sequence[ChecksumAddress]] = None,
                               include_ursulas: Optional[Sequence[ChecksumAddress]] = None):
        if self.federated_only:
            sample_size = quantity - (len(include_ursulas) if include_ursulas else 0)
            if not self.block_until_number_of_known_nodes_is(sample_size,
                                                             timeout=self.DEFAULT_EXECUTION_TIMEOUT,
                                                             learn_on_this_thread=True):
                raise ValueError("Unable to learn about sufficient Ursulas")
            return make_federated_staker_reservoir(known_nodes=self.known_nodes,
                                                   exclude_addresses=exclude_ursulas,
                                                   include_addresses=include_ursulas)
        else:
            if not duration_periods:
                raise ValueError("Duration periods must be provided in decentralized mode")
            return make_decentralized_staker_reservoir(staking_agent=self.staking_agent,
                                                       duration_periods=duration_periods,
                                                       exclude_addresses=exclude_ursulas,
                                                       include_addresses=include_ursulas)

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

    def make_web_controller(self, crash_on_error: bool = False, htpasswd_filepath: str = None):
        controller = WebController(app_name=self.APP_NAME,
                                   crash_on_error=crash_on_error,
                                   interface=self._interface_class(porter=self))
        self.controller = controller

        # Register Flask Decorator
        porter_flask_control = controller.make_control_transport()
        if htpasswd_filepath:
            try:
                from flask_htpasswd import HtPasswdAuth
            except ImportError:
                raise ImportError('Porter installation is required for basic authentication '
                                  '- run "pip install nucypher[porter]" and try again.')

            porter_flask_control.config['FLASK_HTPASSWD_PATH'] = htpasswd_filepath
            # ensure basic auth required for all endpoints
            porter_flask_control.config['FLASK_AUTH_ALL'] = True
            _ = HtPasswdAuth(app=porter_flask_control)

        #
        # Porter Control HTTP Endpoints
        #
        @porter_flask_control.route('/get_ursulas', methods=['GET'])
        def get_ursulas() -> Response:
            """Porter control endpoint for sampling Ursulas on behalf of Alice."""
            response = controller(method_name='get_ursulas', control_request=request)
            return response

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
