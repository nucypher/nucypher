import time
from collections import deque
from contextlib import suppress
from queue import Queue
from typing import Optional, Set, Tuple

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
from nucypher.blockchain.eth import domains
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
from nucypher.utilities.logging import Logger

TEACHER_NODES = {
    domains.MAINNET: (
        "https://closest-seed.nucypher.network:9151",
        "https://seeds.nucypher.network:9151",
        "https://mainnet.nucypher.network:9151",
    ),
    domains.LYNX: ("https://lynx.nucypher.network:9151",),
    domains.TAPIR: ("https://tapir.nucypher.network:9151",),
}


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
            is_me=False,
            crypto_power=crypto_power,
            rest_host=self._metadata_payload.host,
            rest_port=self._metadata_payload.port,
            checksum_address=self.checksum_address,
            domain=self._metadata_payload.domain,
            timestamp=self.timestamp,
            operator_signature_from_metadata=self.operator_signature_from_metadata,
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

    def __call__(self, learning_deferred):
        if self.stop_now:
            assert False
        self.stop_now = True
        # learning_deferred.callback(RELAX)


class Learner:
    """
    Any participant in the "learning loop" - a class inheriting from
    this one has the ability, synchronously or asynchronously,
    to learn about nodes in the network, verify some essential
    details about them, and store information about them for later use.
    """

    _SHORT_LEARNING_DELAY = 5
    _LONG_LEARNING_DELAY = 90
    LEARNING_TIMEOUT = 10
    _ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN = 10
    __DEFAULT_MIDDLEWARE_CLASS = RestMiddleware

    _crashed = (
        False  # moved from Character - why was this in Character and not Learner before
    )

    tracker_class = FleetSensor

    invalid_metadata_message = "{} has invalid metadata.  The node's stake may have ended, or it is transitioning to a new interface. Ignoring."

    _DEBUG_MODE = False

    class NotEnoughNodes(RuntimeError):
        pass

    class NotEnoughTeachers(NotEnoughNodes):
        crash_right_now = True

    class UnresponsiveTeacher(ConnectionError):
        pass

    class NotATeacher(ValueError):
        """
        Raised when a character cannot be properly utilized because
        it does not have the proper attributes for learning or verification.
        """

    def __init__(
        self,
        domain: TACoDomain,
        node_class: object = None,
        network_middleware: RestMiddleware = None,
        start_learning_now: bool = False,
        learn_on_same_thread: bool = False,
        known_nodes: tuple = None,
        seed_nodes: Tuple[tuple] = None,
        save_metadata: bool = False,
        abort_on_learning_error: bool = False,
        lonely: bool = False,
        verify_node_bonding: bool = True,
        include_self_in_the_state: bool = False,
    ) -> None:
        self.log = Logger("learning-loop")  # type: Logger
        self.domain = domain

        self.learning_deferred = Deferred()
        default_middleware = self.__DEFAULT_MIDDLEWARE_CLASS(
            registry=self.registry, eth_endpoint=self.eth_endpoint
        )
        self.network_middleware = network_middleware or default_middleware
        self.save_metadata = save_metadata
        self.start_learning_now = start_learning_now
        self.learn_on_same_thread = learn_on_same_thread

        self._abort_on_learning_error = abort_on_learning_error

        self.__known_nodes = self.tracker_class(
            domain=self.domain, this_node=self if include_self_in_the_state else None
        )
        self._verify_node_bonding = verify_node_bonding

        self.lonely = lonely
        self.done_seeding = False
        self._learning_deferred = None
        self._discovery_canceller = DiscoveryCanceller()

        self.node_class = node_class or characters.lawful.Ursula

        known_nodes = known_nodes or tuple()
        self.unresponsive_startup_nodes = (
            list()
        )  # TODO: Buckets - Attempt to use these again later  #567
        for node in known_nodes:
            try:
                self.remember_node(node, eager=True, record_fleet_state=False)
            except self.UnresponsiveTeacher:
                self.unresponsive_startup_nodes.append(node)

        # This node has not initialized its metadata yet.
        self.known_nodes.record_fleet_state(skip_this_node=True)

        self.teacher_nodes = deque()
        self._current_teacher_node = None  # type: Union[Teacher, None]
        self._learning_task = task.LoopingCall(self.keep_learning_about_nodes)

        if self._DEBUG_MODE:
            # Very slow, but provides useful info when trying to track down a stray Character.
            # Seems mostly useful for Bob but perhaps useful for other Characters as well.

            import inspect
            import os

            frames = inspect.stack(3)
            self._learning_task = task.LoopingCall(
                self.keep_learning_about_nodes, learner=self, frames=frames
            )
            self._init_frames = frames
            from tests.conftest import global_mutable_where_everybody

            test_name = os.environ["PYTEST_CURRENT_TEST"]
            global_mutable_where_everybody[test_name].append(self)
            self._FOR_TEST = test_name
            ########################

        self._learning_round = 0  # type: int
        self._rounds_without_new_nodes = 0  # type: int
        self._seed_nodes = seed_nodes or []

        if self.start_learning_now and not self.lonely:
            self.start_learning_loop(now=self.learn_on_same_thread)

    @property
    def known_nodes(self):
        return self.__known_nodes

    def load_seednodes(self, record_fleet_state=False):
        """
        Pre-fetch hardcoded seednode certificates for node learning.

        TODO: Dehydrate this with nucypher.utilities.seednodes.load_seednodes
        """
        if self.done_seeding:
            raise RuntimeError(
                "Already finished seeding.  Why try again?  Is this a thread safety problem?"
            )

        discovered = []

        if self.domain:
            canonical_sage_uris = TEACHER_NODES.get(self.domain, ())

            for uri in canonical_sage_uris:
                try:
                    maybe_sage_node = self.node_class.from_teacher_uri(
                        teacher_uri=uri,
                        min_stake=0,
                        eth_endpoint=self.eth_endpoint,
                        network_middleware=self.network_middleware,
                        registry=self.registry,
                    )
                except Exception as e:
                    # TODO: log traceback here?
                    # TODO: distinguish between versioning errors and other errors?
                    self.log.warn(f"Failed to instantiate a node at {uri}: {e}")
                else:
                    new_node = self.remember_node(
                        maybe_sage_node, record_fleet_state=False
                    )
                    discovered.append(new_node)

        for seednode_metadata in self._seed_nodes:
            node_tag = "{}|{}:{}".format(
                seednode_metadata.checksum_address,
                seednode_metadata.rest_host,
                seednode_metadata.rest_port,
            )

            self.log.debug(f"Seeding from: {node_tag}")

            try:
                seed_node = self.node_class.from_seednode_metadata(
                    seednode_metadata=seednode_metadata,
                    network_middleware=self.network_middleware,
                    eth_endpoint=self.eth_endpoint,
                )
            except Exception as e:
                # TODO: log traceback here?
                # TODO: distinguish between versioning errors and other errors?
                self.log.warn(f"Failed to instantiate a node {node_tag}: {e}")
            else:
                new_node = self.remember_node(seed_node, record_fleet_state=False)
                discovered.append(new_node)

        self.log.info("Finished learning about all seednodes.")

        self.done_seeding = True

        if discovered and record_fleet_state:
            self.known_nodes.record_fleet_state()

        return discovered

    def remember_node(
        self,
        node,
        force_verification_recheck=False,
        record_fleet_state=True,
        eager: bool = False,
    ):
        # UNPARSED
        # PARSED
        # METADATA_CHECKED
        # VERIFIED_CERT
        # VERIFIED_STAKE

        if node == self:  # No need to remember self.
            return False

        # First, determine if this is an outdated representation of an already known node.
        # TODO: #1032 or, since it's closed and will never re-opened, i am the :=
        with suppress(KeyError):
            already_known_node = self.known_nodes[node.checksum_address]
            if not node.timestamp > already_known_node.timestamp:
                # This node is already known.  We can safely return.
                return False

        self.known_nodes.record_node(
            node
        )  # FIXME - dont always remember nodes, bucket them.

        if eager:
            node.mature()
            registry = self.registry if self._verify_node_bonding else None

            try:
                node.verify_node(
                    force=force_verification_recheck,
                    network_middleware_client=self.network_middleware.client,
                    registry=registry,
                    eth_endpoint=self.eth_endpoint,
                )
            except SSLError:
                # TODO: Bucket this node as having bad TLS info - maybe it's an update that hasn't fully propagated?  567
                return False

            except RestMiddleware.Unreachable:
                self.log.info(
                    "No Response while trying to verify node {}|{}".format(
                        node.rest_interface, node
                    )
                )
                # TODO: Bucket this node as "ghost" or something: somebody else knows about it, but we can't get to it.  567
                return False

            except node.NotStaking:
                # TODO: Bucket this node as inactive, and potentially safe to forget.  567
                self.log.info(
                    f"StakingProvider:Operator {node.checksum_address}:{node.operator_address} is not actively staking, skipping."
                )
                return False

            # TODO: What about InvalidNode?  (for that matter, any SuspiciousActivity)  1714, 567 too really

        if record_fleet_state:
            self.known_nodes.record_fleet_state()

        return node

    def start_learning_loop(self, now=False):
        if self._learning_task.running:
            return False
        elif now:
            self.log.info("Starting Learning Loop NOW.")
            self.learn_from_teacher_node()

            self.learning_deferred = self._learning_task.start(
                interval=self._SHORT_LEARNING_DELAY
            )
            self.learning_deferred.addErrback(self.handle_learning_errors)
            return self.learning_deferred
        else:
            self.log.info("Starting Learning Loop.")
            learner_deferred = self._learning_task.start(
                interval=self._SHORT_LEARNING_DELAY, now=False
            )
            learner_deferred.addErrback(self.handle_learning_errors)
            self.learning_deferred = learner_deferred
            return self.learning_deferred

    def stop_learning_loop(self, reason=None):
        """
        Only for tests at this point.  Maybe some day for graceful shutdowns.
        """
        if self._learning_task.running:
            self._learning_task.stop()

        if self._learning_deferred is RELAX:
            assert False

        if self._learning_deferred is not None:
            # self._learning_deferred.cancel()  # TODO: The problem here is that this might already be called.
            self._discovery_canceller(self._learning_deferred)

        # self.learning_deferred.cancel()  # TODO: The problem here is that there's no way to get a canceller into the LoopingCall.

    def handle_learning_errors(self, failure, *args, **kwargs):
        _exception = failure.value
        crash_right_now = getattr(_exception, "crash_right_now", False)
        if self._abort_on_learning_error or crash_right_now:
            reactor.callFromThread(self._crash_gracefully, failure=failure)
            self.log.critical(
                "Unhandled error during node learning.  Attempting graceful crash."
            )
        else:
            self.log.warn(
                f"Unhandled error during node learning: {failure.getTraceback()}"
            )
            if not self._learning_task.running:
                self.start_learning_loop()  # TODO: Consider a single entry point for this with more elegant pause and unpause.  NRN

    def _crash_gracefully(self, failure=None):
        """
        A facility for crashing more gracefully in the event that an exception
        is unhandled in a different thread, especially inside a loop like the acumen loop, Alice's publication loop, or Bob's retrieval loop..
        """

        self._crashed = failure

        # When using Learner._DEBUG_MODE in tests, it may be helpful to uncomment this to be able to introspect.
        # from tests.conftest import global_mutable_where_everybody
        # gmwe = global_mutable_where_everybody

        failure.raiseException()
        # TODO: We don't actually have checksum_address at this level - maybe only Characters can crash gracefully :-)  1711
        self.log.critical("{} crashed with {}".format(self.checksum_address, failure))
        reactor.stop()

    def select_teacher_nodes(self):
        nodes_we_know_about = self.known_nodes.shuffled()

        if not nodes_we_know_about:
            self.log.warn("Need some nodes to start learning from.")
            return False

        self.teacher_nodes.extend(nodes_we_know_about)

    def cycle_teacher_node(self):
        if not self.teacher_nodes:
            self.select_teacher_nodes()
        try:
            self._current_teacher_node = self.teacher_nodes.pop()
        except IndexError:
            error = "Not enough nodes to select a good teacher, Check your network connection then node configuration"
            self.log.warn(error)
        self.log.debug(
            "Cycled teachers; New teacher is {}".format(self._current_teacher_node)
        )

    def current_teacher_node(self, cycle=False):
        if cycle:
            self.cycle_teacher_node()

        if not self._current_teacher_node:
            self.cycle_teacher_node()

        teacher = self._current_teacher_node

        return teacher

    def learn_about_nodes_now(self, force=False):
        if self._learning_task.running:
            self._learning_task.reset()
            # self._learning_task()
        elif not force:
            self.log.warn(
                "Learning loop isn't started; can't learn about nodes now.  You can override this with force=True."
            )
        elif force:
            # TODO: What if this has been stopped?
            self.log.info("Learning loop wasn't started; forcing start now.")
            self._learning_task.start(self._SHORT_LEARNING_DELAY, now=True)

    def keep_learning_about_nodes(self):
        """
        Continually learn about new nodes.
        """

        # TODO: Allow the user to set eagerness?  1712
        # TODO: Also, if we do allow eager, don't even defer; block right here.

        self._learning_deferred = Deferred(
            canceller=self._discovery_canceller
        )  # TODO: No longer relevant.

        def _discover_or_abort(_first_result):
            # self.log.debug(f"{self} learning at {datetime.datetime.now()}")   # 1712
            result = self.learn_from_teacher_node(
                eager=False, canceller=self._discovery_canceller
            )
            # self.log.debug(f"{self} finished learning at {datetime.datetime.now()}")  # 1712
            return result

        self._learning_deferred.addCallback(_discover_or_abort)
        self._learning_deferred.addErrback(self.handle_learning_errors)

        # Instead of None, we might want to pass something useful about the context.
        # Alternately, it might be nice for learn_from_teacher_node to (some or all of the time) return a Deferred.
        reactor.callInThread(self._learning_deferred.callback, None)
        return self._learning_deferred

    # TODO: Dehydrate these next two methods.  NRN

    def block_until_number_of_known_nodes_is(
        self,
        number_of_nodes_to_know: int,
        timeout: int = 10,
        learn_on_this_thread: bool = False,
        eager: bool = False,
    ):
        start = maya.now()
        starting_round = self._learning_round

        # if not learn_on_this_thread and self._learning_task.running:
        #     # Get a head start by firing the looping call now.  If it's very fast, maybe we'll have enough nodes on the first iteration.
        #     self._learning_task()

        while True:
            rounds_undertaken = self._learning_round - starting_round
            if len(self.known_nodes) >= number_of_nodes_to_know:
                if rounds_undertaken:
                    self.log.info(
                        "Learned about enough nodes after {} rounds.".format(
                            rounds_undertaken
                        )
                    )
                return True

            if not self._learning_task.running:
                self.log.warn(
                    "Blocking to learn about nodes, but learning loop isn't running."
                )
            if learn_on_this_thread:
                try:
                    self.learn_from_teacher_node(eager=eager)
                except (
                    requests.exceptions.ReadTimeout,
                    requests.exceptions.ConnectTimeout,
                ):
                    # TODO: Even this "same thread" logic can be done off the main thread.  NRN
                    self.log.warn(
                        "Teacher was unreachable.  No good way to handle this on the main thread."
                    )

            # The rest of the fucking owl
            round_finish = maya.now()
            elapsed = (round_finish - start).seconds
            if elapsed > timeout:
                if len(self.known_nodes) >= number_of_nodes_to_know:  # Last chance!
                    self.log.info(
                        f"Learned about enough nodes after {rounds_undertaken} rounds."
                    )
                    return True
                if not self._learning_task.running:
                    raise RuntimeError(
                        "Learning loop is not running.  Start it with start_learning_loop()."
                    )
                elif not reactor.running and not learn_on_this_thread:
                    raise RuntimeError(
                        f"The reactor isn't running, but you're trying to use it for discovery.  You need to start the Reactor in order to use {self} this way."
                    )
                else:
                    raise self.NotEnoughNodes(
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
        starting_round = self._learning_round

        addresses = set(addresses)

        while True:
            if self._crashed:
                return self._crashed
            rounds_undertaken = self._learning_round - starting_round
            if addresses.issubset(self.known_nodes.addresses()):
                if rounds_undertaken:
                    self.log.info(
                        "Learned about all nodes after {} rounds.".format(
                            rounds_undertaken
                        )
                    )
                return True

            if learn_on_this_thread:
                self.learn_from_teacher_node(eager=True)
            elif not self._learning_task.running:
                raise RuntimeError(
                    "Tried to block while discovering nodes on another thread, but the learning task isn't running."
                )

            if (maya.now() - start).seconds > timeout:
                still_unknown = addresses.difference(self.known_nodes.addresses())

                if len(still_unknown) <= allow_missing:
                    return False
                else:
                    raise self.NotEnoughTeachers(
                        "After {} seconds and {} rounds, didn't find these {} nodes: {}".format(
                            timeout,
                            rounds_undertaken,
                            len(still_unknown),
                            still_unknown,
                        )
                    )
            else:
                time.sleep(0.1)

    def _adjust_learning(self, node_list):
        """
        Takes a list of new nodes, adjusts learning accordingly.

        Currently, simply slows down learning loop when no new nodes have been discovered in a while.
        TODO: Do other important things - scrub, bucket, etc.  567
        """
        if node_list:
            self._rounds_without_new_nodes = 0
            self._learning_task.interval = self._SHORT_LEARNING_DELAY
        else:
            self._rounds_without_new_nodes += 1
            if (
                self._rounds_without_new_nodes
                > self._ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN
            ):
                self.log.info(
                    "After {} rounds with no new nodes, it's time to slow down to {} seconds.".format(
                        self._ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN,
                        self._LONG_LEARNING_DELAY,
                    )
                )
                self._learning_task.interval = self._LONG_LEARNING_DELAY

    def get_nodes_by_ids(self, node_ids):
        for node_id in node_ids:
            try:
                # Scenario 1: We already know about this node.
                return self.__known_nodes[node_id]
            except KeyError:
                raise NotImplementedError
        # Scenario 2: We don't know about this node, but a nearby node does.
        # TODO: Build a concurrent pool of lookups here.  NRN

        # Scenario 3: We don't know about this node, and neither does our friend.

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
                node_on_the_other_end = self.node_class.from_seednode_metadata(
                    stranger.seed_node_metadata(),
                    eth_endpoint=self.eth_endpoint,
                    network_middleware=self.network_middleware,
                )
                if node_on_the_other_end != stranger:
                    raise self.node_class.InvalidNode(
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

    def learn_from_teacher_node(self, eager=False, canceller=None):
        """
        Sends a request to node_url to find out about known nodes.
        TODO: Does this (and related methods) belong on FleetSensor for portability?
        TODO: A lot of other code can be simplified if this is converted to async def.  That's a project, though.
        """
        remembered = []

        if not self.done_seeding:
            try:
                remembered_seednodes = self.load_seednodes(record_fleet_state=True)
            except Exception as e:
                # Even if we aren't aborting on learning errors, we want this to crash the process pronto.
                e.crash_right_now = True
                raise
            else:
                remembered.extend(remembered_seednodes)

        self._learning_round += 1

        current_teacher = self.current_teacher_node()
        if not current_teacher:
            return RELAX
        current_teacher.mature()

        if isinstance(self, Teacher):
            announce_nodes = [self.metadata()]
        else:
            announce_nodes = []

        unresponsive_nodes = set()

        #
        # Request
        #
        if canceller and canceller.stop_now:
            return RELAX

        try:
            response = self.network_middleware.get_nodes_via_rest(
                node=current_teacher,
                announce_nodes=announce_nodes,
                fleet_state_checksum=self.known_nodes.checksum,
            )
        # These except clauses apply to the current_teacher itself, not the learned-about nodes.
        except NodeSeemsToBeDown as e:
            unresponsive_nodes.add(current_teacher)
            self.log.info(
                f"Teacher {current_teacher.seed_node_metadata(as_teacher_uri=True)} is unreachable: {e}."
            )
            return
        except current_teacher.InvalidNode as e:
            # TODO (#567): bucket the node as suspicious
            unresponsive_nodes.add(current_teacher)  # This does nothing.
            self.log.warn(f"Teacher {str(current_teacher)} is invalid: {e}.")
            return
        except RuntimeError as e:
            if canceller and canceller.stop_now:
                # Race condition that seems limited to tests.
                # TODO: Sort this out.
                return RELAX
            else:
                self.log.warn(
                    f"Unhandled error while learning from {str(current_teacher)} "
                    f"(hex={bytes(current_teacher.metadata()).hex()}):{e}."
                )
                raise
        except Exception as e:
            self.log.warn(
                f"Unhandled error while learning from {str(current_teacher)} "
                f"(hex={bytes(current_teacher.metadata()).hex()}):{e}."
            )  # To track down 2345 / 1698
            raise
        finally:
            # cycle now -- cycle even if this function raises an exception or returns early.
            self.cycle_teacher_node()

        if response.status_code != 200:
            self.log.info(
                "Bad response from teacher {}: {} - {}".format(
                    current_teacher, response, response.text
                )
            )
            return

        # TODO: we really should be checking this *before* we ask it for a node list,
        # but currently we may not know this before the REST request (which may mature the node)
        if self.domain != current_teacher.domain:
            # Ignore nodes from other domains.
            self.log.debug(
                f"{current_teacher} is serving '{current_teacher.domain}', "
                f"ignore since we are learning about '{self.domain}'"
            )
            return

        #
        # Deserialize
        #
        response_data = response.content
        try:
            metadata = MetadataResponse.from_bytes(response_data)
        except Exception as e:
            self.log.warn(
                f"Failed to deserialize MetadataResponse from Teacher {current_teacher} ({e}): hex bytes={response_data.hex()}"
            )
            return

        try:
            metadata_payload = metadata.verify(current_teacher.stamp.as_umbral_pubkey())
        except Exception as e:
            # TODO (#567): bucket the node as suspicious
            self.log.warn(
                f"Failed to verify MetadataResponse from Teacher {current_teacher} ({e}): hex bytes={response_data.hex()}"
            )
            return

        # End edge case handling.

        fleet_state_updated = maya.MayaDT(metadata_payload.timestamp_epoch)

        if not metadata_payload.announce_nodes:
            # The teacher had the same fleet state
            self.known_nodes.record_remote_fleet_state(
                current_teacher.checksum_address,
                self.known_nodes.checksum,
                fleet_state_updated,
                self.known_nodes.population,
            )

            return FLEET_STATES_MATCH

        sprouts = [NodeSprout(node) for node in metadata_payload.announce_nodes]

        for sprout in sprouts:
            try:
                node_or_false = self.remember_node(
                    sprout,
                    record_fleet_state=False,
                    # Do we want both of these to be decided by `eager`?
                    eager=eager,
                )
                if node_or_false is not False:
                    remembered.append(node_or_false)

                #
                # Report Failure
                #

            except NodeSeemsToBeDown:
                self.log.info(
                    f"Verification Failed - "
                    f"Cannot establish connection to {sprout}."
                )

            # # TODO: This whole section is weird; sprouts down have any of these things.
            except sprout.StampNotSigned:
                self.log.warn(f"Verification Failed - " f"{sprout} {NOT_SIGNED}.")

            except sprout.NotStaking:
                self.log.warn(
                    f"Verification Failed - " f"{sprout} has no active stakes "
                )

            except sprout.InvalidOperatorSignature:
                self.log.warn(
                    f"Verification Failed - "
                    f"{sprout} has an invalid wallet signature for {sprout.operator_signature_from_metadata}"
                )

            except sprout.UnbondedOperator:
                self.log.warn(
                    f"Verification Failed - " f"{sprout} is not bonded to a Staker."
                )

            # TODO: Handle invalid sprouts
            # except sprout.Invalidsprout:
            #     self.log.warn(sprout.invalid_metadata_message.format(sprout))

            except NodeSeemsToBeDown as e:
                message = f"Node is unreachable: {sprout}. Full error: {e.__str__()} "
                self.log.warn(message)

            except SuspiciousActivity:
                message = (
                    f"Suspicious Activity: Discovered sprout with bad signature: {sprout}."
                    f"Propagated by: {current_teacher}"
                )
                self.log.warn(message)

        ###################

        learning_round_log_message = (
            "Learning round {}.  Teacher: {} knew about {} nodes, {} were new."
        )
        self.log.info(
            learning_round_log_message.format(
                self._learning_round, current_teacher, len(sprouts), len(remembered)
            )
        )
        if remembered:
            self.known_nodes.record_fleet_state()

        # Now that we updated all our nodes with the teacher's,
        # our fleet state checksum should be the same as the teacher's checksum.

        # Is cycling happening in the right order?
        self.known_nodes.record_remote_fleet_state(
            current_teacher.checksum_address,
            self.known_nodes.checksum,
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
        self.verified_stamp = False
        self.verified_operator = False
        self.verified_metadata = False
        self.verified_node = False

    class InvalidNode(SuspiciousActivity):
        """Raised when a node has an invalid characteristic - stamp, interface, or address."""

    class InvalidStamp(InvalidNode):
        """Base exception class for invalid character stamps"""

    class StampNotSigned(InvalidStamp):
        """Raised when a node does not have a stamp signature when one is required for verification"""

    class InvalidOperatorSignature(InvalidStamp):
        """Raised when a stamp fails signature verification or recovers an unexpected worker address"""

    class NotStaking(InvalidStamp):
        """Raised when a node fails verification because it is not currently staking"""

    class UnbondedOperator(InvalidNode):
        """Raised when a node fails verification because it is not bonded to a Staker"""

    def mature(self, *args, **kwargs):
        """This is the most mature form, so we do nothing."""
        return self

    #
    # Known Nodes
    #

    def seed_node_metadata(self, as_teacher_uri=False) -> SeednodeMetadata:
        if as_teacher_uri:
            teacher_uri = f"{self.checksum_address}@{self.rest_server.rest_interface.host}:{self.rest_server.rest_interface.port}"
            return teacher_uri
        return SeednodeMetadata(
            self.checksum_address,
            self.rest_server.rest_interface.host,
            self.rest_server.rest_interface.port,
        )

    def bytestring_of_known_nodes(self):
        # TODO (#1537): FleetSensor does metadata-to-byte conversion as well,
        # we may be able to cache the results there.
        announce_nodes = [self.metadata()] + [
            node.metadata() for node in self.known_nodes
        ]
        response_payload = MetadataResponsePayload(
            timestamp_epoch=self.known_nodes.timestamp.epoch,
            announce_nodes=announce_nodes,
        )
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
        is_staking = application_agent.is_authorized(
            staking_provider=self.checksum_address
        )  # checksum address here is staking provider
        return is_staking

    def validate_operator(
        self,
        registry: ContractRegistry = None,
        eth_endpoint: Optional[str] = None,
    ) -> None:
        # TODO: restore this enforcement
        # if registry and not eth_provider_uri:
        #     raise ValueError("If registry is provided, eth_provider_uri must also be provided.")

        # Try to derive the worker address if it hasn't been derived yet.
        try:
            # TODO: This is overtly implicit
            _operator_address = self.operator_address
        except Exception as e:
            raise self.InvalidOperatorSignature(str(e)) from e
        self.verified_stamp = True  # TODO: Does this belong here?

        # On-chain staking check, if registry is present
        if registry:
            if not self._operator_is_bonded(
                registry=registry, eth_endpoint=eth_endpoint
            ):  # <-- Blockchain CALL
                message = f"Operator {self.operator_address} is not bonded to staking provider {self.checksum_address}"
                self.log.debug(message)
                raise self.UnbondedOperator(message)

            if self._staking_provider_is_really_staking(
                registry=registry, eth_endpoint=eth_endpoint
            ):  # <-- Blockchain CALL
                self.log.debug(f"Verified operator {self}")
                self.verified_operator = True
            else:
                raise self.NotStaking(f"{self.checksum_address} is not staking")

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

    def validate_metadata(
        self, registry: ContractRegistry = None, eth_endpoint: Optional[str] = None
    ):
        # Verify the metadata signature
        if not self.verified_metadata:
            self.validate_metadata_signature()

        # Verify the identity evidence
        if self.verified_stamp:
            return

        # Offline check of valid stamp signature by worker
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
            self.verified_metadata = False
            self.verified_node = False
            self.verified_stamp = False
            self.verified_operator = False

        if self.verified_node:
            return True

        if not registry:  # TODO: # 466
            self.log.debug(
                "No registry provided for peer verification - "
                "on-chain stake verification will not be performed."
            )

        # This is both the stamp's client signature and interface metadata check; May raise InvalidNode
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
