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
import random
import time
from base64 import b64encode
from collections import OrderedDict
from functools import partial
from json.decoder import JSONDecodeError
from typing import Dict, Iterable, List, Set, Tuple, Union

import maya
import requests
from bytestring_splitter import BytestringKwargifier, BytestringSplittingError
from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from constant_sorrow import constants
from constant_sorrow.constants import INCLUDED_IN_BYTESTRING, PUBLIC_ONLY, FEDERATED_POLICY, STRANGER_ALICE
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurve
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import load_pem_x509_certificate, Certificate, NameOID
from eth_utils import to_checksum_address
from flask import request, Response
from twisted.internet import threads
from twisted.logger import Logger
from umbral.keys import UmbralPublicKey
from umbral.pre import UmbralCorrectnessError
from umbral.signing import Signature

import nucypher
from nucypher.blockchain.eth.actors import PolicyAuthor, Staker
from nucypher.blockchain.eth.agents import StakingEscrow
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.utils import calculate_period_duration, datetime_at_period
from nucypher.characters.banners import ALICE_BANNER, BOB_BANNER, ENRICO_BANNER, URSULA_BANNER
from nucypher.characters.base import Character, Learner
from nucypher.characters.control.controllers import AliceJSONController, BobJSONController, EnricoJSONController, \
    WebController
from nucypher.config.storages import NodeStorage, ForgetfulNodeStorage
from nucypher.crypto.api import keccak_digest, encrypt_and_sign
from nucypher.crypto.constants import PUBLIC_KEY_LENGTH, PUBLIC_ADDRESS_LENGTH
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import SigningPower, DecryptingPower, DelegatingPower, BlockchainPower, PowerUpError
from nucypher.crypto.signing import InvalidSignature
from nucypher.keystore.keypairs import HostingKeypair
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import RestMiddleware, UnexpectedResponse, NotFound
from nucypher.network.nicknames import nickname_from_seed
from nucypher.network.nodes import Teacher
from nucypher.network.protocols import InterfaceInfo, parse_node_uri
from nucypher.network.server import ProxyRESTServer, TLSHostingPower, make_rest_app


