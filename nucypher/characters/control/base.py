from abc import ABC


class CharacterControlSpecification(ABC):

    specifications = NotImplemented

    class SpecificationError(ValueError):
        """The protocol request is completely unusable"""

    class MissingField(SpecificationError):
        """The protocol request can be deserialized by is missing required fields"""

    class InvalidInputField(SpecificationError):
        """Response data does not match the output specification"""

    class InvalidOutputField(SpecificationError):
        """Response data does not match the output specification"""

    @classmethod
    def get_specifications(cls, interface_name: str) -> tuple:
        try:
            input_specification, output_specification = cls.specifications[interface_name]
        except KeyError:
            raise cls.SpecificationError(f"No Such Control Interface '{interface_name}'")
        return input_specification, output_specification

