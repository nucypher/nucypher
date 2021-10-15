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


import contextlib
import json
import time
from base64 import b64encode
from datetime import datetime
from json.decoder import JSONDecodeError
from pathlib import Path
from queue import Queue
from typing import Dict, Iterable, List, NamedTuple, Tuple, Union, Optional, Sequence, Set, Any

import maya
from constant_sorrow import constants
from constant_sorrow.constants import (
    PUBLIC_ONLY,
    STRANGER_ALICE,
    READY,
    INVALIDATED,
    NOT_SIGNED
)
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import Certificate, NameOID
from eth_typing.evm import ChecksumAddress
from flask import Response, request
from twisted.internet import reactor, stdio, threads
from twisted.internet.defer import Deferred
from twisted.internet.task import LoopingCall
from twisted.logger import Logger
from web3.types import TxReceipt

from nucypher.core import (
    MessageKit,
    HRAC,
    AuthorizedKeyFrag,
    UnauthorizedKeyFragError,
    TreasureMap,
    EncryptedTreasureMap,
    ReencryptionResponse,
    NodeMetadata
    )

import nucypher
from nucypher.acumen.nicknames import Nickname
from nucypher.acumen.perception import FleetSensor, ArchivedFleetState, RemoteUrsulaStatus
from nucypher.blockchain.eth.actors import BlockchainPolicyAuthor, Worker
from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.characters.banners import ALICE_BANNER, BOB_BANNER, ENRICO_BANNER, URSULA_BANNER
from nucypher.characters.base import Character, Learner
from nucypher.characters.control.interfaces import AliceInterface, BobInterface, EnricoInterface
from nucypher.cli.processes import UrsulaCommandProtocol
from nucypher.config.constants import END_OF_POLICIES_PROBATIONARY_PERIOD
from nucypher.config.storages import ForgetfulNodeStorage, NodeStorage
from nucypher.control.controllers import WebController
from nucypher.control.emitters import StdoutEmitter
from nucypher.crypto.keypairs import HostingKeypair
from nucypher.crypto.powers import (
    DecryptingPower,
    DelegatingPower,
    PowerUpError,
    SigningPower,
    TransactingPower,
    TLSHostingPower,
)
from nucypher.crypto.umbral_adapter import (
    PublicKey,
    reencrypt,
    VerifiedKeyFrag,
)
from nucypher.datastore.datastore import DatastoreTransactionError, RecordNotFound
from nucypher.datastore.queries import find_expired_policies
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nodes import NodeSprout, TEACHER_NODES, Teacher
from nucypher.network.protocols import parse_node_uri
from nucypher.network.retrieval import RetrievalClient
from nucypher.network.server import ProxyRESTServer, make_rest_app
from nucypher.network.trackers import AvailabilityTracker
from nucypher.policy.kits import PolicyMessageKit
from nucypher.policy.policies import Policy
from nucypher.utilities.logging import Logger
from nucypher.utilities.networking import validate_worker_ip


