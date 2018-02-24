import inspect
from typing import Iterable, List, Tuple

from umbral import pre
from nkms.crypto import api as API
from nkms.crypto.kits import MessageKit
from nkms.keystore import keypairs
from nkms.keystore.keypairs import SigningKeypair, EncryptingKeypair
from umbral.keys import UmbralPublicKey, UmbralPrivateKey


class PowerUpError(TypeError):
    pass


class NoSigningPower(PowerUpError):
    pass


class NoEncryptingPower(PowerUpError):
    pass


class CryptoPower(object):
    def __init__(self, power_ups=None, generate_keys_if_needed=False):
        self._power_ups = {}
        # TODO: The keys here will actually be IDs for looking up in a KeyStore.
        self.public_keys = {}
        self.generate_keys = generate_keys_if_needed

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
            power_up_instance = power_up(
                generate_keys_if_needed=self.generate_keys)
        else:
            raise TypeError(
                ("power_up must be a subclass of CryptoPowerUp or an instance "
                 "of a subclass of CryptoPowerUp."))
        self._power_ups[power_up_class] = power_up_instance

        if power_up.confers_public_key:
            self.public_keys[power_up_class] = power_up_instance.public_key()

    def pubkey_sig_bytes(self):
        try:
            pubkey_sig = self._power_ups[SigningPower].public_key()
            return bytes(pubkey_sig)
        except KeyError:
            raise NoSigningPower

    def sign(self, message):
        """
        TODO: New docstring.
        """
        try:
            sig_keypair = self._power_ups[SigningPower]
        except KeyError as e:
            raise NoSigningPower(e)
        return sig_keypair.sign(message)

    def decrypt(self, message_kit):
        try:
            encrypting_power = self._power_ups[EncryptingPower]
            return encrypting_power.decrypt(message_kit)
        except KeyError:
            raise NoEncryptingPower

    def encrypt_for(self, recipient_pubkey_enc, plaintext):
        ciphertext, capsule = pre.encrypt(recipient_pubkey_enc, plaintext)
        return MessageKit(ciphertext=ciphertext, capsule=capsule)


class CryptoPowerUp(object):
    """
    Gives you MORE CryptoPower!
    """
    confers_public_key = False


class KeyPairBasedPower(CryptoPowerUp):
    _keypair_class = keypairs.Keypair

    def __init__(self, keypair: keypairs.Keypair=None,
                 pubkey: UmbralPublicKey=None,
                 generate_keys_if_needed=True) -> None:
        if keypair and pubkey:
            raise ValueError(
                "Pass keypair or pubkey_bytes (or neither), but not both.")
        elif keypair:
            self.keypair = keypair
        else:
            # They didn't pass a keypair; we'll make one with the bytes (if any)
            # they provided.
            if pubkey:
                key_to_pass_to_keypair = pubkey
            else:
                # They didn't even pass pubkey_bytes.  We'll generate a keypair.
                key_to_pass_to_keypair = UmbralPrivateKey.gen_key()
            self.keypair = self._keypair_class(
                umbral_key=key_to_pass_to_keypair)

    def public_key(self):
        return self.keypair.pubkey


class SigningPower(KeyPairBasedPower):
    confers_public_key = True
    _keypair_class = SigningKeypair

    def sign(self, message):
        """
        Signs a message message and returns a Signature.
        """
        return self.keypair.sign(message)


class EncryptingPower(KeyPairBasedPower):
    confers_public_key = True
    _keypair_class = EncryptingKeypair

    def decrypt(self, message_kit: MessageKit) -> bytes:
        cleartext = pre.decrypt(message_kit.capsule, self.keypair.privkey,
                              message_kit.ciphertext, message_kit.alice_pubkey)

        return cleartext
