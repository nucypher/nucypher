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


import json
from base64 import b64encode
from collections import OrderedDict
from functools import partial
from json.decoder import JSONDecodeError
from typing import Dict, Iterable, List, Set, Tuple, Union

import maya
import requests
import time
from bytestring_splitter import BytestringKwargifier, BytestringSplittingError
from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from constant_sorrow import constants
from constant_sorrow.constants import INCLUDED_IN_BYTESTRING, PUBLIC_ONLY, STRANGER_ALICE
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurve
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import load_pem_x509_certificate, Certificate, NameOID
from eth_utils import to_checksum_address
from flask import request, Response
from twisted.internet import threads
from twisted.logger import Logger
from umbral import pre
from umbral.keys import UmbralPublicKey
from umbral.kfrags import KFrag
from umbral.pre import UmbralCorrectnessError
from umbral.signing import Signature

import nucypher
from nucypher.blockchain.eth.actors import BlockchainPolicyAuthor, Worker
from nucypher.blockchain.eth.agents import StakingEscrowAgent, ContractAgency
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.blockchain.eth.token import WorkTracker
from nucypher.characters.banners import ALICE_BANNER, BOB_BANNER, ENRICO_BANNER, URSULA_BANNER
from nucypher.characters.base import Character, Learner
from nucypher.characters.control.controllers import (
    AliceJSONController,
    BobJSONController,
    EnricoJSONController,
    WebController
)
from nucypher.config.storages import NodeStorage, ForgetfulNodeStorage
from nucypher.crypto.api import keccak_digest, encrypt_and_sign
from nucypher.crypto.constants import PUBLIC_KEY_LENGTH, PUBLIC_ADDRESS_LENGTH
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import SigningPower, DecryptingPower, DelegatingPower, TransactingPower, PowerUpError
from nucypher.crypto.signing import InvalidSignature
from nucypher.keystore.keypairs import HostingKeypair
from nucypher.keystore.threading import ThreadedSession
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import RestMiddleware, UnexpectedResponse, NotFound
from nucypher.network.nicknames import nickname_from_seed
from nucypher.network.nodes import Teacher, NodeSprout
from nucypher.network.protocols import InterfaceInfo, parse_node_uri
from nucypher.network.server import ProxyRESTServer, TLSHostingPower, make_rest_app


