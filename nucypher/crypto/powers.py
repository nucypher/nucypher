import inspect
import web3
from binascii import unhexlify
from eth_keys.datatypes import PublicKey, Signature
from typing import List, Union

from eth_utils import keccak
from nucypher.keystore import keypairs
from nucypher.keystore.keypairs import SigningKeypair, EncryptingKeypair
from umbral.keys import UmbralPublicKey, UmbralPrivateKey, UmbralKeyingMaterial
from umbral import pre


class PowerUpError(TypeError):
    pass


class NoSigningPower(PowerUpError):
    pass


class NoEncryptingPower(PowerUpError):
    pass


class CryptoPower(object):
    def __init__(self, power_ups=None):
        self._power_ups = {}
        # TODO: The keys here will actually be IDs for looking up in a KeyStore.
        self.public_keys = {}

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

    def __init__(self, blockchain: 'Blockchain', account: str):
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
        self.is_unlocked = self.blockchain.interface.w3.personal.unlockAccount(
                self.account, password, duration=duration)

        if not self.is_unlocked:
            raise PowerUpError("Account failed to unlock for {}".format(self.account))

    def sign_message(self, message: bytes):
        """
        Signs the message with the private key of the BlockchainPower.
        """
        if not self.is_unlocked:
            raise PowerUpError("Account is not unlocked.")

        signature = self.blockchain.interface.call_backend_sign(self.account, message)
        return signature

    def verify_message(self, address: str, pubkey: bytes, message: bytes, signature: str):
        """
        Verifies that the message was signed by the keypair.
        """
        # Check that address and pubkey match
        eth_pubkey = PublicKey(pubkey)
        if not eth_pubkey.to_checksum_address() == address:
            raise ValueError("Pubkey address ({}) doesn't match the provided address ({})".format(eth_pubkey.to_checksum_address, address))

        hashed_message = keccak(message)
        eth_signature = Signature(signature_bytes=unhexlify(signature[2:]))

        if not self.blockchain.interface.call_backend_verify(
                eth_pubkey, eth_signature, hashed_message):
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

    def __init__(self,
                 pubkey: UmbralPublicKey = None,
                 keypair: keypairs.Keypair = None,
                 generate_keys_if_needed=True) -> None:
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
                    key_to_pass_to_keypair = pubkey.as_umbral_pubkey()
                except AttributeError:
                    try:
                        key_to_pass_to_keypair = UmbralPublicKey.from_bytes(pubkey)
                    except TypeError:
                        key_to_pass_to_keypair = pubkey
            else:
                # They didn't even pass pubkey_bytes.  We'll generate a keypair.
                key_to_pass_to_keypair = UmbralPrivateKey.gen_key()
            self.keypair = self._keypair_class(
                umbral_key=key_to_pass_to_keypair)

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
    provides = ("sign", "generate_self_signed_cert", "get_signature_stamp")


class EncryptingPower(KeyPairBasedPower):
    _keypair_class = EncryptingKeypair
    not_found_error = NoEncryptingPower
    provides = ("decrypt",)


class DelegatingPower(DerivedKeyBasedPower):

    def __init__(self):
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
