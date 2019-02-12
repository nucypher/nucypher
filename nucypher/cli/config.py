"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.

"""

import os

import click
from constant_sorrow.constants import NO_PASSWORD
from twisted.logger import Logger
from twisted.logger import globalLogPublisher

from nucypher.cli.painting import BANNER
from nucypher.utilities.logging import (
    logToSentry,
    getTextFileObserver,
    initialize_sentry,
    getJsonFileObserver)


class NucypherClickConfig:

    __sentry_endpoint = "https://d8af7c4d692e4692a455328a280d845e@sentry.io/1310685"  # TODO: Use nucypher domain

    # Environment Variables
    config_file = os.environ.get('NUCYPHER_CONFIG_FILE', None)
    sentry_endpoint = os.environ.get("NUCYPHER_SENTRY_DSN", __sentry_endpoint)
    log_to_sentry = os.environ.get("NUCYPHER_SENTRY_LOGS", True)
    log_to_file = os.environ.get("NUCYPHER_FILE_LOGS", True)

    # Sentry Logging
    if log_to_sentry is True:
        initialize_sentry(dsn=__sentry_endpoint)
        globalLogPublisher.addObserver(logToSentry)

    # File Logging
    if log_to_file is True:
        globalLogPublisher.addObserver(getTextFileObserver())
        globalLogPublisher.addObserver(getJsonFileObserver())

    def __init__(self):
        self.log = Logger(self.__class__.__name__)
        self.__keyring_password = NO_PASSWORD

    def get_password(self, confirm: bool =False) -> str:
        keyring_password = os.environ.get("NUCYPHER_KEYRING_PASSWORD", NO_PASSWORD)

        if keyring_password is NO_PASSWORD:  # Collect password, prefer env var
            prompt = "Enter keyring password"
            keyring_password = click.prompt(prompt, confirmation_prompt=confirm, hide_input=True)

        self.__keyring_password = keyring_password
        return self.__keyring_password


# Register the above click configuration class as a decorator
nucypher_click_config = click.make_pass_decorator(NucypherClickConfig, ensure=True)


def echo_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.secho(BANNER, bold=True)
    ctx.exit()
