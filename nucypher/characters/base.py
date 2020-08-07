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
from contextlib import suppress

from constant_sorrow import default_constant_splitter
from constant_sorrow.constants import (DO_NOT_SIGN, NO_BLOCKCHAIN_CONNECTION, NO_CONTROL_PROTOCOL,
                                       NO_DECRYPTION_PERFORMED, NO_NICKNAME, NO_SIGNING_POWER,
                                       SIGNATURE_IS_ON_CIPHERTEXT, SIGNATURE_TO_FOLLOW, STRANGER)
from cryptography.exceptions import InvalidSignature
from eth_keys import KeyAPI as EthKeyAPI
from eth_utils import to_canonical_address, to_checksum_address
from typing import ClassVar, Dict, List, Optional, Set, Union

from nucypher.acumen.nicknames import nickname_from_seed
from umbral.keys import UmbralPublicKey
from umbral.signing import Signature

from nucypher.blockchain.eth.registry import BaseContractRegistry, InMemoryContractRegistry
from nucypher.blockchain.eth.signers import Signer
from nucypher.characters.control.controllers import CLIController, JSONRPCController
from nucypher.config.keyring import NucypherKeyring
from nucypher.config.node import CharacterConfiguration
from nucypher.crypto.api import encrypt_and_sign
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import (
    CryptoPower,
    SigningPower,
    DecryptingPower,
    NoSigningPower,
    CryptoPowerUp,
    DelegatingPower, TransactingPower, NoTransactingPower
)
from nucypher.crypto.signing import signature_splitter, StrangerStamp, SignatureStamp
from nucypher.crypto.powers import (CryptoPower, CryptoPowerUp, DecryptingPower, DelegatingPower, NoSigningPower,
                                    SigningPower)
from nucypher.crypto.signing import SignatureStamp, StrangerStamp, signature_splitter
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nodes import Learner