class Alice(Character, BlockchainPolicyAuthor):
    banner = ALICE_BANNER
    _controller_class = AliceJSONController
    _default_crypto_powerups = [SigningPower, DecryptingPower, DelegatingPower]

    def __init__(self,

                 # Mode
                 is_me: bool = True,
                 federated_only: bool = False,

                 # Ownership
                 checksum_address: str = None,
                 client_password: str = None,

                 # Ursulas
                 m: int = None,
                 n: int = None,

                 # Policy Value
                 rate: int = None,
                 duration_periods: int = None,

                 # Middleware
                 timeout: int = 10,  # seconds  # TODO: configure
                 network_middleware: RestMiddleware = None,
                 controller: bool = True,

                 *args, **kwargs) -> None:

        #
        # Fallback Policy Values
        #

        self.timeout = timeout

        if is_me:
            self.m = m
            self.n = n
        else:
            self.m = STRANGER_ALICE
            self.n = STRANGER_ALICE

        Character.__init__(self,
                           known_node_class=Ursula,
                           is_me=is_me,
                           federated_only=federated_only,
                           checksum_address=checksum_address,
                           network_middleware=network_middleware,
                           *args, **kwargs)

        if is_me and not federated_only:  # TODO: #289
            transacting_power = TransactingPower(account=self.checksum_address,
                                                 password=client_password,
                                                 provider_uri=self.provider_uri)
            self._crypto_power.consume_power_up(transacting_power)
            BlockchainPolicyAuthor.__init__(self,
                                            registry=self.registry,
                                            rate=rate,
                                            duration_periods=duration_periods,
                                            checksum_address=checksum_address)

        if is_me and controller:
            self.controller = self._controller_class(alice=self)

        self.log = Logger(self.__class__.__name__)
        self.log.info(self.banner)

        self.active_policies = dict()
        self.revocation_kits = dict()

    def add_active_policy(self, active_policy):
        """
        Adds a Policy object that is active on the NuCypher network to Alice's
        `active_policies` dictionary by the policy ID.
        The policy ID is a Keccak hash of the policy label and Bob's stamp bytes
        """
        if active_policy.id in self.active_policies:
            raise KeyError("Policy already exists in active_policies.")
        self.active_policies[active_policy.id] = active_policy

    def generate_kfrags(self,
                        bob: 'Bob',
                        label: bytes,
                        m: int = None,
                        n: int = None
                        ) -> List:
        """
        Generates re-encryption key frags ("KFrags") and returns them.

        These KFrags can be used by Ursula to re-encrypt a Capsule for Bob so
        that he can activate the Capsule.

        :param bob: Bob instance which will be able to decrypt messages re-encrypted with these kfrags.
        :param m: Minimum number of kfrags needed to activate a Capsule.
        :param n: Total number of kfrags to generate
        """

        bob_encrypting_key = bob.public_keys(DecryptingPower)
        delegating_power = self._crypto_power.power_ups(DelegatingPower)
        return delegating_power.generate_kfrags(bob_pubkey_enc=bob_encrypting_key,
                                                signer=self.stamp,
                                                label=label,
                                                m=m or self.m,
                                                n=n or self.n)

    def create_policy(self, bob: "Bob", label: bytes, **policy_params):
        """
        Create a Policy to share uri with bob.
        Generates KFrags and attaches them.
        """

        policy_params = self.generate_policy_parameters(**policy_params)
        N = policy_params.pop('n')

        # Generate KFrags
        public_key, kfrags = self.generate_kfrags(bob=bob,
                                                  label=label,
                                                  m=policy_params['m'],
                                                  n=N)

        payload = dict(label=label,
                       bob=bob,
                       kfrags=kfrags,
                       public_key=public_key,
                       m=policy_params['m'],
                       expiration=policy_params['expiration'])

        if self.federated_only:
            # Use known nodes
            from nucypher.policy.policies import FederatedPolicy
            policy = FederatedPolicy(alice=self, **payload)

        else:
            # Sample from blockchain via PolicyManager
            from nucypher.policy.policies import BlockchainPolicy
            payload.update(**policy_params)
            policy = BlockchainPolicy(alice=self, **payload)

        return policy

    def generate_policy_parameters(self,
                                   m: int = None,
                                   n: int = None,
                                   duration_periods: int = None,
                                   expiration: maya.MayaDT = None,
                                   *args, **kwargs
                                   ) -> dict:
        """
        Construct policy creation from parameters or overrides.
        """

        if not duration_periods and not expiration:
            raise ValueError("Policy end time must be specified as 'expiration' or 'duration_periods', got neither.")

        # Merge injected and default params.
        m = m or self.m
        n = n or self.n
        base_payload = dict(m=m, n=n, expiration=expiration)

        # Calculate Policy Rate and Value
        if not self.federated_only:
            payload = super().generate_policy_parameters(number_of_ursulas=n,
                                                         duration_periods=duration_periods,
                                                         expiration=expiration,
                                                         *args, **kwargs)
            base_payload.update(payload)
        elif not expiration:
            raise TypeError("For a federated policy, you must specify expiration (duration_periods don't count).")
        return base_payload

    def grant(self,
              bob: "Bob",
              label: bytes,
              handpicked_ursulas: set = None,
              discover_on_this_thread: bool = True,
              timeout: int = None,
              publish_treasure_map: bool = True,
              **policy_params):

        timeout = timeout or self.timeout

        #
        # Policy Creation
        #

        if handpicked_ursulas:
            # This might be the first time alice learns about the handpicked Ursulas.
            for handpicked_ursula in handpicked_ursulas:
                self.remember_node(node=handpicked_ursula)

        policy = self.create_policy(bob=bob, label=label, **policy_params)
        self.log.debug(f"Succesfully created {policy} ... ")

        #
        # We'll find n Ursulas by default.  It's possible to "play the field" by trying different
        # value and expiration combinations on a limited number of Ursulas;
        # Users may decide to inject some market strategies here.
        #
        # TODO: 289

        # If we're federated only, we need to block to make sure we have enough nodes.
        if self.federated_only and len(self.known_nodes) < policy.n:
            good_to_go = self.block_until_number_of_known_nodes_is(number_of_nodes_to_know=policy.n,
                                                                   learn_on_this_thread=discover_on_this_thread,
                                                                   timeout=timeout)
            if not good_to_go:
                raise ValueError(
                    "To make a Policy in federated mode, you need to know about "
                    "all the Ursulas you need (in this case, {}); there's no other way to "
                    "know which nodes to use.  Either pass them here or when you make the Policy, "
                    "or run the learning loop on a network with enough Ursulas.".format(policy.n))

        self.log.debug(f"Making arrangements for {policy} ... ")
        policy.make_arrangements(network_middleware=self.network_middleware,
                                 handpicked_ursulas=handpicked_ursulas)

        # REST call happens here, as does population of TreasureMap.
        self.log.debug(f"Enacting {policy} ... ")
        policy.enact(network_middleware=self.network_middleware, publish=publish_treasure_map)
        return policy  # Now with TreasureMap affixed!

    def get_policy_encrypting_key_from_label(self, label: bytes) -> UmbralPublicKey:
        alice_delegating_power = self._crypto_power.power_ups(DelegatingPower)
        policy_pubkey = alice_delegating_power.get_pubkey_from_label(label)
        return policy_pubkey

    def revoke(self, policy) -> Dict:
        """
        Parses the treasure map and revokes arrangements in it.
        If any arrangements can't be revoked, then the node_id is added to a
        dict as a key, and the revocation and Ursula's response is added as
        a value.
        """
        try:
            # Wait for a revocation threshold of nodes to be known ((n - m) + 1)
            revocation_threshold = ((policy.n - policy.treasure_map.m) + 1)
            self.block_until_specific_nodes_are_known(
                policy.revocation_kit.revokable_addresses,
                allow_missing=(policy.n - revocation_threshold))

        except self.NotEnoughTeachers:
            raise  # TODO

        else:
            failed_revocations = dict()
            for node_id in policy.revocation_kit.revokable_addresses:
                ursula = self.known_nodes[node_id]
                revocation = policy.revocation_kit[node_id]
                try:
                    response = self.network_middleware.revoke_arrangement(ursula, revocation)
                except NotFound:
                    failed_revocations[node_id] = (revocation, NotFound)
                except UnexpectedResponse:
                    failed_revocations[node_id] = (revocation, UnexpectedResponse)
                else:
                    if response.status_code != 200:
                        raise self.ActorError(f"Failed to revoke {policy.id} with status code {response.status_code}")

        return failed_revocations

    def decrypt_message_kit(self,
                            message_kit: UmbralMessageKit,
                            data_source: Character,
                            label: bytes
                            ) -> List[bytes]:

        """
        Decrypt this Alice's own encrypted data.

        I/O signatures match Bob's retrieve interface.
        """

        cleartexts = [self.verify_from(
            data_source,
            message_kit,
            signature=message_kit.signature,
            decrypt=True,
            label=label
        )]
        return cleartexts

    # def make_rpc_controller(drone_alice, crash_on_error: bool = False):
    #     app_name = bytes(drone_alice.stamp).hex()[:6]
    #     controller = JSONRPCController(app_name=app_name,
    #                                    character_controller=drone_alice.controller,
    #                                    crash_on_error=crash_on_error)
    #
    #     drone_alice.controller = controller
    #     alice_rpc_control = controller.make_control_transport(rpc_controller=controller)
    #     return controller

    def make_web_controller(drone_alice, crash_on_error: bool = False):
        app_name = bytes(drone_alice.stamp).hex()[:6]
        controller = WebController(app_name=app_name,
                                   character_controller=drone_alice.controller,
                                   crash_on_error=crash_on_error)
        drone_alice.controller = controller

        # Register Flask Decorator
        alice_flask_control = controller.make_control_transport()

        #
        # Character Control HTTP Endpoints
        #

        @alice_flask_control.route('/public_keys', methods=['GET'])
        def public_keys():
            """
            Character control endpoint for getting Alice's encrypting and signing public keys
            """
            return controller(interface=controller._internal_controller.public_keys,
                              control_request=request)

        @alice_flask_control.route("/create_policy", methods=['PUT'])
        def create_policy() -> Response:
            """
            Character control endpoint for creating a policy and making
            arrangements with Ursulas.
            """
            response = controller(interface=controller._internal_controller.create_policy,
                                  control_request=request)
            return response

        @alice_flask_control.route("/decrypt", methods=['POST'])
        def decrypt():
            """
            Character control endpoint for decryption of Alice's own policy data.
            """

            response = controller(
                interface=controller._internal_controller.decrypt,
                control_request=request
            )
            return response

        @alice_flask_control.route('/derive_policy_encrypting_key/<label>', methods=['POST'])
        def derive_policy_encrypting_key(label) -> Response:
            """
            Character control endpoint for deriving a policy encrypting given a unicode label.
            """
            response = controller(interface=controller._internal_controller.derive_policy_encrypting_key,
                                  control_request=request,
                                  label=label)
            return response

        @alice_flask_control.route("/grant", methods=['PUT'])
        def grant() -> Response:
            """
            Character control endpoint for policy granting.
            """
            response = controller(interface=controller._internal_controller.grant, control_request=request)
            return response

        @alice_flask_control.route("/revoke", methods=['DELETE'])
        def revoke():
            """
            Character control endpoint for policy revocation.
            """
            response = controller(interface=controller._internal_controller.revoke,
                                  control_request=request)
            return response

        return controller


