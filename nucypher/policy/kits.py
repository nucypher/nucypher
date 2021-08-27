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


from typing import Dict, Optional, Tuple

from bytestring_splitter import BytestringKwargifier, VariableLengthBytestring
from constant_sorrow.constants import NOT_SIGNED, UNKNOWN_SENDER
from constant_sorrow import constants

from nucypher.crypto.splitters import capsule_splitter, key_splitter
import nucypher.crypto.umbral_adapter as umbral # need it to mock `umbral.encrypt`
from nucypher.crypto.umbral_adapter import PublicKey, VerifiedCapsuleFrag, Capsule, Signature


class CryptoKit:
    """
    A package of discrete items, meant to be sent over the wire or saved to disk (in either case, as bytes),
    capable of performing a distinct cryptological function.
    """
    splitter = None

    @classmethod
    def split_bytes(cls, some_bytes):
        if not cls.splitter:
            raise TypeError("This kit doesn't have a splitter defined.")
        splitter = cls.splitter()
        return splitter(some_bytes)

    @classmethod
    def from_bytes(cls, some_bytes):
        return cls.split_bytes(some_bytes)


class BaseMessageKit(CryptoKit):
    """
    All the components needed to transmit and verify an encrypted message.
    """

    def __init__(self,
                 capsule: Capsule,
                 sender_verifying_key: Optional[PublicKey] = None,
                 ciphertext: bytes = None,
                 signature=NOT_SIGNED) -> None:

        self.ciphertext = ciphertext
        self.capsule = capsule
        self.sender_verifying_key = sender_verifying_key
        self._signature = signature

        self._cfrags = set()
        self._delegating_key = None
        self._receiving_key = None
        self._verifying_key = None

    def attach_cfrag(self, cfrag: VerifiedCapsuleFrag):
        # TODO: check that the cfrag belongs to this capsule?
        self._cfrags.add(cfrag)

    def clear_cfrags(self):
        self._cfrags = set()

    def set_correctness_keys(self,
                             delegating: Optional[PublicKey] = None,
                             receiving: Optional[PublicKey] = None,
                             verifying: Optional[PublicKey] = None):

        # TODO (#2028): remove the need in sanity checks

        if self._delegating_key is None:
            self._delegating_key = delegating
        elif delegating is not None and delegating != self._delegating_key:
            raise Exception("Replacing an existing delegating key")

        if self._receiving_key is None:
            self._receiving_key = receiving
        elif receiving is not None and receiving != self._receiving_key:
            raise Exception("Replacing an existing receiving key")

        if self._verifying_key is None:
            self._verifying_key = verifying
        elif verifying is not None and verifying != self._verifying_key:
            raise Exception("Replacing an existing verifying key")

    def get_correctness_keys(self) -> Dict[str, PublicKey]:
        return dict(delegating=self._delegating_key,
                    receiving=self._receiving_key,
                    verifying=self._verifying_key)

    def __len__(self):
        # TODO: may be better to just have a "has enough cfrags" method
        return len(self._cfrags)

    def __str__(self):
        return f"{self.__class__.__name__}({self.capsule}, {len(self)} cfrags)"

    def to_bytes(self, include_alice_pubkey=True):
        # We include the capsule first.
        as_bytes = bytes(self.capsule)

        # Then, before the ciphertext, we see if we're including alice's public key.
        # We want to put that first because it's typically of known length.
        if include_alice_pubkey and self.sender_verifying_key:
            as_bytes += bytes(self.sender_verifying_key)

        as_bytes += VariableLengthBytestring(self.ciphertext)
        return as_bytes

    @classmethod
    def splitter(cls, *args, **kwargs):
        return BytestringKwargifier(cls,
                                    capsule=capsule_splitter,
                                    sender_verifying_key=key_splitter,
                                    ciphertext=VariableLengthBytestring)

    @property
    def signature(self):
        return self._signature


