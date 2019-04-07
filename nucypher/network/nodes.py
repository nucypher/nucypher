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

import binascii
import random
from collections import defaultdict, OrderedDict
from collections import deque
from collections import namedtuple
from contextlib import suppress

from twisted.python.threadpool import ThreadPool
from typing import Set, Tuple

import maya
import requests
import time
from cryptography.x509 import Certificate
from eth_keys.datatypes import Signature as EthSignature
from requests.exceptions import SSLError
from twisted.internet import reactor, defer
from twisted.internet import task
from twisted.internet.threads import deferToThread
from twisted.logger import Logger

from bytestring_splitter import BytestringSplitter
from bytestring_splitter import VariableLengthBytestring, BytestringSplittingError
from constant_sorrow import constant_or_bytes
from constant_sorrow.constants import NO_KNOWN_NODES, NOT_SIGNED, NEVER_SEEN, NO_STORAGE_AVAILIBLE, FLEET_STATES_MATCH
from nucypher.config.constants import SeednodeMetadata, GLOBAL_DOMAIN
from nucypher.config.storages import ForgetfulNodeStorage
from nucypher.crypto.api import keccak_digest
from nucypher.crypto.powers import BlockchainPower, SigningPower, DecryptingPower, NoSigningPower
from nucypher.crypto.signing import signature_splitter
from nucypher.network import LEARNING_LOOP_VERSION
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nicknames import nickname_from_seed
from nucypher.network.protocols import SuspiciousActivity
from nucypher.network.server import TLSHostingPower


def icon_from_checksum(checksum,
                       nickname_metadata,
                       number_of_nodes="Unknown number of "):
    if checksum is NO_KNOWN_NODES:
        return "NO FLEET STATE AVAILABLE"
    icon_template = """
    <div class="nucypher-nickname-icon" style="border-color:{color};">
    <div class="small">{number_of_nodes} nodes</div>
    <div class="symbols">
        <span class="single-symbol" style="color: {color}">{symbol}&#xFE0E;</span>
    </div>
    <br/>
    <span class="small-address">{fleet_state_checksum}</span>
    </div>
    """.replace("  ", "").replace('\n', "")
    return icon_template.format(
        number_of_nodes=number_of_nodes,
        color=nickname_metadata[0][0]['hex'],
        symbol=nickname_metadata[0][1],
        fleet_state_checksum=checksum[0:8]
    )


