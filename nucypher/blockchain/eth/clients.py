import json
import os
import shutil
from typing import Union

import maya
import time
from constant_sorrow.constants import NOT_RUNNING, UNKNOWN_DEVELOPMENT_CHAIN_ID
from cytoolz.dicttoolz import dissoc
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import to_canonical_address
from eth_utils import to_checksum_address
from geth import LoggingMixin
from geth.accounts import get_accounts, create_new_account
from geth.chain import (
    get_chain_data_dir,
    initialize_chain,
    is_live_chain,
    is_ropsten_chain
)
from geth.process import BaseGethProcess
from twisted.logger import Logger
from web3 import Web3

from nucypher.blockchain.eth.signers import ClefSigner
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, DEPLOY_DIR, USER_LOG_DIR

UNKNOWN_DEVELOPMENT_CHAIN_ID.bool_value(True)


class Web3ClientError(Exception):
    pass


class Web3ClientConnectionFailed(Web3ClientError):
    pass


class Web3ClientUnexpectedVersionString(Web3ClientError):
    pass


PUBLIC_CHAINS = {0: "Olympic",
                 1: "Mainnet",
                 2: "Morden",
                 3: "Ropsten",
                 4: "Rinkeby",
                 5: "Goerli",
                 6: "Kotti",
                 8: "Ubiq",
                 42: "Kovan",
                 60: "GoChain",
                 77: "Sokol",
                 99: "Core",
                 100: "xDai",
                 31337: "GoChain",
                 401697: "Tobalaba",
                 7762959: "Musicoin",
                 61717561: "Aquachain"}

LOCAL_CHAINS = {1337: "GethDev",
                5777: "Ganache/TestRPC"}


