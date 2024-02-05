import os
import time
from functools import cached_property
from typing import Union

from constant_sorrow.constants import UNKNOWN_DEVELOPMENT_CHAIN_ID
from cytoolz.dicttoolz import dissoc
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_typing.evm import BlockNumber, ChecksumAddress
from eth_utils import to_canonical_address, to_checksum_address
from web3 import Web3
from web3._utils.threads import Timeout
from web3.contract.contract import Contract
from web3.exceptions import TimeExhausted, TransactionNotFound
from web3.types import TxReceipt, Wei

from nucypher.blockchain.eth.constants import AVERAGE_BLOCK_TIME_IN_SECONDS
from nucypher.blockchain.middleware.retry import (
    AlchemyRetryRequestMiddleware,
    InfuraRetryRequestMiddleware,
    RetryRequestMiddleware,
)
from nucypher.utilities.logging import Logger

UNKNOWN_DEVELOPMENT_CHAIN_ID.bool_value(True)


class Web3ClientError(Exception):
    pass


class Web3ClientConnectionFailed(Web3ClientError):
    pass


class Web3ClientUnexpectedVersionString(Web3ClientError):
    pass


# TODO: Consider creating a ChainInventory class and/or moving this to a separate module

PUBLIC_CHAINS = {
    0: "Olympic",
    1: "Mainnet",
    2: "Morden",
    3: "Ropsten",
    4: "Rinkeby",
    5: "Goerli",
    6: "Kotti",
    42: "Kovan",
    77: "Sokol",
    100: "xDai",
    137: "Polygon/Mainnet",
    11155111: "Sepolia",
    80001: "Polygon/Mumbai"
}

LOCAL_CHAINS = {
    1337: "GethDev",
    5777: "Ganache/TestRPC"
}

# This list is not exhaustive,
# but is sufficient for the current needs of the project.
POA_CHAINS = {
    4,  # Rinkeby
    5,  # Goerli
    42,  # Kovan
    77,  # Sokol
    100,  # xDAI
    10200,  # gnosis/chiado,
    137,  # Polygon/Mainnet
    80001,  # "Polygon/Mumbai"
}


