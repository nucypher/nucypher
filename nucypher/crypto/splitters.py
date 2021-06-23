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


from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from nucypher.crypto.umbral_adapter import CapsuleFrag, PublicKey, Capsule, Signature

key_splitter = BytestringSplitter((PublicKey, PublicKey.serialized_size()))
capsule_splitter = BytestringSplitter((Capsule, Capsule.serialized_size()))
cfrag_splitter = BytestringSplitter((CapsuleFrag, CapsuleFrag.serialized_size()))
signature_splitter = BytestringSplitter((Signature, Signature.serialized_size()))
