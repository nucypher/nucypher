import asyncio
import random
import time
from collections import OrderedDict, defaultdict
from collections import deque
from contextlib import suppress
from functools import partial
from logging import Logger
from logging import getLogger
from typing import Dict, ClassVar, Set, DefaultDict, Iterable
from typing import Tuple
from typing import Union, List

import kademlia
import maya
from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from constant_sorrow import constants, default_constant_splitter
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import load_pem_x509_certificate
from eth_keys import KeyAPI as EthKeyAPI
from eth_utils import to_checksum_address, to_canonical_address
from kademlia.utils import digest
from twisted.internet import reactor
from twisted.internet import task, threads
from umbral.keys import UmbralPublicKey
from umbral.signing import Signature

from nucypher.blockchain.eth.actors import PolicyAuthor, Miner, only_me
from nucypher.blockchain.eth.agents import MinerAgent
from nucypher.blockchain.eth.constants import datetime_to_period
from nucypher.config.constants import DEFAULT_INI_FILEPATH
from nucypher.config.parsers import parse_ursula_config, parse_alice_config, \
    parse_character_config
from nucypher.crypto.api import keccak_digest, encrypt_and_sign
from nucypher.crypto.constants import PUBLIC_ADDRESS_LENGTH, PUBLIC_KEY_LENGTH
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import CryptoPower, SigningPower, EncryptingPower, DelegatingPower, NoSigningPower, \
    BlockchainPower, CryptoPowerUp
from nucypher.crypto.signing import signature_splitter, StrangerStamp, SignatureStamp
from nucypher.keystore.keypairs import HostingKeypair
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nodes import VerifiableNode
from nucypher.network.protocols import InterfaceInfo
from nucypher.network.server import NucypherDHTServer, NucypherSeedOnlyDHTServer, ProxyRESTServer, TLSHostingPower, \
    ProxyRESTRoutes


