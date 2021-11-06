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
from collections import defaultdict, deque
from contextlib import suppress
from pathlib import Path
from queue import Queue
from typing import Callable, List, Optional, Set, Tuple, Union

import maya
import requests
from constant_sorrow import constant_or_bytes
from constant_sorrow.constants import (
    CERTIFICATE_NOT_SAVED,
    FLEET_STATES_MATCH,
    NOT_SIGNED,
    NO_STORAGE_AVAILABLE,
    RELAX,
)
from cryptography.x509 import Certificate, load_pem_x509_certificate
from cryptography.hazmat.backends import default_backend
from eth_utils import to_checksum_address
from requests.exceptions import SSLError
from twisted.internet import reactor, task
from twisted.internet.defer import Deferred

from nucypher.core import NodeMetadata, MetadataResponse

from nucypher.acumen.nicknames import Nickname
from nucypher.acumen.perception import FleetSensor
from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.config.constants import SeednodeMetadata
from nucypher.config.storages import ForgetfulNodeStorage
from nucypher.crypto.powers import (
    CryptoPower,
    DecryptingPower,
    NoSigningPower,
    SigningPower,
)
from nucypher.crypto.signing import SignatureStamp, InvalidSignature
from nucypher.crypto.umbral_adapter import Signature
from nucypher.crypto.utils import recover_address_eip_191, verify_eip_191
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import RestMiddleware
from nucypher.network.protocols import SuspiciousActivity, InterfaceInfo
from nucypher.utilities.logging import Logger

TEACHER_NODES = {
    NetworksInventory.MAINNET: (
        'https://closest-seed.nucypher.network:9151',
        'https://seeds.nucypher.network',
        'https://mainnet.nucypher.network:9151',
    ),
    NetworksInventory.LYNX: ('https://lynx.nucypher.network:9151',),
    NetworksInventory.IBEX: ('https://ibex.nucypher.network:9151',),
}