class Alice(Character, PolicyAuthor):

    banner = ALICE_BANNER
    _controller_class = AliceJSONController
    _default_crypto_powerups = [SigningPower, DecryptingPower, DelegatingPower]

    def __init__(self,
                 checksum_address: str = None,
                 m: int = None,
                 n: int = None,
                 rate: int = None,
                 duration: int = None,
                 first_period_rate: float = None,
                 timeout: int = 10,
                 is_me: bool = True,
                 federated_only: bool = False,
                 network_middleware=None,
                 controller=True,
                 policy_agent=None,
                 *args, **kwargs) -> None:

        #
        # Fallback Policy Values
        #

        self.timeout = timeout

        if is_me:
            self.m = m
            self.n = n
            self.rate = rate
            self.duration = duration
            self.first_period_rate = first_period_rate
        else:
            self.m = STRANGER_ALICE
            self.n = STRANGER_ALICE
            self.rate = STRANGER_ALICE
            self.duration = STRANGER_ALICE
            self.first_period_rate = STRANGER_ALICE

        Character.__init__(self,
                           is_me=is_me,
                           federated_only=federated_only,
                           checksum_address=checksum_address,
                           network_middleware=network_middleware,
                           *args, **kwargs)

        if is_me and not federated_only:  # TODO: #289
            PolicyAuthor.__init__(self, policy_agent=policy_agent, checksum_address=checksum_address)

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

    def create_policy(self,
                      bob: "Bob",
                      label: bytes,
                      handpicked_ursulas: set = None,
                      **policy_params):
        """
        Create a Policy to share uri with bob.
        Generates KFrags and attaches them.
        """

        params = self.generate_policy_parameters(**policy_params)

        # Generate KFrags
        public_key, kfrags = self.generate_kfrags(bob=bob,
                                                  label=label,
                                                  m=params['m'],
                                                  n=params['n'])

        # Federated Payload
        payload = dict(label=label,
                       bob=bob,
                       kfrags=kfrags,
                       public_key=public_key,
                       m=params['m'])

        # Use known nodes
        if self.federated_only:
            from nucypher.policy.models import FederatedPolicy
            known_nodes = self.known_nodes.shuffled()
            policy = FederatedPolicy(alice=self, ursulas=known_nodes, **payload)

        # Sample from blockchain via PolicyManager
        else:
            blockchain_payload = dict(duration=params['duration'],
                                      expiration=params['expiration'],
                                      value=params['value'],
                                      initial_reward=params['first_period_value'],
                                      handpicked_ursulas=handpicked_ursulas)

            payload.update(blockchain_payload)

            from nucypher.blockchain.eth.policies import BlockchainPolicy
            policy = BlockchainPolicy(alice=self, **payload)

        return policy

    def generate_policy_parameters(self,
                                   m: int = None,
                                   n: int = None,
                                   duration: int = None,
                                   expiration: maya.MayaDT = None,
                                   value: int = None,
                                   rate: int = None,
                                   first_period_value: int = None,
                                   first_period_rate: float = None) -> dict:
        """
        Construct policy creation from parameters or overrides.
        """

        m = m or self.m
        n = n or self.n

        # Calculate Policy Rate and Value
        if not self.federated_only:

            # Calculate duration periods and expiration datetime
            if expiration:
                duration = calculate_period_duration(future_time=expiration)
            else:
                duration = duration or self.duration
                expiration = datetime_at_period(self.miner_agent.get_current_period() + duration)

            if not value and not rate:
                value = int(self.rate * duration)
                rate = self.rate
            elif rate:
                value = int(rate * duration)
            elif value:
                rate = value // duration

            # TODO: #1063 - What is the best way to calculate default first period value?
            # first_period_rate = first_period_rate or self.first_period_rate
            first_period_value = first_period_value or 0

        else:
            value = first_period_value = duration = FEDERATED_POLICY

        payload = dict(m=m, n=n,
                       duration=duration,
                       expiration=expiration,
                       first_period_value=first_period_value,
                       value=value,
                       rate=rate)
        return payload

    def grant(self,
              bob: "Bob",
              label: bytes,
              handpicked_ursulas: set = None,
              discover_on_this_thread: bool = True,
              timeout: int = None,
              **policy_params):

        timeout = timeout or self.timeout
        params = self.generate_policy_parameters(**policy_params)

        #
        # Policy Creation
        #

        if handpicked_ursulas is None:
            handpicked_ursulas = set()

        else:
            # This might be the first time alice learns about the handpicked Ursulas.
            for handpicked_ursula in handpicked_ursulas:
                self.remember_node(node=handpicked_ursula)

        policy = self.create_policy(bob=bob,
                                    label=label,
                                    m=params['m'],
                                    n=params['n'],
                                    duration=params['duration'],
                                    expiration=params['expiration'],
                                    value=params['value'],
                                    handpicked_ursulas=handpicked_ursulas)

        #
        # We'll find n Ursulas by default.  It's possible to "play the field" by trying different
        # value and expiration combinations on a limited number of Ursulas;
        # Users may decide to inject some market strategies here.
        #
        # TODO: #289

        # If we're federated only, we need to block to make sure we have enough nodes.
        if self.federated_only and len(self.known_nodes) < params['n']:
            good_to_go = self.block_until_number_of_known_nodes_is(number_of_nodes_to_know=params['n'],
                                                                   learn_on_this_thread=discover_on_this_thread,
                                                                   timeout=timeout)
            if not good_to_go:
                raise ValueError(
                    "To make a Policy in federated mode, you need to know about "
                    "all the Ursulas you need (in this case, {}); there's no other way to "
                    "know which nodes to use.  Either pass them here or when you make the Policy, "
                    "or run the learning loop on a network with enough Ursulas.".format(params['n']))

            if len(handpicked_ursulas) < params['n']:
                number_of_ursulas_needed = params['n'] - len(handpicked_ursulas)
                new_ursulas = random.sample(list(self.known_nodes), number_of_ursulas_needed)
                handpicked_ursulas.update(new_ursulas)

        policy.make_arrangements(network_middleware=self.network_middleware,
                                 value=params['value'],
                                 expiration=params['expiration'],
                                 handpicked_ursulas=handpicked_ursulas)

        # REST call happens here, as does population of TreasureMap.
        policy.enact(network_middleware=self.network_middleware)
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

    def make_web_controller(drone_alice, crash_on_error: bool = False):

        app_name = bytes(drone_alice.stamp).hex()[:6]
        controller = WebController(app_name=app_name,
                                   character_contoller=drone_alice.controller,
                                   crash_on_error=crash_on_error)
        drone_alice.controller = controller

        # Register Flask Decorator
        alice_control = controller.make_web_controller()

        #
        # Character Control HTTP Endpoints
        #

        @alice_control.route('/public_keys', methods=['GET'])
        def public_keys():
            """
            Character control endpoint for getting Alice's encrypting and signing public keys
            """
            return controller(interface=controller._internal_controller.public_keys,
                              control_request=request)

        @alice_control.route("/create_policy", methods=['PUT'])
        def create_policy() -> Response:
            """
            Character control endpoint for creating a policy and making
            arrangements with Ursulas.
            """
            response = controller(interface=controller._internal_controller.create_policy,
                                  control_request=request)
            return response

        @alice_control.route("/decrypt", methods=['POST'])
        def decrypt():
            """
            Character control endpoint for decryption of Alice's own policy data.
            """

            response = controller(
                interface=controller._internal_controller.decrypt,
                control_request=request
            )
            return response

        @alice_control.route('/derive_policy_encrypting_key/<label>', methods=['POST'])
        def derive_policy_encrypting_key(label) -> Response:
            """
            Character control endpoint for deriving a policy encrypting given a unicode label.
            """
            response = controller(interface=controller._internal_controller.derive_policy_encrypting_key,
                                  control_request=request,
                                  label=label)
            return response

        @alice_control.route("/grant", methods=['PUT'])
        def grant() -> Response:
            """
            Character control endpoint for policy granting.
            """
            response = controller(interface=controller._internal_controller.grant, control_request=request)
            return response

        @alice_control.route("/revoke", methods=['DELETE'])
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

    def __init__(self, controller=True, *args, **kwargs) -> None:
        Character.__init__(self, *args, **kwargs)

        if controller:
            self.controller = self._controller_class(bob=self)

        from nucypher.policy.models import WorkOrderHistory  # Need a bigger strategy to avoid circulars.
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
        from nucypher.policy.models import TreasureMap
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

    def generate_work_orders(self, map_id, *capsules, num_ursulas=None):
        from nucypher.policy.models import WorkOrder  # Prevent circular import

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
            ursula = self.known_nodes[node_id]

            capsules_to_include = []
            for capsule in capsules:
                if not capsule in self._saved_work_orders[node_id]:
                    capsules_to_include.append(capsule)

            if capsules_to_include:
                work_order = WorkOrder.construct_by_bob(
                    arrangement_id, capsules_to_include, ursula, self)
                generated_work_orders[node_id] = work_order

                # TODO: Fix this. It's always using the last capsule, via leaky-loop
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

    def retrieve(self, message_kit, data_source, alice_verifying_key, label):

        capsule = message_kit.capsule  # TODO: generalize for WorkOrders with more than one capsule
        capsule.set_correctness_keys(
            delegating=data_source.policy_pubkey,
            receiving=self.public_keys(DecryptingPower),
            verifying=alice_verifying_key)

        hrac, map_id = self.construct_hrac_and_map_id(alice_verifying_key, label)
        _unknown_ursulas, _known_ursulas, m = self.follow_treasure_map(map_id=map_id, block=True)

        # TODO: Consider blocking until map is done being followed.

        work_orders = self.generate_work_orders(map_id, capsule)

        cleartexts = []
        the_airing_of_grievances = []
        work_orders = work_orders.values()
        for work_order in work_orders:
            try:
                cfrags = self.get_reencrypted_cfrags(work_order)
            except requests.exceptions.ConnectTimeout:
                continue

            cfrag = cfrags[0]  # TODO: generalize for WorkOrders with more than one capsule/task
            try:
                message_kit.capsule.attach_cfrag(cfrag)
                if len(message_kit.capsule._attached_cfrags) >= m:
                    break
            except UmbralCorrectnessError:
                task = work_order.tasks[0]  # TODO: generalize for WorkOrders with more than one capsule/task
                from nucypher.policy.models import IndisputableEvidence
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
                                   character_contoller=drone_bob.controller,
                                   crash_on_error=crash_on_error)
        drone_bob.controller = controller.make_web_controller()

        # Register Flask Decorator
        bob_control = controller.make_web_controller()

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


