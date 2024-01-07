from typing import ClassVar, Dict, List, Optional
from typing import Union

from constant_sorrow.constants import NO_SIGNING_POWER, STRANGER
from nucypher_core.umbral import PublicKey

from nucypher.acumen.nicknames import Nickname
from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.domains import TACoDomain
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.blockchain.eth.wallets import Wallet
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
        is_peer: bool = False,
        eth_endpoint: str = None,
        polygon_endpoint: str = None,
        wallet: Wallet = None,
        registry: ContractRegistry = None,
        keystore: Keystore = None,
        network_middleware: RestMiddleware = None,
        crypto_power: CryptoPower = None,
        crypto_power_ups: List[CryptoPowerUp] = None,
        *args, **kwargs
    ):
        """
        A participant in the cryptological drama (a screenplay, if you like) of NuCypher.
        Characters can represent users, nodes, wallets, offline devices, or other objects of varying levels of abstraction.
        The Named Characters use this class as a Base, and achieve their individuality from additional methods and PowerUps.
        """
        self.domain = domains.get_domain(str(domain))

        crypto_power_ups = crypto_power_ups or list()
        if keystore:
            for power_up in self._default_crypto_powerups:
                power = keystore.derive_crypto_power(power_class=power_up)
                crypto_power_ups.append(power)
        self.keystore = keystore

        if crypto_power and crypto_power_ups:
            raise ValueError("Pass crypto_power or crypto_power_ups (or neither), but not both.")
        crypto_power_ups = crypto_power_ups or list()

        if crypto_power:
            self._crypto_power = crypto_power
        elif crypto_power_ups:
            self._crypto_power = CryptoPower(power_ups=crypto_power_ups)
        else:
            self._crypto_power = CryptoPower(power_ups=self._default_crypto_powerups)

        if is_peer:
            if network_middleware is not None:
                raise TypeError("Network middleware cannot be attached to a peer.")
            if registry is not None:
                raise TypeError("Registry cannot be attached to peer.")
            verifying_key = self.public_keys(SigningPower)
            self._stamp = StrangerStamp(verifying_key)
            self.keystore_dir = STRANGER
            self.network_middleware = STRANGER

        else:
            try:
                signing_power: SigningPower = self._crypto_power.power_ups(SigningPower)
                self._stamp: SignatureStamp = signing_power.get_signature_stamp()
            except NoSigningPower:
                self._stamp = NO_SIGNING_POWER
            self.wallet = wallet
            self.eth_endpoint = eth_endpoint
            self.polygon_endpoint = polygon_endpoint
            self.registry = registry or ContractRegistry.from_latest_publication(domain)
            self.network_middleware = network_middleware or RestMiddleware(
                registry=self.registry, eth_endpoint=eth_endpoint
            )

            Learner.__init__(
                self,
                domain=self.domain,
                network_middleware=self.network_middleware,
                *args, **kwargs,
            )

    def __eq__(self, other) -> bool:
        try:
            other_stamp = other.stamp
        except (AttributeError, NoSigningPower):
            return False
        return bytes(self.stamp) == bytes(other_stamp)

    def __hash__(self):
        return int.from_bytes(bytes(self.stamp), byteorder="big")

    @property
    def name(self):
        return self.__class__.__name__

    @property
    def nickname(self):
        return Nickname.from_seed(self.checksum_address)

    @property
    def stamp(self):
        if self._stamp is NO_SIGNING_POWER:
            raise NoSigningPower
        elif not self._stamp:
            raise AttributeError("SignatureStamp has not been set up yet.")
        else:
            return self._stamp

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
            is_peer=True,
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
        Learner.stop_peering(self)