class NodeSprout:
    """
    An abridged node class designed for optimization of instantiation of > 100 nodes simultaneously.
    """
    verified_node = False

    def __init__(self, node_metadata):
        self._metadata = node_metadata

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
            self._checksum_address = to_checksum_address(self._metadata.public_address)
        return self._checksum_address

    @property
    def nickname(self):
        if not self._nickname:
            self._nickname = Nickname.from_seed(self.checksum_address)
        return self._nickname

    @property
    def rest_interface(self):
        if not self._rest_interface:
            self._rest_interface = InterfaceInfo(self._metadata.host, self._metadata.port)
        return self._rest_interface

    def rest_url(self):
        return self.rest_interface.uri

    def metadata(self):
        return self._metadata

    @property
    def verifying_key(self):
        return self._metadata.verifying_key

    @property
    def encrypting_key(self):
        return self._metadata.encrypting_key

    @property
    def decentralized_identity_evidence(self):
        return self._metadata.decentralized_identity_evidence or NOT_SIGNED

    @property
    def public_address(self):
        return self._metadata.public_address

    @property
    def timestamp(self):
        return maya.MayaDT(self._metadata.timestamp_epoch)

    @property
    def stamp(self) -> SignatureStamp:
        return SignatureStamp(self._metadata.verifying_key)

    @property
    def domain(self) -> str:
        return self._metadata.domain

    def finish(self):
        from nucypher.characters.lawful import Ursula

        crypto_power = CryptoPower()
        crypto_power.consume_power_up(SigningPower(public_key=self._metadata.verifying_key))
        crypto_power.consume_power_up(DecryptingPower(public_key=self._metadata.encrypting_key))

        return Ursula(is_me=False,
                      crypto_power=crypto_power,
                      rest_host=self._metadata.host,
                      rest_port=self._metadata.port,
                      checksum_address=self.checksum_address,
                      domain=self._metadata.domain,
                      timestamp=self.timestamp,
                      decentralized_identity_evidence=self.decentralized_identity_evidence,
                      certificate=load_pem_x509_certificate(self._metadata.certificate_bytes, backend=default_backend()),
                      metadata=self._metadata
                      )

    def mature(self):
        if self._is_finishing:
            return self._finishing_mutex.get()

        self._is_finishing = True  # Prevent reentrance.
        _finishing_mutex = self._finishing_mutex

        mature_node = self.finish()
        self.__class__ = mature_node.__class__
        self.__dict__ = mature_node.__dict__

        # As long as we're doing egregious workarounds, here's another one.  # TODO: 1481
        filepath = mature_node._cert_store_function(certificate=mature_node.certificate, port=mature_node.rest_interface.port)
        mature_node.certificate_filepath = filepath

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

    # For Keeps
    __DEFAULT_NODE_STORAGE = ForgetfulNodeStorage
    __DEFAULT_MIDDLEWARE_CLASS = RestMiddleware

    _crashed = False  # moved from Character - why was this in Character and not Learner before

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

    def __init__(self,
                 domain: str,
                 node_class: object = None,
                 network_middleware: RestMiddleware = None,
                 start_learning_now: bool = False,
                 learn_on_same_thread: bool = False,
                 known_nodes: tuple = None,
                 seed_nodes: Tuple[tuple] = None,
                 node_storage=None,
                 save_metadata: bool = False,
                 abort_on_learning_error: bool = False,
                 lonely: bool = False,
                 verify_node_bonding: bool = True,
                 include_self_in_the_state: bool = False,
                 ) -> None:

        self.log = Logger("learning-loop")  # type: Logger

        self.learning_deferred = Deferred()
        self.domain = domain
        if not self.federated_only:
            default_middleware = self.__DEFAULT_MIDDLEWARE_CLASS(registry=self.registry)
        else:
            default_middleware = self.__DEFAULT_MIDDLEWARE_CLASS()
        self.network_middleware = network_middleware or default_middleware
        self.save_metadata = save_metadata
        self.start_learning_now = start_learning_now
        self.learn_on_same_thread = learn_on_same_thread

        self._abort_on_learning_error = abort_on_learning_error

        self.__known_nodes = self.tracker_class(domain=domain, this_node=self if include_self_in_the_state else None)
        self._verify_node_bonding = verify_node_bonding

        self.lonely = lonely
        self.done_seeding = False
        self._learning_deferred = None
        self._discovery_canceller = DiscoveryCanceller()

        if not node_storage:
            node_storage = self.__DEFAULT_NODE_STORAGE(federated_only=self.federated_only)
        self.node_storage = node_storage
        if save_metadata and node_storage is NO_STORAGE_AVAILABLE:
            raise ValueError("Cannot save nodes without a configured node storage")

        from nucypher.characters.lawful import Ursula
        self.node_class = node_class or Ursula
        self.node_class.set_cert_storage_function(
            node_storage.store_node_certificate)  # TODO: Fix this temporary workaround for on-disk cert storage.  #1481

        known_nodes = known_nodes or tuple()
        self.unresponsive_startup_nodes = list()  # TODO: Buckets - Attempt to use these again later  #567
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
            # Seems mostly useful for Bob or federated Ursulas, but perhaps useful for other Characters as well.

            import inspect, os
            frames = inspect.stack(3)
            self._learning_task = task.LoopingCall(self.keep_learning_about_nodes, learner=self, frames=frames)
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

    def load_seednodes(self, read_storage: bool = True, record_fleet_state=False):
        """
        Engage known nodes from storages and pre-fetch hardcoded seednode certificates for node learning.

        TODO: Dehydrate this with nucypher.utilities.seednodes.load_seednodes
        """
        if self.done_seeding:
            raise RuntimeError("Already finished seeding.  Why try again?  Is this a thread safety problem?")

        discovered = []

        if self.domain:
            canonical_sage_uris = TEACHER_NODES.get(self.domain, ())

            for uri in canonical_sage_uris:
                try:
                    maybe_sage_node = self.node_class.from_teacher_uri(teacher_uri=uri,
                                                                       min_stake=0,  # TODO: Where to get this?
                                                                       federated_only=self.federated_only,
                                                                       network_middleware=self.network_middleware,
                                                                       registry=self.registry)
                except Exception as e:
                    # TODO: log traceback here?
                    # TODO: distinguish between versioning errors and other errors?
                    self.log.warn(f"Failed to instantiate a node at {uri}: {e}")
                else:
                    new_node = self.remember_node(maybe_sage_node, record_fleet_state=False)
                    discovered.append(new_node)

        for seednode_metadata in self._seed_nodes:

            node_tag = "{}|{}:{}".format(seednode_metadata.checksum_address,
                                         seednode_metadata.rest_host,
                                         seednode_metadata.rest_port)

            self.log.debug(f"Seeding from: {node_tag}")

            try:
                seed_node = self.node_class.from_seednode_metadata(seednode_metadata=seednode_metadata,
                                                                   network_middleware=self.network_middleware,
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

        nodes_restored_from_storage = self.read_nodes_from_storage() if read_storage else []
        discovered.extend(nodes_restored_from_storage)

        if discovered and record_fleet_state:
            self.known_nodes.record_fleet_state()

        return discovered

    def read_nodes_from_storage(self) -> List:
        stored_nodes = self.node_storage.all(federated_only=self.federated_only)  # TODO: #466

        restored_from_disk = []
        invalid_nodes = defaultdict(list)
        for node in stored_nodes:
            if node.domain != self.domain:
                invalid_nodes[node.domain].append(node)
                continue
            restored_node = self.remember_node(node, record_fleet_state=False)  # TODO: Validity status 1866
            restored_from_disk.append(restored_node)

        if invalid_nodes:
            self.log.warn(f"We're learning about domain '{self.domain}', but found nodes from other domains; "
                          f"let's ignore them. These domains and nodes are: {dict(invalid_nodes)}")

        return restored_from_disk

    def remember_node(self,
                      node,
                      force_verification_recheck=False,
                      record_fleet_state=True,
                      eager: bool = False):

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

        self.known_nodes.record_node(node)  # FIXME - dont always remember nodes, bucket them.

        if self.save_metadata:
            self.node_storage.store_node_metadata(node=node)

        if eager:
            node.mature()
            stranger_certificate = node.certificate

            # Store node's certificate - It has been seen.
            certificate_filepath = self.node_storage.store_node_certificate(certificate=stranger_certificate, port=node.rest_interface.port)

            # In some cases (seed nodes or other temp stored certs),
            # this will update the filepath from the temp location to this one.
            node.certificate_filepath = certificate_filepath

            # Use this to control whether or not this node performs
            # blockchain calls to determine if stranger nodes are bonded.
            # Note: self.registry is composed on blockchainy character subclasses.
            registry = self.registry if self._verify_node_bonding else None  # TODO: Federated mode?

            try:
                node.verify_node(force=force_verification_recheck,
                                 network_middleware_client=self.network_middleware.client,
                                 registry=registry)
            except SSLError:
                # TODO: Bucket this node as having bad TLS info - maybe it's an update that hasn't fully propagated?  567
                return False

            except NodeSeemsToBeDown:
                self.log.info("No Response while trying to verify node {}|{}".format(node.rest_interface, node))
                # TODO: Bucket this node as "ghost" or something: somebody else knows about it, but we can't get to it.  567
                return False

            except node.NotStaking:
                # TODO: Bucket this node as inactive, and potentially safe to forget.  567
                self.log.info(
                    f'Staker:Worker {node.checksum_address}:{node.worker_address} is not actively staking, skipping.')
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

            self.learning_deferred = self._learning_task.start(interval=self._SHORT_LEARNING_DELAY)
            self.learning_deferred.addErrback(self.handle_learning_errors)
            return self.learning_deferred
        else:
            self.log.info("Starting Learning Loop.")
            learner_deferred = self._learning_task.start(interval=self._SHORT_LEARNING_DELAY, now=False)
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
            self.log.critical("Unhandled error during node learning.  Attempting graceful crash.")
        else:
            self.log.warn(f"Unhandled error during node learning: {failure.getTraceback()}")
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
            raise self.NotEnoughTeachers("Need some nodes to start learning from.")

        self.teacher_nodes.extend(nodes_we_know_about)

    def cycle_teacher_node(self):
        if not self.teacher_nodes:
            self.select_teacher_nodes()
        try:
            self._current_teacher_node = self.teacher_nodes.pop()
        except IndexError:
            error = "Not enough nodes to select a good teacher, Check your network connection then node configuration"
            raise self.NotEnoughTeachers(error)
        self.log.debug("Cycled teachers; New teacher is {}".format(self._current_teacher_node))

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
                "Learning loop isn't started; can't learn about nodes now.  You can override this with force=True.")
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

        self._learning_deferred = Deferred(canceller=self._discovery_canceller)  # TODO: No longer relevant.

        def _discover_or_abort(_first_result):
            # self.log.debug(f"{self} learning at {datetime.datetime.now()}")   # 1712
            result = self.learn_from_teacher_node(eager=False, canceller=self._discovery_canceller)
            # self.log.debug(f"{self} finished learning at {datetime.datetime.now()}")  # 1712
            return result

        self._learning_deferred.addCallback(_discover_or_abort)
        self._learning_deferred.addErrback(self.handle_learning_errors)

        # Instead of None, we might want to pass something useful about the context.
        # Alternately, it might be nice for learn_from_teacher_node to (some or all of the time) return a Deferred.
        reactor.callInThread(self._learning_deferred.callback, None)
        return self._learning_deferred

    # TODO: Dehydrate these next two methods.  NRN

    def block_until_number_of_known_nodes_is(self,
                                             number_of_nodes_to_know: int,
                                             timeout: int = 10,
                                             learn_on_this_thread: bool = False,
                                             eager: bool = False):
        start = maya.now()
        starting_round = self._learning_round

        # if not learn_on_this_thread and self._learning_task.running:
        #     # Get a head start by firing the looping call now.  If it's very fast, maybe we'll have enough nodes on the first iteration.
        #     self._learning_task()

        while True:
            rounds_undertaken = self._learning_round - starting_round
            if len(self.known_nodes) >= number_of_nodes_to_know:
                if rounds_undertaken:
                    self.log.info("Learned about enough nodes after {} rounds.".format(rounds_undertaken))
                return True

            if not self._learning_task.running:
                self.log.warn("Blocking to learn about nodes, but learning loop isn't running.")
            if learn_on_this_thread:
                try:
                    self.learn_from_teacher_node(eager=eager)
                except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout):
                    # TODO: Even this "same thread" logic can be done off the main thread.  NRN
                    self.log.warn("Teacher was unreachable.  No good way to handle this on the main thread.")

            # The rest of the fucking owl
            round_finish = maya.now()
            elapsed = (round_finish - start).seconds
            if elapsed > timeout:
                if len(self.known_nodes) >= number_of_nodes_to_know:  # Last chance!
                    self.log.info(f"Learned about enough nodes after {rounds_undertaken} rounds.")
                    return True
                if not self._learning_task.running:
                    raise RuntimeError("Learning loop is not running.  Start it with start_learning().")
                elif not reactor.running and not learn_on_this_thread:
                    raise RuntimeError(
                        f"The reactor isn't running, but you're trying to use it for discovery.  You need to start the Reactor in order to use {self} this way.")
                else:
                    raise self.NotEnoughNodes("After {} seconds and {} rounds, didn't find {} nodes".format(
                        timeout, rounds_undertaken, number_of_nodes_to_know))
            else:
                time.sleep(.1)

    def block_until_specific_nodes_are_known(self,
                                             addresses: Set,
                                             timeout=LEARNING_TIMEOUT,
                                             allow_missing=0,
                                             learn_on_this_thread=False):
        start = maya.now()
        starting_round = self._learning_round

        addresses = set(addresses)

        while True:
            if self._crashed:
                return self._crashed
            rounds_undertaken = self._learning_round - starting_round
            if addresses.issubset(self.known_nodes.addresses()):
                if rounds_undertaken:
                    self.log.info("Learned about all nodes after {} rounds.".format(rounds_undertaken))
                return True

            if learn_on_this_thread:
                self.learn_from_teacher_node(eager=True)
            elif not self._learning_task.running:
                raise RuntimeError(
                    "Tried to block while discovering nodes on another thread, but the learning task isn't running.")

            if (maya.now() - start).seconds > timeout:

                still_unknown = addresses.difference(self.known_nodes.addresses())

                if len(still_unknown) <= allow_missing:
                    return False
                else:
                    raise self.NotEnoughTeachers(
                        "After {} seconds and {} rounds, didn't find these {} nodes: {}".format(
                            timeout, rounds_undertaken, len(still_unknown), still_unknown))
            else:
                time.sleep(.1)

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
            if self._rounds_without_new_nodes > self._ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN:
                self.log.info("After {} rounds with no new nodes, it's time to slow down to {} seconds.".format(
                    self._ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN,
                    self._LONG_LEARNING_DELAY))
                self._learning_task.interval = self._LONG_LEARNING_DELAY

    def network_bootstrap(self, node_list: list) -> None:
        for node_addr, port in node_list:
            new_nodes = self.learn_about_nodes_now(node_addr, port)
            self.__known_nodes.update(new_nodes)

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

    def write_node_metadata(self, node, serializer=bytes) -> str:
        return self.node_storage.store_node_metadata(node=node)

    def verify_from(self,
                    stranger: 'Character',
                    message: bytes,
                    signature: Signature
                    ):

        if not signature.verify(verifying_pk=stranger.stamp.as_umbral_pubkey(), message=message):
            try:
                node_on_the_other_end = self.node_class.from_seednode_metadata(stranger.seed_node_metadata(),
                                                                               network_middleware=self.network_middleware)
                if node_on_the_other_end != stranger:
                    raise self.node_class.InvalidNode(
                        f"Expected to connect to {stranger}, got {node_on_the_other_end} instead.")
                else:
                    raise InvalidSignature("Signature for message isn't valid: {}".format(signature))
            except (TypeError, AttributeError):
                raise InvalidSignature(f"Unable to verify message from stranger: {stranger}")

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

        current_teacher = self.current_teacher_node()  # Will raise if there's no available teacher.

        if isinstance(self, Teacher):
            announce_nodes = [self.metadata()]
        else:
            announce_nodes = None

        unresponsive_nodes = set()

        #
        # Request
        #
        if canceller and canceller.stop_now:
            return RELAX

        try:
            response = self.network_middleware.get_nodes_via_rest(node=current_teacher,
                                                                  announce_nodes=announce_nodes,
                                                                  fleet_state_checksum=self.known_nodes.checksum)
        # These except clauses apply to the current_teacher itself, not the learned-about nodes.
        except NodeSeemsToBeDown as e:
            unresponsive_nodes.add(current_teacher)
            self.log.info(
                f"Teacher {str(current_teacher)} is perhaps down:{e}.")  # FIXME: This was printing the node bytestring. Is this really necessary?  #1712
            return
        except current_teacher.InvalidNode as e:
            # Ugh.  The teacher is invalid.  Rough.
            # TODO: Bucket separately and report.
            unresponsive_nodes.add(current_teacher)  # This does nothing.
            self.known_nodes.mark_as(current_teacher.InvalidNode, current_teacher)
            self.log.warn(f"Teacher {str(current_teacher)} is invalid (hex={bytes(current_teacher.metadata()).hex()}):{e}.")
            # TODO (#567): bucket the node as suspicious
            return
        except RuntimeError as e:
            if canceller and canceller.stop_now:
                # Race condition that seems limited to tests.
                # TODO: Sort this out.
                return RELAX
            else:
                self.log.warn(
                    f"Unhandled error while learning from {str(current_teacher)} "
                    f"(hex={bytes(current_teacher.metadata()).hex()}):{e}.")
                raise
        except Exception as e:
            self.log.warn(
                f"Unhandled error while learning from {str(current_teacher)} "
                f"(hex={bytes(current_teacher.metadata()).hex()}):{e}.")  # To track down 2345 / 1698
            raise
        finally:
            # Is cycling happening in the right order?
            self.cycle_teacher_node()

        if response.status_code != 200:
            self.log.info("Bad response from teacher {}: {} - {}".format(current_teacher, response, response.content))
            return

        # TODO: we really should be checking this *before* we ask it for a node list,
        # but currently we may not know this before the REST request (which may mature the node)
        if self.domain != current_teacher.domain:
            self.log.debug(f"{current_teacher} is serving '{current_teacher.domain}', "
                           f"ignore since we are learning about '{self.domain}'")
            return  # This node is not serving our domain.

        #
        # Deserialize
        #
        try:
            metadata = MetadataResponse.from_bytes(response.content)
        except Exception as e:
            self.log.warn(f"Failed to deserialize MetadataResponse from Teacher {current_teacher} ({e}): {response.content}")
            return

        try:
            metadata.verify(current_teacher.stamp.as_umbral_pubkey())
        except InvalidSignature:
            # TODO (#567): bucket the node as suspicious
            self.log.warn(
                f"Invalid signature received from teacher {current_teacher} for MetadataResponse {response.content}")
            return

        # End edge case handling.

        fleet_state_updated = maya.MayaDT(metadata.timestamp_epoch)

        if not metadata.this_node and not metadata.other_nodes:
            # The teacher had the same fleet state
            self.known_nodes.record_remote_fleet_state(
                current_teacher.checksum_address,
                self.known_nodes.checksum,
                fleet_state_updated,
                self.known_nodes.population)

            return FLEET_STATES_MATCH

        # Note: There was previously a version check here, but that required iterating through node bytestrings twice,
        # so it has been removed.  When we create a new Ursula bytestring version, let's put the check
        # somewhere more performant, like mature() or verify_node().

        nodes = (
            ([metadata.this_node] if metadata.this_node else []) +
            (metadata.other_nodes if metadata.other_nodes else [])
            )
        sprouts = [NodeSprout(node) for node in nodes]

        for sprout in sprouts:
            try:
                node_or_false = self.remember_node(sprout,
                                                   record_fleet_state=False,
                                                   # Do we want both of these to be decided by `eager`?
                                                   eager=eager)
                if node_or_false is not False:
                    remembered.append(node_or_false)

                #
                # Report Failure
                #

            except NodeSeemsToBeDown:
                self.log.info(f"Verification Failed - "
                              f"Cannot establish connection to {sprout}.")

            # TODO: This whole section is weird; sprouts down have any of these things.
            except sprout.StampNotSigned:
                self.log.warn(f'Verification Failed - '
                              f'{sprout} {NOT_SIGNED}.')

            except sprout.NotStaking:
                self.log.warn(f'Verification Failed - '
                              f'{sprout} has no active stakes in the current period '
                              f'({self.staking_agent.get_current_period()}')

            except sprout.InvalidWorkerSignature:
                self.log.warn(f'Verification Failed - '
                              f'{sprout} has an invalid wallet signature for {sprout.decentralized_identity_evidence}')

            except sprout.UnbondedWorker:
                self.log.warn(f'Verification Failed - '
                              f'{sprout} is not bonded to a Staker.')

            # TODO: Handle invalid sprouts
            # except sprout.Invalidsprout:
            #     self.log.warn(sprout.invalid_metadata_message.format(sprout))

            except sprout.SuspiciousActivity:
                message = f"Suspicious Activity: Discovered sprout with bad signature: {sprout}." \
                          f"Propagated by: {current_teacher}"
                self.log.warn(message)

        ###################

        learning_round_log_message = "Learning round {}.  Teacher: {} knew about {} nodes, {} were new."
        self.log.info(learning_round_log_message.format(self._learning_round,
                                                        current_teacher,
                                                        len(sprouts),
                                                        len(remembered)))
        if remembered:
            self.known_nodes.record_fleet_state()

        # Now that we updated all our nodes with the teacher's,
        # our fleet state checksum should be the same as the teacher's checksum.

        # Is cycling happening in the right order?
        self.known_nodes.record_remote_fleet_state(
            current_teacher.checksum_address,
            self.known_nodes.checksum,
            fleet_state_updated,
            len(sprouts))

        return sprouts