class MessageKit(BaseMessageKit):
    """
    A MessageKit which includes sufficient additional information to be retrieved on the NuCypher Network.
    """

    @classmethod
    def author(cls,
               recipient_key: PublicKey,
               plaintext: bytes,
               signer: 'SignatureStamp',
               sign_plaintext: bool = True
               ) -> Tuple['MessageKit', Signature]:
        if signer is not constants.DO_NOT_SIGN:
            # The caller didn't expressly tell us not to sign; we'll sign.
            if sign_plaintext:
                # Sign first, encrypt second.
                sig_header = constants.SIGNATURE_TO_FOLLOW
                signature = signer(plaintext)
                capsule, ciphertext = umbral.encrypt(recipient_key, sig_header + bytes(signature) + plaintext)
            else:
                # Encrypt first, sign second.
                sig_header = constants.SIGNATURE_IS_ON_CIPHERTEXT
                capsule, ciphertext = umbral.encrypt(recipient_key, sig_header + plaintext)
                signature = signer(ciphertext)
            message_kit = MessageKit(ciphertext=ciphertext, capsule=capsule,
                                           sender_verifying_key=signer.as_umbral_pubkey(),
                                           signature=signature)
        else:
            # Don't sign.
            signature = sig_header = constants.NOT_SIGNED
            capsule, ciphertext = umbral.encrypt(recipient_key, sig_header + plaintext)
            message_kit = MessageKit(ciphertext=ciphertext, capsule=capsule)

        return message_kit, signature

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sender = UNKNOWN_SENDER.bool_value(False)

    @property
    def sender(self):
        return self._sender

    @sender.setter
    def sender(self, enrico):
        # Here we set the delegating correctness key to the policy public key (which happens to be composed on enrico, but for which of course he doesn't have the corresponding private key).
        self.set_correctness_keys(delegating=enrico.policy_pubkey)
        self._sender = enrico

    def __eq__(self, other):
        return bytes(self) == bytes(other)

    def __bytes__(self):
        return super().to_bytes(include_alice_pubkey=True)

    def ensure_correct_sender(self,
                              enrico: Optional["Enrico"] = None,
                              policy_encrypting_key: Optional[PublicKey] = None):
        """
        Make sure that the sender of the message kit is set and corresponds to
        the given ``enrico``, or create it from the given ``policy_encrypting_key``.
        """
        if self.sender:
            if enrico and self.sender != enrico:
                raise ValueError(f"Mismatched sender: the object has {self.sender}, provided {enrico}")
        elif enrico:
            self.sender = enrico
        elif self.sender_verifying_key and policy_encrypting_key:
            # Well, after all, this is all we *really* need.
            from nucypher.characters.lawful import Enrico
            self.sender = Enrico.from_public_keys(verifying_key=self.sender_verifying_key,
                                                  policy_encrypting_key=policy_encrypting_key)
        else:
            raise ValueError(
                "No information provided to set the message kit sender. "
                "Need eiter `enrico` or `policy_encrypting_key` to be given.")


class RevocationKit:

    def __init__(self, treasure_map, signer: 'SignatureStamp'):
        from nucypher.policy.orders import Revocation
        self.revocations = dict()
        for node_id, encrypted_kfrag in treasure_map:
            self.revocations[node_id] = Revocation(ursula_checksum_address=node_id,
                                                   encrypted_kfrag=encrypted_kfrag,
                                                   signer=signer)

    def __iter__(self):
        return iter(self.revocations.values())

    def __getitem__(self, node_id):
        return self.revocations[node_id]

    def __len__(self):
        return len(self.revocations)

    def __eq__(self, other):
        return self.revocations == other.revocations

    @property
    def revokable_addresses(self):
        """
        Returns a Set of revokable addresses in the checksum address formatting
        """
        return set(self.revocations.keys())

    def add_confirmation(self, node_id, signed_receipt):
        """
        Adds a signed confirmation of Ursula's ability to revoke the arrangement.
        """
        # TODO: Verify Ursula's signature
        # TODO: Implement receipts
        raise NotImplementedError