class FleetStateTracker:
    """
    A representation of a fleet of NuCypher nodes.
    """
    _checksum = NO_KNOWN_NODES.bool_value(False)
    _nickname = NO_KNOWN_NODES
    _nickname_metadata = NO_KNOWN_NODES
    _tracking = False
    most_recent_node_change = NO_KNOWN_NODES
    snapshot_splitter = BytestringSplitter(32, 4)
    log = Logger("Learning")
    state_template = namedtuple("FleetState", ("nickname", "metadata", "icon", "nodes", "updated"))

    def __init__(self):
        self.additional_nodes_to_track = []
        self.updated = maya.now()
        self._nodes = OrderedDict()
        self.states = OrderedDict()

    def __setitem__(self, key, value):
        self._nodes[key] = value

        if self._tracking:
            self.log.info("Updating fleet state after saving node {}".format(value))
            self.record_fleet_state()
        else:
            self.log.debug("Not updating fleet state.")

    def __getitem__(self, item):
        return self._nodes[item]

    def __bool__(self):
        return bool(self._nodes)

    def __contains__(self, item):
        return item in self._nodes.keys() or item in self._nodes.values()

    def __iter__(self):
        yield from self._nodes.values()

    def __len__(self):
        return len(self._nodes)

    def __eq__(self, other):
        return self._nodes == other._nodes

    def __repr__(self):
        return self._nodes.__repr__()

    @property
    def checksum(self):
        return self._checksum

    @checksum.setter
    def checksum(self, checksum_value):
        self._checksum = checksum_value
        self._nickname, self._nickname_metadata = nickname_from_seed(checksum_value, number_of_pairs=1)

    @property
    def nickname(self):
        return self._nickname

    @property
    def nickname_metadata(self):
        return self._nickname_metadata

    @property
    def icon(self) -> str:
        if self.nickname_metadata is NO_KNOWN_NODES:
            return str(NO_KNOWN_NODES)
        return self.nickname_metadata[0][1]

    def addresses(self):
        return self._nodes.keys()

    def icon_html(self):
        return icon_from_checksum(checksum=self.checksum,
                                  number_of_nodes=str(len(self)),
                                  nickname_metadata=self.nickname_metadata)

    def snapshot(self):
        fleet_state_checksum_bytes = binascii.unhexlify(self.checksum)
        fleet_state_updated_bytes = self.updated.epoch.to_bytes(4, byteorder="big")
        return fleet_state_checksum_bytes + fleet_state_updated_bytes

    def record_fleet_state(self, additional_nodes_to_track=None):
        if additional_nodes_to_track:
            self.additional_nodes_to_track.extend(additional_nodes_to_track)
        if not self._nodes:
            # No news here.
            return
        sorted_nodes = self.sorted()

        sorted_nodes_joined = b"".join(bytes(n) for n in sorted_nodes)
        checksum = keccak_digest(sorted_nodes_joined).hex()
        if checksum not in self.states:
            self.checksum = keccak_digest(b"".join(bytes(n) for n in self.sorted())).hex()
            self.updated = maya.now()
            # For now we store the sorted node list.  Someday we probably spin this out into
            # its own class, FleetState, and use it as the basis for partial updates.
            new_state = self.state_template(nickname=self.nickname,
                                            metadata=self.nickname_metadata,
                                            nodes=sorted_nodes,
                                            icon=self.icon,
                                            updated=self.updated,
                                            )
            self.states[checksum] = new_state
            return checksum, new_state

    def start_tracking_state(self, additional_nodes_to_track=None):
        if additional_nodes_to_track is None:
            additional_nodes_to_track = list()
        self.additional_nodes_to_track.extend(additional_nodes_to_track)
        self._tracking = True
        self.update_fleet_state()

    def sorted(self):
        nodes_to_consider = list(self._nodes.values()) + self.additional_nodes_to_track
        return sorted(nodes_to_consider, key=lambda n: n.checksum_public_address)

    def shuffled(self):
        nodes_we_know_about = list(self._nodes.values())
        random.shuffle(nodes_we_know_about)
        return nodes_we_know_about

    def abridged_states_dict(self):
        abridged_states = {}
        for k, v in self.states.items():
            abridged_states[k] = self.abridged_state_details(v)

        return abridged_states

    def abridged_nodes_dict(self):
        abridged_nodes = {}
        for checksum_address, node in self._nodes.items():
            abridged_nodes[checksum_address] = self.abridged_node_details(node)

        return abridged_nodes

    @staticmethod
    def abridged_state_details(state):
        return {"nickname": state.nickname,
                "symbol": state.metadata[0][1],
                "color_hex": state.metadata[0][0]['hex'],
                "color_name": state.metadata[0][0]['color'],
                "updated": state.updated.rfc2822()
                }

    @staticmethod
    def abridged_node_details(node):
        try:
            last_seen = node.last_seen.iso8601()
        except AttributeError:  # TODO: This logic belongs somewhere - anywhere - else.
            last_seen = str(node.last_seen)  # In case it's the constant NEVER_SEEN
        return {
                "icon_details": node.nickname_icon_details(),  # TODO: Mix this in better.
                "rest_url": node.rest_url(),
                "nickname": node.nickname,
                "checksum_address": node.checksum_public_address,
                "timestamp": node.timestamp.iso8601(),
                "last_seen": last_seen,
                "fleet_state_icon": node.fleet_state_icon,
                }


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

    LEARNER_VERSION = LEARNING_LOOP_VERSION
    node_splitter = BytestringSplitter(VariableLengthBytestring)
    version_splitter = BytestringSplitter((int, 2, {"byteorder": "big"}))
    tracker_class = FleetStateTracker

    invalid_metadata_message = "{} has invalid metadata.  Maybe its stake is over?  Or maybe it is transitioning to a new interface.  Ignoring."
    unknown_version_message = "{} purported to be of version {}, but we're only version {}.  Is there a new version of NuCypher?"
    really_unknown_version_message = "Unable to glean address from node that perhaps purported to be version {}.  We're only version {}."
    fleet_state_icon = ""

    class NotEnoughNodes(RuntimeError):
        pass

    class NotEnoughTeachers(NotEnoughNodes):
        pass

    class UnresponsiveTeacher(ConnectionError):
        pass

    class NotATeacher(ValueError):
        """
        Raised when a character cannot be properly utilized because
        it does not have the proper attributes for learning or verification.
        """

    def __init__(self,
                 domains: Set,
                 network_middleware: RestMiddleware = __DEFAULT_MIDDLEWARE_CLASS(),
                 start_learning_now: bool = False,
                 learn_on_same_thread: bool = False,
                 known_nodes: tuple = None,
                 seed_nodes: Tuple[tuple] = None,
                 node_storage=None,
                 save_metadata: bool = False,
                 abort_on_learning_error: bool = False,
                 lonely: bool = False,
                 ) -> None:

        self.log = Logger("learning-loop")  # type: Logger

        self.learning_domains = domains
        self.network_middleware = network_middleware
        self.save_metadata = save_metadata
        self.start_learning_now = start_learning_now
        self.learn_on_same_thread = learn_on_same_thread

        self._abort_on_learning_error = abort_on_learning_error
        self._learning_listeners = defaultdict(list)
        self._node_ids_to_learn_about_immediately = set()

        self.__known_nodes = self.tracker_class()

        self.lonely = lonely
        self.done_seeding = False

        # Read
        if node_storage is None:
            node_storage = self.__DEFAULT_NODE_STORAGE(federated_only=self.federated_only,
                                                       # TODO: remove federated_only
                                                       character_class=self.__class__)

        self.node_storage = node_storage
        if save_metadata and node_storage is NO_STORAGE_AVAILIBLE:
            raise ValueError("Cannot save nodes without a configured node storage")

        known_nodes = known_nodes or tuple()
        self.unresponsive_startup_nodes = list()  # TODO: Attempt to use these again later
        for node in known_nodes:
            try:
                self.remember_node(
                    node)  # TODO: Need to test this better - do we ever init an Ursula-Learner with Node Storage?
            except self.UnresponsiveTeacher:
                self.unresponsive_startup_nodes.append(node)

        self.teacher_nodes = deque()
        self._current_teacher_node = None  # type: Teacher
        self._learning_task = task.LoopingCall(self.keep_learning_about_nodes)
        self._learning_round = 0  # type: int
        self._rounds_without_new_nodes = 0  # type: int
        self._seed_nodes = seed_nodes or []
        self.unresponsive_seed_nodes = set()

        if self.start_learning_now:
            self.start_learning_loop(now=self.learn_on_same_thread)

    @property
    def known_nodes(self):
        return self.__known_nodes

    def load_seednodes(self,
                       read_storages: bool = True,
                       retry_attempts: int = 3):  # TODO: why are these unused?
        """
        Engage known nodes from storages and pre-fetch hardcoded seednode certificates for node learning.
        """
        if self.done_seeding:
            self.log.debug("Already done seeding; won't try again.")
            return

        from nucypher.characters.lawful import Ursula
        for seednode_metadata in self._seed_nodes:

            self.log.debug(
                "Seeding from: {}|{}:{}".format(seednode_metadata.checksum_public_address,
                                                seednode_metadata.rest_host,
                                                seednode_metadata.rest_port))

            seed_node = Ursula.from_seednode_metadata(seednode_metadata=seednode_metadata,
                                                      network_middleware=self.network_middleware,
                                                      federated_only=self.federated_only)  # TODO: 466
            if seed_node is False:
                self.unresponsive_seed_nodes.add(seednode_metadata)
            else:
                self.unresponsive_seed_nodes.discard(seednode_metadata)
                self.remember_node(seed_node)

        if not self.unresponsive_seed_nodes:
            self.log.info("Finished learning about all seednodes.")

        self.done_seeding = True

        if read_storages is True:
            self.read_nodes_from_storage()

        if not self.known_nodes:
            self.log.warn("No seednodes were available after {} attempts".format(retry_attempts))
            # TODO: Need some actual logic here for situation with no seed nodes (ie, maybe try again much later)

    def read_nodes_from_storage(self) -> set:
        stored_nodes = self.node_storage.all(federated_only=self.federated_only)  # TODO: 466
        for node in stored_nodes:
            self.remember_node(node)

    def remember_node(self, node, force_verification_check=False, record_fleet_state=True):

        if node == self:  # No need to remember self.
            return False

        # First, determine if this is an outdated representation of an already known node.
        with suppress(KeyError):
            already_known_node = self.known_nodes[node.checksum_public_address]
            if not node.timestamp > already_known_node.timestamp:
                self.log.debug("Skipping already known node {}".format(already_known_node))
                # This node is already known.  We can safely return.
                return False

        try:
            stranger_certificate = node.certificate
        except AttributeError:
            # Whoops, we got an Alice, Bob, or someone...
            raise self.NotATeacher(f"{node.__class__.__name__} does not have a certificate and cannot be remembered.")

        # Store node's certificate - It has been seen.
        certificate_filepath = self.node_storage.store_node_certificate(certificate=stranger_certificate)

        # In some cases (seed nodes or other temp stored certs),
        # this will update the filepath from the temp location to this one.
        node.certificate_filepath = certificate_filepath
        self.log.info(f"Saved TLS certificate for {node.nickname}: {certificate_filepath}")

        try:
            node.verify_node(force=force_verification_check,
                             network_middleware=self.network_middleware,
                             accept_federated_only=self.federated_only,
                             # TODO: 466 - move federated-only up to Learner?
                             )
        except SSLError:
            return False  # TODO: Bucket this node as having bad TLS info - maybe it's an update that hasn't fully propagated?

        except NodeSeemsToBeDown:
            self.log.info("No Response while trying to verify node {}|{}".format(node.rest_interface, node))
            return False  # TODO: Bucket this node as "ghost" or something: somebody else knows about it, but we can't get to it.

        listeners = self._learning_listeners.pop(node.checksum_public_address, tuple())
        address = node.checksum_public_address

        self.known_nodes[address] = node

        if self.save_metadata:
            self.node_storage.store_node_metadata(node=node)

        self.log.info("Remembering {} ({}), popping {} listeners.".format(node.nickname, node.checksum_public_address, len(listeners)))
        for listener in listeners:
            listener.add(address)
        self._node_ids_to_learn_about_immediately.discard(address)

        if record_fleet_state:
            self.known_nodes.record_fleet_state()

        return node

    def start_learning_loop(self, now=False):
        if self._learning_task.running:
            return False
        elif now:
            self.log.info("Starting Learning Loop NOW.")

            if self.lonely:
                self.done_seeding = True
                self.read_nodes_from_storage()

            else:
                self.load_seednodes()

            self.learn_from_teacher_node()
            self.learning_deferred = self._learning_task.start(interval=self._SHORT_LEARNING_DELAY)
            self.learning_deferred.addErrback(self.handle_learning_errors)
            return self.learning_deferred
        else:
            self.log.info("Starting Learning Loop.")

            learning_deferreds = list()
            if not self.lonely:
                seeder_deferred = deferToThread(self.load_seednodes)
                seeder_deferred.addErrback(self.handle_learning_errors)
                learning_deferreds.append(seeder_deferred)

            learner_deferred = self._learning_task.start(interval=self._SHORT_LEARNING_DELAY, now=now)
            learner_deferred.addErrback(self.handle_learning_errors)
            learning_deferreds.append(learner_deferred)

            self.learning_deferred = defer.DeferredList(learning_deferreds)
            return self.learning_deferred

    def stop_learning_loop(self, reason=None):
        """
        Only for tests at this point.  Maybe some day for graceful shutdowns.
        """
        self._learning_task.stop()

    def handle_learning_errors(self, *args, **kwargs):
        failure = args[0]
        if self._abort_on_learning_error:
            self.log.critical("Unhandled error during node learning.  Attempting graceful crash.")
            reactor.callFromThread(self._crash_gracefully, failure=failure)
        else:
            cleaned_traceback = failure.getTraceback().replace('{', '').replace('}', '')  # FIXME: Amazing.
            self.log.warn("Unhandled error during node learning: {}".format(cleaned_traceback))
            if not self._learning_task.running:
                self.start_learning_loop()  # TODO: Consider a single entry point for this with more elegant pause and unpause.

    def _crash_gracefully(self, failure=None):
        """
        A facility for crashing more gracefully in the event that an exception
        is unhandled in a different thread, especially inside a loop like the learning loop.
        """
        self._crashed = failure
        failure.raiseException()
        # TODO: We don't actually have checksum_public_address at this level - maybe only Characters can crash gracefully :-)
        self.log.critical("{} crashed with {}".format(self.checksum_public_address, failure))

    def select_teacher_nodes(self):
        nodes_we_know_about = self.known_nodes.shuffled()

        if not nodes_we_know_about:
            raise self.NotEnoughTeachers("Need some nodes to start learning from.")

        self.teacher_nodes.extend(nodes_we_know_about)

    def cycle_teacher_node(self):
        # To ensure that all the best teachers are available, first let's make sure
        # that we have connected to all the seed nodes.
        if self.unresponsive_seed_nodes and not self.lonely:
            self.log.info("Still have unresponsive seed nodes; trying again to connect.")
            self.load_seednodes()  # Ideally, this is async and singular.

        if not self.teacher_nodes:
            self.select_teacher_nodes()
        try:
            self._current_teacher_node = self.teacher_nodes.pop()
        except IndexError:
            error = "Not enough nodes to select a good teacher, Check your network connection then node configuration"
            raise self.NotEnoughTeachers(error)
        self.log.info("Cycled teachers; New teacher is {}".format(self._current_teacher_node))

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
            self._learning_task()
        elif not force:
            self.log.warn(
                "Learning loop isn't started; can't learn about nodes now.  You can override this with force=True.")
        elif force:
            self.log.info("Learning loop wasn't started; forcing start now.")
            self._learning_task.start(self._SHORT_LEARNING_DELAY, now=True)

    def keep_learning_about_nodes(self):
        """
        Continually learn about new nodes.
        """
        # TODO: Allow the user to set eagerness?
        self.learn_from_teacher_node(eager=False)

    def learn_about_specific_nodes(self, addresses: Set):
        self._node_ids_to_learn_about_immediately.update(addresses)  # hmmmm
        self.learn_about_nodes_now()

    # TODO: Dehydrate these next two methods.

    def block_until_number_of_known_nodes_is(self,
                                             number_of_nodes_to_know: int,
                                             timeout: int = 10,
                                             learn_on_this_thread: bool = False):
        start = maya.now()
        starting_round = self._learning_round

        while True:
            rounds_undertaken = self._learning_round - starting_round
            if len(self.__known_nodes) >= number_of_nodes_to_know:
                if rounds_undertaken:
                    self.log.info("Learned about enough nodes after {} rounds.".format(rounds_undertaken))
                return True

            if not self._learning_task.running:
                self.log.warn("Blocking to learn about nodes, but learning loop isn't running.")
            if learn_on_this_thread:
                try:
                    self.learn_from_teacher_node(eager=True)
                except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout):
                    # TODO: Even this "same thread" logic can be done off the main thread.
                    self.log.warn("Teacher was unreachable.  No good way to handle this on the main thread.")

            # The rest of the fucking owl
            if (maya.now() - start).seconds > timeout:
                if not self._learning_task.running:
                    raise RuntimeError("Learning loop is not running.  Start it with start_learning().")
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

        while True:
            if self._crashed:
                return self._crashed
            rounds_undertaken = self._learning_round - starting_round
            if addresses.issubset(self.known_nodes.addresses()):
                if rounds_undertaken:
                    self.log.info("Learned about all nodes after {} rounds.".format(rounds_undertaken))
                return True

            if not self._learning_task.running:
                self.log.warn("Blocking to learn about nodes, but learning loop isn't running.")
            if learn_on_this_thread:
                self.learn_from_teacher_node(eager=True)

            if (maya.now() - start).seconds > timeout:

                still_unknown = addresses.difference(self.known_nodes.addresses())

                if len(still_unknown) <= allow_missing:
                    return False
                elif not self._learning_task.running:
                    raise self.NotEnoughTeachers("The learning loop is not running.  Start it with start_learning().")
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
        TODO: Do other important things - scrub, bucket, etc.
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

    def _push_certain_newly_discovered_nodes_here(self, queue_to_push, node_addresses):
        """
        If any node_addresses are discovered, push them to queue_to_push.
        """
        for node_address in node_addresses:
            self.log.info("Adding listener for {}".format(node_address))
            self._learning_listeners[node_address].append(queue_to_push)

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
        # TODO: Build a concurrent pool of lookups here.

        # Scenario 3: We don't know about this node, and neither does our friend.

    def write_node_metadata(self, node, serializer=bytes) -> str:
        return self.node_storage.store_node_metadata(node=node)

    def learn_from_teacher_node(self, eager=True):
        """
        Sends a request to node_url to find out about known nodes.
        """
        self._learning_round += 1

        try:
            current_teacher = self.current_teacher_node()
        except self.NotEnoughTeachers as e:
            self.log.warn("Can't learn right now: {}".format(e.args[0]))
            return

        if Teacher in self.__class__.__bases__:
            announce_nodes = [self]
        else:
            announce_nodes = None

        unresponsive_nodes = set()
        try:
            # TODO: Streamline path generation
            certificate_filepath = self.node_storage.generate_certificate_filepath(
                checksum_address=current_teacher.checksum_public_address)
            response = self.network_middleware.get_nodes_via_rest(node=current_teacher,
                                                                  nodes_i_need=self._node_ids_to_learn_about_immediately,
                                                                  announce_nodes=announce_nodes,
                                                                  fleet_checksum=self.known_nodes.checksum)
        except NodeSeemsToBeDown as e:
            unresponsive_nodes.add(current_teacher)
            self.log.info("Bad Response from teacher: {}:{}.".format(current_teacher, e))
            return
        finally:
            self.cycle_teacher_node()

        #
        # Before we parse the response, let's handle some edge cases.
        if response.status_code == 204:
            # In this case, this node knows about no other nodes.  Hopefully we've taught it something.
            if response.content == b"":
                return NO_KNOWN_NODES
            # In the other case - where the status code is 204 but the repsonse isn't blank - we'll keep parsing.
            # It's possible that our fleet states match, and we'll check for that later.

        elif response.status_code != 200:
            self.log.info("Bad response from teacher {}: {} - {}".format(current_teacher, response, response.content))
            return

        try:
            signature, node_payload = signature_splitter(response.content, return_remainder=True)
        except BytestringSplittingError as e:
            self.log.warn(e.args[0])
            return

        try:
            self.verify_from(current_teacher, node_payload, signature=signature)
        except current_teacher.InvalidSignature:
            # TODO: What to do if the teacher improperly signed the node payload?
            raise
        # End edge case handling.
        #

        fleet_state_checksum_bytes, fleet_state_updated_bytes, node_payload = FleetStateTracker.snapshot_splitter(
            node_payload,
            return_remainder=True)
        current_teacher.last_seen = maya.now()
        # TODO: This is weird - let's get a stranger FleetState going.
        checksum = fleet_state_checksum_bytes.hex()

        # TODO: This doesn't make sense - a decentralized node can still learn about a federated-only node.
        from nucypher.characters.lawful import Ursula
        if constant_or_bytes(node_payload) is FLEET_STATES_MATCH:
            current_teacher.update_snapshot(checksum=checksum,
                                            updated=maya.MayaDT(
                                                int.from_bytes(fleet_state_updated_bytes, byteorder="big")),
                                            number_of_known_nodes=len(self.known_nodes)
                                            )
            return FLEET_STATES_MATCH

        node_list = Ursula.batch_from_bytes(node_payload, federated_only=self.federated_only)  # TODO: 466

        current_teacher.update_snapshot(checksum=checksum,
                                        updated=maya.MayaDT(
                                            int.from_bytes(fleet_state_updated_bytes, byteorder="big")),
                                        number_of_known_nodes=len(node_list)
                                        )

        new_nodes = []
        for node in node_list:
            if GLOBAL_DOMAIN not in self.learning_domains:
                if not set(self.learning_domains).intersection(set(node.serving_domains)):
                    continue  # This node is not serving any of our domains.

            # First, determine if this is an outdated representation of an already known node.
            with suppress(KeyError):
                already_known_node = self.known_nodes[node.checksum_public_address]
                if not node.timestamp > already_known_node.timestamp:
                    self.log.debug("Skipping already known node {}".format(already_known_node))
                    # This node is already known.  We can safely continue to the next.
                    continue

            certificate_filepath = self.node_storage.store_node_certificate(certificate=node.certificate)

            try:
                if eager:
                    node.verify_node(self.network_middleware,
                                     accept_federated_only=self.federated_only,  # TODO: 466
                                     certificate_filepath=certificate_filepath)
                    self.log.debug("Verified node: {}".format(node.checksum_public_address))

                else:
                    node.validate_metadata(accept_federated_only=self.federated_only)  # TODO: 466
            # This block is a mess of eagerness.  This can all be done better lazily.
            except NodeSeemsToBeDown as e:
                self.log.info(f"Can't connect to {node} to verify it right now.")
            except node.InvalidNode:
                # TODO: Account for possibility that stamp, rather than interface, was bad.
                self.log.warn(node.invalid_metadata_message.format(node))
            except node.SuspiciousActivity:
                message = "Suspicious Activity: Discovered node with bad signature: {}.  " \
                          "Propagated by: {}".format(current_teacher.checksum_public_address, teacher_uri)
                self.log.warn(message)
            else:
                new = self.remember_node(node, record_fleet_state=False)
                if new:
                    new_nodes.append(node)

        self._adjust_learning(new_nodes)

        learning_round_log_message = "Learning round {}.  Teacher: {} knew about {} nodes, {} were new."
        self.log.info(learning_round_log_message.format(self._learning_round,
                                                        current_teacher,
                                                        len(node_list),
                                                        len(new_nodes)), )
        if new_nodes:
            self.known_nodes.record_fleet_state()
            for node in new_nodes:
                self.node_storage.store_node_certificate(certificate=node.certificate)
        return new_nodes


