import time
from collections import deque
from contextlib import suppress
from queue import Queue
from typing import Optional, Set, Union

import maya
import requests
from constant_sorrow.constants import (
    FLEET_STATES_MATCH,
    NOT_SIGNED,
    RELAX,
)
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import Certificate, load_der_x509_certificate
from eth_utils import to_checksum_address
from nucypher_core import MetadataResponse, MetadataResponsePayload, NodeMetadata
from nucypher_core.umbral import Signature
from requests.exceptions import SSLError
from twisted.internet import reactor, task
from twisted.internet.defer import Deferred

from nucypher import characters
from nucypher.acumen.nicknames import Nickname
from nucypher.acumen.perception import FleetSensor
from nucypher.blockchain.eth.agents import ContractAgency, TACoApplicationAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.domains import TACoDomain
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.config.constants import SeednodeMetadata
from nucypher.crypto.powers import (
    CryptoPower,
    DecryptingPower,
    NoSigningPower,
    RitualisticPower,
    SigningPower,
)
from nucypher.crypto.signing import InvalidSignature, SignatureStamp
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import RestMiddleware
from nucypher.network.protocols import InterfaceInfo, SuspiciousActivity
from nucypher.network.seednodes import TEACHER_NODES
from nucypher.utilities.logging import Logger


class NodeSprout:
    """
    An abridged node class designed for optimization of instantiation of > 100 nodes simultaneously.
    """

    verified_node = False

    def __init__(self, metadata: NodeMetadata):
        self._metadata = metadata
        self._metadata_payload = metadata.payload

        # cached properties
        self._checksum_address = None
        self._nickname = None
        self._hash = None
        self._repr = None
        self._rest_interface = None

        self._is_finishing = False
        self._finishing_mutex = Queue()

    def __eq__(self, other):
        try:
            other_stamp = other.stamp
        except (AttributeError, NoSigningPower):
            return False
        return bytes(self.stamp) == bytes(other_stamp)

    def __hash__(self):
        if not self._hash:
            self._hash = int.from_bytes(bytes(self.stamp), byteorder="big")
        return self._hash

    def __repr__(self):
        if not self._repr:
            self._repr = f"({self.__class__.__name__})⇀{self.nickname}↽ ({self.checksum_address})"
        return self._repr

    @property
    def checksum_address(self):
        if not self._checksum_address:
            self._checksum_address = to_checksum_address(bytes(self.canonical_address))
        return self._checksum_address

    @property
    def canonical_address(self):
        return self._metadata_payload.staking_provider_address

    @property
    def nickname(self):
        if not self._nickname:
            self._nickname = Nickname.from_seed(self.checksum_address)
        return self._nickname

    @property
    def rest_interface(self):
        if not self._rest_interface:
            self._rest_interface = InterfaceInfo(
                self._metadata_payload.host, self._metadata_payload.port
            )
        return self._rest_interface

    def rest_url(self):
        return self.rest_interface.uri

    def metadata(self):
        return self._metadata

    @property
    def verifying_key(self):
        return self._metadata_payload.verifying_key

    @property
    def encrypting_key(self):
        return self._metadata_payload.encrypting_key

    @property
    def ferveo_public_key(self):
        return self._metadata_payload.ferveo_public_key

    @property
    def operator_signature_from_metadata(self):
        return self._metadata_payload.operator_signature or NOT_SIGNED

    @property
    def timestamp(self):
        return maya.MayaDT(self._metadata_payload.timestamp_epoch)

    @property
    def stamp(self) -> SignatureStamp:
        return SignatureStamp(self._metadata_payload.verifying_key)

    @property
    def domain(self) -> str:
        return self._metadata_payload.domain

    def finish(self):
        # Remote node cryptographic material
        crypto_power = CryptoPower()
        crypto_power.consume_power_up(
            SigningPower(public_key=self._metadata_payload.verifying_key)
        )
        crypto_power.consume_power_up(
            DecryptingPower(public_key=self._metadata_payload.encrypting_key)
        )
        crypto_power.consume_power_up(
            RitualisticPower(public_key=self._metadata_payload.ferveo_public_key)
        )
        tls_certificate = load_der_x509_certificate(
            self._metadata_payload.certificate_der, backend=default_backend()
        )

        return characters.lawful.Ursula(
            is_peer=True,
            crypto_power=crypto_power,
            host=self._metadata_payload.host,
            port=self._metadata_payload.port,
            domain=self._metadata_payload.domain,
            timestamp=self.timestamp,
            certificate=tls_certificate,
            metadata=self._metadata,
        )

    def mature(self):
        if self._is_finishing:
            return self._finishing_mutex.get()

        self._is_finishing = True  # Prevent reentrance.
        _finishing_mutex = self._finishing_mutex
        mature_node = self.finish()

        self.__class__ = mature_node.__class__
        self.__dict__ = mature_node.__dict__
        _finishing_mutex.put(self)

        return self  # To reduce the awkwardity of renaming; this is always the weird part of polymorphism for me.