class EthereumClient:

    is_local = False

    GETH = 'Geth'
    PARITY = 'Parity'
    ALT_PARITY = 'Parity-Ethereum'
    GANACHE = 'EthereumJS TestRPC'

    ETHEREUM_TESTER = 'EthereumTester'  # (PyEVM)
    CLEF = 'Clef'  # Signer-only

    PEERING_TIMEOUT = 30        # seconds
    SYNC_TIMEOUT_DURATION = 60  # seconds to wait for various blockchain syncing endeavors
    SYNC_SLEEP_DURATION = 5     # seconds

    class ConnectionNotEstablished(RuntimeError):
        pass

    class SyncTimeout(RuntimeError):
        pass

    class UnknownAccount(ValueError):
        pass

    def __init__(self,
                 w3,
                 node_technology: str,
                 version: str,
                 platform: str,
                 backend: str):

        self.w3 = w3
        self.node_technology = node_technology
        self.node_version = version
        self.platform = platform
        self.backend = backend
        self.log = Logger(self.__class__.__name__)

    @classmethod
    def _get_variant(cls, w3):
        return cls

    @classmethod
    def from_w3(cls, w3: Web3) -> 'EthereumClient':
        """

        Client version strings
        ======================

        Geth    -> 'Geth/v1.4.11-stable-fed692f6/darwin/go1.7'
        Parity  -> 'Parity-Ethereum/v2.5.1-beta-e0141f8-20190510/x86_64-linux-gnu/rustc1.34.1'
        Ganache -> 'EthereumJS TestRPC/v2.1.5/ethereum-js'
        PyEVM   -> 'EthereumTester/0.1.0b39/linux/python3.6.7'
        """
        clients = {

            # Geth
            cls.GETH: GethClient,

            # Parity
            cls.PARITY: ParityClient,
            cls.ALT_PARITY: ParityClient,

            # Test Clients
            cls.GANACHE: GanacheClient,
            cls.ETHEREUM_TESTER: EthereumTesterClient,
        }

        try:
            client_data = w3.clientVersion.split('/')
            node_technology = client_data[0]
            ClientSubclass = clients[node_technology]

        except (ValueError, IndexError):
            raise ValueError(f"Invalid client version string. Got '{w3.clientVersion}'")

        except KeyError:
            raise NotImplementedError(f'{w3.clientVersion} is not a supported ethereum client')

        client_kwargs = {
            'node_technology': node_technology,
            'version': client_data[1],
            'backend': client_data[-1],
            'platform': client_data[2] if len(client_data) == 4 else None  # Platform is optional
        }

        instance = ClientSubclass._get_variant(w3)(w3, **client_kwargs)
        return instance

    @property
    def peers(self):
        raise NotImplementedError

    @property
    def chain_name(self) -> str:
        if not self.is_local:
            return PUBLIC_CHAINS[int(self.chain_id)]
        name = LOCAL_CHAINS.get(self.chain_id, UNKNOWN_DEVELOPMENT_CHAIN_ID)
        return name

    @property
    def syncing(self) -> Union[bool, dict]:
        return self.w3.eth.syncing

    def lock_account(self, account) -> bool:
        if self.is_local:
            return True
        return NotImplemented

    def unlock_account(self, account, password, duration=None) -> bool:
        if self.is_local:
            return True
        return NotImplemented

    @property
    def is_connected(self):
        return self.w3.isConnected()

    @property
    def etherbase(self) -> str:
        return self.w3.eth.accounts[0]

    @property
    def accounts(self):
        return self.w3.eth.accounts

    def get_balance(self, account):
        return self.w3.eth.getBalance(account)

    def inject_middleware(self, middleware, **kwargs):
        return self.w3.middleware_onion.inject(middleware, **kwargs)

    def add_middleware(self, middleware):
        return self.w3.middleware_onion.add(middleware)

    @property
    def chain_id(self) -> int:
        try:
            # from hex-str
            return int(self.w3.eth.chainId, 16)
        except TypeError:
            # from str
            return int(self.w3.eth.chainId)

    @property
    def net_version(self) -> int:
        return int(self.w3.net.version)

    def get_contract(self, **kwargs):
        return self.w3.eth.contract(**kwargs)

    @property
    def gas_price(self):
        return self.w3.eth.gasPrice

    @property
    def block_number(self) -> int:
        return self.w3.eth.blockNumber

    @property
    def coinbase(self) -> str:
        return self.w3.eth.coinbase

    def wait_for_receipt(self, transaction_hash: str, timeout: int) -> dict:
        receipt = self.w3.eth.waitForTransactionReceipt(transaction_hash=transaction_hash, timeout=timeout)
        return receipt

    def sign_transaction(self, transaction_dict: dict):
        raise NotImplementedError

    def get_transaction(self, transaction_hash) -> str:
        return self.w3.eth.getTransaction(transaction_hash=transaction_hash)

    def send_transaction(self, transaction_dict: dict) -> str:
        return self.w3.eth.sendTransaction(transaction=transaction_dict)

    def send_raw_transaction(self, transaction_bytes: bytes) -> str:
        return self.w3.eth.sendRawTransaction(raw_transaction=transaction_bytes)

    def sign_message(self, account: str, message: bytes) -> str:
        """
        Calls the appropriate signing function for the specified account on the
        backend. If the backend is based on eth-tester, then it uses the
        eth-tester signing interface to do so.
        """
        return self.w3.eth.sign(account, data=message)

    def _has_latest_block(self):
        # check that our local chain data is up to date
        return (
            time.time() -
            self.w3.eth.getBlock(self.w3.eth.blockNumber)['timestamp']
        ) < 30

    def sync(self,
             timeout: int = 120,
             quiet: bool = False):

        # Provide compatibility with local chains
        if self.is_local:
            return

        # Record start time for timeout calculation
        now = maya.now()
        start_time = now

        def check_for_timeout(t):
            last_update = maya.now()
            duration = (last_update - start_time).total_seconds()
            if duration > t:
                raise self.SyncTimeout

        while not self._has_latest_block():
            # Check for ethereum peers
            self.log.info(f"Waiting for Ethereum peers ({len(self.peers)} known)")
            while not self.peers:
                time.sleep(0)
                check_for_timeout(t=self.PEERING_TIMEOUT)

            # Wait for sync start
            self.log.info(f"Waiting for {self.chain_name.capitalize()} chain synchronization to begin")
            while not self.syncing:
                time.sleep(0)
                check_for_timeout(t=self.SYNC_TIMEOUT_DURATION*2)

            while True:
                syncdata = self.syncing
                if not syncdata:
                    return False

                self.log.info(f"Syncing {syncdata['currentBlock']}/{syncdata['highestBlock']}")
                time.sleep(self.SYNC_SLEEP_DURATION)
                yield syncdata

        return True