class Teacher:
    TEACHER_VERSION = LEARNING_LOOP_VERSION
    verified_stamp = False
    verified_interface = False
    _verified_node = False
    _interface_info_splitter = (int, 4, {'byteorder': 'big'})
    log = Logger("teacher")
    __DEFAULT_MIN_SEED_STAKE = 0

    def __init__(self,
                 domains: Set,
                 certificate: Certificate,
                 certificate_filepath: str,
                 interface_signature=NOT_SIGNED.bool_value(False),
                 timestamp=NOT_SIGNED,
                 identity_evidence=NOT_SIGNED,
                 substantiate_immediately=False,
                 passphrase=None,
                 ) -> None:

        self.serving_domains = domains
        self.certificate = certificate
        self.certificate_filepath = certificate_filepath
        self._interface_signature_object = interface_signature
        self._timestamp = timestamp
        self.last_seen = NEVER_SEEN("Haven't connected to this node yet.")
        self.fleet_state_checksum = None
        self.fleet_state_updated = None
        self._evidence_of_decentralized_identity = constant_or_bytes(identity_evidence)

        if substantiate_immediately:
            self.substantiate_stamp(password=passphrase)  # TODO: Derive from keyring

    class InvalidNode(SuspiciousActivity):
        """
        Raised when a node has an invalid characteristic - stamp, interface, or address.
        """

    class WrongMode(TypeError):
        """
        Raised when a Character tries to use another Character as decentralized when the latter is federated_only.
        """

    class IsFromTheFuture(TypeError):
        """
        Raised when deserializing a Character from a future version.
        """

    @classmethod
    def from_tls_hosting_power(cls, tls_hosting_power: TLSHostingPower, *args, **kwargs) -> 'Teacher':
        certificate_filepath = tls_hosting_power.keypair.certificate_filepath
        certificate = tls_hosting_power.keypair.certificate
        return cls(certificate=certificate, certificate_filepath=certificate_filepath, *args, **kwargs)

    #
    # Known Nodes
    #

    def seed_node_metadata(self, as_teacher_uri=False):
        if as_teacher_uri:
            teacher_uri = f'{self.checksum_public_address}@{self.rest_server.rest_interface.host}:{self.rest_server.rest_interface.port}'
            return teacher_uri
        return SeednodeMetadata(self.checksum_public_address,  # type: str
                                self.rest_server.rest_interface.host,  # type: str
                                self.rest_server.rest_interface.port)  # type: int

    def sorted_nodes(self):
        nodes_to_consider = list(self.known_nodes.values()) + [self]
        return sorted(nodes_to_consider, key=lambda n: n.checksum_public_address)

    def _stamp_has_valid_wallet_signature(self):
        signature_bytes = self._evidence_of_decentralized_identity
        if signature_bytes is NOT_SIGNED:
            return False
        else:
            signature = EthSignature(signature_bytes)
        proper_pubkey = signature.recover_public_key_from_msg(bytes(self.stamp))
        proper_address = proper_pubkey.to_checksum_address()
        return proper_address == self.checksum_public_address

    def update_snapshot(self, checksum, updated, number_of_known_nodes):
        # We update the simple snapshot here, but of course if we're dealing with an instance that is also a Learner, it has
        # its own notion of its FleetState, so we probably need a reckoning of sorts here to manage that.  In time.
        self.fleet_state_nickname, self.fleet_state_nickname_metadata = nickname_from_seed(checksum, number_of_pairs=1)
        self.fleet_state_checksum = checksum
        self.fleet_state_updated = updated
        self.fleet_state_icon = icon_from_checksum(self.fleet_state_checksum,
                                                   nickname_metadata=self.fleet_state_nickname_metadata,
                                                   number_of_nodes=number_of_known_nodes)

    #
    # Stamp
    #

    def _stamp_has_valid_wallet_signature(self):
        signature_bytes = self._evidence_of_decentralized_identity
        if signature_bytes is NOT_SIGNED:
            return False
        else:
            signature = EthSignature(signature_bytes)
        proper_pubkey = signature.recover_public_key_from_msg(bytes(self.stamp))
        proper_address = proper_pubkey.to_checksum_address()
        return proper_address == self.checksum_public_address

    def stamp_is_valid(self):
        """
        :return:
        """
        signature = self._evidence_of_decentralized_identity
        if self._stamp_has_valid_wallet_signature():
            self.verified_stamp = True
            return True
        elif self.federated_only and signature is NOT_SIGNED:
            message = "This node can't be verified in this manner, " \
                      "but is OK to use in federated mode if you" \
                      " have reason to believe it is trustworthy."
            raise self.WrongMode(message)
        else:
            raise self.InvalidNode

    def verify_id(self, ursula_id, digest_factory=bytes):
        self.verify()
        if not ursula_id == digest_factory(self.canonical_public_address):
            raise self.InvalidNode

    def validate_metadata(self, accept_federated_only=False):
        if not self.verified_interface:
            self.interface_is_valid()
        if not self.verified_stamp:
            try:
                self.stamp_is_valid()
            except self.WrongMode:
                if not accept_federated_only:
                    raise

    def verify_node(self,
                    network_middleware,
                    certificate_filepath: str = None,
                    accept_federated_only: bool = False,
                    force: bool = False
                    ) -> bool:
        """
        Three things happening here:

        * Verify that the stamp matches the address (raises InvalidNode is it's not valid, or WrongMode if it's a federated mode and being verified as a decentralized node)
        * Verify the interface signature (raises InvalidNode if not valid)
        * Connect to the node, make sure that it's up, and that the signature and address we checked are the same ones this node is using now. (raises InvalidNode if not valid; also emits a specific warning depending on which check failed).
        """
        if not force:
            if self._verified_node:
                return True

        self.validate_metadata(accept_federated_only)  # This is both the stamp and interface check.

        if not certificate_filepath:

            if not self.certificate_filepath:
                raise TypeError("We haven't saved a certificate for this node yet.")
            else:
                certificate_filepath = self.certificate_filepath

        # The node's metadata is valid; let's be sure the interface is in order.
        response_data = network_middleware.node_information(host=self.rest_information()[0].host,
                                                            port=self.rest_information()[0].port,
                                                            certificate_filepath=certificate_filepath)

        version, node_bytes = self.version_splitter(response_data, return_remainder=True)

        node_details = self.internal_splitter(node_bytes)
        # TODO check timestamp here.  589

        verifying_keys_match = node_details['verifying_key'] == self.public_keys(SigningPower)
        encrypting_keys_match = node_details['encrypting_key'] == self.public_keys(DecryptingPower)
        addresses_match = node_details['public_address'] == self.canonical_public_address
        evidence_matches = node_details['identity_evidence'] == self._evidence_of_decentralized_identity

        if not all((encrypting_keys_match, verifying_keys_match, addresses_match, evidence_matches)):
            # TODO: Optional reporting.  355
            if not addresses_match:
                self.log.warn("Wallet address swapped out.  It appears that someone is trying to defraud this node.")
            if not verifying_keys_match:
                self.log.warn("Verifying key swapped out.  It appears that someone is impersonating this node.")
            raise self.InvalidNode("Wrong cryptographic material for this node - something fishy going on.")
        else:
            self._verified_node = True

    def substantiate_stamp(self, password: str):
        blockchain_power = self._crypto_power.power_ups(BlockchainPower)
        blockchain_power.unlock_account(password=password)  # TODO: 349
        signature = blockchain_power.sign_message(bytes(self.stamp))
        self._evidence_of_decentralized_identity = signature

    #
    # Interface
    #

    def interface_is_valid(self):
        """
        Checks that the interface info is valid for this node's canonical address.
        """
        interface_info_message = self._signable_interface_info_message()  # Contains canonical address.
        message = self.timestamp_bytes() + interface_info_message
        interface_is_valid = self._interface_signature.verify(message, self.public_keys(SigningPower))
        self.verified_interface = interface_is_valid
        if interface_is_valid:
            return True
        else:
            raise self.InvalidNode

    def _signable_interface_info_message(self):
        message = self.canonical_public_address + self.rest_information()[0]
        return message

    def _sign_and_date_interface_info(self):
        message = self._signable_interface_info_message()
        self._timestamp = maya.now()
        self._interface_signature_object = self.stamp(self.timestamp_bytes() + message)

    @property
    def _interface_signature(self):
        if not self._interface_signature_object:
            try:
                self._sign_and_date_interface_info()
            except NoSigningPower:
                raise NoSigningPower("This Ursula is a stranger and cannot be used to verify.")
        return self._interface_signature_object

    @property
    def timestamp(self):
        if not self._timestamp:
            try:
                self._sign_and_date_interface_info()
            except NoSigningPower:
                raise NoSigningPower("This Node is a Stranger; you didn't init with a timestamp, so you can't verify.")
        return self._timestamp

    def timestamp_bytes(self):
        return self.timestamp.epoch.to_bytes(4, 'big')

    #
    # Nicknames
    #

    @property
    def nickname_icon(self):
        return '{} {}'.format(self.nickname_metadata[0][1], self.nickname_metadata[1][1])

    def nickname_icon_html(self):
        icon_template = """
        <div class="nucypher-nickname-icon" style="border-top-color:{first_color}; border-left-color:{first_color}; border-bottom-color:{second_color}; border-right-color:{second_color};">
        <span class="small">{node_class} v{version}</span>
        <div class="symbols">
            <span class="single-symbol" style="color: {first_color}">{first_symbol}&#xFE0E;</span>
            <span class="single-symbol" style="color: {second_color}">{second_symbol}&#xFE0E;</span>
        </div>
        <br/>
        <span class="small-address">{address_first6}</span>
        </div>
        """.replace("  ", "").replace('\n', "")
        return icon_template.format(**self.nickname_icon_details)

    def nickname_icon_details(self):
        return dict(
            node_class=self.__class__.__name__,
            version=self.TEACHER_VERSION,
            first_color=self.nickname_metadata[0][0]['hex'],  # TODO: These index lookups are awful.
            first_symbol=self.nickname_metadata[0][1],
            second_color=self.nickname_metadata[1][0]['hex'],
            second_symbol=self.nickname_metadata[1][1],
            address_first6=self.checksum_public_address[2:8]
        )
