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

import click
from twisted.logger import Logger

from nucypher.config.constants import NUCYPHER_SENTRY_ENDPOINT
from nucypher.config.node import CharacterConfiguration
from nucypher.utilities.logging import GlobalLoggerSettings


class NucypherClickConfig:

    # Output Sinks
    capture_stdout = False
    __emitter = None

    # Environment Variables
    config_file = os.environ.get('NUCYPHER_CONFIG_FILE')
    sentry_endpoint = os.environ.get("NUCYPHER_SENTRY_DSN", NUCYPHER_SENTRY_ENDPOINT)
    log_to_sentry = os.environ.get("NUCYPHER_SENTRY_LOGS", True)
    log_to_file = os.environ.get("NUCYPHER_FILE_LOGS", True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Sentry Logging
        if self.log_to_sentry is True:
            GlobalLoggerSettings.start_sentry_logging(self.sentry_endpoint)

        # File Logging
        if self.log_to_file is True:
            GlobalLoggerSettings.start_text_file_logging()
            GlobalLoggerSettings.start_json_file_logging()

        # You guessed it
        self.debug = False

        # Logging
        self.quiet = False
        self.log = Logger(self.__class__.__name__)

    @classmethod
    def attach_emitter(cls, emitter) -> None:
        cls.__emitter = emitter

    @classmethod
    def emit(cls, *args, **kwargs):
        cls.__emitter(*args, **kwargs)


# Register the above click configuration classes as a decorators
nucypher_click_config = click.make_pass_decorator(NucypherClickConfig, ensure=True)