class DiscoveryCanceller:
    def __init__(self):
        self.stop_now = False

    def __call__(self, peering_deferred):
        if self.stop_now:
            assert False
        self.stop_now = True
        # peering_deferred.callback(RELAX)


class Learner:
    """
    Any participant in the "peering loop" - a class inheriting from
    this one has the ability, synchronously or asynchronously,
    to learn about nodes in the network, verify some essential
    details about them, and store information about them for later use.
    """

    _SHORT_LEARNING_DELAY = 10  # seconds
    LEARNING_TIMEOUT = 10

    _crashed = (
        False  # moved from Character - why was this in Character and not Learner before
    )

    tracker_class = FleetSensor

    invalid_metadata_message = (
        "{} has invalid metadata.  The node's stake may have ended, "
        "or it is transitioning to a new interface. Ignoring."
    )

    class P2PError(Exception):
        pass

    class NotEnoughPeers(P2PError):
        crash_right_now = True

    class UnresponsivePeer(P2PError):
        pass

    class NotATeacher(P2PError):
        """
        Raised when a character cannot be properly utilized because
        it does not have the proper attributes for peering or verification.
        """

    def __init__(
        self,
        domain: TACoDomain,
        network_middleware: RestMiddleware = None,
        start_peering_now: bool = False,
        peering_on_same_thread: bool = True,
        seed_nodes: tuple = None,
        abort_on_peering_error: bool = False,
        lonely: bool = False,
        verify_peer_bonding: bool = True,
        include_self_in_the_state: bool = True,
    ):
        self.log = Logger("p2p")

        # async
        self.peering_deferred = Deferred()
        self._discovery_canceller = DiscoveryCanceller()
        self._peering_task = task.LoopingCall(self.continue_peering)

        # network
        self.network_middleware = network_middleware or RestMiddleware(
            eth_endpoint=self.eth_endpoint, registry=self.registry
        )

        # settings
        self.domain = domain
        self.lonely = lonely
        self._verify_peer_bonding = verify_peer_bonding
        self.start_peering_now = start_peering_now
        self.peering_on_same_thread = peering_on_same_thread
        self._abort_on_peering_error = abort_on_peering_error

        # initialize
        self._current_peer = None
        self._peers_sample = deque()
        self._peering_round = 0
        self._rounds_without_new_nodes = 0
        self.done_seeding = False
        self._seed_nodes = seed_nodes or []

        self.peers = self.tracker_class(
            domain=self.domain, this_node=self if include_self_in_the_state else None
        )

        # launch
        if self.start_peering_now and not self.lonely:
            # This node has not initialized its metadata yet.
            self.peers.record_fleet_state(skip_this_node=True)
            self.start_peering(now=self.peering_on_same_thread)

    def load_seednodes(self, record_fleet_state=False):
        if self.done_seeding:
            raise self.P2PError("Already finished seeding.")

        canonical_sage_uris = TEACHER_NODES.get(self.domain, ())

        discovered = []
        for uri in canonical_sage_uris:
            try:
                maybe_sage_node = characters.lawful.Ursula.from_peer_uri(
                    peer_uri=uri,
                    eth_endpoint=self.eth_endpoint,
                    registry=self.registry,
                    network_middleware=self.network_middleware,
                )
            except Exception as e:
                # TODO: distinguish between versioning errors and other errors?
                self.log.warn(f"Failed to instantiate seednode at {uri}: {e}")
            else:
                new_peer = self.remember_peer(maybe_sage_node, record_fleet_state=False)
                discovered.append(new_peer)

        for peer in self._seed_nodes:
            new_peer = self.remember_peer(peer, record_fleet_state=False)
            discovered.append(new_peer)

        self.done_seeding = True
        if discovered and record_fleet_state:
            self.peers.record_fleet_state()

        self.log.info("Finished contacting seednodes.")
        return discovered

    def remember_peer(
        self,
        node: Union["characters.lawful.Ursula", NodeSprout],
        force_verification_recheck: bool = False,
        record_fleet_state: bool = True,
        eager: bool = False,
    ) -> Union["characters.lawful.Ursula", False]:

        # No need to remember self.
        if node == self:
            return False

        # If this node is not on the same domain, ignore it.
        if str(node.domain) != str(self.domain):
            return False

        # Determine if this is an outdated representation of an already known node.
        with suppress(KeyError):
            already_known_peer = self.peers[node.checksum_address]
            if not node.timestamp > already_known_peer.timestamp:
                # This node is already known and not stale.  We can safely return.
                return False

        if eager:
            # mature and verify the node immediately
            node.mature()
            try:
                node.verify_node(
                    force=force_verification_recheck,
                    network_middleware_client=self.network_middleware.client,
                    registry=self.registry if self._verify_peer_bonding else None,
                    eth_endpoint=self.eth_endpoint,
                )
            except SSLError:
                self.log.debug(f"SSL Error while trying to verify node {node.rest_interface}.")
                self.peers.mark_for_removal(SSLError, node)
                return False
            except RestMiddleware.Unreachable:
                self.log.debug("No Response while trying to verify node {}|{}.".format(node.rest_interface, node))
                self.peers.mark_for_removal(node.Unreachable, node)
                return False
            except Teacher.NotStaking:
                self.log.debug(f'Provider:Operator {node.checksum_address}:{node.operator_address} is not staking.')
                self.peers.mark_for_removal(Teacher.NotStaking, node)
                return False

        # commit adding this node to the local view of the next fleet state.
        self.peers.record_node(node)
        if record_fleet_state:
            # generate the next fleet state.
            self.peers.record_fleet_state()
        return node

    def start_peering(self, now=False):
        if self._peering_task.running:
            return False
        elif now:
            self.log.info("Starting P2P.")
            self.learn_from_peer()

            self.peering_deferred = self._peering_task.start(interval=self._SHORT_LEARNING_DELAY)
            self.peering_deferred.addErrback(self.handle_peering_errors)
            return self.peering_deferred
        else:
            self.log.info("Starting P2P.")
            learner_deferred = self._peering_task.start(interval=self._SHORT_LEARNING_DELAY, now=False)
            learner_deferred.addErrback(self.handle_peering_errors)
            self.peering_deferred = learner_deferred
            return self.peering_deferred

    def stop_peering(self):
        if self._peering_task.running:
            self._peering_task.stop()
        if self.peering_deferred is RELAX:
            assert False
        if self.peering_deferred is not None:
            self._discovery_canceller(self.peering_deferred)

    def handle_peering_errors(self, failure, *args, **kwargs):
        _exception = failure.value
        crash_right_now = getattr(_exception, "crash_right_now", False)
        if self._abort_on_peering_error or crash_right_now:
            reactor.callFromThread(self._crash_gracefully, failure=failure)
            self.log.critical("Unhandled error during node peering.  Attempting graceful crash.")
        else:
            self.log.warn(f"Unhandled error during node peering: {failure.getTraceback()}")
            if not self._peering_task.running:
                self.start_peering()  # TODO: Consider a single entry point for this with more elegant pause and unpause.  NRN

    def _crash_gracefully(self, failure=None):
        """
        A facility for crashing more gracefully in the event that an exception
        is unhandled in a different thread, especially inside a loop like the acumen loop,
        Alice's publication loop, or Bob's retrieval loop..
        """
        self._crashed = failure
        failure.raiseException()
        reactor.stop()

    def select_peers(self):
        nodes_we_know_about = self.peers.shuffled()
        if not nodes_we_know_about:
            raise self.NotEnoughPeers("Need some nodes to start peering from.")
        self._peers_sample.extend(nodes_we_know_about)

    def cycle_peers(self):
        if not self._peers_sample:
            self.select_peers()
        try:
            self._current_peer = self._peers_sample.pop()
        except IndexError:
            error = "Not enough nodes to select a good peer, Check your network connection then node configuration"
            raise self.NotEnoughPeers(error)
        self.log.debug("Cycled peers; New peer is {}".format(self._current_peer))

    def current_peer(self, cycle=False):
        if cycle:
            self.cycle_peers()
        if not self._current_peer:
            self.cycle_peers()
        peer = self._current_peer
        return peer
    def continue_peering(self):
        self.peering_deferred = Deferred(canceller=self._discovery_canceller)

        def _discover_or_abort(_first_result):
            # self.log.debug(f"{self} peering at {datetime.datetime.now()}")   # 1712
            result = self.learn_from_peer(eager=False, canceller=self._discovery_canceller)
            # self.log.debug(f"{self} finished peering at {datetime.datetime.now()}")  # 1712
            return result

        self.peering_deferred.addCallback(_discover_or_abort)
        self.peering_deferred.addErrback(self.handle_peering_errors)

        # Instead of None, we might want to pass something useful about the context.
        # Alternately, it might be nice for learn_from_peer to (some or all of the time) return a Deferred.
        reactor.callInThread(self.peering_deferred.callback, None)
        return self.peering_deferred

    # TODO: Dehydrate these next two methods.  NRN

    def block_until_number_of_peers_is(self,
                                       number_of_nodes_to_know: int,
                                       timeout: int = 10,
                                       learn_on_this_thread: bool = False,
                                       eager: bool = False):
        start = maya.now()
        starting_round = self._peering_round

        # if not learn_on_this_thread and self._peering_task.running:
        #     # Get a head start by firing the looping call now.  If it's very fast, maybe we'll have enough nodes on the first iteration.
        #     self._peering_task()

        while True:
            rounds_undertaken = self._peering_round - starting_round
            if len(self.peers) >= number_of_nodes_to_know:
                if rounds_undertaken:
                    self.log.info(
                        "Learned about enough nodes after {} rounds.".format(
                            rounds_undertaken
                        )
                    )
                return True

            if not self._peering_task.running:
                self.log.warn("Blocking to learn about nodes, but peering loop isn't running.")
            if learn_on_this_thread:
                try:
                    self.learn_from_peer(eager=eager)
                except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout):
                    # TODO: Even this "same thread" logic can be done off the main thread.  NRN
                    self.log.warn(
                        "Teacher was unreachable.  No good way to handle this on the main thread."
                    )

            # The rest of the fucking owl
            round_finish = maya.now()
            elapsed = (round_finish - start).seconds
            if elapsed > timeout:
                if len(self.peers) >= number_of_nodes_to_know:  # Last chance!
                    self.log.info(f"Learned about enough nodes after {rounds_undertaken} rounds.")
                    return True
                if not self._peering_task.running:
                    raise RuntimeError("Learning loop is not running.  Start it with start_peering().")
                elif not reactor.running and not learn_on_this_thread:
                    raise RuntimeError(
                        f"The reactor isn't running, but you're trying to use it for discovery.  "
                        f"You need to start the Reactor in order to use {self} this way."
                    )
                else:
                    raise self.NotEnoughPeers(
                        "After {} seconds and {} rounds, didn't find {} nodes".format(
                            timeout, rounds_undertaken, number_of_nodes_to_know
                        )
                    )
            else:
                time.sleep(0.1)

    def block_until_specific_nodes_are_known(
        self,
        addresses: Set,
        timeout=LEARNING_TIMEOUT,
        allow_missing=0,
        learn_on_this_thread=False,
    ):
        start = maya.now()
        starting_round = self._peering_round

        addresses = set(addresses)

        while True:
            if self._crashed:
                return self._crashed
            rounds_undertaken = self._peering_round - starting_round
            if addresses.issubset(self.peers.addresses()):
                if rounds_undertaken:
                    self.log.info(
                        "Learned about all nodes after {} rounds.".format(
                            rounds_undertaken
                        )
                    )
                return True

            if learn_on_this_thread:
                self.learn_from_peer(eager=True)
            elif not self._peering_task.running:
                raise RuntimeError(
                    "Tried to block while discovering nodes on another thread, but the peering task isn't running.")

            if (maya.now() - start).seconds > timeout:
                still_unknown = addresses.difference(self.peers.addresses())
                if len(still_unknown) <= allow_missing:
                    return False
                else:
                    raise self.NotEnoughPeers(
                        "After {} seconds and {} rounds, didn't find these {} nodes: {}".format(
                            timeout,
                            rounds_undertaken,
                            len(still_unknown),
                            still_unknown,
                        )
                    )
            else:
                time.sleep(0.1)

    def verify_from(
        self,
        stranger: "characters.base.Character",
        message: bytes,
        signature: Signature,
    ):
        if not signature.verify(
            verifying_pk=stranger.stamp.as_umbral_pubkey(), message=message
        ):
            try:
                node_on_the_other_end = characters.lawful.Ursula.from_seednode_metadata(
                    stranger.seed_node_metadata(),
                    eth_endpoint=self.eth_endpoint,
                    network_middleware=self.network_middleware,
                )
                if node_on_the_other_end != stranger:
                    raise characters.lawful.Ursula.InvalidNode(
                        f"Expected to connect to {stranger}, got {node_on_the_other_end} instead."
                    )
                else:
                    raise InvalidSignature(
                        "Signature for message isn't valid: {}".format(signature)
                    )
            except (TypeError, AttributeError):
                raise InvalidSignature(
                    f"Unable to verify message from stranger: {stranger}"
                )

    def learn_from_peer(self, eager=False, canceller=None):
        """
        Sends a request to node_url to find out about it's known nodes.
        TODO: Does this (and related methods) belong on FleetSensor for portability?
        """
        remembered = []
        announce_nodes = []

        if not self.done_seeding:
            try:
                remembered_seednodes = self.load_seednodes(record_fleet_state=True)
            except Exception as e:
                # Even if we aren't aborting on peering errors, we want this to crash the process pronto.
                e.crash_right_now = True
                raise
            else:
                remembered.extend(remembered_seednodes)

        self._peering_round += 1
        current_peer = self.current_peer()  # Will raise if there's no available peer.

        if isinstance(self, Teacher):
            announce_nodes = [self.metadata()]

        if canceller and canceller.stop_now:
            return RELAX

        #
        # Request
        #

        current_peer.mature()
        if self.domain != current_peer.domain:
            self.log.debug(f"{current_peer} is serving '{current_peer.domain}', "
                           f"ignore since we are peering '{self.domain}'")
            return

        try:
            response = self.network_middleware.get_peers_via_rest(
                node=current_peer,
                announce_nodes=announce_nodes,
                fleet_state_checksum=self.peers.checksum
            )
        except (*NodeSeemsToBeDown, RestMiddleware.Unreachable) as e:
            self.log.info(f"Peer {current_peer.seed_node_metadata(as_peer_uri=True)} is unreachable: {e}.")
            return
        except current_peer.InvalidNode as e:
            self.log.warn(f"Peer {str(current_peer.checksum_address)} is invalid: {e}.")
            self.peers.mark_for_removal(current_peer.InvalidNode, current_peer)
            self.peers.record_fleet_state()
            return
        except Exception as e:
            self.log.warn(
                f"Unhandled error while peering from {str(current_peer)} "
                f"(hex={bytes(current_peer.metadata()).hex()}):{e}."
            )
            raise
        finally:
            self.cycle_peers()

        #
        # Deserialize
        #

        if response.status_code != 200:
            self.log.info(f"Bad response from peer {current_peer}: {response} - {response.text}")
            return
        response_data = response.content

        try:
            metadata = MetadataResponse.from_bytes(response_data)
        except Exception as e:
            self.log.warn(
                f"Failed to deserialize MetadataResponse from Teacher {current_peer} ({e}): hex bytes={response_data.hex()}"
            )
            return

        try:
            metadata_payload = metadata.verify(current_peer.stamp.as_umbral_pubkey())
        except Exception as e:
            # TODO (#567): bucket the node as suspicious
            self.log.warn(
                f"Failed to verify MetadataResponse from Teacher {current_peer} ({e}): hex bytes={response_data.hex()}"
            )
            return

        # Optimization: The peer had the same fleet state
        fleet_state_updated = maya.MayaDT(metadata_payload.timestamp_epoch)
        if not metadata_payload.announce_nodes:
            self.peers.record_remote_fleet_state(
                current_peer.checksum_address,
                self.peers.checksum,
                fleet_state_updated,
                self.peers.population)
            return FLEET_STATES_MATCH

        # Process the sprouts we received from the peer.
        sprouts = [NodeSprout(node) for node in metadata_payload.announce_nodes]
        for sprout in sprouts:
            try:
                node_or_false = self.remember_peer(sprout,
                                                   record_fleet_state=False,
                                                   # Do we want both of these to be decided by `eager`?
                                                   eager=eager)
                if node_or_false is not False:
                    remembered.append(node_or_false)

            except NodeSeemsToBeDown:
                self.log.debug(f"Verification Failed - "
                               f"Cannot establish connection to {sprout.rest_url()}.")

            except SuspiciousActivity:
                message = f"Suspicious Activity: Discovered sprout with bad signature: {sprout.rest_url()}." \
                          f"Propagated by: {current_peer.checksum_address}"
                self.peers.mark_for_removal(SuspiciousActivity, sprout)
                self.log.warn(message)

        peering_round_log_message = "Learning round {}.  Teacher: {} knew about {} nodes, {} were new."
        self.log.info(peering_round_log_message.format(self._peering_round,
                                                        current_peer,
                                                        len(sprouts),
                                                        len(remembered)))
        if remembered:
            self.peers.record_fleet_state()

        # Now that we updated all our nodes with the peer's,
        # our fleet state checksum should be the same as the peer's checksum.
        self.peers.record_remote_fleet_state(
            current_peer.checksum_address,
            self.peers.checksum,
            fleet_state_updated,
            len(sprouts),
        )

        return sprouts


