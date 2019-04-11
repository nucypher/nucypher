import json
from abc import ABC
from base64 import b64decode, b64encode
from json import JSONDecodeError
from typing import Callable

import maya

import nucypher
from nucypher.characters.control.specifications import CharacterSpecification


class CharacterControlSerializer(ABC):

    class SerializerError(ValueError):
        """Invalid data for I/O serialization or deserialization"""


class CharacterControlJSONSerializer(CharacterControlSerializer):

    def __call__(self, data, specification: tuple, *args, **kwargs):
        if isinstance(data, dict):
            return self.__serialize(response_data=data)
        elif isinstance(data, bytes):
            return self.__deserialize(request_payload=data)
        else:
            error_message = f"{self.__class__.__name__} only accepts dict or bytes as input. Got {data.__class__.__name__} "
            raise ValueError(error_message)

    @staticmethod
    def build_response_metadata(response: dict, duration: maya.timedelta) -> dict:
        response_data = {'result': response,
                         'version': str(nucypher.__version__),
                         'duration': str(duration)}
        return response_data

    def __deserialize(self, request_payload: bytes) -> dict:

        # Deserialize
        if not request_payload:
            request_data = dict()  # Handle Empty Request Body
        else:
            try:
                request_data = json.loads(request_payload)
            except JSONDecodeError:
                raise self.SerializerError(f"Invalid {self.__class__.__name__} input: got {request_payload}")

        # Validate
        return request_data

    def __serialize(self, response_data: dict) -> bytes:

        # Serialize
        try:
            response_data = json.dumps(response_data)
        except TypeError as e:
            raise self.SerializerError(f"Invalid serializer output; {response_data} is not JSON serializable. "
                                       f"Original exception: {str(e)}")

        return response_data


class AliceControlJSONSerializer(CharacterControlJSONSerializer):

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
    def dump_derive_policy_encrypting_key_output(response: dict):
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

        # FIXME: Differences in bytes casters by default :-(
        policy_encrypting_key_hex = bytes(response['policy_encrypting_key']).hex()
        alice_verifying_key_hex = bytes(response['alice_verifying_key']).hex()

        response_data = {'treasure_map': treasure_map_base64,
                         'policy_encrypting_key': policy_encrypting_key_hex,
                         'alice_verifying_key': alice_verifying_key_hex}

        return response_data

    @staticmethod
    def parse_revoke_input(request: dict):
        parsed_input = dict(label=request['label'].encode(),
                            bob_verifying_key=bytes.fromhex(request['bob_verifying_key']))
        return parsed_input

    @staticmethod
    def dump_public_keys_output(response: dict):
        verifying_key_hex = response['alice_verifying_key'].to_bytes().hex()
        response_data = {'alice_verifying_key': verifying_key_hex}
        return response_data


class MessageHandlerMixin:

    __message_kit_transport_encoder = b64encode
    __message_kit_transport_decoder = b64decode

    def set_message_encoder(self, encoder: Callable):
        self.__message_kit_transport_encoder = encoder

    def set_message_decoder(self, decoder: Callable):
        self.__message_kit_transport_decoder = decoder

    def encode(self, plaintext: bytes) -> str:
        return MessageHandlerMixin.__message_kit_transport_encoder(plaintext).encode()

    def decode(self, cleartext: bytes) -> bytes:
        return MessageHandlerMixin.__message_kit_transport_decoder(cleartext)


class BobControlJSONSerializer(CharacterControlJSONSerializer, MessageHandlerMixin):

    @staticmethod
    def load_join_policy_input(request: dict):
        label_bytes = request['label'].encode()
        alice_verifying_key_bytes = bytes.fromhex(request['alice_verifying_key'])
        return dict(label=label_bytes, alice_verifying_key=alice_verifying_key_bytes)

    @staticmethod
    def dump_join_policy_output(response: dict):
        pass  # TODO

    def load_retrieve_input(self, request: dict):
        parsed_input = dict(label=request['label'].encode(),
                            policy_encrypting_key=bytes.fromhex(request['policy_encrypting_key']),
                            alice_verifying_key=bytes.fromhex(request['alice_verifying_key']),
                            message_kit=self.decode(request['message_kit']))
        return parsed_input

    def dump_retrieve_output(self, response: dict):
        cleartexts = [cleartext.decode() for cleartext in response['cleartexts']]
        response_data = {'cleartexts': cleartexts}
        return response_data

    @staticmethod
    def dump_public_keys_output(response: dict):
        encrypting_key_hex = response['bob_encrypting_key'].to_bytes().hex()
        verifying_key_hex = response['bob_verifying_key'].to_bytes().hex()
        response_data = {'bob_encrypting_key': encrypting_key_hex, 'bob_verifying_key': verifying_key_hex}
        return response_data


class EnricoControlJSONSerializer(CharacterControlJSONSerializer, MessageHandlerMixin):

    @staticmethod
    def load_encrypt_message_input(request: dict):
        plaintext = b64encode(bytes(request['message'], encoding='utf-8')).decode()
        response_data = {'message': plaintext}
        return response_data

    @staticmethod
    def dump_encrypt_message_output(response: dict):
        response_data = {'message_kit': b64encode(response['message_kit'].to_bytes()).decode(),
                         'signature': b64encode(bytes(response['signature'])).decode()}
        return response_data
