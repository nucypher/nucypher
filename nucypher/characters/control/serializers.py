import json
from abc import ABC
from base64 import b64decode, b64encode
from json import JSONDecodeError
from typing import Union

import maya

import nucypher
from nucypher.characters.control.base import CharacterControlSpecification


class CharacterControlSerializer(ABC):

    _serializer = NotImplemented
    _deserializer = NotImplemented

    class SerializerError(ValueError):
        """Invalid data for I/O serialization or deserialization"""


class CharacterControlJsonSerializer(CharacterControlSerializer):

    _serializer = json.dumps
    _deserializer = json.loads

    def __call__(self, data: Union[bytes, dict], specification: tuple, *args, **kwargs):
        if isinstance(data, bytes):
            self.read(request_payload=data, input_specification=specification)
        elif isinstance(data, dict):
            self.write(response_data=data, output_specification=specification)
        else:
            raise self.SerializerError(f"Invalid serializer input types: Got {data.__class__.__name__}")

    @staticmethod
    def __build_response(response_data: dict):
        response_data = {'result': response_data, 'version': str(nucypher.__version__)}
        return response_data

    @staticmethod
    def __validate_input(request_data: dict, input_specification: tuple) -> bool:
        for field in input_specification:
            if field not in request_data:
                raise CharacterControlSpecification.MissingField(f"Request is missing the '{field}' field")
        return True

    @staticmethod
    def __validate_output(response_data: dict, output_specification: tuple) -> bool:
        for field in output_specification:
            if field not in response_data['result']:
                raise CharacterControlSpecification.InvalidResponseField(f"Response is missing the '{field}' field")
        return True

    def read(self, request_payload: bytes, input_specification: tuple) -> dict:
        if not request_payload:
            return dict()  # Handle Empty Request Body
        try:
            request_data = CharacterControlJsonSerializer._deserializer(request_payload)

        except JSONDecodeError:
            raise self.SerializerError(f"Invalid protocol input: got {request_payload}")

        self.__validate_input(request_data=request_data, input_specification=input_specification)
        return request_data

    def write(self, response_data: dict, output_specification) -> bytes:
        response_data = self.__build_response(response_data=response_data)
        response_payload = CharacterControlJsonSerializer._serializer(response_data)
        self.__validate_output(response_data=response_data, output_specification=output_specification)
        return response_payload


class AliceCharacterControlJsonSerializer(CharacterControlJsonSerializer):

    @staticmethod
    def load_create_policy_input(request: dict):
        parsed_input = dict(bob_encrypting_key=bytes.fromhex(request['bob_encrypting_key']),
                            bob_verifying_key=bytes.fromhex(request['bob_verifying_key']),
                            label=b64decode(request['label']),
                            m=request['m'],
                            n=request['n'])
        return parsed_input

    @staticmethod
    def dump_create_policy_output(response):
        unicode_label = response['label'].decode()
        policy_encrypting_key_hex = response['policy_encrypting_key'].to_bytes().hex()
        response_data = {'label': unicode_label, 'policy_encrypting_key': policy_encrypting_key_hex}
        return response_data

    @staticmethod
    def dump_derive_policy_output(response: dict):
        policy_encrypting_key_hex = bytes(response['policy_encrypting_key']).hex()
        response_data = {'policy_encrypting_key': policy_encrypting_key_hex}
        return response_data

    @staticmethod
    def parse_grant_input(request: dict):
        parsed_input = dict(bob_encrypting_key=bytes.fromhex(request['bob_encrypting_key']),
                            bob_verifying_key=bytes.fromhex(request['bob_verifying_key']),
                            label=request['label'].encode(),
                            m=request['m'],
                            n=request['n'],
                            expiration=maya.MayaDT.from_iso8601(request['expiration']))
        return parsed_input

    @staticmethod
    def dump_grant_output(response: dict):
        treasure_map_base64 = b64encode(bytes(response['treasure_map'])).decode()
        policy_encrypting_key_hex = bytes(response['policy_encrypting_key']).hex()
        alice_signing_key_hex = bytes(response['alice_signing_key']).hex()
        unicode_label = response['label'].decode()

        response_data = {'treasure_map': treasure_map_base64,
                         'policy_encrypting_key': policy_encrypting_key_hex,
                         'alice_signing_key': alice_signing_key_hex,
                         'label': unicode_label}
        return response_data