class Character(Learner):
    """
    A base-class for any character in our cryptography protocol narrative.
    """

    _display_name_template = "({})⇀{}↽ ({})"  # Used in __repr__ and in cls.from_bytes
    _default_crypto_powerups = None
    _stamp = None
    _crashed = False

    from nucypher.network.protocols import SuspiciousActivity  # Ship this exception with every Character.

    def __init__(self,
                 domains: Set = None,
                 known_node_class: object = None,
                 is_me: bool = True,
                 federated_only: bool = False,
                 checksum_address: str = NO_BLOCKCHAIN_CONNECTION.bool_value(False),
                 network_middleware: RestMiddleware = None,
                 keyring: NucypherKeyring = None,
                 keyring_root: str = None,
                 crypto_power: CryptoPower = None,
                 crypto_power_ups: List[CryptoPowerUp] = None,
                 provider_uri: str = None,
                 signer: Signer = None,
                 registry: BaseContractRegistry = None,
                 *args, **kwargs
                 ) -> None:

        """

        A participant in the cryptological drama (a screenplay, if you like) of NuCypher.

        Characters can represent users, nodes, wallets, offline devices, or other objects of varying levels of abstraction.

        The Named Characters use this class as a Base, and achieve their individuality from additional methods and PowerUps.


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

        #
        # Operating Mode
        if hasattr(self, '_interface_class'):  # TODO: have argument about meaning of 'lawful'
            #                                         and whether maybe only Lawful characters have an interface
            self.interface = self._interface_class(character=self)
        if is_me:
            if not known_node_class:
                # Once in a while, in tests or demos, we init a plain Character who doesn't already know about its node class.
                from nucypher.characters.lawful import Ursula
                known_node_class = Ursula
            # If we're federated only, we assume that all other nodes in our domain are as well.
            known_node_class.set_federated_mode(federated_only)
        else:
            # What an awful hack.  The last convulsions of #466.
            # TODO: Anything else.
            with suppress(AttributeError):
                federated_only = known_node_class._federated_only_instances

        if federated_only:
            if registry or provider_uri:
                raise ValueError(f"Cannot init federated-only character with {registry or provider_uri}.")
        self.federated_only: bool = federated_only

        #
        # Powers
        #

        # Derive powers from keyring
        if keyring_root and keyring:
            if keyring_root != keyring.keyring_root:
                raise ValueError("Inconsistent keyring root directory path")
        if keyring:
            keyring_root, checksum_address = keyring.keyring_root, keyring.checksum_address
            crypto_power_ups = list()
            for power_up in self._default_crypto_powerups:
                power = keyring.derive_crypto_power(power_class=power_up)
                crypto_power_ups.append(power)
        self.keyring_root = keyring_root
        self.keyring = keyring

        if crypto_power and crypto_power_ups:
            raise ValueError("Pass crypto_power or crypto_power_ups (or neither), but not both.")
        crypto_power_ups = crypto_power_ups or list()  # type: list

        if crypto_power:
            self._crypto_power = crypto_power  # type: CryptoPower
        elif crypto_power_ups:
            self._crypto_power = CryptoPower(power_ups=crypto_power_ups)
        else:
            self._crypto_power = CryptoPower(power_ups=self._default_crypto_powerups)

        # Fleet and Blockchain Connection (Everyone)
        if not domains:
            domains = {CharacterConfiguration.DEFAULT_DOMAIN}

        #
        # Self-Character
        #

        if is_me:
            self.treasure_maps = {}  # type: dict

            #
            # Signing Power
            #
            self.signer = signer
            try:
                signing_power = self._crypto_power.power_ups(SigningPower)  # type: SigningPower
                self._stamp = signing_power.get_signature_stamp()  # type: SignatureStamp
            except NoSigningPower:
                self._stamp = NO_SIGNING_POWER

            #
            # Blockchain
            #
            self.provider_uri = provider_uri
            if not self.federated_only:
                self.registry = registry or InMemoryContractRegistry.from_latest_publication(
                    network=list(domains)[0])  # TODO: #1580
            else:
                self.registry = NO_BLOCKCHAIN_CONNECTION.bool_value(False)

            # REST
            self.network_middleware = network_middleware or RestMiddleware(registry=self.registry)

            #
            # Learner
            #
            Learner.__init__(self,
                             domains=domains,
                             network_middleware=self.network_middleware,
                             node_class=known_node_class,
                             *args, **kwargs)

        #
        # Stranger-Char acter
        #

        else:  # Feel like a stranger
            if network_middleware is not None:
                raise TypeError("Network middleware cannot be attached to a Stranger-Character.")

            if registry is not None:
                raise TypeError("Registry cannot be attached to stranger-Characters.")

            verifying_key = self.public_keys(SigningPower)
            self._stamp = StrangerStamp(verifying_key)
            self.keyring_root = STRANGER
            self.network_middleware = STRANGER

        # TODO: Figure out when to do this.
        try:
            _transacting_power = self._crypto_power.power_ups(TransactingPower)
        except NoTransactingPower:
            self._checksum_address = checksum_address
            if checksum_address is None:
                assert True  # Hmm, so this Character has no checksum address at all.  Is that what we want?
        else:
            self._set_checksum_address(checksum_address)

        #
        # Nicknames
        #
        if self._checksum_address is NO_BLOCKCHAIN_CONNECTION and not self.federated_only and not is_me:
            # Sometimes we don't care about the nickname.  For example, if Alice is granting to Bob, she usually
            # doesn't know or care about his wallet.  Maybe this needs to change?
            # Currently, if this is a stranger and there's no blockchain connection, we assign NO_NICKNAME:
            self.nickname = self.nickname_metadata = NO_NICKNAME
        else:
            try:
                # TODO: It's possible that this is NO_BLOCKCHAIN_CONNECTION.
                if self.checksum_address is NO_BLOCKCHAIN_CONNECTION:
                    self.nickname = self.nickname_metadata = NO_NICKNAME
                else:
                    # This can call _set_checksum_address.
                    self.nickname, self.nickname_metadata = nickname_from_seed(self.checksum_address)
            except SigningPower.not_found_error:  # TODO: Handle NO_BLOCKCHAIN_CONNECTION more coherently - #1547
                if self.federated_only:
                    self.nickname = self.nickname_metadata = NO_NICKNAME
                else:
                    raise

        #
        # Fleet state
        #
        if is_me is True:
            self.known_nodes.record_fleet_state()

        #
        # Character Control
        #
        self.controller = NO_CONTROL_PROTOCOL

    def __eq__(self, other) -> bool:
        try:
            other_stamp = other.stamp
        except (AttributeError, NoSigningPower):
            return False
        return bytes(self.stamp) == bytes(other_stamp)

    def __hash__(self):
        return int.from_bytes(bytes(self.stamp), byteorder="big")

    def __repr__(self):
        r = self._display_name_template
        try:
            r = r.format(self.__class__.__name__, self.nickname, self.checksum_address)
        except (NoSigningPower, TypeError):  # TODO: ....yeah?  We can probably do better for a repr here.
            r = f"({self.__class__.__name__})⇀{self.nickname}↽"
        return r

    @property
    def name(self):
        return self.__class__.__name__

    @property
    def stamp(self):
        if self._stamp is NO_SIGNING_POWER:
            raise NoSigningPower
        elif not self._stamp:
            raise AttributeError("SignatureStamp has not been set up yet.")
        else:
            return self._stamp

    @property
    def canonical_public_address(self):
        # TODO: This is wasteful.  #1995
        return to_canonical_address(self._checksum_address)

    @canonical_public_address.setter
    def canonical_public_address(self, address_bytes):
        self._checksum_address = to_checksum_address(address_bytes)

    @property
    def checksum_address(self):
        if not self._checksum_address:
            self._set_checksum_address()
        return self._checksum_address

    @classmethod
    def from_config(cls, config, **overrides) -> 'Character':
        return config.produce(**overrides)

    @classmethod
    def from_public_keys(cls,
                         powers_and_material: Dict = None,
                         verifying_key: Union[bytes, UmbralPublicKey] = None,
                         encrypting_key: Union[bytes, UmbralPublicKey] = None,
                         *args, **kwargs) -> 'Character':
        """
        Sometimes we discover a Character and, at the same moment,
        learn the public parts of more of their powers. Here, we take a Dict
        (powers_and_material) in the format {CryptoPowerUp class: material},
        where material can be bytes or UmbralPublicKey.

        Each item in the collection will have the CryptoPowerUp instantiated
        with the given material, and the resulting CryptoPowerUp instance
        consumed by the Character.

        Alternatively, you can pass directly a verifying public key
        (for SigningPower) and/or an encrypting public key (for DecryptionPower).
        """
        crypto_power = CryptoPower()

        if powers_and_material is None:
            powers_and_material = dict()

        if verifying_key:
            powers_and_material[SigningPower] = verifying_key
        if encrypting_key:
            powers_and_material[DecryptingPower] = encrypting_key

        for power_up, public_key in powers_and_material.items():
            try:
                umbral_key = UmbralPublicKey.from_bytes(public_key)
            except TypeError:
                umbral_key = public_key

            crypto_power.consume_power_up(power_up(public_key=umbral_key))

        return cls(is_me=False, crypto_power=crypto_power, *args, **kwargs)

    def store_metadata(self, filepath: str) -> str:
        """
        Save this node to the disk.
        :param filepath: Output filepath to save node metadata.
        :return: Output filepath
        """

        return self.node_storage.store_node_metadata(node=self, filepath=filepath)

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
        signer = self.stamp if sign else DO_NOT_SIGN

        message_kit, signature = encrypt_and_sign(recipient_pubkey_enc=recipient.public_keys(DecryptingPower),
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
                    label=None,
                    ) -> bytes:
        """
        Inverse of encrypt_for.

        :param stranger: A Character instance representing
            the actor whom the sender claims to be.  We check the public key
            owned by this Character instance to verify.
        :param message_kit: the message to be (perhaps decrypted and) verified.
        :param signature: The signature to check.
        :param decrypt: Whether or not to decrypt the messages.
        :param label: A label used for decrypting messages encrypted under its associated policy encrypting key

        :return: Whether or not the signature is valid, the decrypted plaintext or NO_DECRYPTION_PERFORMED
        """

        #
        # Optional Sanity Check
        #

        # In the spirit of duck-typing, we want to accept a message kit object, or bytes
        # If the higher-order object MessageKit is passed, we can perform an additional
        # eager sanity check before performing decryption.

        with contextlib.suppress(AttributeError):
            sender_verifying_key = stranger.stamp.as_umbral_pubkey()
            if message_kit.sender_verifying_key:
                if not message_kit.sender_verifying_key == sender_verifying_key:
                    raise ValueError("This MessageKit doesn't appear to have come from {}".format(stranger))

        #
        # Decrypt
        #

        signature_from_kit = None
        if decrypt:

            # We are decrypting the message; let's do that first and see what the sig header says.
            cleartext_with_sig_header = self.decrypt(message_kit=message_kit, label=label)
            sig_header, cleartext = default_constant_splitter(cleartext_with_sig_header, return_remainder=True)

            if sig_header == SIGNATURE_IS_ON_CIPHERTEXT:
                # The ciphertext is what is signed - note that for later.
                message = message_kit.ciphertext
                if not signature:
                    raise ValueError("Can't check a signature on the ciphertext if don't provide one.")

            elif sig_header == SIGNATURE_TO_FOLLOW:
                # The signature follows in this cleartext - split it off.
                signature_from_kit, cleartext = signature_splitter(cleartext, return_remainder=True)
                message = cleartext

        else:
            # Not decrypting - the message is the object passed in as a message kit.  Cast it.
            message = bytes(message_kit)
            cleartext = NO_DECRYPTION_PERFORMED

        #
        # Verify Signature
        #

        if signature and signature_from_kit:
            if signature != signature_from_kit:
                raise ValueError(
                    "The MessageKit has a Signature, but it's not the same one you provided.  Something's up.")

        signature_to_use = signature or signature_from_kit
        if signature_to_use:
            is_valid = signature_to_use.verify(message, sender_verifying_key)  # FIXME: Message is undefined here
            if not is_valid:
                raise InvalidSignature("Signature for message isn't valid: {}".format(signature_to_use))
        else:
            raise InvalidSignature("No signature provided -- signature presumed invalid.")

        return cleartext

    def decrypt(self,
                message_kit: UmbralMessageKit,
                label: Optional[bytes] = None) -> bytes:
        if label and DelegatingPower in self._default_crypto_powerups:
            delegating_power = self._crypto_power.power_ups(DelegatingPower)
            decrypting_power = delegating_power.get_decrypting_power_from_label(label)
        else:
            decrypting_power = self._crypto_power.power_ups(DecryptingPower)
        return decrypting_power.decrypt(message_kit)

    def sign(self, message):
        return self._crypto_power.power_ups(SigningPower).sign(message)

    def public_keys(self, power_up_class: ClassVar):
        """
        Pass a power_up_class, get the public material for this Character which corresponds to that
        class - whatever type of object that may be.

        If the Character doesn't have the power corresponding to that class, raises the
        appropriate PowerUpError (ie, NoSigningPower or NoDecryptingPower).
        """
        power_up = self._crypto_power.power_ups(power_up_class)
        return power_up.public_key()

    def _set_checksum_address(self, checksum_address=None):

        if checksum_address is not None:

            #
            # Decentralized
            #
            if not self.federated_only:
                # TODO: And why not return here then?
                self._checksum_address = checksum_address  # TODO: Check that this matches TransactingPower

            #
            # Federated
            #
            elif self.federated_only:  # TODO: What are we doing here?
                try:
                    self._set_checksum_address()  # type: str
                except NoSigningPower:
                    self._checksum_address = NO_BLOCKCHAIN_CONNECTION
                if checksum_address:
                    # We'll take a checksum address, as long as it matches their singing key
                    if not checksum_address == self.checksum_address:
                        error = "Federated-only Characters derive their address from their Signing key; got {} instead."
                        raise self.SuspiciousActivity(error.format(checksum_address))

        if self.federated_only:
            verifying_key = self.public_keys(SigningPower)
            uncompressed_bytes = verifying_key.to_bytes(is_compressed=False)
            without_prefix = uncompressed_bytes[1:]
            verifying_key_as_eth_key = EthKeyAPI.PublicKey(without_prefix)
            public_address = verifying_key_as_eth_key.to_checksum_address()
        else:
            try:
                # TODO: Some circular logic here if we haven't set the canonical address.
                public_address = to_checksum_address(self.canonical_public_address)
            except TypeError:
                public_address = NO_BLOCKCHAIN_CONNECTION
                # raise TypeError("You can't use a decentralized character without a _checksum_address.")
            except NotImplementedError:
                raise TypeError(
                    "You can't use a plain Character in federated mode - you need to implement ether_address.")  # TODO: update comment

        self._checksum_address = public_address

    def make_rpc_controller(self, crash_on_error: bool = False):
        app_name = bytes(self.stamp).hex()[:6]
        controller = JSONRPCController(app_name=app_name,
                                       crash_on_error=crash_on_error,
                                       interface=self.interface)

        self.controller = controller
        return controller

    def make_cli_controller(self, crash_on_error: bool = False):
        app_name = bytes(self.stamp).hex()[:6]
        controller = CLIController(app_name=app_name,
                                   crash_on_error=crash_on_error,
                                   interface=self.interface)

        self.controller = controller
        return controller
