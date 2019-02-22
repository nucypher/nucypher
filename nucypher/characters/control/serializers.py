import json
from abc import ABC
from base64 import b64decode, b64encode
from json import JSONDecodeError

import maya

import nucypher
from nucypher.characters.control.specifications import CharacterControlSpecification


class CharacterControlSerializer(ABC):

    _serializer = NotImplemented
    _deserializer = NotImplemented

    class SerializerError(ValueError):
        """Invalid data for I/O serialization or deserialization"""


class CharacterControlJsonSerializer(CharacterControlSerializer):

    _serializer = json.dumps
    _deserializer = json.loads

    @staticmethod
    def _build_response(response_data: dict):
        response_data = {'result': response_data, 'version': str(nucypher.__version__)}
        return response_data

    @staticmethod
    def validate_input(request_data: dict, input_specification: tuple) -> bool:
        # Handle client input

        # Invalid Fields
        input_fields = set(request_data.keys())
        extra_fields = input_fields - set(input_specification)

        if extra_fields:
            raise CharacterControlSpecification.InvalidInputField(f"Invalid request fields '{', '.join(extra_fields)}'."
                                                                  f"Valid fields are: {', '.join(input_specification)}.")

        # Missing Fields
        missing_fields = list()
        for field in input_specification:
            if field not in request_data:
                missing_fields.append(field)
        if missing_fields:
            missing = ', '.join(missing_fields)
            raise CharacterControlSpecification.MissingField(f"Request is missing fields: '{missing}'.")
        return True

    @staticmethod
    def validate_output(response_data: dict, output_specification: tuple) -> bool:
        # Handle process output

        for field in output_specification:
            if field not in response_data['result']:
                raise CharacterControlSpecification.InvalidOutputField(f"Response is missing the '{field}' field")
        return True

    def _read(self, request_payload: bytes) -> dict:
        if not request_payload:
            return dict()  # Handle Empty Request Body
        try:
            request_data = CharacterControlJsonSerializer._deserializer(request_payload)

        except JSONDecodeError:
            raise self.SerializerError(f"Invalid protocol input: got {request_payload}")
        return request_data

    def _write(self, response_data: dict, output_specification) -> bytes:
        response_payload = CharacterControlJsonSerializer._serializer(response_data)
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
        unicode_label = response['label'].decode()
        response_data = {'policy_encrypting_key': policy_encrypting_key_hex, 'label': unicode_label}
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


class BobCharacterControlJSONSerializer(CharacterControlJsonSerializer):

    @staticmethod
    def load_join_policy_input(request: dict):
        label_bytes = request['label'].encode()
        alice_signing_key_bytes = bytes.fromhex(request['alice_signing_key'])
        return dict(label=label_bytes, alice_signing_key=alice_signing_key_bytes)

    @staticmethod
    def dump_join_policy_output(response: dict):
        pass  # TODO

    @staticmethod
    def load_retrieve_input(request: dict):
        parsed_input = dict(label=request['label'].encode(),
                            policy_encrypting_key=bytes.fromhex(request['policy_encrypting_key']),
                            alice_signing_key=bytes.fromhex(request['alice_signing_key']),
                            message_kit=b64decode(request['message_kit'].encode()))
        return parsed_input

    @staticmethod
    def dump_retrieve_output(response: dict):
        plaintexts = [b64encode(plaintext).decode() for plaintext in response['plaintexts']]
        response_data = {'plaintexts': plaintexts}
        return response_data

    @staticmethod
    def dump_public_keys_output(response: dict):
        encrypting_key_hex = response['bob_encrypting_key'].to_bytes().hex()
        verifying_key_hex = response['bob_verifying_key'].to_bytes().hex()
        response_data = {'bob_encrypting_key': encrypting_key_hex, 'bob_verifying_key': verifying_key_hex}
        return response_data