class Bob(Character):
    banner = BOB_BANNER
    _controller_class = BobJSONController

    _default_crypto_powerups = [SigningPower, DecryptingPower]

    class IncorrectCFragsReceived(Exception):
        """
        Raised when Bob detects incorrect CFrags returned by some Ursulas
        """

        def __init__(self, evidence: List):
            self.evidence = evidence

    def __init__(self, controller: bool = True, *args, **kwargs) -> None:
        Character.__init__(self, known_node_class=Ursula, *args, **kwargs)

        if controller:
            self.controller = self._controller_class(bob=self)

        from nucypher.policy.collections import WorkOrderHistory  # Need a bigger strategy to avoid circulars.
        self._saved_work_orders = WorkOrderHistory()

        self.log = Logger(self.__class__.__name__)
        self.log.info(self.banner)

    def _pick_treasure_map(self, treasure_map=None, map_id=None):
        if not treasure_map:
            if map_id:
                treasure_map = self.treasure_maps[map_id]
            else:
                raise ValueError("You need to pass either treasure_map or map_id.")
        elif map_id:
            raise ValueError("Don't pass both treasure_map and map_id - pick one or the other.")
        return treasure_map

    def peek_at_treasure_map(self, treasure_map=None, map_id=None):
        """
        Take a quick gander at the TreasureMap matching map_id to see which
        nodes are already known to us.

        Don't do any learning, pinging, or anything other than just seeing
        whether we know or don't know the nodes.

        Return two sets: nodes that are unknown to us, nodes that are known to us.
        """
        treasure_map = self._pick_treasure_map(treasure_map, map_id)

        # The intersection of the map and our known nodes will be the known Ursulas...
        known_treasure_ursulas = treasure_map.destinations.keys() & self.known_nodes.addresses()

        # while the difference will be the unknown Ursulas.
        unknown_treasure_ursulas = treasure_map.destinations.keys() - self.known_nodes.addresses()

        return unknown_treasure_ursulas, known_treasure_ursulas

    def follow_treasure_map(self,
                            treasure_map=None,
                            map_id=None,
                            block=False,
                            new_thread=False,
                            timeout=10,
                            allow_missing=0):
        """
        Follows a known TreasureMap, looking it up by map_id.

        Determines which Ursulas are known and which are unknown.

        If block, will block until either unknown nodes are discovered or until timeout seconds have elapsed.
        After timeout seconds, if more than allow_missing nodes are still unknown, raises NotEnoughUrsulas.

        If block and new_thread, does the same thing but on a different thread, returning a Deferred which
        fires after the blocking has concluded.

        Otherwise, returns (unknown_nodes, known_nodes).

        # TODO: Check if nodes are up, declare them phantom if not.
        """
        treasure_map = self._pick_treasure_map(treasure_map, map_id)

        unknown_ursulas, known_ursulas = self.peek_at_treasure_map(treasure_map=treasure_map)

        if unknown_ursulas:
            self.learn_about_specific_nodes(unknown_ursulas)

        self._push_certain_newly_discovered_nodes_here(known_ursulas, unknown_ursulas)

        if block:
            if new_thread:
                return threads.deferToThread(self.block_until_specific_nodes_are_known, unknown_ursulas,
                                             timeout=timeout,
                                             allow_missing=allow_missing)
            else:
                self.block_until_specific_nodes_are_known(unknown_ursulas,
                                                          timeout=timeout,
                                                          allow_missing=allow_missing,
                                                          learn_on_this_thread=True)

        return unknown_ursulas, known_ursulas, treasure_map.m

    def get_treasure_map(self, alice_verifying_key, label):
        _hrac, map_id = self.construct_hrac_and_map_id(verifying_key=alice_verifying_key, label=label)

        if not self.known_nodes and not self._learning_task.running:
            # Quick sanity check - if we don't know of *any* Ursulas, and we have no
            # plans to learn about any more, than this function will surely fail.
            raise self.NotEnoughTeachers

        treasure_map = self.get_treasure_map_from_known_ursulas(self.network_middleware,
                                                                map_id)

        alice = Alice.from_public_keys(verifying_key=alice_verifying_key)
        compass = self.make_compass_for_alice(alice)
        try:
            treasure_map.orient(compass)
        except treasure_map.InvalidSignature:
            raise  # TODO: Maybe do something here?
        else:
            self.treasure_maps[map_id] = treasure_map

        return treasure_map

    def make_compass_for_alice(self, alice):
        return partial(self.verify_from, alice, decrypt=True)

    def construct_policy_hrac(self, verifying_key: Union[bytes, UmbralPublicKey], label: bytes) -> bytes:
        _hrac = keccak_digest(bytes(verifying_key) + self.stamp + label)
        return _hrac

    def construct_hrac_and_map_id(self, verifying_key, label):
        hrac = self.construct_policy_hrac(verifying_key, label)
        map_id = keccak_digest(bytes(verifying_key) + hrac).hex()
        return hrac, map_id

    def get_treasure_map_from_known_ursulas(self, network_middleware, map_id):
        """
        Iterate through the nodes we know, asking for the TreasureMap.
        Return the first one who has it.
        """
        from nucypher.policy.collections import TreasureMap
        for node in self.known_nodes.shuffled():
            try:
                response = network_middleware.get_treasure_map_from_node(node=node, map_id=map_id)
            except NodeSeemsToBeDown:
                continue

            if response.status_code == 200 and response.content:
                try:
                    treasure_map = TreasureMap.from_bytes(response.content)
                except InvalidSignature:
                    # TODO: What if a node gives a bunk TreasureMap?
                    raise
                break
            else:
                continue  # TODO: Actually, handle error case here.
        else:
            # TODO: Work out what to do in this scenario -
            #       if Bob can't get the TreasureMap, he needs to rest on the learning mutex or something.
            raise TreasureMap.NowhereToBeFound

        return treasure_map

    def generate_work_orders(self, map_id, *capsules, num_ursulas=None, cache=False):
        from nucypher.policy.collections import WorkOrder  # Prevent circular import

        try:
            treasure_map_to_use = self.treasure_maps[map_id]
        except KeyError:
            raise KeyError(
                "Bob doesn't have the TreasureMap {}; can't generate work orders.".format(map_id))

        generated_work_orders = OrderedDict()

        if not treasure_map_to_use:
            raise ValueError(
                "Bob doesn't have a TreasureMap to match any of these capsules: {}".format(
                    capsules))

        for node_id, arrangement_id in treasure_map_to_use:
            # TODO: Bob crashes if he hasn't learned about this Ursula #999
            ursula = self.known_nodes[node_id]

            capsules_to_include = []
            for capsule in capsules:
                if not capsule in self._saved_work_orders[node_id]:
                    capsules_to_include.append(capsule)

            if capsules_to_include:
                work_order = WorkOrder.construct_by_bob(
                    arrangement_id, capsules_to_include, ursula, self)
                generated_work_orders[node_id] = work_order
                # TODO: Fix this. It's always taking the last capsule
                if cache:
                    self._saved_work_orders[node_id][capsule] = work_order

            if num_ursulas == len(generated_work_orders):
                break

        return generated_work_orders

    def get_reencrypted_cfrags(self, work_order):
        cfrags = self.network_middleware.reencrypt(work_order)
        for task in work_order.tasks:
            # TODO: Maybe just update the work order here instead of setting it anew.
            work_orders_by_ursula = self._saved_work_orders[work_order.ursula.checksum_address]
            work_orders_by_ursula[task.capsule] = work_order
        return cfrags

    def join_policy(self, label, alice_verifying_key, node_list=None, block=False):
        if node_list:
            self._node_ids_to_learn_about_immediately.update(node_list)
        treasure_map = self.get_treasure_map(alice_verifying_key, label)
        self.follow_treasure_map(treasure_map=treasure_map, block=block)

    def retrieve(self, message_kit, data_source, alice_verifying_key, label, cache=False):
        # Try our best to get an UmbralPublicKey from input
        alice_verifying_key = UmbralPublicKey.from_bytes(bytes(alice_verifying_key))

        capsule = message_kit.capsule  # TODO: generalize for WorkOrders with more than one capsule

        hrac, map_id = self.construct_hrac_and_map_id(alice_verifying_key, label)
        _unknown_ursulas, _known_ursulas, m = self.follow_treasure_map(map_id=map_id, block=True)

        already_retrieved = len(message_kit.capsule._attached_cfrags) >= m

        if already_retrieved:
            if cache:
                must_do_new_retrieval = False
            else:
                raise TypeError(
                    "Not using cached retrievals, but the MessageKit's capsule has attached CFrags.  Not sure what to do.")
        else:
            must_do_new_retrieval = True

        capsule.set_correctness_keys(
            delegating=data_source.policy_pubkey,
            receiving=self.public_keys(DecryptingPower),
            verifying=alice_verifying_key)

        cleartexts = []

        if must_do_new_retrieval:
            # TODO: Consider blocking until map is done being followed. #1114 

            work_orders = self.generate_work_orders(map_id, capsule, cache=cache)
            the_airing_of_grievances = []

            # TODO: Of course, it's possible that we have cached CFrags for one of these and thus need to retrieve for one WorkOrder and not another.
            for work_order in work_orders.values():
                try:
                    cfrags = self.get_reencrypted_cfrags(work_order)
                except requests.exceptions.ConnectTimeout:
                    continue
                except NotFound:
                    # This Ursula claims not to have a matching KFrag.  Maybe this has been revoked?
                    # TODO: What's the thing to do here?  Do we want to track these Ursulas in some way in case they're lying?
                    continue

                cfrag = cfrags[0]  # TODO: generalize for WorkOrders with more than one capsule/task
                try:
                    message_kit.capsule.attach_cfrag(cfrag)
                    if len(message_kit.capsule._attached_cfrags) >= m:
                        break
                except UmbralCorrectnessError:
                    task = work_order.tasks[0]  # TODO: generalize for WorkOrders with more than one capsule/task
                    from nucypher.policy.collections import IndisputableEvidence
                    evidence = IndisputableEvidence(task=task, work_order=work_order)
                    # I got a lot of problems with you people ...
                    the_airing_of_grievances.append(evidence)
            else:
                raise Ursula.NotEnoughUrsulas("Unable to snag m cfrags.")

            if the_airing_of_grievances:
                # ... and now you're gonna hear about it!
                raise self.IncorrectCFragsReceived(the_airing_of_grievances)
                # TODO: Find a better strategy for handling incorrect CFrags #500
                #  - There maybe enough cfrags to still open the capsule
                #  - This line is unreachable when NotEnoughUrsulas

        delivered_cleartext = self.verify_from(data_source, message_kit, decrypt=True)
        cleartexts.append(delivered_cleartext)

        return cleartexts

    def make_web_controller(drone_bob, crash_on_error: bool = False):

        app_name = bytes(drone_bob.stamp).hex()[:6]
        controller = WebController(app_name=app_name,
                                   character_controller=drone_bob.controller,
                                   crash_on_error=crash_on_error)

        drone_bob.controller = controller.make_control_transport()

        # Register Flask Decorator
        bob_control = controller.make_control_transport()

        #
        # Character Control HTTP Endpoints
        #

        @bob_control.route('/public_keys', methods=['GET'])
        def public_keys():
            """
            Character control endpoint for getting Bob's encrypting and signing public keys
            """
            return controller(interface=controller._internal_controller.public_keys,
                              control_request=request)

        @bob_control.route('/join_policy', methods=['POST'])
        def join_policy():
            """
            Character control endpoint for joining a policy on the network.

            This is an unfinished endpoint. You're probably looking for retrieve.
            """
            return controller(interface=controller._internal_controller.join_policy, control_request=request)

        @bob_control.route('/retrieve', methods=['POST'])
        def retrieve():
            """
            Character control endpoint for re-encrypting and decrypting policy
            data.
            """
            return controller(interface=controller._internal_controller.retrieve, control_request=request)

        return controller


