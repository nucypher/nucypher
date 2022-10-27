"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import json
import os
from functools import partial
from http import HTTPStatus
from typing import Callable

import click
from flask import Response

import nucypher
from nucypher.utilities.logging import Logger


def null_stream():
    return open(os.devnull, 'w')


class StdoutEmitter:

    class MethodNotFound(BaseException):
        """Cannot find interface method to handle request"""

    transport_serializer = str
    default_color = 'white'

    # sys.stdout.write() TODO: doesn't work well with click_runner's output capture
    default_sink_callable = partial(print, flush=True)

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
             message: str = None,
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

    def pretty(self, response):
        if self.verbosity >= 1:
            click.secho("-" * 90, fg='cyan')
            for k, v in response.items():
                click.secho(k, bold=True)
                click.secho(message=str(v), fg=self.default_color)
                click.secho("-"*90, fg='cyan')

    def error(self, e):
        if self.verbosity >= 1:
            e_str = str(e)
            click.echo(message=e_str, color="red")
            self.log.info(e_str)

    def get_stream(self, verbosity: int = 0):
        if verbosity <= self.verbosity:
            return click.get_text_stream('stdout')
        else:
            return null_stream()


class WebEmitter:

    class MethodNotFound(BaseException):
        """Cannot find interface method to handle request"""

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

    def _log_exception(self, e, error_message, log_level, response_code):
        exception = f"{type(e).__name__}: {str(e)}" if str(e) else type(e).__name__
        message = f"{self} [{str(response_code)} - {error_message}] | ERROR: {exception}"
        logger = getattr(self.log, log_level)
        message_cleaned_for_logger = Logger.escape_format_string(message)
        logger(message_cleaned_for_logger)

    @staticmethod
    def assemble_response(response: dict) -> dict:
        response_data = {'result': response,
                         'version': str(nucypher.__version__)}
        return response_data

    def exception(self,
                  e,
                  error_message: str,
                  log_level: str = 'info',
                  response_code: int = 500):

        self._log_exception(e, error_message, log_level, response_code)
        if self.crash_on_error:
            raise e

        response_message = str(e) or type(e).__name__
        return self.sink(response_message, status=response_code)

    def exception_with_response(self,
                                json_error_response,
                                e,
                                error_message: str,
                                response_code: int,
                                log_level: str = 'info'):
        self._log_exception(e, error_message, log_level, response_code)
        if self.crash_on_error:
            raise e

        assembled_response = self.assemble_response(response=json_error_response)
        serialized_response = WebEmitter.transport_serializer(assembled_response)

        json_response = self.sink(response=serialized_response, status=response_code, content_type="application/json")
        return json_response

    def respond(self, json_response) -> Response:
        assembled_response = self.assemble_response(response=json_response)
        serialized_response = WebEmitter.transport_serializer(assembled_response)

        json_response = self.sink(response=serialized_response, status=HTTPStatus.OK, content_type="application/json")
        return json_response

    def get_stream(self, *args, **kwargs):
        return null_stream()