class Ursula(Teacher, Character, Staker):

    banner = URSULA_BANNER
    _alice_class = Alice

    # TODO: Maybe this wants to be a registry, so that, for example,
    # TLSHostingPower still can enjoy default status, but on a different class
    _default_crypto_powerups = [SigningPower, DecryptingPower]

    class NotEnoughUrsulas(Learner.NotEnoughTeachers, StakingEscrow.NotEnoughStakers):
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
                 checksum_address: str = None,

                 # Character
                 password: str = None,
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
            from nucypher.config.node import NodeConfiguration
            domains = (NodeConfiguration.DEFAULT_DOMAIN,)

        self._work_orders = list()
        Character.__init__(self,
                           is_me=is_me,
                           checksum_address=checksum_address,
                           start_learning_now=start_learning_now,
                           federated_only=federated_only,
                           crypto_power=crypto_power,
                           abort_on_learning_error=abort_on_learning_error,
                           known_nodes=known_nodes,
                           domains=domains,
                           **character_kwargs)

        #
        # Self-Ursula
        #
        if is_me is True:  # TODO: 340
            self._stored_treasure_maps = dict()

            #
            # Staking Ursula
            #
            if not federated_only:
                Staker.__init__(self, is_me=is_me, checksum_address=checksum_address)

                # Access staking node via node's transacting keys  TODO: Better handle ephemeral staking self ursula
                blockchain_power = BlockchainPower(blockchain=self.blockchain, account=self.checksum_address)
                self._crypto_power.consume_power_up(blockchain_power)

                # Use blockchain power to substantiate stamp, instead of signing key
                self.substantiate_stamp(client_password=password)  # TODO: Derive from keyring

        #
        # ProxyRESTServer and TLSHostingPower # TODO: Maybe we want _power_ups to be public after all?
        #
        if not crypto_power or (TLSHostingPower not in crypto_power._power_ups):

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
                         password=password,
                         domains=domains,
                         certificate=certificate,
                         certificate_filepath=certificate_filepath,
                         interface_signature=interface_signature,
                         timestamp=timestamp,
                         decentralized_identity_evidence=decentralized_identity_evidence,
                         substantiate_immediately=is_me and not federated_only,
                         # FIXME: When is_me and not federated_only, the stamp is substantiated twice
                         )

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

    def get_deployer(self):
        port = self.rest_information()[0].port
        deployer = self._crypto_power.power_ups(TLSHostingPower).get_deployer(rest_app=self.rest_app, port=port)
        return deployer

    def rest_server_certificate(self):
        return self._crypto_power.power_ups(TLSHostingPower).keypair.certificate

    def __bytes__(self):

        version = self.TEACHER_VERSION.to_bytes(2, "big")
        interface_info = VariableLengthBytestring(bytes(self.rest_information()[0]))
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
        response_data = network_middleware.node_information(host, port, certificate_filepath=certificate_filepath)

        stranger_ursula_from_public_keys = cls.from_bytes(response_data,
                                                          federated_only=federated_only,
                                                          *args, **kwargs)

        return stranger_ursula_from_public_keys

    @classmethod
    def from_seednode_metadata(cls,
                               seednode_metadata,
                               *args,
                               **kwargs):
        """
        Essentially another deserialization method, but this one doesn't reconstruct a complete
        node from bytes; instead it's just enough to connect to and verify a node.
        """

        return cls.from_seed_and_stake_info(checksum_address=seednode_metadata.checksum_address,
                                            seed_uri='{}:{}'.format(seednode_metadata.rest_host,
                                                                    seednode_metadata.rest_port),
                                            *args, **kwargs)

    @classmethod
    def from_teacher_uri(cls,
                         federated_only: bool,
                         teacher_uri: str,
                         min_stake: int,
                         network_middleware: RestMiddleware = None,
                         ) -> 'Ursula':

        hostname, port, checksum_address = parse_node_uri(uri=teacher_uri)

        def __attempt(attempt=1, interval=10) -> Ursula:
            if attempt > 3:
                raise ConnectionRefusedError("Host {} Refused Connection".format(teacher_uri))

            try:
                teacher = cls.from_seed_and_stake_info(seed_uri='{host}:{port}'.format(host=hostname, port=port),
                                                       federated_only=federated_only,
                                                       checksum_address=checksum_address,
                                                       minimum_stake=min_stake,
                                                       network_middleware=network_middleware)

            except NodeSeemsToBeDown:
                log = Logger(cls.__name__)
                log.warn("Can't connect to seed node (attempt {}).  Will retry in {} seconds.".format(attempt, interval))
                time.sleep(interval)
                return __attempt(attempt=attempt + 1)
            else:
                return teacher

        return __attempt()

    @classmethod
    @validate_checksum_address
    def from_seed_and_stake_info(cls,
                                 seed_uri: str,
                                 federated_only: bool,
                                 minimum_stake: int = 0,
                                 checksum_address: str = None,  # TODO: Why is this unused?
                                 network_middleware: RestMiddleware = None,
                                 *args,
                                 **kwargs
                                 ) -> 'Ursula':

        #
        # WARNING: xxx Poison xxx
        # Let's learn what we can about the ... "seednode".
        #

        if network_middleware is None:
            network_middleware = RestMiddleware()

        host, port, checksum_address = parse_node_uri(seed_uri)

        # Fetch the hosts TLS certificate and read the common name
        certificate = network_middleware.get_certificate(host=host, port=port)
        real_host = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        temp_node_storage = ForgetfulNodeStorage(federated_only=federated_only)
        certificate_filepath = temp_node_storage.store_node_certificate(certificate=certificate)
        # Load the host as a potential seed node
        potential_seed_node = cls.from_rest_url(
            host=real_host,
            port=port,
            network_middleware=network_middleware,
            certificate_filepath=certificate_filepath,
            federated_only=federated_only,
            *args,
            **kwargs)  # TODO: 466

        potential_seed_node.certificate_filepath = certificate_filepath

        if checksum_address:
            # Ensure this is the specific node we expected
            if not checksum_address == potential_seed_node.checksum_address:
                template = "This seed node has a different wallet address: {} (expected {}). " \
                           " Are you sure this is a seednode?"
                raise potential_seed_node.SuspiciousActivity(
                    template.format(potential_seed_node.checksum_address,
                                    checksum_address))

        # Check the node's stake (optional)
        if minimum_stake > 0:
            # TODO: check the blockchain to verify that address has more then minimum_stake. #511
            raise NotImplementedError("Stake checking is not implemented yet.")

        # Verify the node's TLS certificate
        try:
            potential_seed_node.verify_node(
                network_middleware=network_middleware,
                accept_federated_only=federated_only,
                certificate_filepath=certificate_filepath)

        except potential_seed_node.InvalidNode:
            raise  # TODO: What if our seed node fails verification?

        # OK - everyone get out
        temp_node_storage.forget()

        return potential_seed_node

    @classmethod
    def internal_splitter(cls, splittable):
        result = BytestringKwargifier(
            dict,
            public_address=PUBLIC_ADDRESS_LENGTH,
            domains=VariableLengthBytestring,
            timestamp=(int, 4, {'byteorder': 'big'}),
            interface_signature=Signature,
            decentralized_identity_evidence=VariableLengthBytestring,
            verifying_key=(UmbralPublicKey, PUBLIC_KEY_LENGTH),
            encrypting_key=(UmbralPublicKey, PUBLIC_KEY_LENGTH),
            certificate=(load_pem_x509_certificate, VariableLengthBytestring, {"backend": default_backend()}),
            rest_interface=InterfaceInfo,
        )
        return result(splittable)

    @classmethod
    def from_bytes(cls,
                   ursula_as_bytes: bytes,
                   version: int = INCLUDED_IN_BYTESTRING,
                   federated_only: bool = False,
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
        node_info = cls.internal_splitter(payload)

        interface_info = node_info.pop("rest_interface")
        node_info['rest_host'] = interface_info.host
        node_info['rest_port'] = interface_info.port

        node_info['timestamp'] = maya.MayaDT(node_info.pop("timestamp"))
        node_info['checksum_address'] = to_checksum_address(node_info.pop("public_address"))

        domains_vbytes = VariableLengthBytestring.dispense(node_info['domains'])
        node_info['domains'] = set(d.decode('utf-8') for d in domains_vbytes)

        ursula = cls.from_public_keys(federated_only=federated_only, **node_info)
        return ursula

    @classmethod
    def batch_from_bytes(cls,
                         ursulas_as_bytes: Iterable[bytes],
                         federated_only: bool = False,
                         fail_fast: bool = False,
                         ) -> List['Ursula']:

        node_splitter = BytestringSplitter(VariableLengthBytestring)
        nodes_vbytes = node_splitter.repeat(ursulas_as_bytes)
        version_splitter = BytestringSplitter((int, 2, {"byteorder": "big"}))
        versions_and_node_bytes = [version_splitter(n, return_remainder=True) for n in nodes_vbytes]

        ursulas = []
        for version, node_bytes in versions_and_node_bytes:
            try:
                ursula = cls.from_bytes(node_bytes, version, federated_only=federated_only)
            except Ursula.IsFromTheFuture as e:
                if fail_fast:
                    raise
                else:
                    cls.log.warn(e.args[0])
            else:
                ursulas.append(ursula)

        return ursulas

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
    # Utilities
    #

    def work_orders(self, bob=None):
        """
        TODO: This is better written as a model method for Ursula's datastore.
        """
        if not bob:
            return self._work_orders
        else:
            work_orders_from_bob = []
            for work_order in self._work_orders:
                if work_order.bob == bob:
                    work_orders_from_bob.append(work_order)
            return work_orders_from_bob


class Enrico(Character):
    """A Character that represents a Data Source that encrypts data for some policy's public key"""

    banner = ENRICO_BANNER
    _controller_class = EnricoJSONController
    _default_crypto_powerups = [SigningPower]

    def __init__(self, policy_encrypting_key, controller: bool = True, *args, **kwargs):
        self.policy_pubkey = policy_encrypting_key

        # Encrico never uses the blockchain, hence federated_only)
        kwargs['federated_only'] = True
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
                                   character_contoller=drone_enrico.controller,
                                   crash_on_error=crash_on_error)
        drone_enrico.controller = controller

        # Register Flask Decorator
        enrico_control = controller.make_web_controller()

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
                    'message_kit': b64encode(message_kit.to_bytes()).decode(),   # FIXME
                    'signature': b64encode(bytes(signature)).decode(),
                },
                'version': str(nucypher.__version__)
            }

            return Response(json.dumps(response_data), status=200)

        return controller
