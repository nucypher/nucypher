import json
import sys

import click
from flask import Response
from twisted.logger import Logger


class StdoutEmitter:

    transport_serializer = str
    default_color = 'white'

    _sink_callable = sys.stdout.write

    __stdout_trap = list()

    def __init__(self,
                 capture_stdout: bool = False,
                 quiet: bool = False):

        self.name = self.__class__.__name__.lower()
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

    def trap_output(self, output):
        self.__stdout_trap.append(output)

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


class IPCStdoutEmitter(StdoutEmitter):

    transport_serializer = json.dumps

    def _emit(self, response: dict = None, message: str = None, *args, **kwargs) -> None:
        """
        Write data to stdout.  For machine consumption only.
        """

        if not (bool(response) ^ bool(message)):
            raise ValueError(f"response or message is required to emit a IPC message; Got {(response, message)}")

        if message:
            # If a message is received that is not an IPC message
            # while running in IPC mode, log it and move on.
            self.log.debug(message)
            return

        elif response:

            # Serialize IPC Message
            serialized_response = IPCStdoutEmitter.transport_serializer(response)

            # Capture Message Output
            if self.capture_stdout:
                return self.trap_output(serialized_response)

            # Write to stdout file descriptor
            else:
                number_of_written_bytes = sys.stdout.write(serialized_response)  # < ------ STANDARD OUT
                return number_of_written_bytes


class WebEmitter:

    _sink_callable = Response
    _crash_on_error_default = False
    transport_serializer = json.dumps

    def __init__(self, crash_on_error: bool = _crash_on_error_default):
        self.crash_on_error = crash_on_error
        super().__init__()

        self.log = Logger('web-emitter')

    def __call__(self, *args, **kwargs):
        if 'response' in kwargs:
            return self.__emit_http_response(*args, **kwargs)
        else:
            return self.__emit_exception(*args, **kwargs)

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
        return drone_character._sink_callable(str(e), status=response_code)

    def __emit_http_response(drone_character, response) -> Response:
        serialized_response = WebEmitter.transport_serializer(response)
        response = drone_character._sink_callable(serialized_response, status=200)  # < ---------- HTTP OUTPUT
        response.headers["Content-Type"] = "application/json"
        return response
