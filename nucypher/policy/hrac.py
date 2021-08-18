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

from nucypher.crypto.umbral_adapter import PublicKey
from nucypher.crypto.utils import keccak_digest
from bytestring_splitter import BytestringSplitter


class HRAC:
    """
    "hashed resource access code".

    A hash of:
    * Publisher's verifying key
    * Bob's verifying key
    * the label

    Publisher and Bob have all the information they need to construct this.
    Ursula does not, so we share it with her.

    This way, Bob can generate it and use it to find the TreasureMap.
    """

    # Note: this corresponds to the hardcoded size in the contracts
    # (which use `byte16` for this variable).
    SIZE = 16

    @classmethod
    def derive(cls, publisher_verifying_key: PublicKey, bob_verifying_key: PublicKey, label: bytes) -> 'HRAC':
        return cls(keccak_digest(bytes(publisher_verifying_key) + bytes(bob_verifying_key) + label)[:cls.SIZE])

    def __init__(self, hrac_bytes: bytes):
        self._hrac_bytes = hrac_bytes

    def __bytes__(self):
        return self._hrac_bytes

    @classmethod
    def from_bytes(cls, data: bytes) -> 'HRAC':
        if len(data) != cls.SIZE:
            raise ValueError(f"Incorrect HRAC size: expected {cls.SIZE}, got {len(data)}")
        return cls(data)

    def __eq__(self, other):
        return self._hrac_bytes == other._hrac_bytes

    def __hash__(self):
        return hash(self._hrac_bytes)

    def __str__(self):
        return f"HRAC({self._hrac_bytes.hex()})"


hrac_splitter = BytestringSplitter((HRAC, HRAC.SIZE))