class Ursula(Teacher, Character, Worker):
    banner = URSULA_BANNER
    _alice_class = Alice

    # TODO: Maybe this wants to be a registry, so that, for example,
    # TLSHostingPower still can enjoy default status, but on a different class
    _default_crypto_powerups = [SigningPower, DecryptingPower]

    class NotEnoughUrsulas(Learner.NotEnoughTeachers, StakingEscrowAgent.NotEnoughStakers):
        """
        All Characters depend on knowing about enough Ursulas to perform their role.
        This exception is raised when a piece of logic can't proceed without more Ursulas.
        """

    class NotFound(Exception):
        pass

    # TODO: 289
    def __init__(self,

                 # Ursula
                 rest_host: str,
                 rest_port: int,
                 domains: Set = None,  # For now, serving and learning domains will be the same.
                 certificate: Certificate = None,
                 certificate_filepath: str = None,
                 db_filepath: str = None,
                 is_me: bool = True,
                 interface_signature=None,
                 timestamp=None,

                 # Blockchain
                 decentralized_identity_evidence: bytes = constants.NOT_SIGNED,
                 checksum_address: str = None,  # Staker address
                 worker_address: str = None,
                 work_tracker: WorkTracker = None,
                 start_working_now: bool = True,
                 client_password: str = None,

                 # Character
                 abort_on_learning_error: bool = False,
                 federated_only: bool = False,
                 start_learning_now: bool = None,
                 crypto_power=None,
                 tls_curve: EllipticCurve = None,
                 known_nodes: Iterable = None,

                 **character_kwargs
                 ) -> None:

        #
        # Character
        #

        if domains is None:
            # TODO: Clean up imports
            from nucypher.config.node import CharacterConfiguration
            domains = {CharacterConfiguration.DEFAULT_DOMAIN}

        if is_me:
            # If we're federated only, we assume that all other nodes in our domain are as well.
            self.set_federated_mode(federated_only)

        Character.__init__(self,
                           is_me=is_me,
                           checksum_address=checksum_address,
                           start_learning_now=False,  # Handled later in this function to avoid race condition
                           federated_only=self._federated_only_instances,  # TODO: 'Ursula' object has no attribute '_federated_only_instances' if an is_me Ursula is not inited prior to this moment
                           crypto_power=crypto_power,
                           abort_on_learning_error=abort_on_learning_error,
                           known_nodes=known_nodes,
                           domains=domains,
                           known_node_class=Ursula,
                           **character_kwargs)

        #
        # Self-Ursula
        #
        # TODO: Better handle ephemeral staking self ursula <-- Is this still relevant?
        self.log.debug(f"URSULA worker: {worker_address}, staker {checksum_address}")
        if is_me is True:  # TODO: #340
            self._stored_treasure_maps = dict()

            #
            # Ursula is a Decentralized Worker
            #
            if not federated_only:
                # Prepare a TransactingPower from worker node's transacting keys
                self.transacting_power = TransactingPower(account=worker_address, password=client_password, cache=True)
                self._crypto_power.consume_power_up(self.transacting_power)

                # Use this power to substantiate the stamp
                self.substantiate_stamp()
                self.log.debug(
                    f"Created decentralized identity evidence: {self.decentralized_identity_evidence[:10].hex()}")
                decentralized_identity_evidence = self.decentralized_identity_evidence

                Worker.__init__(self,
                                is_me=is_me,
                                registry=self.registry,
                                checksum_address=checksum_address,
                                worker_address=worker_address,
                                work_tracker=work_tracker,
                                start_working_now=start_working_now)

        #
        # ProxyRESTServer and TLSHostingPower #
        #
        if not crypto_power or (TLSHostingPower not in crypto_power):

            #
            # Ephemeral Self-Ursula
            #
            if is_me:
                self.suspicious_activities_witnessed = {'vladimirs': [], 'bad_treasure_maps': []}

                #
                # REST Server (Ephemeral Self-Ursula)
                #
                rest_app, datastore = make_rest_app(
                    this_node=self,
                    db_filepath=db_filepath,
                    serving_domains=domains,
                )

                # TODO: attach status app to rest_app

                #
                # TLSHostingPower (Ephemeral Self-Ursula)
                #
                tls_hosting_keypair = HostingKeypair(curve=tls_curve, host=rest_host,
                                                     checksum_address=self.checksum_address)
                tls_hosting_power = TLSHostingPower(keypair=tls_hosting_keypair, host=rest_host)
                self.rest_server = ProxyRESTServer(rest_host=rest_host, rest_port=rest_port,
                                                   rest_app=rest_app, datastore=datastore,
                                                   hosting_power=tls_hosting_power)

            #
            # Stranger-Ursula
            #
            else:

                # TLSHostingPower
                if certificate or certificate_filepath:
                    tls_hosting_power = TLSHostingPower(host=rest_host,
                                                        public_certificate_filepath=certificate_filepath,
                                                        public_certificate=certificate)
                else:
                    tls_hosting_keypair = HostingKeypair(curve=tls_curve, host=rest_host, generate_certificate=False)
                    tls_hosting_power = TLSHostingPower(host=rest_host, keypair=tls_hosting_keypair)

                # REST Server
                # Unless the caller passed a crypto power we'll make our own TLSHostingPower for this stranger.
                self.rest_server = ProxyRESTServer(
                    rest_host=rest_host,
                    rest_port=rest_port,
                    hosting_power=tls_hosting_power
                )

            #
            # OK - Now we have a ProxyRestServer and a TLSHostingPower for some Ursula
            #
            self._crypto_power.consume_power_up(tls_hosting_power)  # Consume!

        #
        # Verifiable Node
        #
        certificate_filepath = self._crypto_power.power_ups(TLSHostingPower).keypair.certificate_filepath
        certificate = self._crypto_power.power_ups(TLSHostingPower).keypair.certificate
        Teacher.__init__(self,
                         domains=domains,
                         certificate=certificate,
                         certificate_filepath=certificate_filepath,
                         interface_signature=interface_signature,
                         timestamp=timestamp,
                         decentralized_identity_evidence=decentralized_identity_evidence,
                         )

        if start_learning_now:
            self.start_learning_loop(now=True)

        #
        # Logging / Updating
        #
        if is_me:
            self.known_nodes.record_fleet_state(additional_nodes_to_track=[self])
            message = "THIS IS YOU: {}: {}".format(self.__class__.__name__, self)
            self.log.info(message)
            self.log.info(self.banner.format(self.nickname))
        else:
            message = "Initialized Stranger {} | {}".format(self.__class__.__name__, self)
            self.log.debug(message)

    def rest_information(self):
        hosting_power = self._crypto_power.power_ups(TLSHostingPower)

        return (
            self.rest_server.rest_interface,
            hosting_power.keypair.certificate,
            hosting_power.keypair.pubkey
        )

    @property
    def rest_interface(self):
        return self.rest_server.rest_interface

    def get_deployer(self):
        port = self.rest_interface.port
        deployer = self._crypto_power.power_ups(TLSHostingPower).get_deployer(rest_app=self.rest_app, port=port)
        return deployer

    def rest_server_certificate(self):
        return self._crypto_power.power_ups(TLSHostingPower).keypair.certificate

    def __bytes__(self):

        version = self.TEACHER_VERSION.to_bytes(2, "big")
        interface_info = VariableLengthBytestring(bytes(self.rest_interface))
        decentralized_identity_evidence = VariableLengthBytestring(self.decentralized_identity_evidence)

        certificate = self.rest_server_certificate()
        cert_vbytes = VariableLengthBytestring(certificate.public_bytes(Encoding.PEM))

        domains = {domain.encode('utf-8') for domain in self.serving_domains}
        as_bytes = bytes().join((version,
                                 self.canonical_public_address,
                                 bytes(VariableLengthBytestring.bundle(domains)),
                                 self.timestamp_bytes(),
                                 bytes(self._interface_signature),
                                 bytes(decentralized_identity_evidence),
                                 bytes(self.public_keys(SigningPower)),
                                 bytes(self.public_keys(DecryptingPower)),
                                 bytes(cert_vbytes),
                                 bytes(interface_info))
                                )
        return as_bytes

    #
    # Alternate Constructors
    #

    @classmethod
    def from_rest_url(cls,
                      network_middleware: RestMiddleware,
                      host: str,
                      port: int,
                      certificate_filepath,
                      federated_only: bool,
                      *args, **kwargs
                      ):
        response_data = network_middleware.client.node_information(host, port, certificate_filepath=certificate_filepath)

        stranger_ursula_from_public_keys = cls.from_bytes(response_data,
                                                          *args, **kwargs)

        return stranger_ursula_from_public_keys

    @classmethod
    def from_seednode_metadata(cls, seednode_metadata, *args, **kwargs):
        """
        Essentially another deserialization method, but this one doesn't reconstruct a complete
        node from bytes; instead it's just enough to connect to and verify a node.

        NOTE: This is a federated only method.
        """
        seed_uri = f'{seednode_metadata.checksum_address}@{seednode_metadata.rest_host}:{seednode_metadata.rest_port}'
        return cls.from_seed_and_stake_info(seed_uri=seed_uri, *args, **kwargs)

    @classmethod
    def from_teacher_uri(cls,
                         federated_only: bool,
                         teacher_uri: str,
                         min_stake: int,
                         network_middleware: RestMiddleware = None,
                         registry: BaseContractRegistry = None,
                         retry_attempts: int = 2,
                         retry_interval: int = 2
                         ) -> 'Ursula':

        def __attempt(attempt=1, interval=retry_interval) -> Ursula:
            if attempt >= retry_attempts:
                raise ConnectionRefusedError("Host {} Refused Connection".format(teacher_uri))

            try:
                teacher = cls.from_seed_and_stake_info(seed_uri=teacher_uri,
                                                       federated_only=federated_only,
                                                       minimum_stake=min_stake,
                                                       network_middleware=network_middleware,
                                                       registry=registry)

            except NodeSeemsToBeDown:
                log = Logger(cls.__name__)
                log.warn(
                    "Can't connect to seed node (attempt {}).  Will retry in {} seconds.".format(attempt, interval))
                time.sleep(interval)
                return __attempt(attempt=attempt + 1)
            else:
                return teacher

        return __attempt()

    @classmethod
    def from_seed_and_stake_info(cls,
                                 seed_uri: str,
                                 federated_only: bool = False,
                                 minimum_stake: int = 0,
                                 registry: BaseContractRegistry = None,
                                 network_middleware: RestMiddleware = None,
                                 *args,
                                 **kwargs
                                 ) -> 'Ursula':

        if network_middleware is None:
            network_middleware = RestMiddleware()

        #
        # WARNING: xxx Poison xxx
        # Let's learn what we can about the ... "seednode".
        #

        # Parse node URI
        host, port, checksum_address = parse_node_uri(seed_uri)

        # Fetch the hosts TLS certificate and read the common name
        certificate = network_middleware.get_certificate(host=host, port=port)
        real_host = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value

        # Create a temporary certificate storage area
        temp_node_storage = ForgetfulNodeStorage(federated_only=federated_only)
        temp_certificate_filepath = temp_node_storage.store_node_certificate(certificate=certificate)

        # Load the host as a potential seed node
        potential_seed_node = cls.from_rest_url(
            registry=registry,
            host=real_host,
            port=port,
            network_middleware=network_middleware,
            certificate_filepath=temp_certificate_filepath,
            federated_only=federated_only,
            *args,
            **kwargs
        )

        # Check the node's stake (optional)
        if minimum_stake > 0 and not federated_only:
            staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
            seednode_stake = staking_agent.get_locked_tokens(staker_address=checksum_address)
            if seednode_stake < minimum_stake:
                raise Learner.NotATeacher(
                    f"{checksum_address} is staking less than the specified minimum stake value ({minimum_stake}).")

        # OK - everyone get out
        temp_node_storage.forget()
        return potential_seed_node

    @classmethod
    def internal_splitter(cls, splittable, partial=False):
        splitter = BytestringKwargifier(
            _receiver=cls.from_processed_bytes,
            _partial_receiver=NodeSprout,
            public_address=PUBLIC_ADDRESS_LENGTH,
            domains=VariableLengthBytestring,  # TODO:  Multiple domains?
            timestamp=(int, 4, {'byteorder': 'big'}),
            interface_signature=Signature,
            decentralized_identity_evidence=VariableLengthBytestring,
            verifying_key=(UmbralPublicKey, PUBLIC_KEY_LENGTH),
            encrypting_key=(UmbralPublicKey, PUBLIC_KEY_LENGTH),
            certificate=(load_pem_x509_certificate, VariableLengthBytestring, {"backend": default_backend()}),
            rest_interface=InterfaceInfo,
        )
        result = splitter(splittable, partial=partial)
        return result

    @classmethod
    def from_bytes(cls,
                   ursula_as_bytes: bytes,
                   version: int = INCLUDED_IN_BYTESTRING,
                   registry: BaseContractRegistry = None,
                   ) -> 'Ursula':

        if version is INCLUDED_IN_BYTESTRING:
            version, payload = cls.version_splitter(ursula_as_bytes, return_remainder=True)
        else:
            payload = ursula_as_bytes

        # Check version and raise IsFromTheFuture if this node is... you guessed it...
        if version > cls.LEARNER_VERSION:

            # Try to handle failure, even during failure, graceful degradation
            # TODO: #154 - Some auto-updater logic?

            try:
                canonical_address, _ = BytestringSplitter(PUBLIC_ADDRESS_LENGTH)(payload, return_remainder=True)
                checksum_address = to_checksum_address(canonical_address)
                nickname, _ = nickname_from_seed(checksum_address)
                display_name = cls._display_name_template.format(cls.__name__, nickname, checksum_address)
                message = cls.unknown_version_message.format(display_name, version, cls.LEARNER_VERSION)
            except BytestringSplittingError:
                message = cls.really_unknown_version_message.format(version, cls.LEARNER_VERSION)
            raise cls.IsFromTheFuture(message)

        # Version stuff checked out.  Moving on.
        node_sprout = cls.internal_splitter(payload, partial=True)
        return node_sprout

    @classmethod
    def from_processed_bytes(cls, **processed_objects):
        """
        A convenience method for completing the maturation of a NodeSprout.
        TODO: Either deprecate or consolidate this logic; it's mostly just workarounds.
        """
        #### This is kind of a ridiculous workaround and repeated logic from Ursula.from_bytes
        interface_info = processed_objects.pop("rest_interface")
        rest_host = interface_info.host
        rest_port = interface_info.port
        checksum_address = to_checksum_address(processed_objects.pop('public_address'))

        domains_vbytes = VariableLengthBytestring.dispense(processed_objects.pop('domains'))
        domains = set(d.decode('utf-8') for d in domains_vbytes)

        timestamp = maya.MayaDT(processed_objects.pop('timestamp'))

        ursula = cls.from_public_keys(rest_host=rest_host,
                                      rest_port=rest_port,
                                      checksum_address=checksum_address,
                                      domains=domains,
                                      timestamp=timestamp,
                                      **processed_objects)
        return ursula

    @classmethod
    def batch_from_bytes(cls,
                         ursulas_as_bytes: Iterable[bytes],
                         registry: BaseContractRegistry = None,
                         fail_fast: bool = False,
                         ) -> List['Ursula']:

        node_splitter = BytestringSplitter(VariableLengthBytestring)
        nodes_vbytes = node_splitter.repeat(ursulas_as_bytes)
        version_splitter = BytestringSplitter((int, 2, {"byteorder": "big"}))
        versions_and_node_bytes = [version_splitter(n, return_remainder=True) for n in nodes_vbytes]

        sprouts = []
        for version, node_bytes in versions_and_node_bytes:
            try:
                sprout = cls.from_bytes(node_bytes,
                                        version=version,
                                        registry=registry)
            except Ursula.IsFromTheFuture as e:
                if fail_fast:
                    raise
                else:
                    cls.log.warn(e.args[0])
            else:
                sprouts.append(sprout)
        return sprouts

    @classmethod
    def from_storage(cls,
                     node_storage: NodeStorage,
                     checksum_adress: str,
                     federated_only: bool = False) -> 'Ursula':
        return node_storage.get(checksum_address=checksum_adress,
                                federated_only=federated_only)

    #
    # Properties
    #
    @property
    def datastore(self):
        try:
            return self.rest_server.datastore
        except AttributeError:
            raise AttributeError("No rest server attached")

    @property
    def rest_url(self):
        try:
            return self.rest_server.rest_url
        except AttributeError:
            raise AttributeError("No rest server attached")

    @property
    def rest_app(self):
        rest_app_on_server = self.rest_server.rest_app

        if rest_app_on_server is PUBLIC_ONLY or not rest_app_on_server:
            m = "This Ursula doesn't have a REST app attached. If you want one, init with is_me and attach_server."
            raise PowerUpError(m)
        else:
            return rest_app_on_server

    def interface_info_with_metadata(self):
        # TODO: Do we ever actually use this without using the rest of the serialized Ursula?  337
        return constants.BYTESTRING_IS_URSULA_IFACE_INFO + bytes(self)

    #
    # Work Orders & Re-Encryption
    #

    def work_orders(self, bob=None) -> List['WorkOrder']:
        with ThreadedSession(self.datastore.engine):
            if not bob:  # All
                return self.datastore.get_workorders()
            else:        # Filter
                work_orders_from_bob = self.datastore.get_workorders(bob_verifying_key=bytes(bob.stamp))
                return work_orders_from_bob

    def _reencrypt(self, kfrag: KFrag, work_order: 'WorkOrder', alice_verifying_key: UmbralPublicKey):

        # Prepare a bytestring for concatenating re-encrypted
        # capsule data for each work order task.
        cfrag_byte_stream = bytes()
        for task in work_order.tasks:

            # Ursula signs on top of Bob's signature of each task.
            # Now both are committed to the same task.  See #259.
            reencryption_metadata = bytes(self.stamp(bytes(task.signature)))

            # Ursula sets Alice's verifying key for capsule correctness verification.
            capsule = task.capsule
            capsule.set_correctness_keys(verifying=alice_verifying_key)

            # Then re-encrypts the fragment.
            cfrag = pre.reencrypt(kfrag, capsule, metadata=reencryption_metadata)  # <--- pyUmbral
            self.log.info(f"Re-encrypted capsule {capsule} -> made {cfrag}.")

            # Next, Ursula signs to commit to her results.
            reencryption_signature = self.stamp(bytes(cfrag))
            cfrag_byte_stream += VariableLengthBytestring(cfrag) + reencryption_signature

        # ... and finally returns all the re-encrypted bytes
        return cfrag_byte_stream


