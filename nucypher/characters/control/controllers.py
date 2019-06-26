import inspect
import json
from abc import ABC, abstractmethod
from json import JSONDecodeError
from typing import Callable

from flask import Response, Flask
from hendrix.deploy.base import HendrixDeploy
from twisted.internet import reactor, stdio
from twisted.logger import Logger

from nucypher.characters.control.emitters import StdoutEmitter, WebEmitter, JSONRPCStdoutEmitter
from nucypher.characters.control.interfaces import (
    AliceInterface,
    character_control_interface,
    EnricoInterface,
    BobInterface
)
from nucypher.characters.control.serializers import (
    AliceControlJSONSerializer,
    BobControlJSONSerializer,
    EnricoControlJSONSerializer,
    CharacterControlSerializer
)
from nucypher.characters.control.specifications import CharacterSpecification
from nucypher.cli.processes import JSONRPCLineReceiver
from nucypher.utilities.controllers import JSONRPCTestClient


class CharacterControllerBase(ABC):
    """
    A transactional interface for a human to  interact with all
    of one characters entry and exit points.

    Subclasses of CharacterControllerBase handle a character's public interface I/O,
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


class AliceJSONController(AliceInterface, CharacterControllerBase):
    """Serialized and validated JSON controller; Implements Alice's public interfaces"""

    _control_serializer_class = AliceControlJSONSerializer
    _emitter_class = StdoutEmitter

    @character_control_interface
    def create_policy(self, request):
        serialized_output = self.serializer.load_create_policy_input(request=request)
        result = super().create_policy(**serialized_output)
        response_data = self.serializer.dump_create_policy_output(response=result)
        return response_data

    @character_control_interface
    def derive_policy_encrypting_key(self, label: str = None, request=None):
        if label:
            label_bytes = label.encode()

        else:
            label_bytes = request['label'].encode()

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
    def decrypt(self, request: dict):
        result = super().decrypt(**self.serializer.load_decrypt_input(request=request))
        response_data = self.serializer.dump_decrypt_output(response=result)
        return response_data

    @character_control_interface
    def public_keys(self, request):
        """
        Character control endpoint for getting Bob's encrypting and signing public keys
        """
        result = super().public_keys()
        response_data = self.serializer.dump_public_keys_output(response=result)
        return response_data


class BobJSONController(BobInterface, CharacterControllerBase):
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


class EnricoJSONController(EnricoInterface, CharacterControllerBase):
    """Serialized and validated JSON controller; Implements Enrico's public interfaces"""

    _control_serializer_class = EnricoControlJSONSerializer
    _emitter_class = StdoutEmitter

    @character_control_interface
    def encrypt_message(self, request: str):
        result = super().encrypt_message(**self.serializer.load_encrypt_message_input(request=request))
        response_data = self.serializer.dump_encrypt_message_output(response=result)
        return response_data


class CharacterControlServer(CharacterControllerBase):

    _emitter_class = StdoutEmitter
    _crash_on_error_default = False

    def __init__(self,
                 app_name: str,
                 character_controller: CharacterControllerBase,
                 start_learning: bool = True,
                 crash_on_error: bool = _crash_on_error_default):

        self.app_name = app_name

        # Configuration
        self.start_learning = start_learning
        self.crash_on_error = crash_on_error

        # Control Cycle Handler
        self.emitter = self._emitter_class()

        # Internals
        self._transport = None

        # Hard-wire the character's output flow to the Emitter
        self._internal_controller = character_controller
        self._internal_controller.emitter = self.emitter

        super().__init__(control_serializer=self._internal_controller.serializer)

        self.log = Logger(app_name)

    @abstractmethod
    def make_control_transport(self):
        return NotImplemented

    @abstractmethod
    def handle_request(self, interface, control_request, *args, **kwargs):
        return NotImplemented

    @abstractmethod
    def test_client(self):
        return NotImplemented


