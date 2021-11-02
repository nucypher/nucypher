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
import re
from typing import Dict, Tuple, Callable


class Versioned(ABC):
    """Base class for serializable entities"""

    _VERSION_PARTS = 2
    _VERSION_PART_SIZE = 2  # bytes
    _BRAND_SIZE = 4
    _VERSION_SIZE = _VERSION_PART_SIZE * _VERSION_PARTS
    _HEADER_SIZE = _BRAND_SIZE + _VERSION_SIZE

    class InvalidHeader(ValueError):
        """Raised when an unexpected or invalid bytes header is encountered."""

    class IncompatibleVersion(ValueError):
        """Raised when attempting to deserialize incompatible bytes"""

    class Empty(ValueError):
        """Raised when 0 bytes are remaining after parsing the header."""

    @classmethod
    @abstractmethod
    def _brand(cls) -> bytes:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def _version(cls) -> Tuple[int, int]:
        """tuple(major, minor)"""
        raise NotImplementedError

    @classmethod
    def version_string(cls) -> str:
        major, minor = cls._version()
        return f'{major}.{minor}'

    #
    # Serialize
    #

    def __bytes__(self) -> bytes:
        return self._header() + self._payload()

    @classmethod
    def _header(cls) -> bytes:
        """The entire bytes header to prepend to the instance payload."""
        major, minor = cls._version()
        major_bytes = major.to_bytes(cls._VERSION_PART_SIZE, 'big')
        minor_bytes = minor.to_bytes(cls._VERSION_PART_SIZE, 'big')
        header = cls._brand() + major_bytes + minor_bytes
        return header

    @abstractmethod
    def _payload(self) -> bytes:
        """The unbranded and unversioned bytes-serialized representation of this instance."""
        raise NotImplementedError

    #
    # Deserialize
    #

    @classmethod
    @abstractmethod
    def _from_bytes_current(cls, data):
        """The current deserializer"""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def _old_version_handlers(cls) -> Dict[Tuple[int, int], Callable]:
        """Old deserializer callables keyed by version."""
        raise NotImplementedError

    @classmethod
    def take(cls, data: bytes):
        """
        Deserializes the object from the given bytestring
        and returns the object and the remainder of the bytestring.
        """
        brand, version, payload = cls._parse_header(data)
        version = cls._resolve_version(version=version)
        handlers = cls._deserializers()
        obj, remainder = handlers[version](payload)
        return obj, remainder

    @classmethod
    def from_bytes(cls, data: bytes):
        """"Public deserialization API"""
        obj, remainder = cls.take(data)
        if remainder:
            raise ValueError(f"{len(remainder)} bytes remaining after deserializing {cls}")
        return obj

    @classmethod
    def _resolve_version(cls, version: Tuple[int, int]) -> Tuple[int, int]:

        # Unpack version metadata
        bytrestring_major, bytrestring_minor = version
        latest_major_version, latest_minor_version = cls._version()

        # Enforce major version compatibility
        if not bytrestring_major == latest_major_version:
            message = f'Incompatible versioned bytes for {cls.__name__}. ' \
                      f'Compatible version is {latest_major_version}.x, ' \
                      f'Got {bytrestring_major}.{bytrestring_minor}.'
            raise cls.IncompatibleVersion(message)

        # Enforce minor version compatibility.
        # Pass future minor versions to the latest minor handler.
        if bytrestring_minor >= latest_minor_version:
            version = cls._version()

        return version

    @classmethod
    def _parse_header(cls, data: bytes) -> Tuple[bytes, Tuple[int, int], bytes]:
        if len(data) < cls._HEADER_SIZE:
            # handles edge case when input is too short.
            raise ValueError(f'Invalid bytes for {cls.__name__}.')
        brand = cls._parse_brand(data)
        version = cls._parse_version(data)
        payload = cls._parse_payload(data)
        return brand, version, payload

    @classmethod
    def _parse_brand(cls, data: bytes) -> bytes:
        brand = data[:cls._BRAND_SIZE]
        if brand != cls._brand():
            error = f"Incorrect brand. Expected {cls._brand()}, Got {brand}."
            if not re.fullmatch(rb'\w+', brand):
                # unversioned entities for older versions will most likely land here.
                error = f"Incompatible bytes for {cls.__name__}."
            raise cls.InvalidHeader(error)
        return brand

    @classmethod
    def _parse_version(cls, data: bytes) -> Tuple[int, int]:
        version_data = data[cls._BRAND_SIZE:cls._HEADER_SIZE]
        major, minor = version_data[:cls._VERSION_PART_SIZE], version_data[cls._VERSION_PART_SIZE:]
        major, minor = int.from_bytes(major, 'big'), int.from_bytes(minor, 'big')
        version = major, minor
        return version

    @classmethod
    def _parse_payload(cls, data: bytes) -> bytes:
        payload = data[cls._HEADER_SIZE:]
        if len(payload) == 0:
            raise ValueError(f'No content to deserialize {cls.__name__}.')
        return payload

    @classmethod
    def _deserializers(cls) -> Dict[Tuple[int, int], Callable]:
        """Return a dict of all known deserialization handlers for this class keyed by version"""
        return {cls._version(): cls._from_bytes_current, **cls._old_version_handlers()}


# Collects the brands of every serializable entity, potentially useful for documentation.
# SERIALIZABLE_ENTITIES = {v.__class__.__name__: v._brand() for v in Versioned.__subclasses__()}
