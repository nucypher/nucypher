"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
from constant_sorrow.constants import NO_SIGNING_POWER
from typing import Tuple
from umbral.keys import UmbralPublicKey

from nucypher.crypto.api import encrypt_and_sign
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.signing import Signature
from nucypher.crypto.powers import SigningPower
from nucypher.keystore.keypairs import SigningKeypair


class DataSource:

    def __init__(self, policy_pubkey_enc, signing_keypair=NO_SIGNING_POWER, label=None) -> None:
        self.policy_pubkey = policy_pubkey_enc
        if signing_keypair is NO_SIGNING_POWER:
            signing_keypair = SigningKeypair()  # TODO: Generate signing key properly.  #241
        signing_power = SigningPower(keypair=signing_keypair)
        self.stamp = signing_power.get_signature_stamp()
        self.label = label

    def encrypt_message(self,
                        message: bytes
                        ) -> Tuple[UmbralMessageKit, Signature]:
        message_kit, signature = encrypt_and_sign(self.policy_pubkey,
                                                  plaintext=message,
                                                  signer=self.stamp)
        message_kit.policy_pubkey = self.policy_pubkey  # TODO: We can probably do better here.
        return message_kit, signature

    @classmethod
    def from_public_keys(cls,
                         policy_public_key: UmbralPublicKey,
                         datasource_public_key: bytes,
                         label: bytes):
        umbral_public_key = UmbralPublicKey.from_bytes(datasource_public_key)
        return cls(policy_public_key,
                   signing_keypair=SigningKeypair(public_key=umbral_public_key),
                   label=label,
                   )
