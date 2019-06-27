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


import inspect
from typing import List, Tuple, Optional

from constant_sorrow.constants import NO_STAKING_DEVICE, NO_BLOCKCHAIN_CONNECTION
from hexbytes import HexBytes
from umbral import pre
from umbral.keys import UmbralPublicKey, UmbralPrivateKey, UmbralKeyingMaterial

from nucypher.keystore import keypairs
from nucypher.keystore.keypairs import SigningKeypair, DecryptingKeypair


class PowerUpError(TypeError):
    pass


class NoSigningPower(PowerUpError):
    pass


class NoDecryptingPower(PowerUpError):
    pass


class NoTransactingPower(PowerUpError):
    pass


class CryptoPower(object):
    def __init__(self, power_ups: list = None) -> None:
        self.__power_ups = {}   # type: dict
        # TODO: The keys here will actually be IDs for looking up in a KeyStore.
        self.public_keys = {}  # type: dict

        if power_ups is not None:
            for power_up in power_ups:
                self.consume_power_up(power_up)

    def __contains__(self, item):
        try:
            self.power_ups(item)
        except PowerUpError:
            return False
        else:
            return True

    def consume_power_up(self, power_up, *args, **kwargs):
        if isinstance(power_up, CryptoPowerUp):
            power_up_class = power_up.__class__
            power_up.activate(*args, **kwargs)
            power_up_instance = power_up
        elif CryptoPowerUp in inspect.getmro(power_up):
            power_up_class = power_up
            power_up_instance = power_up()
        else:
            raise TypeError(
                ("power_up must be a subclass of CryptoPowerUp or an instance "
                 "of a CryptoPowerUp subclass."))
        self.__power_ups[power_up_class] = power_up_instance

        if power_up.confers_public_key:
            self.public_keys[power_up_class] = power_up_instance.public_key()

    def power_ups(self, power_up_class):
        try:
            return self.__power_ups[power_up_class]
        except KeyError:
            raise power_up_class.not_found_error


class CryptoPowerUp:
    """
    Gives you MORE CryptoPower!
    """
    confers_public_key = False

    def activate(self, *args, **kwargs):
        return


class TransactingPower(CryptoPowerUp):
    """
    Allows for transacting on a Blockchain via web3 backend.
    """
    not_found_error = NoTransactingPower

    class AccountLocked(PowerUpError):
        pass

    def __init__(self,
                 blockchain,
                 account: str,
                 password: str = None,
                 device=NO_STAKING_DEVICE):
        """
        Instantiates a TransactingPower for the given checksum_address.
        """
        if password and (device is not NO_STAKING_DEVICE):
            raise ValueError(f"Cannot create a {self.__class__.__name__} with both a client and an device signer.")

        self.blockchain = blockchain
        self.client = NO_BLOCKCHAIN_CONNECTION

        self.account = account
        self.device = device

        self.__password = password
        self.__unlocked = False

    @property
    def is_unlocked(self):
        return self.__unlocked

    def activate(self, password: str = None):
        """Be Consumed"""
        self.blockchain.connect()
        self.client = self.blockchain.client       # Connect
        self.unlock_account(password=password)     # Unlock
        self.blockchain.transacting_power = self   # Attach
        self.__password = None                     # Discard

    def lock_account(self):
        if self.device is not NO_STAKING_DEVICE:
            # TODO: Implement TrustedDevice
            _result = self.device.lock()
        else:
            _result = self.client.lock_account(address=self.account)
        self.__unlocked = False

    def unlock_account(self, password: str = None):
        if self.device is not NO_STAKING_DEVICE:
            # TODO: Embed in TrustedDevice
            ping = 'PING|PONG'
            pong = self.device.client.ping(ping)  # TODO: Use pin protection?
            if not ping == pong:
                raise self.device.NoDeviceDetected
            unlocked = True
        else:
            unlocked = self.client.unlock_account(address=self.account, password=password)

        self.__unlocked = unlocked

    def sign_message(self, message: bytes) -> bytes:
        """
        Signs the message with the private key of the TransactingPower.
        """
        if not self.is_unlocked:
            raise self.AccountLocked("Failed to unlock account {}".format(self.account))

        # HW Signer
        if self.device is not NO_STAKING_DEVICE:
            # TODO: Use a common message signature type from clients and devices
            signature = self.device.sign_message(checksum_address=self.account, message=message)
            signature = signature.signature

        # Web3 Signer
        else:
            signature = self.client.sign_message(account=self.account, message=message)
        return signature

    def sign_transaction(self, unsigned_transaction: dict) -> HexBytes:
        """
        Signs the transaction with the private key of the TransactingPower.
        """
        if not self.is_unlocked:
            raise self.AccountLocked("Failed to unlock account {}".format(self.account))

        # Note: This check is also performed client-side.
        sender_address = unsigned_transaction['from']
        if sender_address != self.account:
            raise PowerUpError(f"'from' field must match key's {self.account}, but it was {sender_address}")

        # HW Signer
        if self.device is not NO_STAKING_DEVICE:
            # TODO: Use a common tx_sign return type from clients and devices
            signed_raw_transaction = self.device.sign_eth_transaction(unsigned_transaction=unsigned_transaction,
                                                                      checksum_address=self.account)
        # Web3 Signer
        else:
            signed_raw_transaction = self.blockchain.client.sign_transaction(transaction=unsigned_transaction,
                                                                             account=self.account)
        return signed_raw_transaction


