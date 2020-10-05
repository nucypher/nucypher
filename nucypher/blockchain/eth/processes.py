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
import time
from eth_utils.address import to_checksum_address
from geth.accounts import get_accounts, create_new_account
from geth.chain import get_chain_data_dir
from geth.mixins import LoggingMixin
from geth.process import BaseGethProcess

from nucypher.config.constants import USER_LOG_DIR, DEFAULT_CONFIG_ROOT
from nucypher.utilities.logging import Logger


class NuCypherGethProcess(LoggingMixin, BaseGethProcess):

    IPC_PROTOCOL = 'http'
    IPC_FILENAME = 'geth.ipc'
    VERBOSITY = 5
    CHAIN_ID = NotImplemented
    _CHAIN_NAME = NotImplemented

    _LOG_NAME = 'nucypher-geth'
    LOG = Logger(_LOG_NAME)
    LOG_PATH = os.path.join(USER_LOG_DIR, f'{LOG}.log')

    def __init__(self,
                 geth_kwargs: dict,
                 stdout_logfile_path: str = LOG_PATH,
                 stderr_logfile_path: str = LOG_PATH,
                 *args, **kwargs):

        super().__init__(geth_kwargs=geth_kwargs,
                         stdout_logfile_path=stdout_logfile_path,
                         stderr_logfile_path=stderr_logfile_path,
                         *args, **kwargs)

    def provider_uri(self, scheme: str = None) -> str:
        if not scheme:
            scheme = self.IPC_PROTOCOL
        if scheme in ('file', 'ipc'):
            location = self.ipc_path
        elif scheme in ('http', 'ws'):
            location = f'{self.rpc_host}:{self.rpc_port}'
        else:
            raise ValueError(f'{scheme} is an unknown ethereum node IPC protocol.')

        uri = f"{scheme}://{location}"
        return uri

    def start(self, timeout: int = 30, extra_delay: int = 1):
        self.LOG.info(f"STARTING GETH NOW | CHAIN ID {self.CHAIN_ID} | {self.IPC_PROTOCOL}://{self.ipc_path}")
        super().start()
        self.wait_for_ipc(timeout=timeout)  # on for all nodes by default
        if self.IPC_PROTOCOL in ('rpc', 'http'):
            self.wait_for_rpc(timeout=timeout)
        time.sleep(extra_delay)

    def ensure_account_exists(self, password: str) -> str:
        accounts = get_accounts(**self.geth_kwargs)
        if not accounts:
            account = create_new_account(password=password.encode(), **self.geth_kwargs)
        else:
            account = accounts[0]  # etherbase by default
        checksum_address = to_checksum_address(account.decode())
        return checksum_address


class NuCypherGethDevProcess(NuCypherGethProcess):
    _CHAIN_NAME = 'poa-development'

    def __init__(self, config_root: str = None, *args, **kwargs):

        base_dir = config_root if config_root else DEFAULT_CONFIG_ROOT
        base_dir = os.path.join(base_dir, '.ethereum')
        self.data_dir = get_chain_data_dir(base_dir=base_dir, name=self._CHAIN_NAME)

        ipc_path = os.path.join(self.data_dir, 'geth.ipc')
        self.geth_kwargs = {'ipc_path': ipc_path,
                            'data_dir': self.data_dir}

        super().__init__(geth_kwargs=self.geth_kwargs, *args, **kwargs)
        self.command = [*self.command, '--dev']

    def start(self, timeout: int = 30, extra_delay: int = 1):
        if not self.is_running:
            self.LOG.info("STARTING GETH DEV PROCESS NOW")
            BaseGethProcess.start(self)  # <--- START GETH
            time.sleep(extra_delay)  # give it a second
            self.wait_for_ipc(timeout=timeout)
        else:
            self.LOG.info("RECONNECTING TO GETH DEV PROCESS")
