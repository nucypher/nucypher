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


from cryptography.hazmat.primitives import hashes

# Policy component sizes
HRAC_LENGTH = 16
SIGNATURE_SIZE = 64
EIP712_MESSAGE_SIGNATURE_SIZE = 65
WRIT_CHECKSUM_SIZE = 32
SIGNED_WRIT_SIZE = HRAC_LENGTH + WRIT_CHECKSUM_SIZE + SIGNATURE_SIZE
ENCRYPTED_KFRAG_PAYLOAD_LENGTH = 619 # Depends on encryption parameters in Umbral, has to be hardcoded

# Digest Lengths
KECCAK_DIGEST_LENGTH = 32
BLAKE2B_DIGEST_LENGTH = 64

# Hashes
SHA256 = hashes.SHA256()
BLAKE2B = hashes.BLAKE2b(64)