class Teacher:
    log = Logger("teacher")
    synchronous_query_timeout = (
        20  # How long to wait during REST endpoints for blockchain queries to resolve
    )
    __DEFAULT_MIN_SEED_STAKE = 0

    def __init__(self, certificate: Certificate) -> None:
        self.certificate = certificate

        # Assume unverified
        self.verified_operator_signature = False
        self.verified_bonding = False
        self.verified_metadata = False
        self.verified_node = False

    class InvalidNode(SuspiciousActivity):
        """Raised when a node has an invalid characteristic - stamp, interface, or address."""

    class InvalidStamp(InvalidNode):
        """Base exception class for invalid character stamps"""

    class InvalidOperatorSignature(InvalidNode):
        """Raised when a stamp fails signature verification or recovers an unexpected worker address"""

    class NotStaking(InvalidNode):
        """Raised when a node fails verification because it is not currently staking"""

    class UnbondedOperator(InvalidNode):
        """Raised when a node fails verification because it is not bonded to a Staker"""

    def mature(self, *args, **kwargs):
        """This is the most mature form, so we do nothing."""
        return self

    #
    # Known Nodes
    #

    def seed_node_metadata(self, as_peer_uri=False) -> SeednodeMetadata:
        if as_peer_uri:
            peer_uri = f'{self.checksum_address}@{self.rest_server.rest_interface.host}:{self.rest_server.rest_interface.port}'
            return peer_uri
        return SeednodeMetadata(
            self.checksum_address,
            self.rest_server.rest_interface.host,
            self.rest_server.rest_interface.port,
        )

    def bytestring_of_peers(self):
        # TODO (#1537): FleetSensor does metadata-to-byte conversion as well,
        # we may be able to cache the results there.
        announce_nodes = [self.metadata()] + [node.metadata() for node in self.peers]
        response_payload = MetadataResponsePayload(timestamp_epoch=self.peers.timestamp.epoch,
                                                   announce_nodes=announce_nodes)
        response = MetadataResponse(self.stamp.as_umbral_signer(), response_payload)
        return bytes(response)

    def _operator_is_bonded(
        self, eth_endpoint: str, registry: ContractRegistry
    ) -> bool:
        """
        This method assumes the stamp's signature is valid and accurate.
        As a follow-up, this checks that the worker is bonded to a staking provider, but it may be
        the case that the "staking provider" isn't "staking" (e.g., all her tokens have been slashed).
        """
        application_agent = ContractAgency.get_agent(
            TACoApplicationAgent, blockchain_endpoint=eth_endpoint, registry=registry
        )  # type: TACoApplicationAgent
        staking_provider_address = application_agent.get_staking_provider_from_operator(
            operator_address=self.operator_address
        )
        if staking_provider_address == NULL_ADDRESS:
            raise self.UnbondedOperator(
                f"Operator {self.operator_address} is not bonded"
            )
        return staking_provider_address == self.checksum_address

    def _staking_provider_is_really_staking(
        self, registry: ContractRegistry, eth_endpoint: Optional[str] = None
    ) -> bool:
        """
        This method assumes the stamp's signature is valid and accurate.
        As a follow-up, this checks that the staking provider is, indeed, staking.
        """
        application_agent = ContractAgency.get_agent(
            TACoApplicationAgent, registry=registry, blockchain_endpoint=eth_endpoint
        )  # type: TACoApplicationAgent
        is_staking = application_agent.is_authorized(staking_provider=self.checksum_address)
        return is_staking

    def validate_operator(
        self,
        registry: ContractRegistry = None,
        eth_endpoint: Optional[str] = None,
    ) -> None:

        if registry and not eth_endpoint:
            raise ValueError("If registry is provided, eth_provider_uri must also be provided.")

        # On-chain staking check, if registry is present
        if registry:
            if not self._operator_is_bonded(
                registry=registry, eth_endpoint=eth_endpoint
            ):  # <-- Blockchain CALL
                message = f"Operator {self.operator_address} is not bonded to staking provider {self.staking_provider_address}"
                self.log.debug(message)
                raise self.UnbondedOperator(message)

            if self._staking_provider_is_really_staking(
                registry=registry, eth_endpoint=eth_endpoint
            ):  # <-- Blockchain CALL
                self.log.info(f"Verified operator {self}")
                self.verified_bonding = True
            else:
                raise self.NotStaking(f"{self.staking_provider_address} is not staking")

        else:
            self.log.info("No registry provided for staking verification.")

    def validate_metadata_signature(self) -> bool:
        """Checks that the interface info is valid for this node's canonical address."""
        metadata_is_valid = self.metadata().verify()
        self.verified_metadata = metadata_is_valid
        if metadata_is_valid:
            return True
        else:
            raise self.InvalidNode("Metadata signature is invalid")

    def validate_operator_signature(self) -> None:
        """Calls into nucypher-core. This will raise if the signature is invalid."""
        payload = self.metadata().payload
        try:
            _canonical_address = payload.derive_operator_address()  # <-- core call
        except Exception as e:
            raise self.InvalidOperatorSignature(str(e)) from e
        self.verified_operator_signature = True

    def validate_metadata(
        self, registry: ContractRegistry = None, eth_endpoint: Optional[str] = None
    ):
        if not self.verified_metadata:
            self.validate_metadata_signature()
        if not self.verified_operator_signature:
            self.validate_operator_signature()
        if not self.verified_bonding:
            self.validate_operator(registry=registry, eth_endpoint=eth_endpoint)

    def verify_node(
        self,
        network_middleware_client,
        registry: ContractRegistry = None,
        eth_endpoint: Optional[str] = None,
        force: bool = False,
    ) -> bool:
        """
        Three things happening here:

        * Verify that the stamp matches the address

        * Verify the interface signature (raises InvalidNode if not valid)

        * Connect to the node, make sure that it's up, and that the signature and address we
          checked are the same ones this node is using now. (raises InvalidNode if not valid;
          also emits a specific warning depending on which check failed).

        """

        if force:
            self.verified_node = False
            self.verified_metadata = False
            self.verified_operator_signature = False
            self.verified_bonding = False

        if self.verified_node:
            return True

        if not registry:  # TODO: # 466
            self.log.debug(
                "No registry provided for peer verification - "
                "on-chain stake verification will not be performed."
            )

        # This is both the stamp's operator wallet signature and interface metadata check; May raise InvalidNode
        self.validate_metadata(registry=registry, eth_endpoint=eth_endpoint)

        response_data = network_middleware_client.node_information(
            host=self.rest_interface.host, port=self.rest_interface.port
        )

        try:
            sprout = self.from_metadata_bytes(response_data)
        except Exception as e:
            raise self.InvalidNode(str(e))

        verifying_keys_match = sprout.verifying_key == self.public_keys(SigningPower)
        encrypting_keys_match = sprout.encrypting_key == self.public_keys(
            DecryptingPower
        )
        addresses_match = sprout.checksum_address == self.checksum_address
        evidence_matches = (
            sprout.operator_signature_from_metadata
            == self.operator_signature_from_metadata
        )

        if not all(
            (
                encrypting_keys_match,
                verifying_keys_match,
                addresses_match,
                evidence_matches,
            )
        ):
            # Failure
            if not addresses_match:
                message = "Wallet address swapped out.  It appears that someone is trying to defraud this node."
            elif not verifying_keys_match:
                message = "Verifying key swapped out.  It appears that someone is impersonating this node."
            else:
                message = "Wrong cryptographic material for this node - something fishy going on."
            # TODO: #355 - Optional reporting.
            raise self.InvalidNode(message)
        else:
            # Success
            self.verified_node = True
