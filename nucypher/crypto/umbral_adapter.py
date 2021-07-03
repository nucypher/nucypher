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

# This module is used to have a single point where the Umbral implementation is chosen.
# Do not import Umbral directly, use re-exports from this module.


from umbral import (
    SecretKey,
    PublicKey,
    SecretKeyFactory,
    Signature,
    Signer,
    Capsule,
    KeyFrag,
    VerifiedKeyFrag,
    CapsuleFrag,
    VerifiedCapsuleFrag,
    VerificationError,
    encrypt,
    decrypt_original,
    generate_kfrags,
    reencrypt,
    decrypt_reencrypted,
)


def secret_key_factory_from_seed(entropy: bytes) -> SecretKeyFactory:
    """TODO: Issue #57 in nucypher/rust-umbral"""
    if len(entropy) < 32:
        raise ValueError('Entropy must be at least 32 bytes.')
    material = entropy.zfill(SecretKeyFactory.serialized_size())
    instance = SecretKeyFactory.from_bytes(material)
    return instance


def secret_key_factory_from_secret_key_factory(skf: SecretKeyFactory, label: bytes) -> SecretKeyFactory:
    """TODO: Issue #59 in nucypher/rust-umbral"""
    secret_key = bytes(skf.secret_key_by_label(label)).zfill(SecretKeyFactory.serialized_size())
    return SecretKeyFactory.from_bytes(secret_key)
