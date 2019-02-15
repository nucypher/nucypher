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