class EthereumClient:
    is_local = False

    # These two are used by Infura
    GETH = 'Geth'
    BOR = 'bor'

    PARITY = 'Parity'
    ALT_PARITY = 'Parity-Ethereum'
    GANACHE = 'EthereumJS TestRPC'

    ETHEREUM_TESTER = 'EthereumTester'  # (PyEVM)

    BLOCK_CONFIRMATIONS_POLLING_TIME = 3  # seconds
    TRANSACTION_POLLING_TIME = 0.5  # seconds
    COOLING_TIME = 5  # seconds
    STALECHECK_ALLOWABLE_DELAY = 30  # seconds

    class ConnectionNotEstablished(RuntimeError):
        pass

    class SyncTimeout(RuntimeError):
        pass

    class UnknownAccount(ValueError):
        pass

    class TransactionBroadcastError(RuntimeError):
        pass

    class NotEnoughConfirmations(TransactionBroadcastError):
        pass

    class TransactionTimeout(TransactionBroadcastError):
        pass

    class ChainReorganizationDetected(TransactionBroadcastError):
        """Raised when block confirmations logic detects that a TX was lost due to a chain reorganization"""

        error_message = ("Chain re-organization detected: Transaction {transaction_hash} was reported to be in "
                         "block {block_hash}, but it's not there anymore")

        def __init__(self, receipt):
            self.receipt = receipt
            self.message = self.error_message.format(transaction_hash=Web3.to_hex(receipt['transactionHash']),
                                                     block_hash=Web3.to_hex(receipt['blockHash']))
            super().__init__(self.message)

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

        self._add_default_middleware()

    def _add_default_middleware(self):
        # default retry functionality
        self.log.debug('Adding RPC retry middleware to client')
        self.add_middleware(RetryRequestMiddleware)

    @classmethod
    def _get_variant(cls, w3):
        return cls

    @classmethod
    def from_w3(cls, w3: Web3) -> 'EthereumClient':
        """

        Client version strings:

        Geth    -> 'Geth/v1.4.11-stable-fed692f6/darwin/go1.7'
        Parity  -> 'Parity-Ethereum/v2.5.1-beta-e0141f8-20190510/x86_64-linux-gnu/rustc1.34.1'
        Ganache -> 'EthereumJS TestRPC/v2.1.5/ethereum-js'
        PyEVM   -> 'EthereumTester/0.1.0b39/linux/python3.6.7'
        Bor     -> 'bor/v0.2.13-beta2-c227a072/linux-amd64/go1.17.5'
        """
        clients = {

            # Geth
            cls.GETH: GethClient,
            cls.BOR: BorClient,

            # Parity
            cls.PARITY: ParityClient,
            cls.ALT_PARITY: ParityClient,

            # Test Clients
            cls.GANACHE: GanacheClient,
            cls.ETHEREUM_TESTER: EthereumTesterClient,
        }

        try:
            client_data = w3.client_version.split('/')
            node_technology = client_data[0]
            ClientSubclass = clients[node_technology]

        except (ValueError, IndexError):
            raise ValueError(f"Invalid client version string. Got '{w3.client_version}'")

        except KeyError:
            raise NotImplementedError(f'{w3.client_version} is not a supported ethereum client')

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
        chain_inventory = LOCAL_CHAINS if self.is_local else PUBLIC_CHAINS
        name = chain_inventory.get(self.chain_id, UNKNOWN_DEVELOPMENT_CHAIN_ID)
        return name

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
        return self.w3.is_connected()

    @property
    def etherbase(self) -> str:
        return self.w3.eth.accounts[0]

    @property
    def accounts(self):
        return self.w3.eth.accounts

    def get_balance(self, account):
        return self.w3.eth.get_balance(account)

    def inject_middleware(self, middleware, **kwargs):
        self.w3.middleware_onion.inject(middleware, **kwargs)

    def add_middleware(self, middleware):
        self.w3.middleware_onion.add(middleware)

    def set_gas_strategy(self, gas_strategy):
        self.w3.eth.set_gas_price_strategy(gas_strategy)

    @cached_property
    def chain_id(self) -> int:
        result = self.w3.eth.chain_id
        try:
            # from hex-str
            chain_id = int(result, 16)
        except TypeError:
            # from str
            chain_id = int(result)

        return chain_id

    @property
    def net_version(self) -> int:
        return int(self.w3.net.version)

    def get_contract(self, **kwargs) -> Contract:
        return self.w3.eth.contract(**kwargs)

    @property
    def gas_price(self) -> Wei:
        """
        Returns client's gas price. Underneath, it uses the eth_gasPrice JSON-RPC method
        """
        return self.w3.eth.gas_price

    def gas_price_for_transaction(self, transaction=None) -> Wei:
        """
        Obtains a gas price via the current gas strategy, if any; otherwise, it resorts to the client's gas price.
        This method mirrors the behavior of web3._utils.transactions when building transactions.
        """
        return self.w3.eth.generate_gas_price(transaction) or self.gas_price

    @property
    def block_number(self) -> BlockNumber:
        return self.w3.eth.block_number

    @property
    def coinbase(self) -> ChecksumAddress:
        return self.w3.eth.coinbase

    def wait_for_receipt(self,
                         transaction_hash: str,
                         timeout: float,
                         confirmations: int = 0) -> TxReceipt:
        receipt: TxReceipt = None
        if confirmations:
            # If we're waiting for confirmations, we may as well let pass some time initially to make everything easier
            time.sleep(self.COOLING_TIME)

            # We'll keep trying to get receipts until there are enough confirmations or the timeout happens
            with Timeout(seconds=timeout, exception=self.TransactionTimeout) as timeout_context:
                while not receipt:
                    try:
                        receipt = self.block_until_enough_confirmations(transaction_hash=transaction_hash,
                                                                        timeout=timeout,
                                                                        confirmations=confirmations)
                    except (self.ChainReorganizationDetected, self.NotEnoughConfirmations, TimeExhausted):
                        timeout_context.sleep(self.BLOCK_CONFIRMATIONS_POLLING_TIME)
                        continue

        else:
            # If not asking for confirmations, just use web3 and assume the returned receipt is final
            try:
                receipt = self.w3.eth.wait_for_transaction_receipt(
                    transaction_hash=transaction_hash,
                    timeout=timeout,
                    poll_latency=self.TRANSACTION_POLLING_TIME
                )
            except TimeExhausted:
                raise  # TODO: #1504 - Handle transaction timeout

        return receipt

    def block_until_enough_confirmations(self, transaction_hash: str, timeout: float, confirmations: int) -> dict:

        receipt: TxReceipt = self.w3.eth.wait_for_transaction_receipt(
            transaction_hash=transaction_hash,
            timeout=timeout,
            poll_latency=self.TRANSACTION_POLLING_TIME
        )

        preliminary_block_hash = Web3.to_hex(receipt['blockHash'])
        tx_block_number = Web3.to_int(receipt['blockNumber'])
        self.log.info(f"Transaction {Web3.to_hex(transaction_hash)} is preliminarily included in "
                      f"block {preliminary_block_hash}")

        confirmations_timeout = self._calculate_confirmations_timeout(confirmations)
        confirmations_so_far = 0
        with Timeout(seconds=confirmations_timeout, exception=self.NotEnoughConfirmations) as timeout_context:
            while confirmations_so_far < confirmations:
                timeout_context.sleep(self.BLOCK_CONFIRMATIONS_POLLING_TIME)
                self.check_transaction_is_on_chain(receipt=receipt)
                confirmations_so_far = self.block_number - tx_block_number
                self.log.info(f"We have {confirmations_so_far} confirmations. "
                              f"Waiting for {confirmations - confirmations_so_far} more.")
            return receipt

    @staticmethod
    def _calculate_confirmations_timeout(confirmations):
        confirmations_timeout = 3 * AVERAGE_BLOCK_TIME_IN_SECONDS * confirmations
        return confirmations_timeout

    def check_transaction_is_on_chain(self, receipt: TxReceipt) -> bool:
        transaction_hash = Web3.to_hex(receipt['transactionHash'])
        try:
            new_receipt = self.w3.eth.get_transaction_receipt(transaction_hash)
        except TransactionNotFound:
            reorg_detected = True
        else:
            reorg_detected = receipt['blockHash'] != new_receipt['blockHash']

        if reorg_detected:
            exception = self.ChainReorganizationDetected(receipt=receipt)
            self.log.info(exception.message)
            raise exception
            # TODO: Consider adding an optional param in this exception to include extra info (e.g. new block)
        return True

    def sign_transaction(self, transaction_dict: dict) -> bytes:
        raise NotImplementedError

    def get_transaction(self, transaction_hash) -> dict:
        return self.w3.eth.get_transaction(transaction_hash)

    def get_transaction_receipt(self, transaction_hash) -> Union[dict, None]:
        return self.w3.eth.get_transaction_receipt(transaction_hash)

    def get_transaction_count(self, account: str, pending: bool) -> int:
        block_identifier = 'pending' if pending else 'latest'
        return self.w3.eth.get_transaction_count(account, block_identifier)

    def send_transaction(self, transaction_dict: dict) -> str:
        return self.w3.eth.send_transaction(transaction_dict)

    def send_raw_transaction(self, transaction_bytes: bytes) -> str:
        return self.w3.eth.send_raw_transaction(transaction_bytes)

    def sign_message(self, account: str, message: bytes) -> str:
        """
        Calls the appropriate signing function for the specified account on the
        backend. If the backend is based on eth-tester, then it uses the
        eth-tester signing interface to do so.
        """
        return self.w3.eth.sign(account, data=message)

    def get_blocktime(self):
        highest_block = self.w3.eth.get_block('latest')
        now = highest_block['timestamp']
        return now

    def get_block(self, block_identifier):
        return self.w3.eth.get_block(block_identifier)

    def _has_latest_block(self) -> bool:
        # TODO: Investigate using `web3.middleware.make_stalecheck_middleware` #2060
        # check that our local chain data is up to date
        return (time.time() - self.get_blocktime()) < self.STALECHECK_ALLOWABLE_DELAY

    def parse_transaction_data(self, transaction):
        return transaction.input


