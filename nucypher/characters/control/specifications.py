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
            spec = cls.specifications()[interface_name]
        except KeyError:
            raise cls.SpecificationError(f"{cls.__class__.__name__} has no such control interface: '{interface_name}'")

        return spec.get('in', tuple()),\
            spec.get('optional', tuple()),\
            spec.get('out', tuple())

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

    __create_policy = {'in': ('bob_encrypting_key', 'bob_verifying_key', 'm', 'n', 'label', 'expiration'),
                       'optional': ('value',),
                       'out': ('label', 'policy_encrypting_key')}

    __derive_policy_encrypting_key = {'in': ('label', ),
                                      'out': ('policy_encrypting_key', 'label')}

    __grant = {'in': ('bob_encrypting_key', 'bob_verifying_key', 'm', 'n', 'label', 'expiration'),
               'optional': ('value',),
               'out': ('treasure_map', 'policy_encrypting_key', 'alice_verifying_key')}

    __revoke = {'in': ('label', 'bob_verifying_key', ),
                'out': ('failed_revocations',)}

    __decrypt = {'in': ('label', 'message_kit'),
                 'out': ('cleartexts', )}

    __public_keys = {'in': (),
                     'out': ('alice_verifying_key',)}

    _specifications = {'create_policy': __create_policy,  # type: Tuple[Tuple[str]]
                       'derive_policy_encrypting_key': __derive_policy_encrypting_key,
                       'grant': __grant,
                       'revoke': __revoke,
                       'public_keys': __public_keys,
                       'decrypt': __decrypt, }


class BobSpecification(CharacterSpecification):

    __join_policy = {'in': ('label', 'alice_verifying_key'),
                     'out': ('policy_encrypting_key', )}

    __retrieve = {'in': ('label', 'policy_encrypting_key', 'alice_verifying_key', 'message_kit'),
                  'out': ('cleartexts', )}

    __public_keys = {'in': (),
                     'out': ('bob_encrypting_key', 'bob_verifying_key')}

    _specifications = {'join_policy': __join_policy,
                       'retrieve': __retrieve,
                       'public_keys': __public_keys}


class EnricoSpecification(CharacterSpecification):

    __encrypt_message = {'in': ('message', ),
                         'out': ('message_kit', 'signature')}

    _specifications = {'encrypt_message': __encrypt_message}