class JSONRPCController(CharacterControlServer):

    _emitter_class = JSONRPCStdoutEmitter

    def start(self):
        _transport = self.make_control_transport()
        reactor.run()  # < ------ Blocking Call (Reactor)

    def test_client(self) -> JSONRPCTestClient:
        test_client = JSONRPCTestClient(rpc_controller=self)
        return test_client

    def make_control_transport(self):
        transport = stdio.StandardIO(JSONRPCLineReceiver(rpc_controller=self))
        return transport

    def get_interface(self, name: str) -> Callable:

        # Examine the controller interface
        interfaces = inspect.getmembers(self._internal_controller,
                                        predicate=inspect.ismethod)

        # Generate a mapping of the public interfaces
        interfaces = {i[0]: i[1] for i in interfaces if not i[0].startswith('_')}

        try:
            interface = interfaces[name]
        except KeyError:
            raise self.emitter.MethodNotFound

        return interface

    def handle_server_notification(self, notification_request) -> int:
        pass

    def handle_procedure_call(self, control_request, *args, **kwargs) -> int:

        # Validate request and read request metadata
        jsonrpc2 = control_request['jsonrpc']
        if jsonrpc2 != '2.0':
            raise self.emitter.InvalidRequest

        request_id = control_request['id']

        # Read the interface's signature metadata
        method_name = control_request['method']
        method_params = control_request.get('params', dict())  # optional

        # Lookup the public interface
        interface = self.get_interface(name=method_name)

        # Call the internal interface | pipe to output
        return interface(request=method_params, request_id=request_id, *args, **kwargs)  # < ------- INLET

    def validate_request(self, request: dict):

        #
        # Phase 1 - Metadata
        #

        required_fields = {'jsonrpc', 'method'}
        optional_fields = {'id', 'params'}
        all_fields = required_fields | optional_fields

        try:
            input_fields = set(request.keys())
        except AttributeError:
            raise self.emitter.InvalidRequest

        contains_required_fields = required_fields.issubset(input_fields)

        unique_fields = all_fields - input_fields - optional_fields
        contains_valid_fields = not bool(unique_fields)

        is_valid = all((contains_required_fields,
                        contains_valid_fields))

        if not is_valid:
            raise self.emitter.InvalidRequest

        #
        # Phase 2 - Content Type
        #

        method_name = request['method']

        try:
            int(method_name)  # must not be a number
        except ValueError:
            valid_method_name = True
        else:
            valid_method_name = False

        is_valid = all((valid_method_name, ))

        if not is_valid:
            raise self.emitter.InvalidRequest

        return is_valid

    def handle_message(self, message: dict, *args, **kwargs) -> int:
        """Handle single JSON RPC message"""

        # Validate incoming message
        self.validate_request(request=message)

        try:
            _request_id = message['id']

        except KeyError:  # Notification
            return self.handle_server_notification(notification_request=message)

        else:             # RPC
            return self.handle_procedure_call(control_request=message, *args, **kwargs)

    def handle_batch(self, control_requests: list) -> int:

        if not control_requests:
            e = self.emitter.InvalidRequest()
            return self.emitter.error(e)

        batch_size = 0
        for request in control_requests:  # TODO: parallelism
            response_size = self.handle_message(message=request)
            batch_size += response_size
        return batch_size

    def handle_request(self, control_request: bytes, *args, **kwargs) -> int:

        try:
            control_request = json.loads(control_request)
        except JSONDecodeError:
            e = self.emitter.ParseError()
            return self.emitter.error(e)

        # Handle batch of messages
        if isinstance(control_request, list):
            return self.handle_batch(control_requests=control_request)

        # Handle single message
        try:
            return self.handle_message(message=control_request, *args, **kwargs)

        except self.emitter.JSONRPCError as e:
            return self.emitter.error(e)

        except Exception as e:
            if self.crash_on_error:
                raise
            return self.emitter.error(e)


class WebController(CharacterControlServer):
    """
    A wrapper around a JSON control interface that
    handles web requests to exert control over a character.
    """

    _emitter_class = WebEmitter
    _crash_on_error_default = False

    _captured_status_codes = {200: 'OK',
                              400: 'BAD REQUEST',
                              500: 'INTERNAL SERVER ERROR'}

    def test_client(self):
        test_client = self._transport.test_client()

        # ease your mind
        self._transport.config.update(TESTING=self.crash_on_error, PROPOGATE_EXCEPTION=self.crash_on_error)

        return test_client

    def make_control_transport(self):

        # Serialize For WSGI <-> Bytes <-> Unicode <-> JSON <-> Hex/B64 <-> Native Requests
        self._internal_controller.serialize = True
        self._transport = Flask(self.app_name)

        # Return FlaskApp decorator
        return self._transport

    def start(self, http_port: int, dry_run: bool = False):

        self.log.info("Starting HTTP Character Control...")
        if dry_run:
            return

        # TODO #845: Make non-blocking web control startup
        hx_deployer = HendrixDeploy(action="start", options={"wsgi": self._transport, "http_port": http_port})
        hx_deployer.run()  # <--- Blocking Call to Reactor

    def __call__(self, *args, **kwargs):
        return self.handle_request(*args, **kwargs)

    def handle_request(self, interface, control_request, *args, **kwargs) -> Response:

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
            return self.emitter.exception(
                e=e,
                log_level='debug',
                response_code=__exception_code,
                error_message=WebController._captured_status_codes[__exception_code])

        #
        # Server Errors
        #
        except CharacterSpecification.SpecificationError as e:
            __exception_code = 500
            if self.crash_on_error:
                raise
            return self.emitter.exception(
                e=e,
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
            return self.emitter.exception(
                e=e,
                log_level='debug',
                response_code=__exception_code,
                error_message=WebController._captured_status_codes[__exception_code])

        #
        # Send to WebEmitter
        #
        else:
            self.log.debug(f"{interface_name} [200 - OK]")
            return response
