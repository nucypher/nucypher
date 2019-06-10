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
from typing import Dict, ClassVar, Set
from typing import Optional
from typing import Union, List

from constant_sorrow import default_constant_splitter
from constant_sorrow.constants import (
    DO_NOT_SIGN,
    NO_BLOCKCHAIN_CONNECTION,
    NO_CONTROL_PROTOCOL,
    NO_DECRYPTION_PERFORMED,
    NO_NICKNAME,
    NO_SIGNING_POWER,
    SIGNATURE_TO_FOLLOW,
    SIGNATURE_IS_ON_CIPHERTEXT,
    STRANGER,
    FEDERATED_ONLY
)
from cryptography.exceptions import InvalidSignature
from eth_keys import KeyAPI as EthKeyAPI
from eth_utils import to_checksum_address, to_canonical_address
from umbral.keys import UmbralPublicKey
from umbral.signing import Signature

from nucypher.blockchain.eth.agents import StakingEscrow
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.config.node import NodeConfiguration
from nucypher.crypto.api import encrypt_and_sign
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import (
    CryptoPower,
    SigningPower,
    DecryptingPower,
    NoSigningPower,
    CryptoPowerUp,
    DelegatingPower
)
from nucypher.crypto.signing import signature_splitter, StrangerStamp, SignatureStamp
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nicknames import nickname_from_seed
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
    from nucypher.crypto.signing import InvalidSignature  # TODO: Restore nucypher Signing exceptions

    def __init__(self,
                 domains: Set = None,
                 is_me: bool = True,
                 federated_only: bool = False,
                 blockchain: Blockchain = None,
                 checksum_address: str = NO_BLOCKCHAIN_CONNECTION.bool_value(False),
                 network_middleware: RestMiddleware = None,
                 keyring_dir: str = None,
                 crypto_power: CryptoPower = None,
                 crypto_power_ups: List[CryptoPowerUp] = None,
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
        self.federated_only = federated_only  # type: bool

        #
        # Powers
        #
        if crypto_power and crypto_power_ups:
            raise ValueError("Pass crypto_power or crypto_power_ups (or neither), but not both.")
        crypto_power_ups = crypto_power_ups or list()  # type: list

        if crypto_power:
            self._crypto_power = crypto_power  # type: CryptoPower
        elif crypto_power_ups:
            self._crypto_power = CryptoPower(power_ups=crypto_power_ups)
        else:
            self._crypto_power = CryptoPower(power_ups=self._default_crypto_powerups)

        self._checksum_address = checksum_address

        # Fleet and Blockchain Connection (Everyone)
        if not domains:
            domains = (NodeConfiguration.DEFAULT_DOMAIN, )

        # Needed for on-chain verification
        if not self.federated_only:
            self.blockchain = blockchain or Blockchain.connect()
            self.staking_agent = StakingEscrow(blockchain=blockchain)
        else:
            self.blockchain = FEDERATED_ONLY
            self.staking_agent = FEDERATED_ONLY

        #
        # Self-Character
        #
        if is_me is True:

            self.keyring_dir = keyring_dir  # type: str
            self.treasure_maps = {}  # type: dict
            self.network_middleware = network_middleware or RestMiddleware()

            #
            # Signing Power
            #
            try:
                signing_power = self._crypto_power.power_ups(SigningPower)  # type: SigningPower
                self._stamp = signing_power.get_signature_stamp()  # type: SignatureStamp
            except NoSigningPower:
                self._stamp = NO_SIGNING_POWER

            #
            # Learner
            #
            Learner.__init__(self,
                             domains=domains,
                             network_middleware=network_middleware,
                             *args, **kwargs)

        #
        # Stranger-Character
        #
        else:  # Feel like a stranger
            if network_middleware is not None:
                raise TypeError("Network middleware cannot be attached to a Stranger-Character.")
            self._stamp = StrangerStamp(self.public_keys(SigningPower))
            self.keyring_dir = STRANGER
            self.network_middleware = STRANGER

        #
        # Decentralized
        #
        if not federated_only:
            if not checksum_address:
                raise ValueError("No checksum_address provided while running in a non-federated mode.")
            else:
                self._checksum_address = checksum_address  # TODO: Check that this matches BlockchainPower
        #
        # Federated
        #
        elif federated_only:
            try:
                self._set_checksum_address()  # type: str
            except NoSigningPower:
                self._checksum_address = NO_BLOCKCHAIN_CONNECTION
            if checksum_address:
                # We'll take a checksum address, as long as it matches their singing key
                if not checksum_address == self.checksum_address:
                    error = "Federated-only Characters derive their address from their Signing key; got {} instead."
                    raise self.SuspiciousActivity(error.format(checksum_address))

        #
        # Nicknames
        #
        try:
            self.nickname, self.nickname_metadata = nickname_from_seed(self.checksum_address)
        except SigningPower.not_found_error:
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
        except NoSigningPower:  # TODO: ....yeah?
            r = r.format(self.__class__.__name__, self.nickname)
        return r

    @property
    def name(self):
        return self.__class__.__name__

    @property
    def rest_interface(self):
        return self.rest_server.rest_url()

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
        return to_canonical_address(self.checksum_address)

    @canonical_public_address.setter
    def canonical_public_address(self, address_bytes):
        self._checksum_address = to_checksum_address(address_bytes)

    @property
    def checksum_address(self):
        if self._checksum_address is NO_BLOCKCHAIN_CONNECTION:
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
                         federated_only: bool = True,
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

        # TODO: Need to be federated only until we figure out the best way to get the checksum_address in here.
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

            crypto_power.consume_power_up(power_up(pubkey=umbral_key))

        return cls(is_me=False, federated_only=federated_only, crypto_power=crypto_power, *args, **kwargs)

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
