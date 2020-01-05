class SpecificationError(ValueError):
        """The protocol request is completely unusable"""

class MissingField(SpecificationError):
    """The protocol request can be deserialized by is missing required fields"""

class InvalidInputField(SpecificationError):
    """Response data does not match the output specification"""

class InvalidOutputField(SpecificationError):
    """Response data does not match the output specification"""
