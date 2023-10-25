from typing import ClassVar, Dict, List, Optional, Union

from constant_sorrow.constants import NO_NICKNAME, NO_SIGNING_POWER, STRANGER
from eth_utils import to_canonical_address
from nucypher_core.umbral import PublicKey

from nucypher.acumen.nicknames import Nickname
from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.domains import TACoDomain
from nucypher.blockchain.eth.registry import (
    ContractRegistry,
)
from nucypher.blockchain.eth.signers.base import Signer
from nucypher.config.constants import TEMPORARY_DOMAIN_NAME
from nucypher.crypto.keystore import Keystore
from nucypher.crypto.powers import (
    CryptoPower,
    CryptoPowerUp,
    DecryptingPower,
    NoSigningPower,
    SigningPower,
)
from nucypher.crypto.signing import SignatureStamp, StrangerStamp
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nodes import Learner


class Character(Learner):
    """A base-class for any character in our cryptography protocol narrative."""

    _display_name_template = "({})⇀{}↽ ({})"  # Used in __repr__ and in cls.from_bytes
    _default_crypto_powerups = None
    _stamp = None

    def __init__(
        self,
        domain: Union[str, TACoDomain],
        eth_endpoint: str = None,
        polygon_endpoint: str = None,
        known_node_class: object = None,
        is_me: bool = True,
        checksum_address: str = None,
        network_middleware: RestMiddleware = None,
        keystore: Keystore = None,
        crypto_power: CryptoPower = None,
        crypto_power_ups: List[CryptoPowerUp] = None,
        signer: Signer = None,
        registry: ContractRegistry = None,
        include_self_in_the_state: bool = False,
        *args,
        **kwargs,
    ):

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
        self.domain = domains.get_domain(str(domain))

        #
        # Keys & Powers
        #

        if keystore:
            crypto_power_ups = list()
            for power_up in self._default_crypto_powerups:
                power = keystore.derive_crypto_power(power_class=power_up)
                crypto_power_ups.append(power)
        self.keystore = keystore

        if crypto_power and crypto_power_ups:
            raise ValueError("Pass crypto_power or crypto_power_ups (or neither), but not both.")
        crypto_power_ups = crypto_power_ups or list()  # type: list

        if crypto_power:
            self._crypto_power = crypto_power  # type: CryptoPower
        elif crypto_power_ups:
            self._crypto_power = CryptoPower(power_ups=crypto_power_ups)
        else:
            self._crypto_power = CryptoPower(power_ups=self._default_crypto_powerups)

        #
        # Local
        #

        if is_me:

            # Signing Power
            self.signer = signer
            try:
                signing_power: SigningPower = self._crypto_power.power_ups(SigningPower)
                self._stamp: SignatureStamp = signing_power.get_signature_stamp()
            except NoSigningPower:
                self._stamp = NO_SIGNING_POWER

            self.eth_endpoint = eth_endpoint
            self.polygon_endpoint = polygon_endpoint

            self.registry = registry or ContractRegistry.from_latest_publication(domain)

            # REST
            self.network_middleware = network_middleware or RestMiddleware(
                registry=self.registry, eth_endpoint=eth_endpoint
            )

            # Learner
            Learner.__init__(
                self,
                domain=self.domain,
                network_middleware=self.network_middleware,
                node_class=known_node_class,
                include_self_in_the_state=include_self_in_the_state,
                *args,
                **kwargs,
            )

            self.checksum_address = checksum_address

        #
        # Peer
        #

        else:
            if network_middleware is not None:
                raise TypeError("Network middleware cannot be attached to a Stranger-Character.")

            if registry is not None:
                raise TypeError("Registry cannot be attached to stranger-Characters.")

            verifying_key = self.public_keys(SigningPower)
            self._stamp = StrangerStamp(verifying_key)
            self.keystore_dir = STRANGER
            self.network_middleware = STRANGER
            self.checksum_address = checksum_address

        self.__setup_nickname(is_me=is_me)

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

    def __setup_nickname(self, is_me: bool):
        if not self.checksum_address and not is_me:
            # Sometimes we don't care about the nickname.  For example, if Alice is granting to Bob, she usually
            # doesn't know or care about his wallet.  Maybe this needs to change?
            # Currently, if this is a stranger and there's no blockchain connection, we assign NO_NICKNAME:
            self.nickname = NO_NICKNAME
        else:
            if not self.checksum_address:
                self.nickname = NO_NICKNAME
            else:
                # This can call _set_checksum_address.
                self.nickname = Nickname.from_seed(self.checksum_address)

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
    def canonical_address(self):
        # TODO: This is wasteful.  #1995
        return to_canonical_address(str(self.checksum_address))

    @classmethod
    def from_public_keys(cls,
                         powers_and_material: Dict = None,
                         verifying_key: Optional[PublicKey] = None,
                         encrypting_key: Optional[PublicKey] = None,
                         *args, **kwargs) -> 'Character':
        """
        Sometimes we discover a Character and, at the same moment,
        learn the public parts of more of their powers. Here, we take a Dict
        (powers_and_material) in the format {CryptoPowerUp class: material},
        where material can be bytes or umbral.PublicKey.

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
                umbral_key = PublicKey.from_compressed_bytes(public_key)
            except TypeError:
                umbral_key = public_key

            crypto_power.consume_power_up(power_up(public_key=umbral_key))

        return cls(
            is_me=False,
            domain=TEMPORARY_DOMAIN_NAME,
            crypto_power=crypto_power,
            *args,
            **kwargs,
        )

    def public_keys(self, power_up_class: ClassVar):
        """
        Pass a power_up_class, get the public material for this Character which corresponds to that
        class - whatever type of object that may be.

        If the Character doesn't have the power corresponding to that class, raises the
        appropriate PowerUpError (ie, NoSigningPower or NoDecryptingPower).
        """
        power_up = self._crypto_power.power_ups(power_up_class)
        return power_up.public_key()

    def disenchant(self):
        self.log.debug(f"Disenchanting {self}")
        Learner.stop_learning_loop(self)