class Enrico(Character):
    """A Character that represents a Data Source that encrypts data for some policy's public key"""

    banner = ENRICO_BANNER
    _controller_class = EnricoJSONController
    _default_crypto_powerups = [SigningPower]

    def __init__(self, policy_encrypting_key, controller: bool = True, *args, **kwargs):
        self.policy_pubkey = policy_encrypting_key

        # Encrico never uses the blockchain, hence federated_only)
        kwargs['federated_only'] = True
        kwargs['known_node_class'] = Ursula
        super().__init__(*args, **kwargs)

        if controller:
            self.controller = self._controller_class(enrico=self)

        self.log = Logger(f'{self.__class__.__name__}-{bytes(policy_encrypting_key).hex()[:6]}')
        self.log.info(self.banner.format(policy_encrypting_key))

    def encrypt_message(self,
                        message: bytes
                        ) -> Tuple[UmbralMessageKit, Signature]:
        message_kit, signature = encrypt_and_sign(self.policy_pubkey,
                                                  plaintext=message,
                                                  signer=self.stamp)
        message_kit.policy_pubkey = self.policy_pubkey  # TODO: We can probably do better here.
        return message_kit, signature

    @classmethod
    def from_alice(cls, alice: Alice, label: bytes):
        """
        :param alice: Not a stranger.  This is your Alice who will derive the policy keypair, leaving Enrico with the public part.
        :param label: The label with which to derive the key.
        :return:
        """
        policy_pubkey_enc = alice.get_policy_encrypting_key_from_label(label)
        return cls(crypto_power_ups={SigningPower: alice.stamp.as_umbral_pubkey()},
                   policy_encrypting_key=policy_pubkey_enc)

    def make_web_controller(drone_enrico, crash_on_error: bool = False):

        app_name = bytes(drone_enrico.stamp).hex()[:6]
        controller = WebController(app_name=app_name,
                                   character_controller=drone_enrico.controller,
                                   crash_on_error=crash_on_error)

        drone_enrico.controller = controller

        # Register Flask Decorator
        enrico_control = controller.make_control_transport()

        #
        # Character Control HTTP Endpoints
        #

        @enrico_control.route('/encrypt_message', methods=['POST'])
        def encrypt_message():
            """
            Character control endpoint for encrypting data for a policy and
            receiving the messagekit (and signature) to give to Bob.
            """
            try:
                request_data = json.loads(request.data)
                message = request_data['message']
            except (KeyError, JSONDecodeError) as e:
                return Response(str(e), status=400)

            # Encrypt
            message_kit, signature = drone_enrico.encrypt_message(bytes(message, encoding='utf-8'))

            response_data = {
                'result': {
                    'message_kit': b64encode(message_kit.to_bytes()).decode(),  # FIXME
                    'signature': b64encode(bytes(signature)).decode(),
                },
                'version': str(nucypher.__version__)
            }

            return Response(json.dumps(response_data), status=200)

        return controller
