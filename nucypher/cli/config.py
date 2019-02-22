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
import collections
import os

import click
from constant_sorrow.constants import NO_PASSWORD
from twisted.logger import Logger
from twisted.logger import globalLogPublisher

from nucypher.config.constants import NUCYPHER_SENTRY_ENDPOINT
from nucypher.utilities.logging import (
    logToSentry,
    getTextFileObserver,
    initialize_sentry,
    getJsonFileObserver)


class NucypherClickConfig:

    __sentry_endpoint = NUCYPHER_SENTRY_ENDPOINT

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


class NucypherDeployerClickConfig(NucypherClickConfig):

    # Deploy Environment Variables
    miner_escrow_deployment_secret = os.environ.get("NUCYPHER_MINER_ESCROW_SECRET", None)
    policy_manager_deployment_secret = os.environ.get("NUCYPHER_POLICY_MANAGER_SECRET", None)
    user_escrow_proxy_deployment_secret = os.environ.get("NUCYPHER_USER_ESCROW_PROXY_SECRET", None)

    Secrets = collections.namedtuple('Secrets', ('miner_secret', 'policy_secret', 'escrow_proxy_secret'))

    def collect_deployment_secrets(self) -> Secrets:

        miner_secret = self.miner_escrow_deployment_secret
        if not miner_secret:
            miner_secret = click.prompt('Enter MinerEscrow Deployment Secret', hide_input=True,
                                        confirmation_prompt=True)

        policy_secret = self.policy_manager_deployment_secret
        if not policy_secret:
            policy_secret = click.prompt('Enter PolicyManager Deployment Secret', hide_input=True,
                                         confirmation_prompt=True)

        escrow_proxy_secret = self.user_escrow_proxy_deployment_secret
        if not escrow_proxy_secret:
            escrow_proxy_secret = click.prompt('Enter UserEscrowProxy Deployment Secret', hide_input=True,
                                               confirmation_prompt=True)

        secrets = self.Secrets(miner_secret=miner_secret,                 # type: str
                               policy_secret=policy_secret,               # type: str
                               escrow_proxy_secret=escrow_proxy_secret    # type: str
                               )
        return secrets


# Register the above click configuration classes as a decorators
nucypher_click_config = click.make_pass_decorator(NucypherClickConfig, ensure=True)
nucypher_deployer_config = click.make_pass_decorator(NucypherDeployerClickConfig, ensure=True)
