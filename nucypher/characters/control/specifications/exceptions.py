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

from bytestring_splitter import BytestringSplittingError
from cryptography.exceptions import InternalError


class SpecificationError(ValueError):
    """The protocol request is completely unusable"""


class MissingField(SpecificationError):
    """The protocol request cannot be deserialized because it is missing required fields"""


class InvalidInputData(SpecificationError):
    """Input data does not match the input specification"""


class InvalidOutputData(SpecificationError):
    """Response data does not match the output specification"""


class InvalidArgumentCombo(SpecificationError):
    """Arguments specified are incompatible"""


# TODO: catch cryptography.exceptions.InternalError in PyUmbral
InvalidNativeDataTypes = (ValueError, TypeError, BytestringSplittingError, InternalError)
