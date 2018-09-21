import random
from abc import abstractmethod, ABC
from collections import defaultdict
from collections import deque
from contextlib import suppress
from logging import Logger
from logging import getLogger
from typing import Dict, ClassVar, Set
from typing import Tuple
from typing import Union, List

import maya
import requests
import time
from constant_sorrow import constants, default_constant_splitter
from eth_keys import KeyAPI as EthKeyAPI
from eth_utils import to_checksum_address, to_canonical_address
from twisted.internet import reactor
from twisted.internet import task
from umbral.keys import UmbralPublicKey
from umbral.signing import Signature

from nucypher.blockchain.eth.agents import MinerAgent
from nucypher.crypto.api import encrypt_and_sign
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import CryptoPower, SigningPower, EncryptingPower, NoSigningPower, CryptoPowerUp
from nucypher.crypto.signing import signature_splitter, StrangerStamp, SignatureStamp
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nodes import VerifiableNode
from nucypher.network.server import TLSHostingPower


class Learner(ABC):
    """
    Any participant in the "learning loop" - a class inheriting from
    this one has the ability, synchronously or asynchronously,
    to learn about nodes in the network, verify some essential
    details about them, and store information about them for later use.
    """

    _SHORT_LEARNING_DELAY = 5
    _LONG_LEARNING_DELAY = 90
    _ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN = 10

    class NotEnoughTeachers(RuntimeError):
        pass

    def __init__(self,
                 always_be_learning: bool = False,
                 start_learning_on_same_thread: bool = False,
                 known_nodes: tuple = None,
                 abort_on_learning_error: bool = False) -> None:

        self.log = getLogger("characters")                       # type: Logger

        self.always_be_learning = always_be_learning
        self.start_learning_on_same_thread = start_learning_on_same_thread
        self._abort_on_learning_error = abort_on_learning_error
        self._learning_listeners = defaultdict(list)
        self._node_ids_to_learn_about_immediately = set()

        known_nodes = known_nodes if known_nodes is not None else tuple()
        self.__known_nodes = dict()
        for node in known_nodes:
            self.remember_node(node)

        self.teacher_nodes = deque()
        self._current_teacher_node = None   # type: Teacher
        self._learning_task = task.LoopingCall(self.keep_learning_about_nodes)
        self._learning_round = 0            # type: int
        self._rounds_without_new_nodes = 0  # type: int

        if self.always_be_learning:
            self.start_learning_loop(now=self.start_learning_on_same_thread)

    @property
    def known_nodes(self):
        return self.__known_nodes

    def remember_node(self, node):
        # TODO: 334
        listeners = self._learning_listeners.pop(node.checksum_public_address, ())
        address = node.checksum_public_address

        self.__known_nodes[address] = node
        self.log.info("Remembering {}, popping {} listeners.".format(node.checksum_public_address, len(listeners)))
        for listener in listeners:
            listener.add(address)
        self._node_ids_to_learn_about_immediately.discard(address)

    def start_learning_loop(self, now=False):
        if self._learning_task.running:
            return False
        else:
            d = self._learning_task.start(interval=self._SHORT_LEARNING_DELAY, now=now)
            d.addErrback(self.handle_learning_errors)
            return d

    def handle_learning_errors(self, *args, **kwargs):
        failure = args[0]
        if self._abort_on_learning_error:
            self.log.critical("Unhandled error during node learning.  Attempting graceful crash.")
            reactor.callFromThread(self._crash_gracefully, failure=failure)
        else:
            self.log.warning("Unhandled error during node learning: {}".format(failure.getTraceback()))

    def _crash_gracefully(self, failure=None):
        """
        A facility for crashing more gracefully in the event that an exception
        is unhandled in a different thread, especially inside a loop like the learning loop.
        """
        self._crashed = failure
        failure.raiseException()

    def shuffled_known_nodes(self):
        nodes_we_know_about = list(self.__known_nodes.values())
        random.shuffle(nodes_we_know_about)
        return nodes_we_know_about

    def select_teacher_nodes(self):
        nodes_we_know_about = self.shuffled_known_nodes()

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

    def current_teacher_node(self, cycle=False):
        if not self._current_teacher_node:
            self.cycle_teacher_node()

        teacher = self._current_teacher_node

        if cycle:
            self.cycle_teacher_node()

        return teacher

    def learn_about_nodes_now(self, force=False):
        if self._learning_task.running:
            self._learning_task.reset()
            self._learning_task()
        elif not force:
            self.log.warning(
                "Learning loop isn't started; can't learn about nodes now.  You can ovverride this with force=True.")
        elif force:
            self.log.info("Learning loop wasn't started; forcing start now.")
            self._learning_task.start(self._SHORT_LEARNING_DELAY, now=True)

    def keep_learning_about_nodes(self):
        """
        Continually learn about new nodes.
        """
        self.learn_from_teacher_node(eager=False)  # TODO: Allow the user to set eagerness?

    def learn_about_specific_nodes(self, canonical_addresses: Set):
        self._node_ids_to_learn_about_immediately.update(canonical_addresses)  # hmmmm
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
                self.log.warning("Blocking to learn about nodes, but learning loop isn't running.")
            if learn_on_this_thread:
                self.learn_from_teacher_node(eager=True)

            if (maya.now() - start).seconds > timeout:
                if not self._learning_task.running:
                    raise self.NotEnoughTeachers(
                        "We didn't discover any nodes because the learning loop isn't running.  Start it with start_learning().")
                else:
                    raise self.NotEnoughTeachers("After {} seconds and {} rounds, didn't find {} nodes".format(
                        timeout, rounds_undertaken, number_of_nodes_to_know))
            else:
                time.sleep(.1)

    def block_until_specific_nodes_are_known(self,
                                             canonical_addresses: Set,
                                             timeout=10,
                                             allow_missing=0,
                                             learn_on_this_thread=False):
        start = maya.now()
        starting_round = self._learning_round

        while True:
            if self._crashed:
                return self._crashed
            rounds_undertaken = self._learning_round - starting_round
            if canonical_addresses.issubset(self.__known_nodes):
                if rounds_undertaken:
                    self.log.info("Learned about all nodes after {} rounds.".format(rounds_undertaken))
                return True

            if not self._learning_task.running:
                self.log.warning("Blocking to learn about nodes, but learning loop isn't running.")
            if learn_on_this_thread:
                self.learn_from_teacher_node(eager=True)

            if (maya.now() - start).seconds > timeout:

                still_unknown = canonical_addresses.difference(self.__known_nodes)

                if len(still_unknown) <= allow_missing:
                    return False
                elif not self._learning_task.running:
                    raise self.NotEnoughTeachers("The learning loop is not running.  Start it with start_learning().")
                else:
                    raise self.NotEnoughTeachers("After {} seconds and {} rounds, didn't find these {} nodes: {}".format(
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
            new_nodes = self.learn_about_nodes(node_addr, port)
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

    @abstractmethod
    def learn_from_teacher_node(self):
        raise NotImplementedError


class Character(Learner):
    """
    A base-class for any character in our cryptography protocol narrative.
    """

    _default_crypto_powerups = None
    _stamp = None
    _crashed = False

    from nucypher.network.protocols import SuspiciousActivity  # Ship this exception with every Character.

    class NotEnoughUrsulas(MinerAgent.NotEnoughMiners):
        """
        All Characters depend on knowing about enough Ursulas to perform their role.
        This exception is raised when a piece of logic can't proceed without more Ursulas.
        """

    class InvalidSignature(Exception):
        """
        Raised when a signature doesn't pass validation/verification.
        """

    def __init__(self,
                 is_me: bool = True,
                 network_middleware: RestMiddleware = None,
                 known_certificates_dir: str = None,
                 known_metadata_dir: str = None,
                 crypto_power: CryptoPower = None,
                 crypto_power_ups: List[CryptoPowerUp] = None,
                 federated_only: bool = False,
                 checksum_address: bytes = None,
                 *args, **kwargs
                 ) -> None:

        """

        Base class for Nucypher protocol actors.


        PowerUps
        ========
        :param crypto_power: A CryptoPower object; if provided, this will be the character's CryptoPower.
        :param crypto_power_ups: If crypto_power is not provided, a new one will be made to consume all CryptoPowerUps.

        If neither crypto_power nor crypto_power_ups are provided, we give this
        Character all CryptoPowerUps listed in their _default_crypto_powerups
        attribute.

        :param is_me: Set this to True when you want this Character to represent
            the owner of the configuration under which the program is being run.
            A Character who is_me can do things that other Characters can't,
            like run servers, sign messages, and decrypt messages which are
            encrypted for them.  Typically this will be True for exactly one
            Character, but there are scenarios in which its imaginable to be
            represented by zero Characters or by more than one Character.

        """
        super().__init__(*args, **kwargs)
        self.federated_only = federated_only                     # type: bool
        self.known_certificates_dir = known_certificates_dir
        self.known_metadata_dir = known_metadata_dir

        #
        # Power-ups and Powers
        #
        if crypto_power and crypto_power_ups:
            raise ValueError("Pass crypto_power or crypto_power_ups (or neither), but not both.")

        crypto_power_ups = crypto_power_ups or []  # type: list

        if crypto_power:
            self._crypto_power = crypto_power      # type: CryptoPower
        elif crypto_power_ups:
            self._crypto_power = CryptoPower(power_ups=crypto_power_ups)
        else:
            self._crypto_power = CryptoPower(power_ups=self._default_crypto_powerups)

        #
        # Identity and Network
        #
        if is_me is True:

            self.treasure_maps = {}  # type: dict
            self.network_middleware = network_middleware or RestMiddleware()

            try:
                signing_power = self._crypto_power.power_ups(SigningPower)  # type: SigningPower
                self._stamp = signing_power.get_signature_stamp()           # type: SignatureStamp
            except NoSigningPower:
                self._stamp = constants.NO_SIGNING_POWER

        else:  # Feel like a stranger
            if network_middleware is not None:
                raise TypeError(
                    "Can't attach network middleware to a Character who isn't me.  What are you even trying to do?")
            self._stamp = StrangerStamp(self.public_keys(SigningPower))

        # Decentralized
        if not federated_only:
            if not checksum_address:
                raise ValueError("No checksum_address provided while running in a non-federated mode.")
            else:
                self._checksum_address = checksum_address  # type: str

        # Federated
        elif federated_only:
            self._checksum_address = constants.NO_BLOCKCHAIN_CONNECTION

            if checksum_address:
                # We'll take a checksum address, as long as it matches their singing key
                self._set_checksum_address()  # type: str
                if not checksum_address == self.checksum_public_address:
                    error = "Federated-only Characters derive their address from their Signing key; got {} instead."
                    raise self.SuspiciousActivity(error.format(checksum_address))

    def __eq__(self, other) -> bool:
        return bytes(self.stamp) == bytes(other.stamp)

    def __hash__(self):
        return int.from_bytes(bytes(self.stamp), byteorder="big")

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{} {}"
        r = r.format(class_name, self.canonical_public_address)
        return r

    @property
    def name(self):
        return self.__class__.__name__

    @property
    def rest_interface(self):
        return self._crypto_power.power_ups(TLSHostingPower).rest_server.rest_url()

    @property
    def stamp(self):
        if self._stamp is constants.NO_SIGNING_POWER:
            raise NoSigningPower
        elif not self._stamp:
            raise AttributeError("SignatureStamp has not been set up yet.")
        else:
            return self._stamp
    @property
    def canonical_public_address(self):
        return to_canonical_address(self.checksum_public_address)

    @canonical_public_address.setter
    def canonical_public_address(self, address_bytes):
        self._checksum_address = to_checksum_address(address_bytes)

    @property
    def ether_address(self):
        raise NotImplementedError

    @property
    def checksum_public_address(self):
        if self._checksum_address is constants.NO_BLOCKCHAIN_CONNECTION:
            self._set_checksum_address()
        return self._checksum_address

    @classmethod
    def from_public_keys(cls, powers_and_material: Dict, federated_only=True, *args, **kwargs) -> 'Character':
        # TODO: Need to be federated only until we figure out the best way to get the checksum_address in here.
        """
        Sometimes we discover a Character and, at the same moment,
        learn the public parts of more of their powers. Here, we take a Dict
        (powers_and_key_bytes) in the following format:
        {CryptoPowerUp class: public_material_bytes}

        Each item in the collection will have the CryptoPowerUp instantiated
        with the public_material_bytes, and the resulting CryptoPowerUp instance
        consumed by the Character.
        """
        crypto_power = CryptoPower()

        for power_up, public_key in powers_and_material.items():
            try:
                umbral_key = UmbralPublicKey(public_key)
            except TypeError:
                umbral_key = public_key

            crypto_power.consume_power_up(power_up(pubkey=umbral_key))

        return cls(is_me=False, federated_only=federated_only, crypto_power=crypto_power, *args, **kwargs)

    def learn_from_teacher_node(self, eager=True):
        """
        Sends a request to node_url to find out about known nodes.
        """
        self._learning_round += 1

        try:
            current_teacher = self.current_teacher_node()
        except self.NotEnoughTeachers as e:
            self.log.warning("Can't learn right now: {}".format(e.args[0]))
            return

        rest_url = current_teacher.rest_interface  # TODO: Name this..?

        # TODO: Do we really want to try to learn about all these nodes instantly?
        # Hearing this traffic might give insight to an attacker.
        if VerifiableNode in self.__class__.__bases__:
            announce_nodes = [self]
        else:
            announce_nodes = None

        unresponsive_nodes = set()
        try:

            # FIXME
            response = self.network_middleware.get_nodes_via_rest(rest_url,
                                                                  nodes_i_need=self._node_ids_to_learn_about_immediately,
                                                                  announce_nodes=announce_nodes,
                                                                  certificate_path=current_teacher.certificate_filepath)
        except requests.exceptions.ConnectionError as e:
            unresponsive_nodes.add(current_teacher)
            teacher_rest_info = current_teacher.rest_information()[0]

            # TODO: This error isn't necessarily "no repsonse" - let's maybe pass on the text of the exception here.
            self.log.info("No Response from teacher: {}:{}.".format(teacher_rest_info.host, teacher_rest_info.port))
            self.cycle_teacher_node()
            return

        if response.status_code != 200:
            raise RuntimeError("Bad response from teacher: {} - {}".format(response, response.content))

        signature, nodes = signature_splitter(response.content, return_remainder=True)

        # TODO: This doesn't make sense - a decentralized node can still learn about a federated-only node.
        from nucypher.characters.lawful import Ursula
        node_list = Ursula.batch_from_bytes(nodes, federated_only=self.federated_only)

        new_nodes = []
        for node in node_list:

            if node.checksum_public_address in self.known_nodes or node.checksum_public_address == self.checksum_public_address:
                continue  # TODO: 168 Check version and update if required.

            try:
                if eager:
                    node.verify_node(self.network_middleware, accept_federated_only=self.federated_only)
                else:
                    node.validate_metadata(accept_federated_only=self.federated_only)
            except node.SuspiciousActivity:
                # TODO: Account for possibility that stamp, rather than interface, was bad.
                message = "Suspicious Activity: Discovered node with bad signature: {}.  " \
                          "Propagated by: {}".format(current_teacher.checksum_public_address, rest_url)
                self.log.warning(message)
            self.log.info("Previously unknown node: {}".format(node.checksum_public_address))

            self.log.info("Previously unknown node: {}".format(node.checksum_public_address))
            self.remember_node(node)
            new_nodes.append(node)

        self._adjust_learning(new_nodes)

        learning_round_log_message = "Learning round {}.  Teacher: {} knew about {} nodes, {} were new."
        self.log.info(learning_round_log_message.format(self._learning_round,
                                                        current_teacher.checksum_public_address,
                                                        len(node_list),
                                                        len(new_nodes)), )
        if new_nodes and self.known_certificates_dir:
            for node in new_nodes:
                node.save_certificate_to_disk(self.known_certificates_dir)

        return new_nodes

    def encrypt_for(self,
                    recipient: 'Character',
                    plaintext: bytes,
                    sign: bool = True,
                    sign_plaintext=True,
                    ) -> tuple:
        """
        Encrypts plaintext for recipient actor. Optionally signs the message as well.

        :param recipient: The character whose public key will be used to encrypt
            cleartext.
        :param plaintext: The secret to be encrypted.
        :param sign: Whether or not to sign the message.
        :param sign_plaintext: When signing, the cleartext is signed if this is
            True,  Otherwise, the resulting ciphertext is signed.

        :return: A tuple, (ciphertext, signature).  If sign==False,
            then signature will be NOT_SIGNED.
        """
        signer = self.stamp if sign else constants.DO_NOT_SIGN

        message_kit, signature = encrypt_and_sign(recipient_pubkey_enc=recipient.public_keys(EncryptingPower),
                                                  plaintext=plaintext,
                                                  signer=signer,
                                                  sign_plaintext=sign_plaintext
                                                  )
        return message_kit, signature

    def verify_from(self,
                    stranger: 'Character',
                    message_kit: Union[UmbralMessageKit, bytes],
                    signature: Signature = None,
                    decrypt=False,
                    delegator_signing_key: UmbralPublicKey = None,
                    ) -> tuple:
        """
        Inverse of encrypt_for.

        :param actor_that_sender_claims_to_be: A Character instance representing
            the actor whom the sender claims to be.  We check the public key
            owned by this Character instance to verify.
        :param message_kit: the message to be (perhaps decrypted and) verified.
        :param signature: The signature to check.
        :param decrypt: Whether or not to decrypt the messages.
        :param delegator_signing_key: A signing key from the original delegator.
            This is used only when decrypting a MessageKit with an activated Capsule
            to check that the KFrag used to create each attached CFrag is the
            authentic KFrag initially created by the delegator.

        :return: Whether or not the signature is valid, the decrypted plaintext
            or NO_DECRYPTION_PERFORMED
        """
        sender_pubkey_sig = stranger.stamp.as_umbral_pubkey()
        with suppress(AttributeError):
            if message_kit.sender_pubkey_sig:
                if not message_kit.sender_pubkey_sig == sender_pubkey_sig:
                    raise ValueError(
                        "This MessageKit doesn't appear to have come from {}".format(stranger))

        signature_from_kit = None

        if decrypt:
            # We are decrypting the message; let's do that first and see what the sig header says.
            cleartext_with_sig_header = self.decrypt(message_kit, verifying_key=delegator_signing_key)
            sig_header, cleartext = default_constant_splitter(cleartext_with_sig_header, return_remainder=True)
            if sig_header == constants.SIGNATURE_IS_ON_CIPHERTEXT:
                # THe ciphertext is what is signed - note that for later.
                message = message_kit.ciphertext
                if not signature:
                    raise ValueError("Can't check a signature on the ciphertext if don't provide one.")
            elif sig_header == constants.SIGNATURE_TO_FOLLOW:
                # The signature follows in this cleartext - split it off.
                signature_from_kit, cleartext = signature_splitter(cleartext,
                                                                   return_remainder=True)
                message = cleartext
        else:
            # Not decrypting - the message is the object passed in as a message kit.  Cast it.
            message = bytes(message_kit)
            cleartext = constants.NO_DECRYPTION_PERFORMED

        if signature and signature_from_kit:
            if signature != signature_from_kit:
                raise ValueError(
                    "The MessageKit has a Signature, but it's not the same one you provided.  Something's up.")

        signature_to_use = signature or signature_from_kit

        if signature_to_use:
            is_valid = signature_to_use.verify(message, sender_pubkey_sig)
            if not is_valid:
                raise stranger.InvalidSignature(
                    "Signature for message isn't valid: {}".format(signature_to_use))
        else:
            raise self.InvalidSignature("No signature provided -- signature presumed invalid.")

        #
        # Next we have decrypt() and sign() - these use the private
        # keys of their respective powers; any character who has these powers can use these functions.
        #
        # If they don't have the correct Power, the appropriate PowerUpError is raised.
        #
        return cleartext

    def decrypt(self, message_kit, verifying_key: UmbralPublicKey = None):
        return self._crypto_power.power_ups(EncryptingPower).decrypt(message_kit, verifying_key)

    def sign(self, message):
        return self._crypto_power.power_ups(SigningPower).sign(message)

    def public_keys(self, power_up_class: ClassVar) -> Union[Tuple, UmbralPublicKey]:
        """
        Pass a power_up_class, get the public material for this Character which corresponds to that
        class - whatever type of object that may be.

        If the Character doesn't have the power corresponding to that class, raises the
        appropriate PowerUpError (ie, NoSigningPower or NoEncryptingPower).
        """
        power_up = self._crypto_power.power_ups(power_up_class)
        return power_up.public_key()

    def _set_checksum_address(self):

        if self.federated_only:
            verifying_key = self.public_keys(SigningPower)
            uncompressed_bytes = verifying_key.to_bytes(is_compressed=False)
            without_prefix = uncompressed_bytes[1:]
            verifying_key_as_eth_key = EthKeyAPI.PublicKey(without_prefix)
            public_address = verifying_key_as_eth_key.to_checksum_address()
        else:
            try:
                public_address = to_checksum_address(self.canonical_public_address)
            except TypeError:
                raise TypeError("You can't use a decentralized character without a _checksum_address.")
            except NotImplementedError:
                raise TypeError(
                    "You can't use a plain Character in federated mode - you need to implement ether_address.")

        self._checksum_address = public_address