class GethClient(EthereumClient):

    @classmethod
    def _get_variant(cls, w3):
        if 'infura' in getattr(w3.provider, 'endpoint_uri', ''):
            return InfuraClient
        return cls

    @property
    def is_local(self):
        # TODO: #1505  -- rethink this metaphor
        return int(self.w3.net.version) not in PUBLIC_CHAINS

    @property
    def peers(self):
        return self.w3.geth.admin.peers()

    def new_account(self, password: str) -> str:
        new_account = self.w3.geth.personal.newAccount(password)
        return to_checksum_address(new_account)  # cast and validate

    def unlock_account(self, account: str, password: str, duration: int = None):
        if self.is_local:
            return True
        debug_message = f"Unlocking account {account}"

        if duration is None:
            debug_message += f" for 5 minutes"
        elif duration == 0:
            debug_message += f" indefinitely"
        elif duration > 0:
            debug_message += f" for {duration} seconds"

        if password is None:
            debug_message += " with no password."

        self.log.debug(debug_message)
        return self.w3.geth.personal.unlockAccount(account, password, duration)

    def lock_account(self, account):
        return self.w3.geth.personal.lockAccount(account)

    def sign_transaction(self, transaction_dict: dict) -> bytes:

        # Do not include a 'to' field for contract creation.
        if transaction_dict['to'] == b'':
            transaction_dict = dissoc(transaction_dict, 'to')

        # Sign
        result = self.w3.eth.signTransaction(transaction=transaction_dict)

        # Return RLP bytes
        rlp_encoded_transaction = result.raw
        return rlp_encoded_transaction

    @property
    def wallets(self):
        return self.w3.manager.request_blocking("personal_listWallets", [])


class ParityClient(EthereumClient):

    @property
    def peers(self) -> list:
        """
        TODO: Look for web3.py support for Parity Peers endpoint
        """
        return self.w3.manager.request_blocking("parity_netPeers", [])

    def new_account(self, password: str) -> str:
        new_account = self.w3.parity.personal.newAccount(password)
        return to_checksum_address(new_account)  # cast and validate

    def unlock_account(self, account, password, duration: int = None) -> bool:
        return self.w3.parity.personal.unlockAccount(account, password, duration)

    def lock_account(self, account):
        return self.w3.parity.personal.lockAccount(account)


class GanacheClient(EthereumClient):

    is_local = True

    def unlock_account(self, *args, **kwargs) -> bool:
        return True

    def sync(self, *args, **kwargs) -> bool:
        return True


class InfuraClient(EthereumClient):

    is_local = False

    def unlock_account(self, *args, **kwargs) -> bool:
        return True

    def sync(self, *args, **kwargs) -> bool:
        return True


class EthereumTesterClient(EthereumClient):

    is_local = True

    def unlock_account(self, account, password, duration: int = None) -> bool:
        """Returns True if the testing backend keyring has control of the given address."""
        account = to_canonical_address(account)
        keystore = self.w3.provider.ethereum_tester.backend._key_lookup
        if account in keystore:
            return True
        else:
            return self.w3.provider.ethereum_tester.unlock_account(account=account,
                                                                   password=password,
                                                                   unlock_seconds=duration)

    def lock_account(self, account) -> bool:
        """Returns True if the testing backend keyring has control of the given address."""
        account = to_canonical_address(account)
        keystore = self.w3.provider.ethereum_tester.backend._key_lookup
        if account in keystore:
            return True
        else:
            return self.w3.provider.ethereum_tester.lock_account(account=account)

    def sync(self, *args, **kwargs):
        return True

    def new_account(self, password: str) -> str:
        insecure_account = self.w3.provider.ethereum_tester.add_account(private_key=os.urandom(32).hex(),
                                                                        password=password)
        return insecure_account

    def __get_signing_key(self, account: bytes):
        """Get signing key of test account"""
        account = to_canonical_address(account)
        try:
            signing_key = self.w3.provider.ethereum_tester.backend._key_lookup[account]._raw_key
        except KeyError:
            raise self.UnknownAccount(account)
        return signing_key

    def sign_transaction(self, transaction_dict: dict) -> bytes:
        # Sign using a local private key
        address = to_canonical_address(transaction_dict['from'])
        signing_key = self.__get_signing_key(account=address)
        signed_transaction = self.w3.eth.account.sign_transaction(transaction_dict, private_key=signing_key)
        rlp_transaction = signed_transaction.rawTransaction
        return rlp_transaction

    def sign_message(self, account: str, message: bytes) -> str:
        """Sign, EIP-191 (Geth) Style"""
        signing_key = self.__get_signing_key(account=account)
        signable_message = encode_defunct(primitive=message)
        signature_and_stuff = Account.sign_message(signable_message=signable_message, private_key=signing_key)
        return signature_and_stuff['signature']


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


