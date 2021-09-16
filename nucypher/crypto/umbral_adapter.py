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
