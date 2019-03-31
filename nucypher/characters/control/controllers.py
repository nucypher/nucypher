from abc import ABC
from base64 import b64encode, b64decode

from constant_sorrow.constants import NO_WEB_APP_ATTACHED
from flask import Response, Flask
from hendrix.deploy.base import HendrixDeploy
from twisted.logger import Logger

from nucypher.characters.control.emitters import StdoutEmitter, WebEmitter
from nucypher.characters.control.interfaces import AliceInterface, character_control_interface, EnricoInterface, \
    BobInterface
from nucypher.characters.control.serializers import (
    AliceControlJSONSerializer,
    BobControlJSONSerializer,
    EnricoControlJSONSerializer,
    CharacterControlSerializer)
from nucypher.characters.control.specifications import CharacterSpecification


class CharacterController(ABC):
    """
    A transactional interface for a human to  interact with all
    of one characters entry and exit points.

    Subclasses of CharacterController handle a character's public interface I/O,
    serialization, interface specification, validation, and transport.

    (stdio, http, in-memory python containers, other IPC, or another protocol.)
    """

    _control_serializer_class = NotImplemented
    _emitter_class = NotImplemented

    def __init__(self, control_serializer=None, serialize: bool = False):

        # Control Serializer
        self.serializer = control_serializer or self._control_serializer_class()

        # Control Emitter
        self.emitter = self._emitter_class()
        self.emitter.transport_serializer = self.serializer

        # Disables request & response serialization
        self.serialize = serialize


class AliceJSONController(AliceInterface, CharacterController):
    """Serialized and validated JSON controller; Implements Alice's public interfaces"""

    _control_serializer_class = AliceControlJSONSerializer
    _emitter_class = StdoutEmitter

    @character_control_interface
    def create_policy(self, request):
        federated_only = True  # TODO #844: const for now
        serialized_output = self.serializer.load_create_policy_input(request=request)
        result = super().create_policy(**serialized_output, federated_only=federated_only)
        response_data = self.serializer.dump_create_policy_output(response=result)
        return response_data

    @character_control_interface
    def derive_policy_encrypting_key(self, label: str, request=None):
        label_bytes = label.encode()
        result = super().derive_policy_encrypting_key(label=label_bytes)
        response_data = self.serializer.dump_derive_policy_encrypting_key_output(response=result)
        return response_data

    @character_control_interface
    def grant(self, request):
        result = super().grant(**self.serializer.parse_grant_input(request=request))
        response_data = self.serializer.dump_grant_output(response=result)
        return response_data

    @character_control_interface
    def revoke(self, request):
        result = super().revoke(**self.serializer.parse_revoke_input(request=request))
        response_data = result
        return response_data

    @character_control_interface
    def public_keys(self, request):
        """
        Character control endpoint for getting Bob's encrypting and signing public keys
        """
        result = super().public_keys()
        response_data = self.serializer.dump_public_keys_output(response=result)
        return response_data


class BobJSONController(BobInterface, CharacterController):
    """Serialized and validated JSON controller; Implements Bob's public interfaces"""

    _control_serializer_class = BobControlJSONSerializer
    _emitter_class = StdoutEmitter

    @character_control_interface
    def join_policy(self, request):
        """
        Character control endpoint for joining a policy on the network.
        """
        serialized_output = self.serializer.load_join_policy_input(request=request)
        _result = super().join_policy(**serialized_output)
        response = {'policy_encrypting_key': 'OK'}  # FIXME
        return response

    @character_control_interface
    def retrieve(self, request):
        """
        Character control endpoint for re-encrypting and decrypting policy data.
        """
        result = super().retrieve(**self.serializer.load_retrieve_input(request=request))
        response_data = self.serializer.dump_retrieve_output(response=result)
        return response_data

    @character_control_interface
    def public_keys(self, request):
        """
        Character control endpoint for getting Bob's encrypting and signing public keys
        """
        result = super().public_keys()
        response_data = self.serializer.dump_public_keys_output(response=result)
        return response_data


class EnricoJSONController(EnricoInterface, CharacterController):
    """Serialized and validated JSON controller; Implements Enrico's public interfaces"""

    _control_serializer_class = EnricoControlJSONSerializer
    _emitter_class = StdoutEmitter

    @character_control_interface
    def encrypt_message(self, request: str):
        result = super().encrypt_message(**self.serializer.load_encrypt_message_input(request=request))
        response_data = self.serializer.dump_encrypt_message_output(response=result)
        return response_data


class WebController(CharacterController):
    """
    A wrapper around a JSON control interface that
    handles web requests to exert control over a character.
    """

    _emitter_class = WebEmitter
    _crash_on_error_default = False

    _captured_status_codes = {200: 'OK',
                              400: 'BAD REQUEST',
                              500: 'INTERNAL SERVER ERROR'}

    def __init__(self,
                 app_name: str,
                 character_contoller: CharacterController,
                 start_learning: bool = True,
                 crash_on_error: bool = _crash_on_error_default):

        self.app_name = app_name

        # Configuration
        self.start_learning = start_learning
        self.crash_on_error = crash_on_error

        # Control Cycle Handler
        self.emitter = self._emitter_class()

        # Internals
        self._web_app = NO_WEB_APP_ATTACHED
        self._captured_status_codes = NO_WEB_APP_ATTACHED

        # Hard-wire the character's output flow to the WebEmitter
        self._internal_controller = character_contoller
        self._internal_controller.emitter = self.emitter

        super().__init__(control_serializer=self._internal_controller.serializer)

        self.log = Logger(app_name)

    def make_web_controller(self):

        # Serialize For WSGI <-> Bytes <-> Unicode <-> JSON <-> Hex/B64 <-> Native Requests
        self._internal_controller.serialize = True
        self._web_app = Flask(self.app_name)

        # Return FlaskApp decorator
        return self._web_app

    def start(self, http_port: int, dry_run: bool = False):

        self.log.info("Starting HTTP Character Control...")

        if dry_run:
            return

        # TODO #845: Make non-blocking web control startup
        hx_deployer = HendrixDeploy(action="start", options={"wsgi": self._web_app,
                                                             "http_port": http_port})
        hx_deployer.run()  # <--- Blocking Call to Reactor

    def __call__(self, *args, **kwargs):
        return self.__handle_request(*args, **kwargs)

    def __handle_request(self, interface, control_request, *args, **kwargs) -> Response:

        interface_name = interface.__name__

        _400_exceptions = (CharacterSpecification.MissingField,
                           CharacterSpecification.InvalidInputField,
                           CharacterControlSerializer.SerializerError)
        try:
            response = interface(request=control_request.data, *args, **kwargs)  # < ------- INLET

        #
        # Client Errors
        #
        except _400_exceptions as e:
            __exception_code = 400
            return self.emitter(e=e,
                                log_level='debug',
                                response_code=__exception_code,
                                error_message=WebController._captured_status_codes[__exception_code])

        #
        # Server Errors
        #
        except CharacterSpecification.SpecificationError as e:
            __exception_code = 500
            return self.emitter(e=e,
                                log_level='critical',
                                response_code=__exception_code,
                                error_message=WebController._captured_status_codes[__exception_code])

        #
        # Unhandled Server Errors
        #
        except Exception as e:
            __exception_code = 500
            if self.crash_on_error:
                raise
            return self.emitter(e=e,
                                log_level='debug',
                                response_code=__exception_code,
                                error_message=WebController._captured_status_codes[__exception_code])

        #
        # Send to Emitter
        #
        else:
            self.log.debug(f"{interface_name} [200 - OK]")  # TODO - include interface name in metadata
            return response