class Alice(Character, BlockchainPolicyAuthor):
    banner = ALICE_BANNER
    _interface_class = AliceInterface
    _default_crypto_powerups = [SigningPower, DecryptingPower, DelegatingPower]

    def __init__(self,

                 # Mode
                 is_me: bool = True,
                 federated_only: bool = False,
                 provider_uri: str = None,
                 signer=None,

                 # Ownership
                 checksum_address: str = None,

                 # M of N
                 threshold: Optional[int] = None,
                 shares: Optional[int] = None,

                 # Policy Value
                 rate: int = None,
                 payment_periods: int = None,

                 # Policy Storage
                 store_policy_credentials: bool = None,
                 store_character_cards: bool = None,

                 # Middleware
                 timeout: int = 10,  # seconds  # TODO: configure  NRN
                 network_middleware: RestMiddleware = None,
                 controller: bool = True,

                 *args, **kwargs) -> None:

        #
        # Fallback Policy Values
        #

        self.timeout = timeout

        if is_me:
            self.threshold = threshold
            self.shares = shares

            self._policy_queue = Queue()
            self._policy_queue.put(READY)
        else:
            self.threshold = STRANGER_ALICE
            self.shares = STRANGER_ALICE

        Character.__init__(self,
                           known_node_class=Ursula,
                           is_me=is_me,
                           federated_only=federated_only,
                           provider_uri=provider_uri,
                           checksum_address=checksum_address,
                           network_middleware=network_middleware,
                           *args, **kwargs)

        if is_me and not federated_only:  # TODO: #289
            if not provider_uri:
                raise ValueError('Provider URI is required to init a decentralized character.')

            blockchain = BlockchainInterfaceFactory.get_interface(provider_uri=self.provider_uri)
            signer = signer or Web3Signer(blockchain.client)  # fallback to web3 provider by default for Alice.
            self.transacting_power = TransactingPower(account=self.checksum_address, signer=signer)
            self._crypto_power.consume_power_up(self.transacting_power)
            BlockchainPolicyAuthor.__init__(self,
                                            domain=self.domain,
                                            transacting_power=self.transacting_power,
                                            registry=self.registry,
                                            rate=rate,
                                            payment_periods=payment_periods)

        self.log = Logger(self.__class__.__name__)
        if is_me:
            if controller:
                self.make_cli_controller()
            self.log.info(self.banner)

        self.active_policies = dict()
        self.revocation_kits = dict()
        self.store_policy_credentials = store_policy_credentials
        self.store_character_cards = store_character_cards

    def get_card(self) -> 'Card':
        from nucypher.policy.identity import Card
        card = Card.from_character(self)
        return card

    def add_active_policy(self, active_policy):
        """
        Adds a Policy object that is active on the NuCypher network to Alice's
        `active_policies` dictionary by the policy ID.
        """
        if active_policy.hrac in self.active_policies:
            raise KeyError("Policy already exists in active_policies.")
        self.active_policies[active_policy.hrac] = active_policy

    def generate_kfrags(self,
                        bob: 'Bob',
                        label: bytes,
                        threshold: int = None,
                        shares: int = None
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
        policy_key_and_kfrags = delegating_power.generate_kfrags(bob_pubkey_enc=bob_encrypting_key,
                                                                 signer=self.stamp.as_umbral_signer(),
                                                                 label=label,
                                                                 threshold=threshold or self.threshold,
                                                                 shares=shares or self.shares)
        return policy_key_and_kfrags

    def create_policy(self, bob: "Bob", label: bytes, **policy_params):
        """
        Create a Policy so that Bob has access to all resources under label.
        Generates KFrags and attaches them.
        """

        policy_params = self.generate_policy_parameters(**policy_params)
        shares = policy_params.pop('shares')

        # Generate KFrags
        public_key, kfrags = self.generate_kfrags(bob=bob,
                                                  label=label,
                                                  threshold=policy_params['threshold'],
                                                  shares=shares)

        payload = dict(label=label,
                       bob=bob,
                       kfrags=kfrags,
                       public_key=public_key,
                       threshold=policy_params['threshold'],
                       expiration=policy_params['expiration'])

        if self.federated_only:
            # Use known nodes
            from nucypher.policy.policies import FederatedPolicy
            policy = FederatedPolicy(publisher=self, **payload)

        else:
            # Sample from blockchain PolicyManager
            payload.update(**policy_params)
            policy = super().create_policy(**payload)

        return policy

    def generate_policy_parameters(self,
                                   threshold: int = None,
                                   shares: int = None,
                                   payment_periods: int = None,
                                   expiration: maya.MayaDT = None,
                                   *args, **kwargs
                                   ) -> dict:
        """
        Construct policy creation from parameters or overrides.
        """

        if not payment_periods and not expiration:
            raise ValueError("Policy end time must be specified as 'expiration' or 'payment_periods', got neither.")

        # Merge injected and default params.
        threshold = threshold or self.threshold
        shares = shares or self.shares
        base_payload = dict(threshold=threshold, shares=shares, expiration=expiration)

        if self.federated_only:
            if not expiration:
                raise TypeError("For a federated policy, you must specify expiration (payment_periods don't count).")
            if expiration <= maya.now():
                raise ValueError(f'Expiration must be in the future ({expiration}).')
        else:
            blocktime = maya.MayaDT(self.policy_agent.blockchain.get_blocktime())
            if expiration and (expiration <= blocktime):
                raise ValueError(f'Expiration must be in the future ({expiration} is earlier than blocktime {blocktime}).')

            # Calculate Policy Rate and Value
            payload = super().generate_policy_parameters(number_of_ursulas=shares,
                                                         payment_periods=payment_periods,
                                                         expiration=expiration,
                                                         *args, **kwargs)
            base_payload.update(payload)

        return base_payload

    def _check_grant_requirements(self, policy):
        """Called immediately before granting."""

        # TODO: Remove when the time is right.
        if policy.expiration > END_OF_POLICIES_PROBATIONARY_PERIOD:
            raise self.ActorError(f"The requested duration for this policy (until {policy.expiration}) exceeds the "
                                  f"probationary period ({END_OF_POLICIES_PROBATIONARY_PERIOD}).")

    def grant(self,
              bob: "Bob",
              label: bytes,
              handpicked_ursulas: set = None,
              timeout: int = None,
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
        self._check_grant_requirements(policy=policy)
        self.log.debug(f"Generated new policy proposal {policy} ... ")

        #
        # We'll find n Ursulas by default.  It's possible to "play the field" by trying different
        # value and expiration combinations on a limited number of Ursulas;
        # Users may decide to inject some market strategies here.
        #

        # If we're federated only, we need to block to make sure we have enough nodes.
        if self.federated_only and len(self.known_nodes) < policy.shares:
            good_to_go = self.block_until_number_of_known_nodes_is(number_of_nodes_to_know=policy.shares,
                                                                   learn_on_this_thread=True,
                                                                   timeout=timeout)
            if not good_to_go:
                raise ValueError(
                    "To make a Policy in federated mode, you need to know about "
                    "all the Ursulas you need (in this case, {}); there's no other way to "
                    "know which nodes to use.  Either pass them here or when you make the Policy, "
                    "or run the learning loop on a network with enough Ursulas.".format(policy.shares))

        self.log.debug(f"Enacting {policy} ... ")
        enacted_policy = policy.enact(network_middleware=self.network_middleware,
                                      handpicked_ursulas=handpicked_ursulas)

        self.add_active_policy(enacted_policy)
        return enacted_policy

    def get_policy_encrypting_key_from_label(self, label: bytes) -> PublicKey:
        alice_delegating_power = self._crypto_power.power_ups(DelegatingPower)
        policy_pubkey = alice_delegating_power.get_pubkey_from_label(label)
        return policy_pubkey

    def revoke(self,
               policy: 'Policy',
               onchain: bool = True,  # forced to False for federated mode
               offchain: bool = True
               ) -> Tuple[TxReceipt, Dict[ChecksumAddress, Tuple['Revocation', Exception]]]:

        if not (offchain or onchain):
            raise ValueError('offchain or onchain must be True to issue revocation')

        receipt, failed = dict(), dict()

        if onchain and (not self.federated_only):
            receipt = self.policy_agent.revoke_policy(policy_id=bytes(policy.hrac),
                                                      transacting_power=self._crypto_power.power_ups(TransactingPower))

        if offchain:
            """
            Parses the treasure map and revokes arrangements in it.
            If any arrangements can't be revoked, then the node_id is added to a
            dict as a key, and the revocation and Ursula's response is added as
            a value.
            """
            try:
                # Wait for a revocation threshold of nodes to be known ((n - m) + 1)
                revocation_threshold = ((policy.shares - policy.threshold) + 1)
                self.block_until_specific_nodes_are_known(
                    policy.revocation_kit.revokable_addresses,
                    allow_missing=(policy.shares - revocation_threshold))
            except self.NotEnoughTeachers:
                raise  # TODO  NRN

            for node_id in policy.revocation_kit.revokable_addresses:
                ursula = self.known_nodes[node_id]
                revocation = policy.revocation_kit[node_id]
                try:
                    response = self.network_middleware.revoke_arrangement(ursula, revocation)
                except self.network_middleware.NotFound:
                    failed[node_id] = (revocation, self.network_middleware.NotFound)
                except self.network_middleware.UnexpectedResponse:
                    failed[node_id] = (revocation, self.network_middleware.UnexpectedResponse)
                else:
                    if response.status_code != 200:
                        message = f"Failed to revocation for node {node_id} with status code {response.status_code}"
                        raise self.ActorError(message)

        return receipt, failed

    def decrypt_message_kit(self, label: bytes, message_kit: MessageKit) -> List[bytes]:
        """
        Decrypt this Alice's own encrypted data.

        I/O signatures match Bob's retrieve interface.
        """

        delegating_power = self._crypto_power.power_ups(DelegatingPower)
        decrypting_power = delegating_power.get_decrypting_power_from_label(label)
        cleartext = decrypting_power.decrypt(message_kit)

        # TODO: why does it return a list of cleartexts but takes a single message kit?
        # Shouldn't it be able to take a list of them too?
        return [cleartext]

    def make_web_controller(drone_alice, crash_on_error: bool = False):
        app_name = bytes(drone_alice.stamp).hex()[:6]
        controller = WebController(app_name=app_name,
                                   crash_on_error=crash_on_error,
                                   interface=drone_alice._interface_class(character=drone_alice))
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
            return controller(method_name='public_keys', control_request=request)

        @alice_flask_control.route("/create_policy", methods=['PUT'])
        def create_policy() -> Response:
            """
            Character control endpoint for creating a policy and making
            arrangements with Ursulas.
            """
            response = controller(method_name='create_policy', control_request=request)
            return response

        @alice_flask_control.route("/decrypt", methods=['POST'])
        def decrypt():
            """
            Character control endpoint for decryption of Alice's own policy data.
            """
            response = controller(method_name='decrypt', control_request=request)
            return response

        @alice_flask_control.route('/derive_policy_encrypting_key/<label>', methods=['POST'])
        def derive_policy_encrypting_key(label) -> Response:
            """
            Character control endpoint for deriving a policy encrypting given a unicode label.
            """
            response = controller(method_name='derive_policy_encrypting_key', control_request=request, label=label)
            return response

        @alice_flask_control.route("/grant", methods=['PUT'])
        def grant() -> Response:
            """
            Character control endpoint for policy granting.
            """
            response = controller(method_name='grant', control_request=request)
            return response

        @alice_flask_control.route("/revoke", methods=['DELETE'])
        def revoke():
            """
            Character control endpoint for policy revocation.
            """
            response = controller(method_name='revoke', control_request=request)
            return response

        return controller


class Bob(Character):
    banner = BOB_BANNER
    _interface_class = BobInterface

    _default_crypto_powerups = [SigningPower, DecryptingPower]

    class IncorrectCFragsReceived(Exception):
        """
        Raised when Bob detects incorrect CFrags returned by some Ursulas
        """

        def __init__(self, evidence: List):
            self.evidence = evidence

    def __init__(self,
                 is_me: bool = True,
                 controller: bool = True,
                 verify_node_bonding: bool = False,
                 provider_uri: str = None,
                 *args, **kwargs) -> None:

        Character.__init__(self,
                           is_me=is_me,
                           known_node_class=Ursula,
                           verify_node_bonding=verify_node_bonding,
                           provider_uri=provider_uri,
                           *args, **kwargs)

        if controller:
            self.make_cli_controller()

        # Cache of decrypted treasure maps
        self._treasure_maps: Dict[HRAC, TreasureMap] = {}

        self.log = Logger(self.__class__.__name__)
        if is_me:
            self.log.info(self.banner)

    def get_card(self) -> 'Card':
        from nucypher.policy.identity import Card
        card = Card.from_character(self)
        return card

    def _decrypt_treasure_map(self,
                              encrypted_treasure_map: EncryptedTreasureMap,
                              publisher_verifying_key: PublicKey
                              ) -> TreasureMap:
        decrypting_power = self._crypto_power.power_ups(DecryptingPower)
        return decrypting_power.decrypt_treasure_map(encrypted_treasure_map, publisher_verifying_key)

    def retrieve(
            self,
            message_kits: Sequence[Union[MessageKit, PolicyMessageKit]],
            alice_verifying_key: PublicKey, # KeyFrag signer's key
            encrypted_treasure_map: EncryptedTreasureMap,
            publisher_verifying_key: Optional[PublicKey] = None,
            ) -> List[PolicyMessageKit]:
        """
        Attempts to retrieve reencrypted capsule fragments
        corresponding to given message kits from Ursulas.

        Accepts both "clean" message kits (obtained from a side channel)
        and "loaded" ones (with earlier retrieved capsule frags attached,
        along with the addresses of Ursulas they were obtained from).

        Returns a list of loaded message kits corresponding to the input list,
        with the kits containing the capsule fragments obtained during the retrieval.
        These kits can be used as an external cache to preserve the cfrags between
        several retrieval attempts.
        """

        if not publisher_verifying_key:
            publisher_verifying_key = alice_verifying_key

        if encrypted_treasure_map.hrac in self._treasure_maps:
            # A small optimization to avoid multiple treasure map decryptions.
            treasure_map = self._treasure_maps[encrypted_treasure_map.hrac]
        else:
            # Have to decrypt the treasure map first to find out what the threshold is.
            # Otherwise we could check the message kits for completeness right away.
            treasure_map = self._decrypt_treasure_map(encrypted_treasure_map, publisher_verifying_key)

        # Normalize input
        message_kits: List[PolicyMessageKit] = [
            PolicyMessageKit.from_message_kit(message_kit, treasure_map.policy_encrypting_key, treasure_map.threshold)
                if isinstance(message_kit, MessageKit) else message_kit
            for message_kit in message_kits
            ]

        # Clear up all unrelated information from message kits before retrieval.
        retrieval_kits = [message_kit.as_retrieval_kit() for message_kit in message_kits]

        # Retrieve capsule frags
        client = RetrievalClient(learner=self)
        retrieval_results = client.retrieve_cfrags(
            treasure_map=treasure_map,
            retrieval_kits=retrieval_kits,
            alice_verifying_key=alice_verifying_key,
            bob_encrypting_key=self.public_keys(DecryptingPower),
            bob_verifying_key=self.stamp.as_umbral_pubkey())

        # Refill message kits with newly retrieved capsule frags
        results = []
        for message_kit, retrieval_result in zip(message_kits, retrieval_results):
            results.append(message_kit.with_result(retrieval_result))

        return results

    def retrieve_and_decrypt(self, *args, **kwds) -> List[bytes]:
        """
        Attempts to retrieve reencrypted capsule fragments from Ursulas
        and decrypt the ciphertexts in the given message kits.

        See ``retrieve()`` for the parameter list.
        """

        message_kits = self.retrieve(*args, **kwds)

        for message_kit in message_kits:
            if not message_kit.is_decryptable_by_receiver():
                raise Ursula.NotEnoughUrsulas(f"Not enough cfrags retrieved to open capsule {message_kit.capsule}")

        cleartexts = []
        decrypting_power = self._crypto_power.power_ups(DecryptingPower)
        for message_kit in message_kits:
            cleartext = decrypting_power.decrypt(message_kit)
            cleartexts.append(cleartext)

        return cleartexts

    def make_web_controller(drone_bob, crash_on_error: bool = False):
        app_name = bytes(drone_bob.stamp).hex()[:6]
        controller = WebController(app_name=app_name,
                                   crash_on_error=crash_on_error,
                                   interface=drone_bob._interface_class(character=drone_bob))

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
            return controller(method_name='public_keys', control_request=request)

        @bob_control.route('/retrieve_and_decrypt', methods=['POST'])
        def retrieve_and_decrypt():
            """
            Character control endpoint for re-encrypting and decrypting policy
            data.
            """
            return controller(method_name='retrieve_and_decrypt', control_request=request)

        return controller


class Ursula(Teacher, Character, Worker):

    banner = URSULA_BANNER
    _alice_class = Alice

    _default_crypto_powerups = [
        SigningPower,
        DecryptingPower,
        # TLSHostingPower  # Still considered a default for Ursula, but needs the host context
    ]

    _pruning_interval = 60  # seconds

    class NotEnoughUrsulas(Learner.NotEnoughTeachers, StakingEscrowAgent.NotEnoughStakers):
        """
        All Characters depend on knowing about enough Ursulas to perform their role.
        This exception is raised when a piece of logic can't proceed without more Ursulas.
        """

    class NotFound(Exception):
        pass

    def __init__(self,

                 # Ursula
                 rest_host: str,
                 rest_port: int,
                 domain: str,
                 is_me: bool = True,

                 certificate: Certificate = None,
                 certificate_filepath: Optional[Path] = None,

                 db_filepath: Optional[Path] = None,
                 interface_signature=None,
                 timestamp=None,
                 availability_check: bool = False,  # TODO: Remove from init

                 # Blockchain
                 checksum_address: ChecksumAddress = None,
                 worker_address: ChecksumAddress = None,  # TODO: deprecate, and rename to "checksum_address"
                 client_password: str = None,
                 decentralized_identity_evidence=NOT_SIGNED,
                 provider_uri: str = None,

                 # Character
                 abort_on_learning_error: bool = False,
                 federated_only: bool = False,
                 crypto_power=None,
                 known_nodes: Iterable[Teacher] = None,

                 **character_kwargs
                 ) -> None:

        Character.__init__(self,
                           is_me=is_me,
                           checksum_address=checksum_address,
                           federated_only=federated_only,
                           crypto_power=crypto_power,
                           abort_on_learning_error=abort_on_learning_error,
                           known_nodes=known_nodes,
                           domain=domain,
                           known_node_class=Ursula,
                           include_self_in_the_state=True,
                           provider_uri=provider_uri,
                           **character_kwargs)

        if is_me:

            # Operating Mode
            self.known_node_class.set_federated_mode(federated_only)

            # Health Checks
            self._availability_check = availability_check
            self._availability_tracker = AvailabilityTracker(ursula=self)

            # Datastore Pruning
            self.__pruning_task: Union[Deferred, None] = None
            self._datastore_pruning_task = LoopingCall(f=self.__prune_datastore)

            # Decentralized Worker
            if not federated_only:

                if not provider_uri:
                    raise ValueError('Provider URI is required to init a decentralized character.')

                # TODO: Move to method
                # Prepare a TransactingPower from worker node's transacting keys
                transacting_power = TransactingPower(account=worker_address,
                                                     password=client_password,
                                                     signer=self.signer,
                                                     cache=True)
                self.transacting_power = transacting_power
                self._crypto_power.consume_power_up(transacting_power)

                # Use this power to substantiate the stamp
                self.__substantiate_stamp()
                decentralized_identity_evidence = self.__decentralized_identity_evidence

                try:
                    Worker.__init__(self,
                                    is_me=is_me,
                                    domain=self.domain,
                                    transacting_power=self.transacting_power,
                                    registry=self.registry,
                                    worker_address=worker_address)
                except (Exception, self.WorkerError):
                    # TODO: ... thanks I hate it
                    # TODO: Do not announce self to "other nodes" until this init is finished.
                    # It's not possible to finish constructing this node.
                    self.stop(halt_reactor=False)
                    raise

            self.rest_server = self._make_local_server(host=rest_host,
                                                       port=rest_port,
                                                       db_filepath=db_filepath,
                                                       domain=domain)

            # Self-signed TLS certificate of self for Teacher.__init__
            certificate_filepath = self._crypto_power.power_ups(TLSHostingPower).keypair.certificate_filepath
            certificate = self._crypto_power.power_ups(TLSHostingPower).keypair.certificate

            # Only *YOU* can prevent forest fires
            self.revoked_policies: Set[bytes] = set()

            # Care to introduce yourself?
            message = "THIS IS YOU: {}: {}".format(self.__class__.__name__, self)
            self.log.info(message)
            self.log.info(self.banner.format(self.nickname))

        else:
            # Stranger HTTP Server
            # TODO: Use InterfaceInfo only
            self.rest_server = ProxyRESTServer(rest_host=rest_host, rest_port=rest_port)

        # Teacher (All Modes)
        Teacher.__init__(self,
                         domain=domain,
                         certificate=certificate,
                         certificate_filepath=certificate_filepath,
                         interface_signature=interface_signature,
                         timestamp=timestamp,
                         decentralized_identity_evidence=decentralized_identity_evidence)

    def __get_hosting_power(self, host: str) -> TLSHostingPower:
        try:
            # Pre-existing or injected power
            tls_hosting_power = self._crypto_power.power_ups(TLSHostingPower)
        except TLSHostingPower.not_found_error:
            if self.keystore:
                # Derive TLS private key from seed
                tls_hosting_power = self.keystore.derive_crypto_power(TLSHostingPower, host=host)
            else:
                # Generate ephemeral private key ("Dev Mode")
                tls_hosting_keypair = HostingKeypair(host=host, generate_certificate=True)
                tls_hosting_power = TLSHostingPower(keypair=tls_hosting_keypair, host=host)
            self._crypto_power.consume_power_up(tls_hosting_power)  # Consume!
        return tls_hosting_power

    def _make_local_server(self, host, port, domain, db_filepath) -> ProxyRESTServer:
        rest_app, datastore = make_rest_app(
            this_node=self,
            db_filepath=db_filepath,
            domain=domain,
        )
        rest_server = ProxyRESTServer(rest_host=host,
                                      rest_port=port,
                                      rest_app=rest_app,
                                      datastore=datastore,
                                      hosting_power=self.__get_hosting_power(host=host))
        return rest_server

    def __substantiate_stamp(self):
        transacting_power = self._crypto_power.power_ups(TransactingPower)
        signature = transacting_power.sign_message(message=bytes(self.stamp))
        self.__decentralized_identity_evidence = signature
        self.__worker_address = transacting_power.account
        message = f"Created decentralized identity evidence: {self.__decentralized_identity_evidence[:10].hex()}"
        self.log.debug(message)

    def __prune_datastore(self) -> None:
        """Deletes all expired arrangements, kfrags, and treasure maps in the datastore."""
        now = maya.MayaDT.from_datetime(datetime.fromtimestamp(self._datastore_pruning_task.clock.seconds()))
        try:
            with find_expired_policies(self.datastore, now) as expired_policies:
                for policy in expired_policies:
                    policy.delete()
                result = len(expired_policies)
        except RecordNotFound:
            self.log.debug("No expired policy arrangements found.")
        except DatastoreTransactionError:
            self.log.warn(f"Failed to prune policy arrangements; DB session rolled back.")
        else:
            if result > 0:
                self.log.debug(f"Pruned {result} policy arrangements.")

    def __preflight(self) -> None:
        """Called immediately before running services
        If an exception is raised, Ursula startup will be interrupted.

        """
        validate_worker_ip(worker_ip=self.rest_interface.host)

    def run(self,
            emitter: StdoutEmitter = None,
            discovery: bool = True,  # TODO: see below
            availability: bool = False,
            worker: bool = True,
            pruning: bool = True,
            interactive: bool = False,
            hendrix: bool = True,
            start_reactor: bool = True,
            prometheus_config: 'PrometheusMetricsConfig' = None,
            preflight: bool = True,
            block_until_ready: bool = True,
            eager: bool = False
            ) -> None:

        """Schedule and start select ursula services, then optionally start the reactor."""

        # Connect to Provider
        if not self.federated_only:
            if not BlockchainInterfaceFactory.is_interface_initialized(provider_uri=self.provider_uri):
                BlockchainInterfaceFactory.initialize_interface(provider_uri=self.provider_uri)

        if preflight:
            self.__preflight()

        #
        # Async loops ordered by schedule priority
        #

        if emitter:
            emitter.message(f"Starting services", color='yellow')

        if pruning:
            self.__pruning_task = self._datastore_pruning_task.start(interval=self._pruning_interval, now=eager)
            if emitter:
                emitter.message(f"✓ Database Pruning", color='green')

        if discovery and not self.lonely:
            self.start_learning_loop(now=eager)
            if emitter:
                emitter.message(f"✓ Node Discovery ({self.domain.capitalize()})", color='green')

        if self._availability_check or availability:
            self._availability_tracker.start(now=eager)
            if emitter:
                emitter.message(f"✓ Availability Checks", color='green')

        if worker and not self.federated_only:
            if block_until_ready:
                # Sets (staker's) checksum address; Prevent worker startup before bonding
                self.block_until_ready()
            self.stakes.checksum_address = self.checksum_address
            self.stakes.refresh()
            if not self.stakes.has_active_substakes:
                msg = "No active stakes found for worker."
                if emitter:
                    emitter.message(f"✗ {msg}", color='red')
                self.log.error(msg)
                return
            self.work_tracker.start(commit_now=True)  # requirement_func=self._availability_tracker.status)  # TODO: #2277
            if emitter:
                emitter.message(f"✓ Work Tracking", color='green')

        #
        # Non-order dependant services
        #

        if prometheus_config:
            # Locally scoped to prevent import without prometheus explicitly installed
            from nucypher.utilities.prometheus.metrics import start_prometheus_exporter
            start_prometheus_exporter(ursula=self, prometheus_config=prometheus_config)
            if emitter:
                emitter.message(f"✓ Prometheus Exporter", color='green')

        if interactive and emitter:
            stdio.StandardIO(UrsulaCommandProtocol(ursula=self, emitter=emitter))

        if hendrix:
            if emitter:
                emitter.message(f"✓ Rest Server https://{self.rest_interface}", color='green')

            deployer = self.get_deployer()
            deployer.addServices()
            deployer.catalogServers(deployer.hendrix)

            if not start_reactor:
                return

            if emitter:
                emitter.message("Working ~ Keep Ursula Online!", color='blue', bold=True)

            try:
                deployer.run()  # <--- Blocking Call (Reactor)
            except Exception as e:
                self.log.critical(str(e))
                if emitter:
                    emitter.message(f"{e.__class__.__name__} {e}", color='red', bold=True)
                raise  # Crash :-(

        elif start_reactor:  # ... without hendrix
            reactor.run()  # <--- Blocking Call (Reactor)

    def stop(self, halt_reactor: bool = False) -> None:
        """
        Stop services for partially or fully initialized characters.
        # CAUTION #
        """
        self.log.debug(f"---------Stopping {self}")
        # Handles the shutdown of a partially initialized character.
        with contextlib.suppress(AttributeError):  # TODO: Is this acceptable here, what are alternatives?
            self._availability_tracker.stop()
            self.stop_learning_loop()
            if not self.federated_only:
                self.work_tracker.stop()
            if self._datastore_pruning_task.running:
                self._datastore_pruning_task.stop()
        if halt_reactor:
            reactor.stop()

    def _finalize(self):
        """
        Cleans up Ursula from objects that may eat up system resources.
        Useful for testing purposes, where many Ursulas are created and destroyed,
        and references to them may persist for too long.
        This method is not needed if all references to the Ursula are released.

        **Warning:** invalidates the Ursula.
        """

        # `rest_server` holds references to the datastore (directly and via `rest_app`).
        # An open datastore hogs up file descriptors.
        self.rest_server = INVALIDATED

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

    def metadata(self) -> NodeMetadata:
        # TODO: sometimes during cleanup in tests the learner is still running and can call this method,
        # but `._finalize()` is already called, so `rest_interface` is unavailable.
        # That doesn't lead to test fails, but produces some tracebacks in stderr.
        # The whole cleanup situation in tests is messed up and needs to be fixed.
        return NodeMetadata(public_address=self.canonical_public_address,
                            domain=self.domain,
                            timestamp_epoch=self.timestamp.epoch,
                            interface_signature=self._interface_signature,
                            decentralized_identity_evidence=self.decentralized_identity_evidence,
                            verifying_key=self.public_keys(SigningPower),
                            encrypting_key=self.public_keys(DecryptingPower),
                            certificate_bytes=self.certificate.public_bytes(Encoding.PEM),
                            host=self.rest_interface.host,
                            port=self.rest_interface.port,
                            )

    #
    # Alternate Constructors
    #

    @classmethod
    def from_metadata_bytes(cls, metadata_bytes):
        # TODO: should be a method of `NodeSprout`, or maybe `NodeMetadata` *is* `NodeSprout`.
        # Fix when we get rid of inplace maturation.
        return NodeSprout(NodeMetadata.from_bytes(metadata_bytes))

    @classmethod
    def from_rest_url(cls,
                      network_middleware: RestMiddleware,
                      host: str,
                      port: int,
                      certificate_filepath,
                      *args, **kwargs
                      ):
        response_data = network_middleware.client.node_information(host, port,
                                                                   certificate_filepath=certificate_filepath)

        stranger_ursula_from_public_keys = cls.from_metadata_bytes(response_data)

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
    def seednode_for_network(cls, network: str) -> 'Ursula':
        """Returns a default seednode ursula for a given network."""
        try:
            url = TEACHER_NODES[network][0]
        except KeyError:
            raise ValueError(f'"{network}" is not a known network.')
        except IndexError:
            raise ValueError(f'No default seednodes available for "{network}".')
        ursula = cls.from_seed_and_stake_info(seed_uri=url)
        return ursula

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

            except NodeSeemsToBeDown as e:
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
            network_middleware = RestMiddleware(registry=registry)

        # Parse node URI
        host, port, staker_address = parse_node_uri(seed_uri)

        # Fetch the hosts TLS certificate and read the common name
        try:
            certificate = network_middleware.get_certificate(host=host, port=port)
        except NodeSeemsToBeDown as e:
            e.args += (f"While trying to load seednode {seed_uri}",)
            e.crash_right_now = True
            raise
        real_host = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value

        # Create a temporary certificate storage area
        temp_node_storage = ForgetfulNodeStorage(federated_only=federated_only)
        temp_certificate_filepath = temp_node_storage.store_node_certificate(certificate=certificate, port=port)

        # Load the host as a potential seed node
        potential_seed_node = cls.from_rest_url(
            host=real_host,
            port=port,
            network_middleware=network_middleware,
            certificate_filepath=temp_certificate_filepath,
            *args,
            **kwargs
        )

        # Check the node's stake (optional)
        if minimum_stake > 0 and staker_address and not federated_only:
            staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
            seednode_stake = staking_agent.get_locked_tokens(staker_address=staker_address)
            if seednode_stake < minimum_stake:
                raise Learner.NotATeacher(f"{staker_address} is staking less than the specified minimum stake value ({minimum_stake}).")

        # OK - everyone get out
        temp_node_storage.forget()
        return potential_seed_node

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
    # Re-Encryption
    #

    def _decrypt_kfrag(self,
                       encrypted_kfrag: MessageKit, # TODO: make its own type? See #2743
                       author_verifying_key: PublicKey
                       ) -> AuthorizedKeyFrag:

        if author_verifying_key != encrypted_kfrag.sender_verifying_key:
            raise ValueError("This encrypted AuthorizedKeyFrag was not created "
                            f"by the expected author {author_verifying_key}")

        decrypting_power = self._crypto_power.power_ups(DecryptingPower)
        kfrag_payload = decrypting_power.decrypt(encrypted_kfrag)
        return AuthorizedKeyFrag.from_bytes(kfrag_payload)

    def verify_kfrag_authorization(self,
                                   hrac: HRAC,
                                   author_verifying_key: PublicKey,
                                   publisher_verifying_key: PublicKey,
                                   authorized_kfrag: AuthorizedKeyFrag,
                                   ) -> VerifiedKeyFrag:

        try:
            verified_kfrag = authorized_kfrag.verify(hrac=hrac,
                                                     author_verifying_key=author_verifying_key,
                                                     publisher_verifying_key=publisher_verifying_key)
        except UnauthorizedKeyFragError as e:
            raise Policy.Unauthorized from e

        if hrac in self.revoked_policies:
            # Note: This is only an off-chain and in-memory check.
            raise Policy.Unauthorized  # Denied

        return verified_kfrag

    def _reencrypt(self, kfrag: VerifiedKeyFrag, capsules) -> ReencryptionResponse:
        cfrags = []
        for capsule in capsules:
            cfrag = reencrypt(capsule, kfrag)
            cfrags.append(cfrag)
            self.log.info(f"Re-encrypted capsule {capsule} -> made {cfrag}.")

        return ReencryptionResponse.construct_by_ursula(capsules, cfrags, self.stamp.as_umbral_signer())

    def status_info(self, omit_known_nodes: bool = False) -> 'LocalUrsulaStatus':

        domain = self.domain
        version = nucypher.__version__

        fleet_state = self.known_nodes.latest_state()
        previous_fleet_states = self.known_nodes.previous_states(4)

        if not omit_known_nodes:
            known_nodes_info = [self.known_nodes.status_info(node) for node in self.known_nodes]
        else:
            known_nodes_info = None

        if not self.federated_only:
            balance_eth = float(self.eth_balance)
            balance_nu = float(self.token_balance.to_tokens())
            missing_commitments = self.missing_commitments
            last_committed_period = self.last_committed_period
        else:
            balance_eth = None
            balance_nu = None
            missing_commitments = None
            last_committed_period = None

        return LocalUrsulaStatus(nickname=self.nickname,
                                 staker_address=self.checksum_address,
                                 worker_address=self.worker_address,
                                 rest_url=self.rest_url(),
                                 timestamp=self.timestamp,
                                 domain=domain,
                                 version=version,
                                 fleet_state=fleet_state,
                                 previous_fleet_states=previous_fleet_states,
                                 known_nodes=known_nodes_info,
                                 balance_eth=balance_eth,
                                 balance_nu=balance_nu,
                                 missing_commitments=missing_commitments,
                                 last_committed_period=last_committed_period,
                                 )


class LocalUrsulaStatus(NamedTuple):
    nickname: Nickname
    staker_address: ChecksumAddress
    worker_address: str
    rest_url: str
    timestamp: maya.MayaDT
    domain: str
    version: str
    fleet_state: ArchivedFleetState
    previous_fleet_states: List[ArchivedFleetState]
    known_nodes: Optional[List[RemoteUrsulaStatus]]
    balance_eth: float
    balance_nu: float
    missing_commitments: int
    last_committed_period: int

    def to_json(self) -> Dict[str, Any]:
        if self.known_nodes is None:
            known_nodes_json = None
        else:
            known_nodes_json = [status.to_json() for status in self.known_nodes]
        return dict(nickname=self.nickname.to_json(),
                    staker_address=self.staker_address,
                    worker_address=self.worker_address,
                    rest_url=self.rest_url,
                    timestamp=self.timestamp.iso8601(),
                    domain=self.domain,
                    version=self.version,
                    fleet_state=self.fleet_state.to_json(),
                    previous_fleet_states=[state.to_json() for state in self.previous_fleet_states],
                    known_nodes=known_nodes_json,
                    balance_eth=self.balance_eth,
                    balance_nu=self.balance_nu,
                    missing_commitments=self.missing_commitments,
                    last_committed_period=self.last_committed_period,
                    )


class Enrico(Character):
    """A Character that represents a Data Source that encrypts data for some policy's public key"""

    banner = ENRICO_BANNER
    _interface_class = EnricoInterface
    _default_crypto_powerups = [SigningPower]

    def __init__(self,
                 is_me: bool = True,
                 policy_encrypting_key: Optional[PublicKey] = None,
                 controller: bool = True,
                 *args, **kwargs):

        self._policy_pubkey = policy_encrypting_key

        # Enrico never uses the blockchain (hence federated_only)
        kwargs['federated_only'] = True
        kwargs['known_node_class'] = None
        super().__init__(is_me=is_me, *args, **kwargs)

        if controller:
            self.make_cli_controller()

        self.log = Logger(f'{self.__class__.__name__}-{bytes(self.public_keys(SigningPower)).hex()[:6]}')
        if is_me:
            self.log.info(self.banner.format(policy_encrypting_key))

    def encrypt_message(self, plaintext: bytes) -> MessageKit:
        # TODO: #2107 Rename to "encrypt"
        message_kit = MessageKit.author(recipient_key=self.policy_pubkey,
                                        plaintext=plaintext,
                                        signer=self.stamp.as_umbral_signer())
        return message_kit

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

    @property
    def policy_pubkey(self):
        if not self._policy_pubkey:
            raise TypeError("This Enrico doesn't know which policy encrypting key he used.  Oh well.")
        return self._policy_pubkey

    def _set_known_node_class(self, *args, **kwargs):
        """
        Enrico doesn't init nodes, so it doesn't care what class they are.
        """

    def make_web_controller(drone_enrico, crash_on_error: bool = False):

        app_name = bytes(drone_enrico.stamp).hex()[:6]
        controller = WebController(app_name=app_name,
                                   crash_on_error=crash_on_error,
                                   interface=drone_enrico._interface_class(character=drone_enrico))

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
            message_kit = drone_enrico.encrypt_message(bytes(message, encoding='utf-8'))

            response_data = {
                'result': {
                    'message_kit': b64encode(bytes(message_kit)).decode(),  # FIXME, but NRN
                },
                'version': str(nucypher.__version__)
            }

            return Response(json.dumps(response_data), status=200)

        return controller