class NuCypherGethDevnetProcess(NuCypherGethProcess):

    IPC_PROTOCOL = 'file'
    GENESIS_FILENAME = 'testnet_genesis.json'
    GENESIS_SOURCE_FILEPATH = os.path.join(DEPLOY_DIR, GENESIS_FILENAME)

    P2P_PORT = 30303
    _CHAIN_NAME = 'devnet'
    __CHAIN_ID = 112358

    def __init__(self,
                 config_root: str = None,
                 overrides: dict = None,
                 *args, **kwargs):

        log = Logger('nucypher-geth-devnet')

        if overrides is None:
            overrides = dict()

        # Validate
        invalid_override = f"You cannot specify `network_id` for a {self.__class__.__name__}"
        if 'data_dir' in overrides:
            raise ValueError(invalid_override)
        if 'network_id' in overrides:
            raise ValueError(invalid_override)

        # Set the data dir
        if config_root is None:
            base_dir = os.path.join(DEFAULT_CONFIG_ROOT, '.ethereum')
        else:
            base_dir = os.path.join(config_root, '.ethereum')
        self.data_dir = get_chain_data_dir(base_dir=base_dir, name=self._CHAIN_NAME)

        # Hardcoded Geth CLI args for devnet child process ("light client")
        ipc_path = os.path.join(self.data_dir, self.IPC_FILENAME)
        geth_kwargs = {'network_id': str(self.__CHAIN_ID),
                       'port': str(self.P2P_PORT),
                       'verbosity': str(self.VERBOSITY),
                       'data_dir': self.data_dir,
                       'ipc_path': ipc_path,
                       'rpc_enabled': True,
                       'no_discover': True,
                       }

        # Genesis & Blockchain Init
        self.genesis_filepath = os.path.join(self.data_dir, self.GENESIS_FILENAME)
        needs_init = all((
            not os.path.exists(self.genesis_filepath),
            not is_live_chain(self.data_dir),
            not is_ropsten_chain(self.data_dir),
        ))

        if needs_init:
            log.debug("Local system needs geth blockchain initialization")
            self.initialized = False
        else:
            self.initialized = True

        self.__process = NOT_RUNNING

        super().__init__(geth_kwargs=geth_kwargs, *args, **kwargs)  # Attaches self.geth_kwargs in super call
        self.command = [*self.command, '--syncmode', 'fast']

    def initialize_blockchain(self, overwrite: bool = True) -> None:
        log = Logger('nucypher-geth-init')
        with open(self.GENESIS_SOURCE_FILEPATH, 'r') as file:
            genesis_data = json.loads(file.read())
            log.info(f"Read genesis file '{self.GENESIS_SOURCE_FILEPATH}'")

        genesis_data.update(dict(overwrite=overwrite))
        log.info(f'Initializing new blockchain database and genesis block.')
        initialize_chain(genesis_data=genesis_data, **self.geth_kwargs)

        # Write static nodes file to data dir
        bootnodes_filepath = os.path.join(DEPLOY_DIR, 'static-nodes.json')
        shutil.copy(bootnodes_filepath, os.path.join(self.data_dir))


class NuCypherGethGoerliProcess(NuCypherGethProcess):

    IPC_PROTOCOL = 'file'
    GENESIS_FILENAME = 'testnet_genesis.json'
    GENESIS_SOURCE_FILEPATH = os.path.join(DEPLOY_DIR, GENESIS_FILENAME)

    P2P_PORT = 30303
    _CHAIN_NAME = 'goerli'
    CHAIN_ID = 5

    def __init__(self,
                 config_root: str = None,
                 overrides: dict = None,
                 *args, **kwargs):

        if overrides is None:
            overrides = dict()

        # Validate
        invalid_override = f"You cannot specify `data_dir` or `network_id` for a {self.__class__.__name__}"
        if 'data_dir' in overrides:
            raise ValueError(invalid_override)
        if 'network_id' in overrides:
            raise ValueError(invalid_override)

        # Set the data dir
        if config_root is None:
            base_dir = os.path.join(DEFAULT_CONFIG_ROOT, '.ethereum')
        else:
            base_dir = os.path.join(config_root, '.ethereum')
        self.data_dir = get_chain_data_dir(base_dir=base_dir, name=self._CHAIN_NAME)

        # Hardcoded Geth CLI args for devnet child process ("light client")
        ipc_path = os.path.join(self.data_dir, self.IPC_FILENAME)
        geth_kwargs = {'port': str(self.P2P_PORT),
                       'verbosity': str(self.VERBOSITY),
                       'data_dir': self.data_dir,
                       'ipc_path': ipc_path,
                       'rpc_enabled': True,
                       'no_discover': False,
                       }

        # Genesis & Blockchain Init
        all_good = all((
            not is_ropsten_chain(self.data_dir),
        ))

        if not all_good:
            raise RuntimeError('Unintentional connection to Ropsten')

        self.__process = NOT_RUNNING
        super().__init__(geth_kwargs=geth_kwargs, *args, **kwargs)  # Attaches self.geth_kwargs in super call
        self.command = [*self.command, '--syncmode', 'fast', '--goerli']
