
from .bob import specifications as bob
from .alice import specifications as alice
from .enrico import specifications as enrico
from .exceptions import (
    SpecificationError,
    MissingField,
    InvalidInputField,
    InvalidOutputField
)

from abc import ABC
from collections import namedtuple

SpecificationTuple = namedtuple('SpecificationTuple', ['input', 'optional', 'output'])


class CharacterSpecification(ABC):

    _specifications = NotImplemented

    SpecificationError = SpecificationError
    MissingField = MissingField
    InvalidInputField = InvalidInputField
    InvalidOutputField = InvalidOutputField

    @classmethod
    def get_specifications(cls, interface_name: str) -> tuple:
        if cls._specifications is NotImplemented:
            raise NotImplementedError("Missing specifications for character")
        try:
            spec = cls.specifications()[interface_name]
        except KeyError:
            raise cls.SpecificationError(f"{cls.__class__.__name__} has no such control interface: '{interface_name}'")

        return SpecificationTuple(**{
            k: spec.get(k, ())
            for k in ['input', 'optional', 'output']})

    @classmethod
    def get_serializer(cls, interface_name: str) -> tuple:
        if cls._specifications is NotImplemented:
            raise NotImplementedError("Missing specifications for character")
        try:
            spec = cls.specifications()[interface_name]
        except KeyError:
            raise cls.SpecificationError(f"{cls.__class__.__name__} has no such control interface: '{interface_name}'")

        return spec

    @classmethod
    def get_specifications(cls, interface_name: str) -> tuple:
        spec = cls.get_serializer(interface_name)

        if isinstance(spec, dict):
            return SpecificationTuple(**{
                k: spec.get(k, ())
                for k in ['input', 'optional', 'output']})

        return SpecificationTuple(
            [k for k, f in spec.load_fields.items() if f.required],
            [k for k, f in spec.load_fields.items() if not f.required],
            list(spec.dump_fields.keys())
        )

    @classmethod
    def specifications(cls):
        if cls._specifications is NotImplemented:
            raise NotImplementedError
        else:
            return cls._specifications

    @staticmethod
    def __validate(specification: tuple, data: dict, error_class,
                   optional_specification: tuple = ()):
        invalid_fields = set(data.keys()) - set(specification) - set(optional_specification)
        if invalid_fields:
            pretty_invalid_fields = ', '.join(invalid_fields)
            raise error_class(f"Got: {pretty_invalid_fields}")

        missing_fields = set(specification) - set(data.keys())
        if missing_fields:
            pretty_missing_fields = ', '.join(missing_fields)
            raise error_class(f"Got: {pretty_missing_fields}")

        return True

    def validate_request(self, interface_name: str, request: dict) -> bool:
        input_specification, optional_specification, _ = self.get_specifications(interface_name=interface_name)
        return self.__validate(specification=input_specification,
                               optional_specification=optional_specification,
                               data=request, error_class=self.InvalidInputField)

    def validate_response(self, interface_name: str, response: dict) -> bool:
        _, _, output_specification = self.get_specifications(interface_name=interface_name)
        return self.__validate(specification=output_specification, data=response, error_class=self.InvalidInputField)

class AliceSpecification(CharacterSpecification):

    _specifications = alice

class BobSpecification(CharacterSpecification):

    _specifications = bob

class EnricoSpecification(CharacterSpecification):

    _specifications = enrico