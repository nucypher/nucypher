import inspect
from typing import List, Union

from nkms.keystore import keypairs
from nkms.keystore.keypairs import SigningKeypair, EncryptingKeypair
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
    provides = ("sign", "generate_self_signed_cert")


class EncryptingPower(KeyPairBasedPower):
    _keypair_class = EncryptingKeypair
    not_found_error = NoEncryptingPower
    provides = ("decrypt",)


class DelegatingPower(DerivedKeyBasedPower):

    def __init__(self):
        self.umbral_keying_material = UmbralKeyingMaterial()

    def generate_kfrags(self, bob_pubkey_enc, label, m, n) -> Union[UmbralPublicKey, List]:
        """
        Generates re-encryption key frags ("KFrags") and returns them.

        These KFrags can be used by Ursula to re-encrypt a Capsule for Bob so
        that he can activate the Capsule.
        :param bob_pubkey_enc: Bob's public key
        :param m: Minimum number of KFrags needed to rebuild ciphertext
        :param n: Total number of rekey shares to generate
        """
        # TODO: salt?

        __private_key = self.umbral_keying_material.derive_privkey_by_label(label)
        kfrags = pre.split_rekey(__private_key, bob_pubkey_enc, m, n)
        return __private_key.get_pubkey(), kfrags