class GethClient(EthereumClient):

    @classmethod
    def _get_variant(cls, w3):
        endpoint_uri = getattr(w3.provider, 'endpoint_uri', '')
        if 'infura' in endpoint_uri:
            return InfuraClient
        elif 'alchemyapi.io' in endpoint_uri:
            return AlchemyClient

        return cls

    @property
    def is_local(self):
        return self.chain_id not in PUBLIC_CHAINS

    @property
    def peers(self):
        return self.w3.geth.admin.peers()

    def new_account(self, password: str) -> str:
        new_account = self.w3.geth.personal.new_account(password)
        return to_checksum_address(new_account)  # cast and validate

    def unlock_account(self, account: str, password: str, duration: int = None):
        if self.is_local:
            return True
        debug_message = f"Unlocking account {account}"

        if duration is None:
            debug_message += " for 5 minutes"
        elif duration == 0:
            debug_message += " indefinitely"
        elif duration > 0:
            debug_message += f" for {duration} seconds"

        if password is None:
            debug_message += " with no password."

        self.log.debug(debug_message)
        return self.w3.geth.personal.unlock_account(account, password, duration)

    def lock_account(self, account):
        return self.w3.geth.personal.lock_account(account)

    def sign_transaction(self, transaction_dict: dict) -> bytes:

        # Do not include a 'to' field for contract creation.
        if transaction_dict['to'] == b'':
            transaction_dict = dissoc(transaction_dict, 'to')

        # Sign
        result = self.w3.eth.sign_transaction(transaction_dict)

        # Return RLP bytes
        rlp_encoded_transaction = result.raw
        return rlp_encoded_transaction

    @property
    def wallets(self):
        return self.w3.geth.personal.list_wallets()