class Character:
    """
    A base-class for any character in our cryptography protocol narrative.
    """
    _dht_server = None
    _dht_server_class = kademlia.network.Server

    _default_crypto_powerups = None
    _stamp = None
    _crashed = False

    _SHORT_LEARNING_DELAY = 5
    _LONG_LEARNING_DELAY = 90
    _ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN = 10

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
                 crypto_power: CryptoPower = None,
                 crypto_power_ups: List[CryptoPowerUp] = None,
                 federated_only: bool = False,
                 checksum_address: bytes = None,
                 always_be_learning: bool = False,
                 start_learning_on_same_thread: bool = False,
                 known_nodes: tuple = None,
                 abort_on_learning_error: bool = False,
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

        known_nodes = known_nodes if known_nodes is not None else tuple()
        self.federated_only = federated_only  # type: bool
        self._abort_on_learning_error = abort_on_learning_error  # type: bool

        self.log = getLogger("characters")  # type: Logger

        #
        # Power-ups and Powers
        #
        if crypto_power and crypto_power_ups:
            raise ValueError("Pass crypto_power or crypto_power_ups (or neither), but not both.")

        crypto_power_ups = crypto_power_ups or []  # type: list

        if crypto_power:
            self._crypto_power = crypto_power  # type: CryptoPower
        elif crypto_power_ups:
            self._crypto_power = CryptoPower(power_ups=crypto_power_ups)
        else:
            self._crypto_power = CryptoPower(power_ups=self._default_crypto_powerups)

        #
        # Identity and Network
        #
        if is_me is True:
            self._known_nodes = {}  # type: dict
            self.treasure_maps = {}  # type: dict
            self.network_middleware = network_middleware or RestMiddleware()

            ##### LEARNING STUFF (Maybe move to a different class?) #####
            self._learning_listeners = defaultdict(list)  # type: DefaultDict
            self._node_ids_to_learn_about_immediately = set()  # type: set

            for node in known_nodes:
                self.remember_node(node)

            self.teacher_nodes = deque()  # type: deque
            self._current_teacher_node = None  # type: Ursula
            self._learning_task = task.LoopingCall(self.keep_learning_about_nodes)
            self._learning_round = 0  # type: int
            self._rounds_without_new_nodes = 0  # type: int

            if always_be_learning:
                self.start_learning_loop(now=start_learning_on_same_thread)
            #####

            try:
                signing_power = self._crypto_power.power_ups(SigningPower)  # type: SigningPower
                self._stamp = signing_power.get_signature_stamp()  # type: SignatureStamp
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
                    raise ValueError(error.format(checksum_address))

    def __eq__(self, other):
        return bytes(self.stamp) == bytes(other.stamp)

    def __hash__(self):
        return int.from_bytes(self.stamp, byteorder="big")

    @property
    def name(self):
        return self.__class__.__name__

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

    def attach_dht_server(self, ksize=20, alpha=3, id=None, storage=None, *args, **kwargs) -> None:
        if self._dht_server:
            raise RuntimeError("Attaching the server twice is almost certainly a bad idea.")

        self._dht_server = self._dht_server_class(node_storage=self._known_nodes,  # TODO: 340
                                                  treasure_map_storage=self._stored_treasure_maps,  # TODO: 340
                                                  federated_only=self.federated_only,
                                                  ksize=ksize, alpha=alpha, id=id,
                                                  storage=storage, *args, **kwargs)

    @property
    def stamp(self):
        if self._stamp is constants.NO_SIGNING_POWER:
            raise NoSigningPower
        elif not self._stamp:
            raise AttributeError("SignatureStamp has not been set up yet.")
        else:
            return self._stamp

    @property
    def dht_server(self) -> kademlia.network.Server:
        if self._dht_server:
            return self._dht_server
        else:
            raise RuntimeError("Server hasn't been attached.")

    ######
    # Knowing and learning about nodes
    ##

    def remember_node(self, node):
        # TODO: 334
        listeners = self._learning_listeners.pop(node.checksum_public_address, ())
        address = node.checksum_public_address

        self._known_nodes[address] = node
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
        nodes_we_know_about = list(self._known_nodes.values())
        random.shuffle(nodes_we_know_about)
        return nodes_we_know_about

    def select_teacher_nodes(self):
        nodes_we_know_about = self.shuffled_known_nodes()

        if nodes_we_know_about is None:
            raise self.NotEnoughUrsulas("Need some nodes to start learning from.")

        self.teacher_nodes.extend(nodes_we_know_about)

    def cycle_teacher_node(self):
        if not self.teacher_nodes:
            self.select_teacher_nodes()
        try:
            self._current_teacher_node = self.teacher_nodes.pop()
        except IndexError:
            error = "Not enough nodes to select a good teacher, Check your network connection then node configuration"
            raise self.NotEnoughUrsulas(error)

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

    def block_until_number_of_known_nodes_is(self, number_of_nodes_to_know: int,
                                             timeout=10,
                                             learn_on_this_thread=False):
        start = maya.now()
        starting_round = self._learning_round

        while True:
            rounds_undertaken = self._learning_round - starting_round
            if len(self._known_nodes) >= number_of_nodes_to_know:
                if rounds_undertaken:
                    self.log.info("Learned about enough nodes after {} rounds.".format(rounds_undertaken))
                return True

            if not self._learning_task.running:
                self.log.warning("Blocking to learn about nodes, but learning loop isn't running.")
            if learn_on_this_thread:
                self.learn_from_teacher_node(eager=True)

            if (maya.now() - start).seconds > timeout:
                if not self._learning_task.running:
                    raise self.NotEnoughUrsulas(
                        "We didn't discover any nodes because the learning loop isn't running.  Start it with start_learning().")
                else:
                    raise self.NotEnoughUrsulas("After {} seconds and {} rounds, didn't find {} nodes".format(
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
            if canonical_addresses.issubset(self._known_nodes):
                if rounds_undertaken:
                    self.log.info("Learned about all nodes after {} rounds.".format(rounds_undertaken))
                return True

            if not self._learning_task.running:
                self.log.warning("Blocking to learn about nodes, but learning loop isn't running.")
            if learn_on_this_thread:
                self.learn_from_teacher_node(eager=True)

            if (maya.now() - start).seconds > timeout:

                still_unknown = canonical_addresses.difference(self._known_nodes)

                if len(still_unknown) <= allow_missing:
                    return False
                elif not self._learning_task.running:
                    raise self.NotEnoughUrsulas(
                        "We didn't discover any nodes because the learning loop isn't running.  Start it with start_learning().")
                else:
                    raise self.NotEnoughUrsulas("After {} seconds and {} rounds, didn't find these {} nodes: {}".format(
                        timeout, rounds_undertaken, len(still_unknown), still_unknown))

            else:
                time.sleep(.1)

    def learn_from_teacher_node(self, eager=True):
        """
        Sends a request to node_url to find out about known nodes.
        """
        self._learning_round += 1

        try:
            current_teacher = self.current_teacher_node()
        except self.NotEnoughUrsulas as e:
            self.log.warning("Can't learn right now: {}".format(e.args[0]))
            return

        rest_url = current_teacher.rest_url()

        # TODO: Do we really want to try to learn about all these nodes instantly?  Hearing this traffic might give insight to an attacker.
        if VerifiableNode in self.__class__.__bases__:
            announce_nodes = [self]
        else:
            announce_nodes = None

        response = self.network_middleware.get_nodes_via_rest(rest_url,
                                                              nodes_i_need=self._node_ids_to_learn_about_immediately,
                                                              announce_nodes=announce_nodes)
        if response.status_code != 200:
            raise RuntimeError("Bad response from teacher: {} - {}".format(response, response.content
                                                                           ))
        signature, nodes = signature_splitter(response.content, return_remainder=True)
        node_list = Ursula.batch_from_bytes(nodes,
                                            federated_only=self.federated_only)  # TODO: This doesn't make sense - a decentralized node can still learn about a federated-only node.

        new_nodes = []

        for node in node_list:

            if node.checksum_public_address in self._known_nodes or node.checksum_public_address == self.checksum_public_address:
                continue  # TODO: 168 Check version and update if required.

            try:
                if eager:
                    node.verify_node(self.network_middleware, accept_federated_only=self.federated_only)
                else:
                    node.validate_metadata(accept_federated_only=self.federated_only)
            except node.SuspiciousActivity:
                # TODO: Account for possibility that stamp, rather than interface, was bad.
                message = "Suspicious Activity: Discovered node with bad signature: {}.  " \
                          "Propagated by: {}:{}".format(current_teacher.checksum_public_address,
                                                        rest_address, port)
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
                                                        len(new_nodes)),
                      )

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
            self._known_nodes.update(new_nodes)

    def get_nodes_by_ids(self, node_ids):
        for node_id in node_ids:
            try:
                # Scenario 1: We already know about this node.
                return self._known_nodes[node_id]
            except KeyError:
                raise NotImplementedError
        # Scenario 2: We don't know about this node, but a nearby node does.
        # TODO: Build a concurrent pool of lookups here.

        # Scenario 3: We don't know about this node, and neither does our friend.

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
                    mystery_stranger: 'Character',
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
        sender_pubkey_sig = mystery_stranger.stamp.as_umbral_pubkey()
        with suppress(AttributeError):
            if message_kit.sender_pubkey_sig:
                if not message_kit.sender_pubkey_sig == sender_pubkey_sig:
                    raise ValueError(
                        "This MessageKit doesn't appear to have come from {}".format(mystery_stranger))

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
                raise mystery_stranger.InvalidSignature(
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

    """
    And finally, some miscellaneous but generally-applicable abilities:
    """

    def public_keys(self, power_up_class: ClassVar) -> Union[Tuple, UmbralPublicKey]:
        """
        Pass a power_up_class, get the public material for this Character which corresponds to that
        class - whatever type of object that may be.

        If the Character doesn't have the power corresponding to that class, raises the
        appropriate PowerUpError (ie, NoSigningPower or NoEncryptingPower).
        """
        power_up = self._crypto_power.power_ups(power_up_class)
        return power_up.public_key()

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

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{} {}"
        r = r.format(class_name, self.canonical_public_address)
        return r


class Alice(Character, PolicyAuthor):
    _default_crypto_powerups = [SigningPower, EncryptingPower, DelegatingPower]

    def __init__(self, is_me=True, federated_only=False, network_middleware=None, *args, **kwargs):

        policy_agent = kwargs.pop("policy_agent", None)
        checksum_address = kwargs.pop("checksum_address", None)
        Character.__init__(self, is_me=is_me, federated_only=federated_only,
                           checksum_address=checksum_address, network_middleware=network_middleware, *args, **kwargs)

        if is_me and not federated_only:  # TODO: 289
            PolicyAuthor.__init__(self, policy_agent=policy_agent, checksum_address=checksum_address)

    @classmethod
    def from_config(cls, filepath=DEFAULT_INI_FILEPATH, overrides: dict = None) -> 'Alice':
        payload = parse_alice_config(filepath=filepath)
        if overrides is not None:
            payload.update(overrides)
        instance = cls(**payload)
        return instance

    def generate_kfrags(self, bob, label, m, n) -> List:
        """
        Generates re-encryption key frags ("KFrags") and returns them.

        These KFrags can be used by Ursula to re-encrypt a Capsule for Bob so
        that he can activate the Capsule.

        :param bob: Bob instance which will be able to decrypt messages re-encrypted with these kfrags.
        :param m: Minimum number of kfrags needed to activate a Capsule.
        :param n: Total number of kfrags to generate
        """

        bob_pubkey_enc = bob.public_keys(EncryptingPower)
        delegating_power = self._crypto_power.power_ups(DelegatingPower)
        return delegating_power.generate_kfrags(bob_pubkey_enc, self.stamp, label, m, n)

    def create_policy(self, bob: "Bob", label: bytes, m: int, n: int, federated=False):
        """
        Create a Policy to share uri with bob.
        Generates KFrags and attaches them.
        """
        public_key, kfrags = self.generate_kfrags(bob, label, m, n)

        payload = dict(label=label,
                       bob=bob,
                       kfrags=kfrags,
                       public_key=public_key,
                       m=m)

        if self.federated_only is True or federated is True:
            from nucypher.policy.models import FederatedPolicy
            # We can't sample; we can only use known nodes.
            known_nodes = self.shuffled_known_nodes()
            policy = FederatedPolicy(alice=self, ursulas=known_nodes, **payload)
        else:
            from nucypher.blockchain.eth.policies import BlockchainPolicy
            policy = BlockchainPolicy(author=self, **payload)

        return policy

    def grant(self, bob, uri, m=None, n=None, expiration=None, deposit=None, handpicked_ursulas=None):
        if not m:
            # TODO: get m from config  #176
            raise NotImplementedError
        if not n:
            # TODO: get n from config  #176
            raise NotImplementedError
        if not expiration:
            # TODO: check default duration in config  #176
            raise NotImplementedError
        if not deposit:
            default_deposit = None  # TODO: Check default deposit in config.  #176
            if not default_deposit:
                deposit = self.network_middleware.get_competitive_rate()
                if deposit == NotImplemented:
                    deposit = constants.NON_PAYMENT(b"0000000")
        if handpicked_ursulas is None:
            handpicked_ursulas = set()

        policy = self.create_policy(bob, uri, m, n)

        #
        # We'll find n Ursulas by default.  It's possible to "play the field" by trying different
        # deposit and expiration combinations on a limited number of Ursulas;
        # Users may decide to inject some market strategies here.
        #
        # TODO: 289

        # If we're federated only, we need to block to make sure we have enough nodes.
        if self.federated_only and len(self._known_nodes) < n:
            good_to_go = self.block_until_number_of_known_nodes_is(n, learn_on_this_thread=True)
            if not good_to_go:
                raise ValueError(
                    "To make a Policy in federated mode, you need to know about\
                     all the Ursulas you need (in this case, {}); there's no other way to\
                      know which nodes to use.  Either pass them here or when you make\
                       the Policy, or run the learning loop on a network with enough Ursulas.".format(self.n))

            if len(handpicked_ursulas) < n:
                number_of_ursulas_needed = n - len(handpicked_ursulas)
                new_ursulas = random.sample(list(self._known_nodes.values()), number_of_ursulas_needed)
                handpicked_ursulas.update(new_ursulas)

        policy.make_arrangements(network_middleware=self.network_middleware,
                                 deposit=deposit,
                                 expiration=expiration,
                                 handpicked_ursulas=handpicked_ursulas,
                                 )

        # REST call happens here, as does population of TreasureMap.
        policy.enact(network_middleware=self.network_middleware)
        return policy  # Now with TreasureMap affixed!


class Bob(Character):
    _dht_server_class = NucypherSeedOnlyDHTServer
    _default_crypto_powerups = [SigningPower, EncryptingPower]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        from nucypher.policy.models import WorkOrderHistory  # Need a bigger strategy to avoid circulars.
        self._saved_work_orders = WorkOrderHistory()

    @classmethod
    def from_config(cls, filepath=DEFAULT_INI_FILEPATH, overrides: dict = None) -> 'Bob':
        payload = parse_character_config(filepath=filepath)
        if overrides is not None:
            payload.update(overrides)
        instance = cls(**payload)
        return instance

    def peek_at_treasure_map(self, treasure_map=None, map_id=None):
        """
        Take a quick gander at the TreasureMap matching map_id to see which
        nodes are already kwown to us.

        Don't do any learning, pinging, or anything other than just seeing
        whether we know or don't know the nodes.

        Return two sets: nodes that are unknown to us, nodes that are known to us.
        """
        if not treasure_map:
            if map_id:
                treasure_map = self.treasure_maps[map_id]
            else:
                raise ValueError("You need to pass either treasure_map or map_id.")
        else:
            if map_id:
                raise ValueError("Don't pass both treasure_map and map_id - pick one or the other.")

        # The intersection of the map and our known nodes will be the known Ursulas...
        known_treasure_ursulas = treasure_map.destinations.keys() & self._known_nodes.keys()

        # while the difference will be the unknown Ursulas.
        unknown_treasure_ursulas = treasure_map.destinations.keys() - self._known_nodes.keys()

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
        if not treasure_map:
            if map_id:
                treasure_map = self.treasure_maps[map_id]
            else:
                raise ValueError("You need to pass either treasure_map or map_id.")
        else:
            if map_id:
                raise ValueError("Don't pass both treasure_map and map_id - pick one or the other.")

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

        return unknown_ursulas, known_ursulas

    def get_treasure_map(self, alice_verifying_key, label):
        _hrac, map_id = self.construct_hrac_and_map_id(verifying_key=alice_verifying_key, label=label)

        if not self._known_nodes and not self._learning_task.running:
            # Quick sanity check - if we don't know of *any* Ursulas, and we have no
            # plans to learn about any more, than this function will surely fail.
            raise self.NotEnoughUrsulas

        treasure_map = self.get_treasure_map_from_known_ursulas(self.network_middleware,
                                                                map_id)

        alice = Alice.from_public_keys({SigningPower: alice_verifying_key})
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

    def construct_policy_hrac(self, verifying_key, label):
        return keccak_digest(bytes(verifying_key) + self.stamp + label)

    def construct_hrac_and_map_id(self, verifying_key, label):
        hrac = self.construct_policy_hrac(verifying_key, label)
        map_id = keccak_digest(bytes(verifying_key) + hrac).hex()
        return hrac, map_id

    def get_treasure_map_from_known_ursulas(self, networky_stuff, map_id):
        """
        Iterate through swarm, asking for the TreasureMap.
        Return the first one who has it.
        TODO: What if a node gives a bunk TreasureMap?
        """
        for node in self._known_nodes.values():
            response = networky_stuff.get_treasure_map_from_node(node, map_id)

            if response.status_code == 200 and response.content:
                from nucypher.policy.models import TreasureMap
                treasure_map = TreasureMap.from_bytes(response.content)
                break
            else:
                continue  # TODO: Actually, handle error case here.
        else:
            # TODO: Work out what to do in this scenario - if Bob can't get the TreasureMap, he needs to rest on the learning mutex or something.
            assert False

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
            ursula = self._known_nodes[node_id]

            capsules_to_include = []
            for capsule in capsules:
                if not capsule in self._saved_work_orders[node_id]:
                    capsules_to_include.append(capsule)

            if capsules_to_include:
                work_order = WorkOrder.construct_by_bob(
                    arrangement_id, capsules_to_include, ursula, self)
                generated_work_orders[node_id] = work_order
                self._saved_work_orders[node_id][capsule] = work_order

            if num_ursulas is not None:
                if num_ursulas == len(generated_work_orders):
                    break

        return generated_work_orders

    def get_reencrypted_cfrags(self, work_order):
        cfrags = self.network_middleware.reencrypt(work_order)
        if not len(work_order) == len(cfrags):
            raise ValueError("Ursula gave back the wrong number of cfrags.  She's up to something.")
        for counter, capsule in enumerate(work_order.capsules):
            # TODO: Ursula is actually supposed to sign this.  See #141.
            # TODO: Maybe just update the work order here instead of setting it anew.
            work_orders_by_ursula = self._saved_work_orders[work_order.ursula.checksum_public_address]
            work_orders_by_ursula[capsule] = work_order
        return cfrags

    def get_ursula(self, ursula_id):
        return self._ursulas[ursula_id]

    def join_policy(self, label, alice_pubkey_sig, node_list=None):
        if node_list:
            self._node_ids_to_learn_about_immediately.update(node_list)
        treasure_map = self.get_treasure_map(alice_pubkey_sig, label)
        self.follow_treasure_map(treasure_map=treasure_map)

    def retrieve(self, message_kit, data_source, alice_verifying_key):

        message_kit.capsule.set_correctness_keys(
            delegating=data_source.policy_pubkey,
            receiving=self.public_keys(EncryptingPower),
            verifying=alice_verifying_key)

        hrac, map_id = self.construct_hrac_and_map_id(alice_verifying_key, data_source.label)
        self.follow_treasure_map(map_id=map_id, block=True)

        work_orders = self.generate_work_orders(map_id, message_kit.capsule)

        cleartexts = []

        for work_order in work_orders.values():
            cfrags = self.get_reencrypted_cfrags(work_order)
            message_kit.capsule.attach_cfrag(cfrags[0])

        delivered_cleartext = self.verify_from(data_source,
                                               message_kit,
                                               decrypt=True,
                                               delegator_signing_key=alice_verifying_key)

        cleartexts.append(delivered_cleartext)
        return cleartexts


class Ursula(Character, VerifiableNode, Miner):
    _internal_splitter = BytestringSplitter(Signature,
                                            VariableLengthBytestring,
                                            (UmbralPublicKey, PUBLIC_KEY_LENGTH),
                                            (UmbralPublicKey, PUBLIC_KEY_LENGTH),
                                            int(PUBLIC_ADDRESS_LENGTH),
                                            VariableLengthBytestring,  # Certificate
                                            InterfaceInfo,
                                            InterfaceInfo)
    _dht_server_class = NucypherDHTServer
    _alice_class = Alice

    # TODO: Maybe this wants to be a registry, so that, for example,
    # TLSHostingPower still can enjoy default status, but on a different class
    _default_crypto_powerups = [SigningPower, EncryptingPower]

    class NotFound(Exception):
        pass

    # TODO: 289
    def __init__(self,

                 # Ursula
                 rest_host,
                 rest_port,
                 certificate=None,
                 db_name=None,
                 is_me=True,
                 dht_host=None,
                 dht_port=None,
                 interface_signature=None,

                 # Blockchain
                 miner_agent=None,
                 checksum_address=None,

                 # Character
                 abort_on_learning_error=False,
                 federated_only=False,
                 always_be_learning=None,
                 crypto_power=None,
                 tls_curve=None,
                 tls_private_key=None,  # Obviously config here. 361
                 known_nodes=None,
                 **character_kwargs
                 ) -> None:

        if known_nodes is None:
            known_nodes = tuple()

        VerifiableNode.__init__(self, interface_signature=interface_signature)

        if dht_host:
            self.dht_interface = InterfaceInfo(host=dht_host, port=dht_port)
        else:
            self.dht_interface = constants.NO_INTERFACE.bool_value(False)
        self._work_orders = []

        Character.__init__(self, is_me=is_me,
                           checksum_address=checksum_address,
                           always_be_learning=always_be_learning,
                           federated_only=federated_only,
                           crypto_power=crypto_power,
                           abort_on_learning_error=abort_on_learning_error,
                           known_nodes=known_nodes,
                           **character_kwargs)

        if not federated_only:
            Miner.__init__(self,
                           is_me=is_me,
                           miner_agent=miner_agent,
                           checksum_address=checksum_address)

            blockchain_power = BlockchainPower(blockchain=self.blockchain, account=self.checksum_public_address)
            self._crypto_power.consume_power_up(blockchain_power)

        if is_me is True:
            # TODO: 340
            self._stored_treasure_maps = {}
            self.attach_dht_server()
            if not federated_only:
                self.substantiate_stamp()

        if not crypto_power or TLSHostingPower not in crypto_power._power_ups:  # TODO: Maybe we want _power_ups to be public after all?
            # We'll hook all the TLS stuff up unless the crypto_power was already passed.
            if is_me:

                rest_routes = ProxyRESTRoutes(
                    db_name=db_name,
                    network_middleware=self.network_middleware,
                    federated_only=self.federated_only,
                    dht_server=self.dht_server,
                    treasure_map_tracker=self.treasure_maps,
                    node_tracker=self._known_nodes,
                    node_bytes_caster=self.__bytes__,
                    work_order_tracker=self._work_orders,
                    node_recorder=self.remember_node,
                    stamp=self.stamp,
                    verifier=self.verify_from
                )

                rest_server = ProxyRESTServer(
                    rest_host=rest_host,
                    rest_port=rest_port,
                    routes=rest_routes,
                )
                self.rest_url = rest_server.rest_url
                self.datastore = rest_routes.datastore  # TODO: Maybe organize this better?

                tls_hosting_keypair = HostingKeypair(
                    common_name=self.checksum_public_address,
                    private_key=tls_private_key,
                    curve=tls_curve,
                    host=rest_host,
                    certificate=certificate)
                tls_hosting_power = TLSHostingPower(rest_server=rest_server,
                                                    keypair=tls_hosting_keypair)
            else:
                # Unless the caller passed a crypto power, we'll make our own TLSHostingPower for this stranger.
                rest_server = ProxyRESTServer(
                    rest_host=rest_host,
                    rest_port=rest_port,
                )
                if certificate:
                    tls_hosting_power = TLSHostingPower(rest_server=rest_server, certificate=certificate)
                else:
                    tls_hosting_keypair = HostingKeypair(
                        common_name=self.checksum_public_address,
                        curve=tls_curve,
                        host=rest_host)
                    tls_hosting_power = TLSHostingPower(rest_server=rest_server,
                                                        keypair=tls_hosting_keypair)
            self._crypto_power.consume_power_up(tls_hosting_power)  # Make this work for not me for certificate to work
        else:
            self.log.info("Not adhering rest_server; we'll use the one on crypto_power..")

    def rest_information(self):
        hosting_power = self._crypto_power.power_ups(TLSHostingPower)

        return (
            hosting_power.rest_server.rest_interface,
            hosting_power.keypair.certificate,
            hosting_power.keypair.pubkey
        )

    def get_deployer(self):
        deployer = self._crypto_power.power_ups(TLSHostingPower).get_deployer(rest_app=self.rest_app,
                                                                              port=self.rest_information()[0].port)
        return deployer

    def rest_server_certificate(self):
        return self.get_deployer().cert.to_cryptography()

    def __bytes__(self):

        interface_info = VariableLengthBytestring(self.rest_information()[0])

        if self.dht_interface:
            interface_info += VariableLengthBytestring(self.dht_interface)

        identity_evidence = VariableLengthBytestring(self._evidence_of_decentralized_identity)

        certificate = self.rest_server_certificate()
        cert_vbytes = VariableLengthBytestring(certificate.public_bytes(Encoding.PEM))

        as_bytes = bytes().join((bytes(self._interface_signature),
                                 bytes(identity_evidence),
                                 bytes(self.public_keys(SigningPower)),
                                 bytes(self.public_keys(EncryptingPower)),
                                 self.canonical_public_address,
                                 bytes(cert_vbytes),
                                 interface_info)
                                )
        return as_bytes

    #
    # Alternate Constructors
    #

    @classmethod
    def from_config(cls,
                    filepath: str = DEFAULT_INI_FILEPATH,
                    overrides: dict = None) -> 'Ursula':
        """
        Initialize Ursula from .ini configuration file.

        Keyword arguments passed will take precedence over values
        in the configuration file.
        """
        payload = parse_ursula_config(filepath=filepath)
        if overrides is not None:
            payload.update(overrides)
        return cls(**payload)

    @classmethod
    def from_rest_url(cls,
                      network_middleware: RestMiddleware,
                      host: str,
                      port: int,
                      federated_only: bool = False) -> 'Ursula':

        response = network_middleware.node_information(host, port)
        if not response.status_code == 200:
            raise RuntimeError("Got a bad response: {}".format(response))

        stranger_ursula_from_public_keys = cls.from_bytes(response.content, federated_only=federated_only)
        return stranger_ursula_from_public_keys

    @classmethod
    def from_bytes(cls, ursula_as_bytes: bytes,
                   federated_only: bool = False) -> 'Ursula':

        (signature,
         identity_evidence,
         verifying_key,
         encrypting_key,
         public_address,
         certificate_vbytes,
         rest_info,
         dht_info) = cls._internal_splitter(ursula_as_bytes)
        certificate = load_pem_x509_certificate(certificate_vbytes.message_as_bytes,
                                                default_backend())
        stranger_ursula_from_public_keys = cls.from_public_keys(
            {SigningPower: verifying_key, EncryptingPower: encrypting_key},
            interface_signature=signature,
            checksum_address=to_checksum_address(public_address),
            rest_host=rest_info.host,
            rest_port=rest_info.port,
            certificate=certificate,
            dht_host=dht_info.host,
            dht_port=dht_info.port,
            federated_only=federated_only  # TODO: 289
        )
        return stranger_ursula_from_public_keys

    @classmethod
    def batch_from_bytes(cls,
                         ursulas_as_bytes: Iterable[bytes],
                         federated_only: bool = False) -> List['Ursula']:

        # TODO: Make a better splitter for this.  This is a workaround until bytestringSplitter #8 is closed.

        stranger_ursulas = []

        ursulas_attrs = cls._internal_splitter.repeat(ursulas_as_bytes)
        for (signature,
             identity_evidence,
             verifying_key,
             encrypting_key,
             public_address,
             certificate_vbytes,
             rest_info,
             dht_info) in ursulas_attrs:
            certificate = load_pem_x509_certificate(certificate_vbytes.message_as_bytes,
                                                    default_backend())
            stranger_ursula_from_public_keys = cls.from_public_keys(
                {SigningPower: verifying_key,
                 EncryptingPower: encrypting_key,
                 },
                interface_signature=signature,
                checksum_address=to_checksum_address(public_address),
                certificate=certificate,
                rest_host=rest_info.host,
                rest_port=rest_info.port,
                dht_host=dht_info.host,
                dht_port=dht_info.port,
                federated_only=federated_only  # TODO: 289
            )
            stranger_ursulas.append(stranger_ursula_from_public_keys)

        return stranger_ursulas

    #
    # Properties
    #

    @property
    def rest_app(self):
        rest_app_on_server = self._crypto_power.power_ups(TLSHostingPower).rest_server.rest_app

        if not rest_app_on_server:
            m = "This Ursula doesn't have a REST app attached. If you want one, init with is_me and attach_server."
            raise AttributeError(m)
        else:
            return rest_app_on_server

    def interface_info_with_metadata(self):
        # TODO: Do we ever actually use this without using the rest of the serialized Ursula?  337
        return constants.BYTESTRING_IS_URSULA_IFACE_INFO + bytes(self)

    #
    # Utilities
    #

    def attach_dht_server(self,
                          ksize: int = 20,
                          alpha: int = 3,
                          node_id=None,
                          storage=None,
                          *args, **kwargs) -> None:

        node_id = node_id or bytes(
            self.canonical_public_address)  # Ursula can still "mine" wallets until she gets a DHT ID she wants.  Does that matter?  #136
        # TODO What do we actually want the node ID to be?  Do we want to verify it somehow?  136
        super().attach_dht_server(ksize=ksize, id=digest(node_id), alpha=alpha, storage=storage)

    def dht_listen(self):
        if self.dht_interface is constants.NO_INTERFACE:
            raise TypeError("This node does not have a DHT interface configured.")
        return self.dht_server.listen(self.dht_interface.port,
                                      self.dht_interface.host)

    def publish_dht_information(self):
        # TODO: Simplify or wholesale deprecate this.  337
        if not self.dht_interface:
            raise RuntimeError("Must listen before publishing interface information.")

        ursula_id = self.canonical_public_address
        interface_value = constants.BYTESTRING_IS_URSULA_IFACE_INFO + bytes(self)
        setter = self.dht_server.set(key=ursula_id, value=interface_value)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(setter)
        return interface_value

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

    @only_me
    def stake(self,
              sample_rate: int = 10,
              refresh_rate: int = 60,
              confirm_now=True,
              resume: bool = False,
              expiration: maya.MayaDT = None,
              lock_periods: int = None,
              *args, **kwargs) -> None:

        """High-level staking daemon loop"""

        if lock_periods and expiration:
            raise ValueError("Pass the number of lock periods or an expiration MayaDT; not both.")
        if expiration:
            lock_periods = datetime_to_period(expiration)

        if resume is False:
            _staking_receipts = super().initialize_stake(expiration=expiration,
                                                         lock_periods=lock_periods,
                                                         *args, **kwargs)

        # TODO: Check if this period has already been confirmed
        # TODO: Check if there is an active stake in the current period: Resume staking daemon
        # TODO: Validation and Sanity checks

        if confirm_now:
            self.confirm_activity()

        # record start time and periods
        start_time = maya.now()
        uptime_period = self.miner_agent.get_current_period()
        terminal_period = uptime_period + lock_periods
        current_period = uptime_period

        #
        # Daemon
        #

        try:
            while True:

                # calculate timedeltas
                now = maya.now()
                initialization_delta = now - start_time

                # check if iteration re-samples
                sample_stale = initialization_delta.seconds > (refresh_rate - 1)
                if sample_stale:

                    period = self.miner_agent.get_current_period()
                    # check for stale sample data
                    if current_period != period:

                        # check for stake expiration
                        stake_expired = current_period >= terminal_period
                        if stake_expired:
                            break

                        self.confirm_activity()
                        current_period = period
                # wait before resampling
                time.sleep(sample_rate)
                continue

        finally:

            # TODO: Cleanup #

            pass
