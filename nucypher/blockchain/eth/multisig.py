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

from collections import namedtuple
from typing import List


class Authorization:
    """
    An edict issued by an Executive authorizing the execution of a multisig
    transaction by the delegated trustee.
    """

    SignatureComponents = namedtuple('SignatureComponents', 'v r s')

    def __init__(self, trustee_address: str, signed_transaction_hash: bytes):
        self.trustee_address = trustee_address
        self.__data = signed_transaction_hash
        self.__r = None
        self.__s = None
        self.__v = None

    def __bytes__(self):
        pass

    def get_signature_components(self) -> SignatureComponents:
        components = self.SignatureComponents(v=self.__v, r=self.__r, s=self.__s)
        return components

    @property
    def id(self):
        # TODO - Unique ID
        pass

    def _serialize(self) -> bytes:
        #TODO: BSS
        pass

    @classmethod
    def _deserialize(cls, data: bytes) -> tuple:
        #TODO: BSS
        pass

    def _write(self, filepath: str = None) -> str:
        with open(filepath, 'wb') as file:
            # TODO: Serialize
            file.write(self.__data)
        return filepath

    @classmethod
    def from_file(cls, filepath: str = None) -> 'Authorization':
        with open(filepath, 'rb') as file:
            data = file.read()
            deserialized_data = cls._deserialize(data=data)
            trustee_address, presigned_transaction_hash = deserialized_data
        instance = cls(trustee_address=trustee_address,
                       signed_transaction_hash=presigned_transaction_hash)
        return instance


class ExecutiveBoard:
    """A collection of Executives plus a Trustee."""

    def __init__(self, executives: List['Executive']):
        self.executives = executives


