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

    class InvalidHeader(ValueError):
        """Raised when an unexpected or invalid bytes header is encountered during deserialization"""

    @classmethod
    def from_bytes(cls, data):

        # Parse brand
        brand = data[:cls._BRAND_LENGTH]
        if brand != cls._brand():
            error = f"Incorrect brand. Expected {cls._brand()}, Got {brand}."
            if not brand.isalpha():
                error = f"Incompatible bytes for {cls.__name__}."
            raise cls.InvalidHeader(error)

        # Parse version
        version_index = cls._BRAND_LENGTH + cls._VERSION_LENGTH
        version_data = data[cls._BRAND_LENGTH:version_index]
        version_number = int.from_bytes(version_data, 'big')
        if version_number != cls._version() and version_number not in cls._old_version_handlers():
            available_versions = ",".join((cls._version(), *cls._old_version_handlers()))
            error = f'Incorrect or unknown version. Available versions for {cls.__name__} are {available_versions}'
            raise cls.InvalidHeader(error)

        # Parse body
        remainder = data[version_index:]

        # Select deserializer and process
        if version_number == cls._version():
            return cls._from_bytes_current(remainder)
        handlers = cls._old_version_handlers()
        return handlers[version_number](remainder)  # process

    def __bytes__(self):
        return self._header() + self._payload()

    @classmethod
    def _header(cls) -> bytes:
        if len(cls._brand()) != cls._BRAND_LENGTH:
            raise cls.InvalidHeader("Brand must be exactly two bytes.")
        if not cls._brand().isalpha():
            raise cls.InvalidHeader("Brand must be alphanumeric.")
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
