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


class AliceSpecification(CharacterControlSpecification):

    __create_policy = (('bob_encrypting_key', 'bob_verifying_key', 'm', 'n', 'label'),  # In
                       ('label', 'policy_encrypting_key'))                              # Out

    __derive_policy = (('label', ),                 # In
                       ('policy_encrypting_key', 'label'))  # Out

    __grant = (('bob_encrypting_key', 'bob_verifying_key', 'm', 'n', 'label', 'expiration'),   # In
               ('treasure_map', 'policy_encrypting_key', 'alice_signing_key', 'label'))        # Out

    # TODO: Implement Revoke Spec
    __revoke = ((),  # In
                ())  # Out

    specifications = {'create_policy': __create_policy,  # type: Tuple[Tuple[str]]
                      'derive_policy': __derive_policy,
                      'grant': __grant,
                      'revoke': __revoke}


class BobSpecification(CharacterControlSpecification):

    __join_policy = (('label', 'alice_signing_key'),
                     ('policy_encrypting_key', ))

    __retrieve = (('label', 'policy_encrypting_key', 'alice_signing_key', 'message_kit'),
                  ('plaintexts', ))

    __public_keys = ((),
                     ('bob_encrypting_key', 'bob_verifying_key'))

    specifications = {'join_policy': __join_policy,
                      'retrieve': __retrieve,
                      'public_keys': __public_keys}
