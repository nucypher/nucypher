import json
import sys
from typing import Callable, Union

import click
import maya
from flask import Response
from twisted.logger import Logger

import nucypher


class StdoutEmitter:

    transport_serializer = str
    default_color = 'white'
    default_sink_callable = sys.stdout.write

    __stdout_trap = list()

    def __init__(self,
                 sink: Callable = None,
                 capture_stdout: bool = False,
                 quiet: bool = False):

        self.name = self.__class__.__name__.lower()
        self.sink = sink or self.default_sink_callable
        self.capture_stdout = capture_stdout
        self.quiet = quiet
        self.log = Logger(self.name)

        super().__init__()

    def __call__(self, *args, **kwargs):
        try:
            return self._emit(*args, **kwargs)
        except Exception:
            self.log.debug("Error while emitting nucypher controller output")
            raise

    def trap_output(self, output) -> int:
        self.__stdout_trap.append(output)
        return len(bytes(output))  # number of bytes written

    def _emit(self,
              response: dict = None,
              message: str = None,
              color: str = None,
              bold: bool = False,
              ) -> None:

        """
        Write pretty messages to stdout.  For Human consumption only.
        """
        if response and message:
            raise ValueError(f'{self.__class__.__name__} received both a response and a message.')

        if self.quiet:
            # reduces the number of CLI conditionals by
            # wrapping console output functions
            return

        if self.capture_stdout:
            self.trap_output(response or message)

        elif response:
            # WARNING: Do not log in this block
            for k, v in response.items():
                click.secho(message=f'{k} ...... {v}',
                            fg=color or self.default_color,
                            bold=bold)

        elif message:
            # Most likely a message emitted without a character control instance
            click.secho(message=message, fg=color or self.default_color, bold=bold)
            self.log.debug(message)

        else:
            raise ValueError('Either "response" dict or "message" str is required, but got neither.')


class JSONRPCStdoutEmitter(StdoutEmitter):

    transport_serializer = json.dumps
    default_sink_callable = print
    delimiter = '\n'

    def __init__(self, sink: Callable = None, *args, **kwargs):
        self.sink = sink or self.default_sink_callable
        super().__init__(*args, **kwargs)

        self.log = Logger("JSON-RPC-Emitter")

    class JSONRPCError(RuntimeError):
        message = "Unknown JSON-RPC Error"

    class ParseError(JSONRPCError):
        code = -32700
        message = "Invalid JSON was received by the server."

    class InvalidRequest(JSONRPCError):
        code = -32600
        message = "The JSON sent is not a valid Request object."

    class MethodNotFound(JSONRPCError):
        code = -32601
        message = "The method does not exist / is not available."

    class InvalidParams(JSONRPCError):
        code = -32602
        message = "Invalid method parameter(s)."

    class InternalError(JSONRPCError):
        code = -32603
        message = "Internal JSON-RPC error."

    def __call__(self, *args, **kwargs):
        if 'response' in kwargs:
            return self.__emit_rpc_response(*args, **kwargs)
        elif 'message' in kwargs:
            if not self.quiet:
                self.log.info(*args, **kwargs)
        elif 'e' in kwargs:
            return self.__emit_rpc_error(*args, **kwargs)
        else:
            raise self.JSONRPCError("Internal Error")

    @staticmethod
    def assemble_response(response: dict, message_id: int) -> dict:
        response_data = {'jsonrpc': '2.0',
                         'id': str(message_id),
                         'result': response}
        return response_data

    @staticmethod
    def assemble_error(message, code, data=None) -> dict:
        response_data = {'jsonrpc': '2.0',
                         'error': {'code': str(code),
                                   'message': str(message),
                                   'data': data},
                         'id': None}  # error has no ID
        return response_data

    def __serialize(self, data: dict, delimiter=delimiter, as_bytes: bool = False) -> Union[str, bytes]:

        # Serialize
        serialized_response = JSONRPCStdoutEmitter.transport_serializer(data)   # type: str

        if as_bytes:
            serialized_response = bytes(serialized_response, encoding='utf-8')  # type: bytes

        # Add delimiter
        if delimiter:
            if as_bytes:
                delimiter = bytes(delimiter, encoding='utf=8')
            serialized_response = delimiter + serialized_response

        return serialized_response

    def __write(self, data: dict):
        """Outlet"""

        serialized_response = self.__serialize(data=data)

        # Capture Message Output
        if self.capture_stdout:
            return self.trap_output(serialized_response)

        # Write to stdout file descriptor
        else:
            number_of_written_bytes = self.sink(serialized_response)  # < ------ OUTLET
            return number_of_written_bytes

    def __emit_rpc_error(self, e):
        """
        Write RPC error object to stdout and return the number of bytes written.
        """
        try:
            assembled_error = self.assemble_error(message=e.message, code=e.code)
        except AttributeError:
            if not isinstance(e, self.JSONRPCError):
                self.log.info(str(e))
                raise e  # a different error was raised
            else:
                raise self.JSONRPCError

        size = self.__write(data=assembled_error)
        if not self.quiet:
            self.log.info(f"Error {e.code} | {e.message}")
        return size

    def __emit_rpc_response(self, response: dict, request_id: int, duration) -> int:
        """
        Write RPC response object to stdout and return the number of bytes written.
        """

        # Serialize JSON RPC Message
        assembled_response = self.assemble_response(response=response, message_id=request_id)
        size = self.__write(data=assembled_response)
        if not self.quiet:
            self.log.info(f"OK | Responded to IPC request #{request_id} with {size} bytes, took {duration}")
        return size


class WebEmitter:

    _crash_on_error_default = False
    transport_serializer = json.dumps
    _default_sink_callable = Response

    def __init__(self,
                 sink: Callable = None,
                 crash_on_error: bool = _crash_on_error_default,
                 *args, **kwargs):

        self.sink = sink or self._default_sink_callable
        self.crash_on_error = crash_on_error
        super().__init__(*args, **kwargs)

        self.log = Logger('web-emitter')

    def __call__(self, *args, **kwargs):
        if 'response' in kwargs:
            return self.__emit_http_response(*args, **kwargs)
        else:
            return self.__emit_exception(*args, **kwargs)

    @staticmethod
    def assemble_response(response: dict, request_id: int, duration) -> dict:
        response_data = {'result': response,
                         'version': str(nucypher.__version__),
                         'id': str(request_id),
                         'duration': str(duration)}
        return response_data

    def __emit_exception(drone_character,
                         e,
                         error_message: str,
                         log_level: str = 'info',
                         response_code: int = 500):

        message = f"{drone_character} [{str(response_code)} - {error_message}] | ERROR: {str(e)}"
        logger = getattr(drone_character.log, log_level)
        logger(message)
        if drone_character.crash_on_error:
            raise e
        return drone_character.sink(str(e), status=response_code)

    def __emit_http_response(drone_character, response, request_id, duration) -> Response:
        assembled_response = drone_character.assemble_response(response=response,
                                                               request_id=request_id,
                                                               duration=duration)
        serialized_response = WebEmitter.transport_serializer(assembled_response)

        # ---------- HTTP OUTPUT
        response = drone_character.sink(response=serialized_response, status=200, content_type="application/json")
        return response
