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
