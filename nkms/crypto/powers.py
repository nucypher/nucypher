import inspect

from umbral import pre
from nkms.crypto.kits import MessageKit
from nkms.keystore import keypairs
from nkms.keystore.keypairs import SigningKeypair, EncryptingKeypair
from umbral.keys import UmbralPublicKey, UmbralPrivateKey
from typing import List


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

    def power_ups(self, power_up_class):
        try:
            return self._power_ups[power_up_class]
        except KeyError:
            raise power_up_class.not_found_error

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

    def generate_kfrags(self, bob, m, n) -> List:
        try:
            encrypting_power = self._power_ups[EncryptingPower]
            return encrypting_power.generate_kfrags(bob, m, n)
        except KeyError:
            raise NoEncryptingPower


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
    not_found_error = NoSigningPower

    def sign(self, message):
        """
        Signs a message message and returns a Signature.
        """
        return self.keypair.sign(message)


class EncryptingPower(KeyPairBasedPower):
    confers_public_key = True
    _keypair_class = EncryptingKeypair
    not_found_error = NoEncryptingPower

    def decrypt(self, message_kit: MessageKit) -> bytes:
        return self.keypair.decrypt(message_kit)

    def generate_kfrags(self, bob_pubkey_enc, m, n) -> List:
        return self.keypair.generate_kfrags(bob_pubkey_enc, m, n)
