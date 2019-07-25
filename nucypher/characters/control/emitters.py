import json
import sys
from typing import Callable, Union

import click
from flask import Response
from twisted.logger import Logger

import nucypher


class StdoutEmitter:

    transport_serializer = str
    default_color = 'white'

    # sys.stdout.write() doesn't work well with click_runner's output capture
    default_sink_callable = print

    def __init__(self,
                 sink: Callable = None,
                 verbosity: int = 1):

        self.name = self.__class__.__name__.lower()
        self.sink = sink or self.default_sink_callable
        self.verbosity = verbosity
        self.log = Logger(self.name)

    def clear(self):
        if self.verbosity >= 1:
            click.clear()

    def message(self,
                message: str,
                color: str = None,
                bold: bool = False,
                verbosity: int = 1):
        self.echo(message, color=color or self.default_color, bold=bold, verbosity=verbosity)
        self.log.debug(message)

    def echo(self,
             message: str,
             color: str = None,
             bold: bool = False,
             nl: bool = True,
             verbosity: int = 0):
        if verbosity <= self.verbosity:
            click.secho(message=message, fg=color or self.default_color, bold=bold, nl=nl)

    def banner(self, banner):
        if self.verbosity >= 1:
            click.echo(banner)

    def ipc(self, response: dict, request_id: int, duration):
        # WARNING: Do not log in this block
        if self.verbosity >= 1:
            for k, v in response.items():
                click.secho(message=f'{k} ...... {v}', fg=self.default_color)

    def error(self, e):
        if self.verbosity >= 1:
            e_str = str(e)
            click.echo(message=e_str)
            self.log.info(e_str)


class JSONRPCStdoutEmitter(StdoutEmitter):

    transport_serializer = json.dumps
    delimiter = '\n'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log = Logger("JSON-RPC-Emitter")

    class JSONRPCError(RuntimeError):
        code = None
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
                delimiter = bytes(delimiter, encoding='utf-8')
            serialized_response = delimiter + serialized_response

        return serialized_response

    def __write(self, data: dict):
        """Outlet"""

        serialized_response = self.__serialize(data=data)

        # Write to stdout file descriptor
        number_of_written_bytes = self.sink(serialized_response)  # < ------ OUTLET
        return number_of_written_bytes

    def clear(self):
        pass

    def message(self, message: str, **kwds):
        self.log.debug(message)

    def echo(self, *args, **kwds):
        pass

    def banner(self, banner):
        pass

    def ipc(self, response: dict, request_id: int, duration) -> int:
        """
        Write RPC response object to stdout and return the number of bytes written.
        """

        # Serialize JSON RPC Message
        assembled_response = self.assemble_response(response=response, message_id=request_id)
        size = self.__write(data=assembled_response)
        self.log.info(f"OK | Responded to IPC request #{request_id} with {size} bytes, took {duration}")
        return size

    def error(self, e):
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
        # self.log.info(f"Error {e.code} | {e.message}")  # TODO: Restore this log message
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

    @staticmethod
    def assemble_response(response: dict, request_id: int, duration) -> dict:
        response_data = {'result': response,
                         'version': str(nucypher.__version__),
                         'id': str(request_id),
                         'duration': str(duration)}
        return response_data

    def exception(drone_character,
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

    def ipc(drone_character, response, request_id, duration) -> Response:
        assembled_response = drone_character.assemble_response(response=response,
                                                               request_id=request_id,
                                                               duration=duration)
        serialized_response = WebEmitter.transport_serializer(assembled_response)

        # ---------- HTTP OUTPUT
        response = drone_character.sink(response=serialized_response, status=200, content_type="application/json")
        return response