class KeyPairBasedPower(CryptoPowerUp):
    confers_public_key = True
    _keypair_class = keypairs.Keypair
    _default_private_key_class = UmbralPrivateKey

    def __init__(self,
                 public_key: UmbralPublicKey = None,
                 keypair: keypairs.Keypair = None,
                 ) -> None:
        if keypair and public_key:
            raise ValueError("Pass keypair or pubkey_bytes (or neither), but not both.")
        elif keypair:
            self.keypair = keypair
        else:
            # They didn't pass a keypair; we'll make one with the bytes or
            # UmbralPublicKey if they provided such a thing.
            if public_key:
                try:
                    public_key = public_key.as_umbral_pubkey()
                except AttributeError:
                    try:
                        public_key = UmbralPublicKey.from_bytes(public_key)
                    except TypeError:
                        public_key = public_key
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

    def public_key(self) -> 'UmbralPublicKey':
        return self.keypair.pubkey


class SigningPower(KeyPairBasedPower):
    _keypair_class = SigningKeypair
    not_found_error = NoSigningPower
    provides = ("sign", "get_signature_stamp")


class DecryptingPower(KeyPairBasedPower):
    _keypair_class = DecryptingKeypair
    not_found_error = NoDecryptingPower
    provides = ("decrypt",)


class DerivedKeyBasedPower(CryptoPowerUp):
    """
    Rather than rely on an established KeyPair, this type of power
    derives a key at moments defined by the user.
    """


class DelegatingPower(DerivedKeyBasedPower):

    def __init__(self,
                 keying_material: Optional[bytes] = None,
                 password: Optional[bytes] = None) -> None:
        if keying_material is None:
            self.__umbral_keying_material = UmbralKeyingMaterial()
        else:
            self.__umbral_keying_material = UmbralKeyingMaterial.from_bytes(key_bytes=keying_material,
                                                                            password=password)

    def _get_privkey_from_label(self, label):
        return self.__umbral_keying_material.derive_privkey_by_label(label)

    def get_pubkey_from_label(self, label):
        return self._get_privkey_from_label(label).get_pubkey()

    def generate_kfrags(self, bob_pubkey_enc, signer, label, m, n) -> Tuple[UmbralPublicKey, List]:
        """
        Generates re-encryption key frags ("KFrags") and returns them.

        These KFrags can be used by Ursula to re-encrypt a Capsule for Bob so
        that he can activate the Capsule.
        :param bob_pubkey_enc: Bob's public key
        :param m: Minimum number of KFrags needed to rebuild ciphertext
        :param n: Total number of KFrags to generate
        """
        # TODO: salt?  #265

        __private_key = self._get_privkey_from_label(label)
        kfrags = pre.generate_kfrags(delegating_privkey=__private_key,
                                     receiving_pubkey=bob_pubkey_enc,
                                     threshold=m,
                                     N=n,
                                     signer=signer,
                                     sign_delegating_key=False,
                                     sign_receiving_key=False,
                                     )
        return __private_key.get_pubkey(), kfrags

    def get_decrypting_power_from_label(self, label):
        label_privkey = self._get_privkey_from_label(label)
        label_keypair = keypairs.DecryptingKeypair(private_key=label_privkey)
        decrypting_power = DecryptingPower(keypair=label_keypair)
        return decrypting_power
