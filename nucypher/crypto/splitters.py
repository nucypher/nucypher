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
from bytestring_splitter import BytestringSplitter
from umbral.config import default_params
from umbral.keys import UmbralPublicKey
from umbral.pre import Capsule

from nucypher.crypto.constants import PUBLIC_KEY_LENGTH, CAPSULE_LENGTH

key_splitter = BytestringSplitter((UmbralPublicKey, PUBLIC_KEY_LENGTH))
capsule_splitter = BytestringSplitter((Capsule, CAPSULE_LENGTH, {"params": default_params()}))

