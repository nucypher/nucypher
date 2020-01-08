
from nucypher.characters.control.specifications.bob import specifications as bob
from nucypher.characters.control.specifications.alice import specifications as alice
from nucypher.characters.control.specifications.enrico import specifications as enrico
from nucypher.characters.control.specifications.exceptions import (
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
    def get_serializer(cls, interface_name: str) -> tuple:
        try:
            spec = cls.specifications()[interface_name]
        except KeyError:
            raise cls.SpecificationError(f"{cls.__class__.__name__} has no such control interface: '{interface_name}'")

        return spec

    @classmethod
    def get_specifications(cls, interface_name: str) -> tuple:
        spec = cls.get_serializer(interface_name)

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

class AliceSpecification(CharacterSpecification):

    _specifications = alice

class BobSpecification(CharacterSpecification):

    _specifications = bob

class EnricoSpecification(CharacterSpecification):

    _specifications = enrico