class Teacher:

    log = Logger("teacher")
    synchronous_query_timeout = 20  # How long to wait during REST endpoints for blockchain queries to resolve
    __DEFAULT_MIN_SEED_STAKE = 0

    def __init__(self,
                 domain: str,  # TODO: Consider using a Domain type
                 certificate: Certificate,
                 certificate_filepath: Path,
                 decentralized_identity_evidence=NOT_SIGNED,
                 ) -> None:

        self.domain = domain

        #
        # Identity
        #

        self.certificate = certificate
        self.certificate_filepath = certificate_filepath
        self.__decentralized_identity_evidence = constant_or_bytes(decentralized_identity_evidence)

        # Assume unverified
        self.verified_stamp = False
        self.verified_worker = False
        self.verified_metadata = False
        self.verified_node = False
        self.__worker_address = None

    class InvalidNode(SuspiciousActivity):
        """Raised when a node has an invalid characteristic - stamp, interface, or address."""

    class InvalidStamp(InvalidNode):
        """Base exception class for invalid character stamps"""

    class StampNotSigned(InvalidStamp):
        """Raised when a node does not have a stamp signature when one is required for verification"""

    class InvalidWorkerSignature(InvalidStamp):
        """Raised when a stamp fails signature verification or recovers an unexpected worker address"""

    class NotStaking(InvalidStamp):
        """Raised when a node fails verification because it is not currently staking"""

    class UnbondedWorker(InvalidNode):
        """Raised when a node fails verification because it is not bonded to a Staker"""

    class WrongMode(TypeError):
        """Raised when a Character tries to use another Character as decentralized when the latter is federated_only."""

    @classmethod
    def set_cert_storage_function(cls, node_storage_function: Callable):
        cls._cert_store_function = node_storage_function

    def mature(self, *args, **kwargs):
        """This is the most mature form, so we do nothing."""
        return self

    @classmethod
    def set_federated_mode(cls, federated_only: bool):
        cls._federated_only_instances = federated_only

    #
    # Known Nodes
    #

    def seed_node_metadata(self, as_teacher_uri=False) -> SeednodeMetadata:
        if as_teacher_uri:
            teacher_uri = f'{self.checksum_address}@{self.rest_server.rest_interface.host}:{self.rest_server.rest_interface.port}'
            return teacher_uri
        return SeednodeMetadata(
            self.checksum_address,
            self.rest_server.rest_interface.host,
            self.rest_server.rest_interface.port
        )

    def bytestring_of_known_nodes(self):
        # TODO (#1537): FleetSensor does metadata-to-byte conversion as well,
        # we may be able to cache the results there.
        response = MetadataResponse.author(signer=self.stamp.as_umbral_signer(),
                                           timestamp_epoch=self.known_nodes.timestamp.epoch,
                                           this_node=self.metadata(),
                                           other_nodes=[node.metadata() for node in self.known_nodes],
                                           )
        return bytes(response)

    #
    # Stamp
    #

    def _stamp_has_valid_signature_by_worker(self) -> bool:
        """
        Off-chain Signature Verification of stamp signature by Worker's ETH account.
        Note that this only "certifies" the stamp with the worker's account,
        so it can be seen like a self certification. For complete assurance,
        it's necessary to validate on-chain the Staker-Worker relation.
        """
        if self.__decentralized_identity_evidence is NOT_SIGNED:
            return False
        signature_is_valid = verify_eip_191(message=bytes(self.stamp),
                                            signature=self.__decentralized_identity_evidence,
                                            address=self.worker_address)
        return signature_is_valid

    def _worker_is_bonded_to_staker(self, registry: BaseContractRegistry) -> bool:
        """
        This method assumes the stamp's signature is valid and accurate.
        As a follow-up, this checks that the worker is bonded to a staker, but it may be
        the case that the "staker" isn't "staking" (e.g., all her tokens have been slashed).
        """
        # Lazy agent get or create
        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)

        staker_address = staking_agent.get_staker_from_worker(worker_address=self.worker_address)
        if staker_address == NULL_ADDRESS:
            raise self.UnbondedWorker(f"Worker {self.worker_address} is not bonded")
        return staker_address == self.checksum_address

    def _staker_is_really_staking(self, registry: BaseContractRegistry) -> bool:
        """
        This method assumes the stamp's signature is valid and accurate.
        As a follow-up, this checks that the staker is, indeed, staking.
        """
        # Lazy agent get or create
        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)  # type: StakingEscrowAgent

        try:
            economics = EconomicsFactory.get_economics(registry=registry)
        except Exception:
            raise  # TODO: Get StandardEconomics  NRN

        min_stake = economics.minimum_allowed_locked

        stake_current_period = staking_agent.get_locked_tokens(staker_address=self.checksum_address, periods=0)
        stake_next_period = staking_agent.get_locked_tokens(staker_address=self.checksum_address, periods=1)
        is_staking = max(stake_current_period, stake_next_period) >= min_stake
        return is_staking

    def validate_worker(self, registry: BaseContractRegistry = None) -> None:

        # Federated
        if self.federated_only:
            message = "This node cannot be verified in this manner, " \
                      "but is OK to use in federated mode if you " \
                      "have reason to believe it is trustworthy."
            raise self.WrongMode(message)

        # Decentralized
        else:

            # Off-chain signature verification
            if not self._stamp_has_valid_signature_by_worker():
                message = f"Invalid signature {self.__decentralized_identity_evidence.hex()} " \
                          f"from worker {self.worker_address} for stamp {bytes(self.stamp).hex()} "
                raise self.InvalidWorkerSignature(message)

            # On-chain staking check, if registry is present
            if registry:
                if not self._worker_is_bonded_to_staker(registry=registry):  # <-- Blockchain CALL
                    message = f"Worker {self.worker_address} is not bonded to staker {self.checksum_address}"
                    self.log.debug(message)
                    raise self.UnbondedWorker(message)

                if self._staker_is_really_staking(registry=registry):  # <-- Blockchain CALL
                    self.verified_worker = True
                else:
                    raise self.NotStaking(f"Staker {self.checksum_address} is not staking")

            self.verified_stamp = True

    def validate_metadata_signature(self) -> bool:
        """
        Checks that the interface info is valid for this node's canonical address.
        """
        metadata_is_valid = self._metadata.verify()
        self.verified_metadata = metadata_is_valid
        if metadata_is_valid:
            return True
        else:
            raise self.InvalidNode("Metadata signature is invalid")

    def validate_metadata(self, registry: BaseContractRegistry = None):

        # Verify the metadata signature
        if not self.verified_metadata:
            self.validate_metadata_signature()

        # Verify the identity evidence
        if self.verified_stamp:
            return

        # Offline check of valid stamp signature by worker
        try:
            self.validate_worker(registry=registry)
        except self.WrongMode:
            if bool(registry):
                raise

    def verify_node(self,
                    network_middleware_client,
                    registry: BaseContractRegistry = None,
                    certificate_filepath: Optional[Path] = None,
                    force: bool = False
                    ) -> bool:
        """
        Three things happening here:

        * Verify that the stamp matches the address (raises InvalidNode is it's not valid,
          or WrongMode if it's a federated mode and being verified as a decentralized node)

        * Verify the interface signature (raises InvalidNode if not valid)

        * Connect to the node, make sure that it's up, and that the signature and address we
          checked are the same ones this node is using now. (raises InvalidNode if not valid;
          also emits a specific warning depending on which check failed).

        """

        if force:
            self.verified_metadata = False
            self.verified_node = False
            self.verified_stamp = False
            self.verified_worker = False

        if self.verified_node:
            return True

        if not registry and not self.federated_only:  # TODO: # 466
            self.log.debug("No registry provided for decentralized stranger node verification - "
                           "on-chain Staking verification will not be performed.")

        # This is both the stamp's client signature and interface metadata check; May raise InvalidNode
        self.validate_metadata(registry=registry)

        # The node's metadata is valid; let's be sure the interface is in order.
        if not certificate_filepath:
            if self.certificate_filepath is CERTIFICATE_NOT_SAVED:
                self.certificate_filepath = self._cert_store_function(self.certificate, port=self.rest_interface.port)
            certificate_filepath = self.certificate_filepath

        response_data = network_middleware_client.node_information(host=self.rest_interface.host,
                                                                   port=self.rest_interface.port,
                                                                   certificate_filepath=certificate_filepath)

        sprout = NodeSprout(NodeMetadata.from_bytes(response_data))

        verifying_keys_match = sprout.verifying_key == self.public_keys(SigningPower)
        encrypting_keys_match = sprout.encrypting_key == self.public_keys(DecryptingPower)
        addresses_match = sprout.public_address == self.canonical_public_address
        evidence_matches = sprout.decentralized_identity_evidence == self.__decentralized_identity_evidence

        if not all((encrypting_keys_match, verifying_keys_match, addresses_match, evidence_matches)):
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

    @property
    def decentralized_identity_evidence(self):
        return self.__decentralized_identity_evidence

    @property
    def worker_address(self):
        if not self.__worker_address and not self.federated_only:
            if self.decentralized_identity_evidence is NOT_SIGNED:
                raise self.StampNotSigned  # TODO: Find a better exception  NRN
            self.__worker_address = recover_address_eip_191(message=bytes(self.stamp),
                                                            signature=self.decentralized_identity_evidence)
        return self.__worker_address
