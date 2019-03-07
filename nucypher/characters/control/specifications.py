from abc import ABC


class CharacterSpecification(ABC):

    _specifications = NotImplemented

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
        if cls._specifications is NotImplemented:
            raise NotImplementedError("Missing specifications for character")
        try:
            input_specification, output_specification = cls.specifications()[interface_name]
        except KeyError:
            raise cls.SpecificationError(f"No Such Control Interface '{interface_name}'")

        return input_specification, output_specification

    @classmethod
    def specifications(cls):
        if cls._specifications is NotImplemented:
            raise NotImplementedError
        else:
            return cls._specifications


class AliceSpecification(CharacterSpecification):

    __create_policy = (('bob_encrypting_key', 'bob_verifying_key', 'm', 'n', 'label'),  # In
                       ('label', 'policy_encrypting_key'))                              # Out

    __derive_policy_encrypting_key = (('label', ),                         # In
                                     ('policy_encrypting_key', 'label'))   # Out

    __grant = (('bob_encrypting_key', 'bob_verifying_key', 'm', 'n', 'label', 'expiration'),  # In
               ('treasure_map', 'policy_encrypting_key', 'alice_verifying_key'))              # Out

    # TODO: Implement Revoke Spec
    __revoke = ((),  # In
                ())  # Out

    __public_keys = ((),
                     ('alice_verifying_key',))

    _specifications = {'create_policy': __create_policy,  # type: Tuple[Tuple[str]]
                       'derive_policy_encrypting_key': __derive_policy_encrypting_key,
                       'grant': __grant,
                       'revoke': __revoke,
                       'public_keys': __public_keys}


class BobSpecification(CharacterSpecification):

    __join_policy = (('label', 'alice_verifying_key'),
                     ('policy_encrypting_key', ))

    __retrieve = (('label', 'policy_encrypting_key', 'alice_verifying_key', 'message_kit'),
                  ('cleartexts', ))

    __public_keys = ((),
                     ('bob_encrypting_key', 'bob_verifying_key'))

    _specifications = {'join_policy': __join_policy,
                       'retrieve': __retrieve,
                       'public_keys': __public_keys}


class EnricoSpecification(CharacterSpecification):

    __encrypt_message = (('message', ),
                         ('message_kit', 'signature'))

    _specifications = {'encrypt_message': __encrypt_message}
