class SpecificationError(ValueError):
    """The protocol request is completely unusable"""

class MissingField(SpecificationError):
    """The protocol request cannot be deserialized because it is missing required fields"""

class InvalidInputField(SpecificationError):
    """Response data does not match the input specification"""

class InvalidOutputField(SpecificationError):
    """Response data does not match the output specification"""

class MethodNotFound(SpecificationError):
    """Response data does not match the output specification"""
