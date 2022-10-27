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


import os
from functools import partial
from typing import Callable

import click

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
