import inspect
from typing import List, Union

from eth_keys.datatypes import PublicKey, Signature as EthSignature
from eth_utils import keccak
from umbral import pre
from umbral.keys import UmbralPublicKey, UmbralPrivateKey, UmbralKeyingMaterial

from nucypher.blockchain.eth.chains import Blockchain
from nucypher.keystore import keypairs
from nucypher.keystore.keypairs import SigningKeypair, EncryptingKeypair, HostingKeypair


class PowerUpError(TypeError):
    pass


class NoSigningPower(PowerUpError):
    pass


class NoEncryptingPower(PowerUpError):
    pass


class NoBlockchainPower(PowerUpError):
    pass


class CryptoPower(object):
    def __init__(self, power_ups: dict = None) -> None:
        self._power_ups = {}   # type: dict
        # TODO: The keys here will actually be IDs for looking up in a KeyStore.
        self.public_keys = {}  # type: dict

        if power_ups is not None:
            for power_up in power_ups:
                self.consume_power_up(power_up)
        else:
            power_ups = []  # default

    def consume_power_up(self, power_up):
        if isinstance(power_up, CryptoPowerUp):
            power_up_class = power_up.__class__
            power_up_instance = power_up
        elif CryptoPowerUp in inspect.getmro(power_up):
            power_up_class = power_up
            power_up_instance = power_up()
        else:
            raise TypeError(
                ("power_up must be a subclass of CryptoPowerUp or an instance "
                 "of a subclass of CryptoPowerUp."))
        self._power_ups[power_up_class] = power_up_instance

        if power_up.confers_public_key:
            self.public_keys[power_up_class] = power_up_instance.public_key()

    def power_ups(self, power_up_class):
        try:
            return self._power_ups[power_up_class]
        except KeyError:
            raise power_up_class.not_found_error


class CryptoPowerUp(object):
    """
    Gives you MORE CryptoPower!
    """
    confers_public_key = False


class BlockchainPower(CryptoPowerUp):
    """
    Allows for transacting on a Blockchain via web3 backend.
    """
    not_found_error = NoBlockchainPower

    def __init__(self, blockchain: 'Blockchain', account: str) -> None:
        """
        Instantiates a BlockchainPower for the given account id.
        """
        self.blockchain = blockchain
        self.account = account
        self.is_unlocked = False

    def unlock_account(self, password: str, duration: int = None):
        """
        Unlocks the account for the specified duration. If no duration is
        provided, it will remain unlocked indefinitely.
        """
        self.is_unlocked = self.blockchain.unlock_account(self.account, password, duration=duration)

        if not self.is_unlocked:
            raise PowerUpError("Failed to unlock account {}".format(self.account))

    def sign_message(self, message: bytes):
        """
        Signs the message with the private key of the BlockchainPower.
        """
        if not self.is_unlocked:
            raise PowerUpError("Account is not unlocked.")

        signature = self.blockchain.interface.call_backend_sign(self.account, message)
        return bytes(signature)

    def verify_message(self, address: str, pubkey: bytes, message: bytes, signature_bytes: bytes):
        """
        Verifies that the message was signed by the keypair.
        """
        # Check that address and pubkey match
        eth_pubkey = PublicKey(pubkey)
        signature = EthSignature(signature_bytes=signature_bytes)
        if not eth_pubkey.to_checksum_address() == address:
            raise ValueError("Pubkey address ({}) doesn't match the provided address ({})".format(eth_pubkey.to_checksum_address, address))

        hashed_message = keccak(message)

        if not self.blockchain.interface.call_backend_verify(
                eth_pubkey, signature, hashed_message):
            raise PowerUpError("Signature is not valid for this message or pubkey.")
        else:
            return True

    def __del__(self):
        """
        Deletes the blockchain power and locks the account.
        """
        self.blockchain.interface.w3.personal.lockAccount(self.account)


class KeyPairBasedPower(CryptoPowerUp):
    confers_public_key = True
    _keypair_class = keypairs.Keypair
    _default_private_key_class = UmbralPrivateKey

    def __init__(self,
                 pubkey: UmbralPublicKey = None,
                 keypair: keypairs.Keypair = None,
                 ) -> None:
        if keypair and pubkey:
            raise ValueError(
                "Pass keypair or pubkey_bytes (or neither), but not both.")
        elif keypair:
            self.keypair = keypair
        else:
            # They didn't pass a keypair; we'll make one with the bytes or
            # UmbralPublicKey if they provided such a thing.
            if pubkey:
                try:
                    public_key = pubkey.as_umbral_pubkey()
                except AttributeError:
                    try:
                        public_key = UmbralPublicKey.from_bytes(pubkey)
                    except TypeError:
                        public_key = pubkey
                self.keypair = self._keypair_class(
                    public_key=public_key)
            else:
                # They didn't even pass a public key.  We have no choice but to generate a keypair.
                self.keypair = self._keypair_class(generate_keys_if_needed=True)

    def __getattr__(self, item):
        if item in self.provides:
            try:
                return getattr(self.keypair, item)
            except AttributeError:
                raise PowerUpError(
                    "This {} has a keypair, {}, which doesn't provide {}.".format(self.__class__,
                                                                                  self.keypair.__class__,
                                                                                  item))
        else:
            raise PowerUpError("This {} doesn't provide {}.".format(self.__class__, item))

    def public_key(self):
        return self.keypair.pubkey


class DerivedKeyBasedPower(CryptoPowerUp):
    """
    Rather than rely on an established KeyPair, this type of power
    derives a key at moments defined by the user.
    """


class SigningPower(KeyPairBasedPower):
    _keypair_class = SigningKeypair
    not_found_error = NoSigningPower
    provides = ("sign", "get_signature_stamp")


class EncryptingPower(KeyPairBasedPower):
    _keypair_class = EncryptingKeypair
    not_found_error = NoEncryptingPower
    provides = ("decrypt",)


class DelegatingPower(DerivedKeyBasedPower):

    def __init__(self) -> None:
        self.umbral_keying_material = UmbralKeyingMaterial()

    def generate_kfrags(self, bob_pubkey_enc, signer, label, m, n) -> Union[UmbralPublicKey, List]:
        """
        Generates re-encryption key frags ("KFrags") and returns them.

        These KFrags can be used by Ursula to re-encrypt a Capsule for Bob so
        that he can activate the Capsule.
        :param bob_pubkey_enc: Bob's public key
        :param m: Minimum number of KFrags needed to rebuild ciphertext
        :param n: Total number of rekey shares to generate
        """
        # TODO: salt?  #265

        __private_key = self.umbral_keying_material.derive_privkey_by_label(label)
        kfrags = pre.split_rekey(__private_key, signer, bob_pubkey_enc, m, n)
        return __private_key.get_pubkey(), kfrags