class BorClient(GethClient):
    """Geth to Bor adapter"""


class ParityClient(EthereumClient):

    @property
    def peers(self) -> list:
        """
        TODO: Look for web3.py support for Parity Peers endpoint
        """
        return self.w3.manager.request_blocking("parity_netPeers", [])

    def new_account(self, password: str) -> str:
        new_account = self.w3.parity.personal.new_account(password)
        return to_checksum_address(new_account)  # cast and validate

    def unlock_account(self, account, password, duration: int = None) -> bool:
        return self.w3.parity.personal.unlock_account(account, password, duration)

    def lock_account(self, account):
        return self.w3.parity.personal.lock_account(account)


class GanacheClient(EthereumClient):
    is_local = True

    def unlock_account(self, *args, **kwargs) -> bool:
        return True


class InfuraClient(EthereumClient):
    is_local = False
    TRANSACTION_POLLING_TIME = 2  # seconds

    def _add_default_middleware(self):
        # default retry functionality
        self.log.debug('Adding Infura RPC retry middleware to client')
        self.add_middleware(InfuraRetryRequestMiddleware)

    def unlock_account(self, *args, **kwargs) -> bool:
        return True


class AlchemyClient(EthereumClient):

    def _add_default_middleware(self):
        # default retry functionality
        self.log.debug('Adding Alchemy RPC retry middleware to client')
        self.add_middleware(AlchemyRetryRequestMiddleware)


class EthereumTesterClient(EthereumClient):
    is_local = True

    def unlock_account(self, account, password, duration: int = None) -> bool:
        """Returns True if the testing backend keystore has control of the given address."""
        account = to_checksum_address(account)
        keystore_accounts = self.w3.provider.ethereum_tester.get_accounts()
        if account in keystore_accounts:
            return True
        else:
            return self.w3.provider.ethereum_tester.unlock_account(account=account,
                                                                   password=password,
                                                                   unlock_seconds=duration)

    def lock_account(self, account) -> bool:
        """Returns True if the testing backend keystore has control of the given address."""
        account = to_canonical_address(account)
        keystore_accounts = self.w3.provider.ethereum_tester.backend.get_accounts()
        if account in keystore_accounts:
            return True
        else:
            return self.w3.provider.ethereum_tester.lock_account(account=account)

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

    def parse_transaction_data(self, transaction):
        return transaction.data  # See https://github.com/ethereum/eth-tester/issues/173
