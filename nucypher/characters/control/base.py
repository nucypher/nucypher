from abc import ABC


class CharacterControlSpecification(ABC):

    specifications = NotImplemented

    class ProtocolError(ValueError):
        """The protocol request is completely unusable"""

    class MissingField(ProtocolError):
        """The protocol request can be deserialized by is missing required fields"""

    class InvalidResponseField(ProtocolError):
        """Response data does not match the output specification"""

    @classmethod
    def get_specifications(cls, interface_name: str) -> tuple:
        try:
            input_specification, output_specification = cls.specifications[interface_name]
        except KeyError:
            raise cls.ProtocolError(f"No Such Interface '{interface_name}'")
        return input_specification, output_specification

