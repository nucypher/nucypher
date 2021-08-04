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

from abc import abstractmethod, ABC
from typing import Dict


class Versioned(ABC):

    _BRAND_LENGTH = 2  # bytes
    _VERSION_LENGTH = 2
    _HEADER_SIZE = _BRAND_LENGTH + _VERSION_LENGTH

    @classmethod
    def from_bytes(cls, data):

        # Metadata
        brand = data[:cls._BRAND_LENGTH]
        version_index = cls._BRAND_LENGTH + cls._VERSION_LENGTH
        version_data = data[cls._BRAND_LENGTH:version_index]
        version_number = int.from_bytes(version_data, 'big')

        # Data passed to deserializer
        remainder = data[version_index:]

        # Validate and Deserialize
        if brand != cls._brand():
            raise ValueError(f"Incorrect brand.  Expected {cls._brand()}, Got {brand}")
        if version_number == cls._version():
            return cls._from_bytes_current(remainder)

        handlers = cls._old_version_handlers()
        try:
            return handlers[version_number](remainder)
        except KeyError:
            raise ValueError(f"Incorrect or unknown version number ({version_number}).")

    def __bytes__(self):
        return self._header() + self._payload()

    @classmethod
    def _header(cls) -> bytes:
        version_bytes = cls._version().to_bytes(cls._VERSION_LENGTH, 'big')
        return cls._brand() + version_bytes

    @classmethod
    @abstractmethod
    def _brand(cls) -> bytes:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def _version(cls) -> int:
        raise NotImplementedError

    @abstractmethod
    def _payload(self) -> bytes:
        """Returns the unversioned bytes serialized representation of this instance."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def _old_version_handlers(cls) -> Dict:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def _from_bytes_current(cls, data):
        raise NotImplementedError
