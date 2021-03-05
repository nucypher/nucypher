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
import stat
import sys
from json.decoder import JSONDecodeError
from typing import List, Dict, Tuple
from urllib.parse import urlparse

from cytoolz.dicttoolz import dissoc
from eth_account.account import Account
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount
from eth_utils.address import to_checksum_address, is_address
from eth_utils.applicators import apply_formatters_to_dict
from hexbytes.main import HexBytes
from web3.main import Web3
from web3.providers.ipc import IPCProvider

from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.signers.base import Signer


class Web3Signer(Signer):

    def __init__(self, client):
        super().__init__()
        self.__client = client

    @classmethod
    def uri_scheme(cls) -> str:
        return NotImplemented  # web3 signer uses a "passthrough" scheme

    @classmethod
    def from_signer_uri(cls, uri: str, testnet: bool = False) -> 'Web3Signer':
        from nucypher.blockchain.eth.interfaces import BlockchainInterface, BlockchainInterfaceFactory
        try:
            blockchain = BlockchainInterfaceFactory.get_or_create_interface(provider_uri=uri)
        except BlockchainInterface.UnsupportedProvider:
            raise cls.InvalidSignerURI(uri)
        signer = cls(client=blockchain.client)
        return signer

    def is_connected(self) -> bool:
        return self.__client.w3.isConnected()

    @property
    def accounts(self) -> List[str]:
        return self.__client.accounts

    @validate_checksum_address
    def is_device(self, account: str):
        try:
            # TODO: Temporary fix for #1128 and #1385. It's ugly af, but it works. Move somewhere else?
            wallets = self.__client.wallets
        except AttributeError:
            return False
        else:
            HW_WALLET_URL_PREFIXES = ('trezor', 'ledger')
            hw_accounts = [w['accounts'] for w in wallets if w['url'].startswith(HW_WALLET_URL_PREFIXES)]
            hw_addresses = [to_checksum_address(account['address']) for sublist in hw_accounts for account in sublist]
            return account in hw_addresses

    @validate_checksum_address
    def unlock_account(self, account: str, password: str, duration: int = None):
        if self.is_device(account=account):
            unlocked = True
        else:
            unlocked = self.__client.unlock_account(account=account, password=password, duration=duration)
        return unlocked

    @validate_checksum_address
    def lock_account(self, account: str):
        if self.is_device(account=account):
            result = None  # TODO: Force Disconnect Devices?
        else:
            result = self.__client.lock_account(account=account)
        return result

    @validate_checksum_address
    def sign_message(self, account: str, message: bytes, **kwargs) -> HexBytes:
        signature = self.__client.sign_message(account=account, message=message)
        return HexBytes(signature)

    def sign_transaction(self, transaction_dict: dict) -> HexBytes:
        signed_raw_transaction = self.__client.sign_transaction(transaction_dict=transaction_dict)
        return signed_raw_transaction


class ClefSigner(Signer):

    DEFAULT_IPC_PATH = '~/Library/Signer/clef.ipc' if sys.platform == 'darwin' else '~/.clef/clef.ipc'  #TODO: #1808

    SIGN_DATA_FOR_VALIDATOR = 'data/validator'   # a.k.a. EIP 191 version 0
    SIGN_DATA_FOR_CLIQUE = 'application/clique'  # not relevant for us
    SIGN_DATA_FOR_ECRECOVER = 'text/plain'       # a.k.a. geth's `personal_sign`, EIP-191 version 45 (E)

    DEFAULT_CONTENT_TYPE = SIGN_DATA_FOR_ECRECOVER
    SIGN_DATA_CONTENT_TYPES = (SIGN_DATA_FOR_VALIDATOR, SIGN_DATA_FOR_CLIQUE, SIGN_DATA_FOR_ECRECOVER)

    TIMEOUT = 180  # Default timeout for Clef of 180 seconds

    def __init__(self,
                 ipc_path: str = DEFAULT_IPC_PATH,
                 timeout: int = TIMEOUT,
                 testnet: bool = False):
        super().__init__()
        self.w3 = Web3(provider=IPCProvider(ipc_path=ipc_path, timeout=timeout))  # TODO: Unify with clients or build error handling
        self.ipc_path = ipc_path
        self.testnet = testnet

    @classmethod
    def uri_scheme(cls) -> str:
        return 'clef'

    def __ipc_request(self, endpoint: str, *request_args):
        """Error handler for clef IPC requests  # TODO: Use web3 RequestHandler"""
        try:
            response = self.w3.manager.request_blocking(endpoint, request_args)
        except FileNotFoundError:
            raise FileNotFoundError(f'Clef IPC file not found. Is clef running and available at "{self.ipc_path}"?')
        except ConnectionRefusedError:
            raise ConnectionRefusedError(f'Clef refused connection. Is clef running and available at "{self.ipc_path}"?')
        return response

    @classmethod
    def is_valid_clef_uri(cls, uri: str) -> bool:  # TODO: Workaround for #1941
        uri_breakdown = urlparse(uri)
        return uri_breakdown.scheme == cls.uri_scheme()

    @classmethod
    def from_signer_uri(cls, uri: str, testnet: bool = False) -> 'ClefSigner':
        uri_breakdown = urlparse(uri)
        if not uri_breakdown.path and not uri_breakdown.netloc:
            raise cls.InvalidSignerURI('Blank signer URI - No keystore path provided')
        if uri_breakdown.scheme != cls.uri_scheme():
            raise cls.InvalidSignerURI(f"{uri} is not a valid clef signer URI.")
        signer = cls(ipc_path=uri_breakdown.path, testnet=testnet)
        return signer

    def is_connected(self) -> bool:
        return self.w3.isConnected()

    @validate_checksum_address
    def is_device(self, account: str):
        return True  # TODO: Detect HW v. SW Wallets via clef API - #1772

    @property
    def accounts(self) -> List[str]:
        normalized_addresses = self.__ipc_request(endpoint="account_list")
        checksum_addresses = [to_checksum_address(addr) for addr in normalized_addresses]
        return checksum_addresses

    @validate_checksum_address
    def sign_transaction(self, transaction_dict: dict) -> HexBytes:
        formatters = {
            'nonce': Web3.toHex,
            'gasPrice': Web3.toHex,
            'gas': Web3.toHex,
            'value': Web3.toHex,
            'chainId': Web3.toHex,
            'from': to_checksum_address
        }

        # Workaround for contract creation TXs
        if transaction_dict['to'] == b'':
            transaction_dict['to'] = None
        elif transaction_dict['to']:
            formatters['to'] = to_checksum_address

        formatted_transaction = apply_formatters_to_dict(formatters, transaction_dict)
        signed = self.__ipc_request("account_signTransaction", formatted_transaction)
        return HexBytes(signed.raw)

    @validate_checksum_address
    def sign_message(self, account: str, message: bytes, content_type: str = None, validator_address: str = None, **kwargs) -> HexBytes:
        """
        See https://github.com/ethereum/go-ethereum/blob/a32a2b933ad6793a2fe4172cd46c5c5906da259a/signer/core/signed_data.go#L185
        """
        if isinstance(message, bytes):
            message = Web3.toHex(message)

        if not content_type:
            content_type = self.DEFAULT_CONTENT_TYPE
        elif content_type not in self.SIGN_DATA_CONTENT_TYPES:
            raise ValueError(f'{content_type} is not a valid content type. '
                             f'Valid types are {self.SIGN_DATA_CONTENT_TYPES}')
        if content_type == self.SIGN_DATA_FOR_VALIDATOR:
            if not validator_address or validator_address == NULL_ADDRESS:
                raise ValueError('When using the intended validator type, a validator address is required.')
            data = {'address': validator_address, 'message': message}
        elif content_type == self.SIGN_DATA_FOR_ECRECOVER:
            data = message
        else:
            raise NotImplementedError

        signed_data = self.__ipc_request("account_signData", content_type, account, data)
        return HexBytes(signed_data)

    def sign_data_for_validator(self, account: str, message: bytes, validator_address: str):
        signature = self.sign_message(account=account,
                                      message=message,
                                      content_type=self.SIGN_DATA_FOR_VALIDATOR,
                                      validator_address=validator_address)
        return signature

    @validate_checksum_address
    def unlock_account(self, account: str, password: str, duration: int = None) -> bool:
        return True

    @validate_checksum_address
    def lock_account(self, account: str) -> bool:
        return True


class KeystoreSigner(Signer):
    """Local Web3 signer implementation supporting keystore files"""

    __keys: Dict[str, dict]
    __signers: Dict[str, LocalAccount]

    class InvalidKeyfile(Signer.SignerError, RuntimeError):
        """
        Raised when a keyfile is corrupt or otherwise invalid.
        Keystore must be in the geth wallet format.
        """

    def __init__(self, path: str, testnet: bool = False):
        super().__init__()
        self.__path = path
        self.__keys = dict()
        self.__signers = dict()
        self.__read_keystore(path=path)
        self.testnet = testnet

    def __del__(self):
        # TODO: Might need a finally block or exception context handling
        if self.__keys:
            for account in self.__keys:
                self.lock_account(account)

    @classmethod
    def uri_scheme(cls) -> str:
        return 'keystore'

    def __read_keystore(self, path: str) -> None:
        """Read the keystore directory from the disk and populate accounts."""
        try:
            st_mode = os.stat(path=path).st_mode
            if stat.S_ISDIR(st_mode):
                paths = (entry.path for entry in os.scandir(path=path) if entry.is_file())
            elif stat.S_ISREG(st_mode):
                paths = (path,)
            else:
                raise self.InvalidSignerURI(f'Invalid keystore file or directory "{path}"')
        except FileNotFoundError:
            if not path:
                message = 'Blank signer URI - No keystore path provided'
            else:
                message = f'No such keystore file or directory "{path}"'
            raise self.InvalidSignerURI(message)
        except OSError as exc:
            raise self.InvalidSignerURI(f'Error accessing keystore file or directory "{path}": {exc}')
        for path in paths:
            account, key_metadata = self.__handle_keyfile(path=path)
            self.__keys[account] = key_metadata

    @staticmethod
    def __read_keyfile(path: str) -> tuple:
        """Read an individual keystore key file from the disk"""
        with open(path, 'r') as keyfile:
            key_metadata = json.load(keyfile)
        address = key_metadata['address']
        return address, key_metadata

    def __handle_keyfile(self, path: str) -> Tuple[str, dict]:
        """
        Read a single keystore file from the disk and return its decoded json contents then internally
        cache it on the keystore instance. Raises InvalidKeyfile if the keyfile is missing or corrupted.
        """
        try:
            address, key_metadata = self.__read_keyfile(path=path)
        except FileNotFoundError:
            error = f"No such keyfile '{path}'"
            raise self.InvalidKeyfile(error)
        except JSONDecodeError:
            error = f"Invalid JSON in keyfile at {path}"
            raise self.InvalidKeyfile(error)
        except KeyError:
            error = f"Keyfile does not contain address field at '{path}'"
            raise self.InvalidKeyfile(error)
        else:
            if not is_address(address):
                raise self.InvalidKeyfile(f"'{path}' does not contain a valid ethereum address")
            address = to_checksum_address(address)
        return address, key_metadata

    @validate_checksum_address
    def __get_signer(self, account: str) -> LocalAccount:
        """Lookup a known keystore account by its checksum address or raise an error"""
        try:
            return self.__signers[account]
        except KeyError:
            if account not in self.__keys:
                raise self.UnknownAccount(account=account)
            else:
                raise self.AccountLocked(account=account)

    #
    # Public API
    #

    @property
    def path(self) -> str:
        """Read only access to the keystore path"""
        return self.__path

    @classmethod
    def from_signer_uri(cls, uri: str, testnet: bool = False) -> 'Signer':
        """Return a keystore signer from URI string i.e. keystore:///my/path/keystore """
        decoded_uri = urlparse(uri)
        if decoded_uri.scheme != cls.uri_scheme() or decoded_uri.netloc:
            raise cls.InvalidSignerURI(uri)
        return cls(path=decoded_uri.path, testnet=testnet)

    @validate_checksum_address
    def is_device(self, account: str) -> bool:
        return False  # Keystore accounts are never devices.

    @property
    def accounts(self) -> List[str]:
        """Return a list of known keystore accounts read from"""
        return list(self.__keys.keys())

    @validate_checksum_address
    def unlock_account(self, account: str, password: str, duration: int = None) -> bool:
        """
        Decrypt the signing material from the key metadata file and cache it on
        the keystore instance is decryption is successful.
        """
        if not self.__signers.get(account):
            try:
                key_metadata = self.__keys[account]
            except KeyError:
                raise self.UnknownAccount(account=account)
            try:
                signing_key = Account.from_key(Account.decrypt(key_metadata, password))
                self.__signers[account] = signing_key
            except TypeError:
                if not password:
                    # It is possible that password is None here passed from the above layer
                    # causing Account.decrypt to crash, expecting a value for password.
                    raise self.AuthenticationFailed('No password supplied to unlock account.')
                raise
            except ValueError as e:
                raise self.AuthenticationFailed("Invalid or incorrect ethereum account password.") from e
        return True

    @validate_checksum_address
    def lock_account(self, account: str) -> bool:
        """
        Deletes a local signer by its checksum address or raises UnknownAccount if
        the address is not a member of this keystore.  Returns True if the account is no longer
        tracked and was successfully locked.
        """
        try:
            self.__signers.pop(account)  # mutate
        except KeyError:
            if account not in self.accounts:
                raise self.UnknownAccount(account=account)
        return account not in self.__signers

    @validate_checksum_address
    def sign_transaction(self, transaction_dict: dict) -> HexBytes:
        """
        Produce a raw signed ethereum transaction signed by the account specified
        in the 'from' field of the transaction dictionary.
        """

        sender = transaction_dict['from']
        signer = self.__get_signer(account=sender)

        # TODO: Handle this at a higher level?
        # Do not include a 'to' field for contract creation.
        if not transaction_dict['to']:
            transaction_dict = dissoc(transaction_dict, 'to')

        raw_transaction = signer.sign_transaction(transaction_dict=transaction_dict).rawTransaction
        return raw_transaction

    @validate_checksum_address
    def sign_message(self, account: str, message: bytes, **kwargs) -> HexBytes:
        signer = self.__get_signer(account=account)
        signature = signer.sign_message(signable_message=encode_defunct(primitive=message)).signature
        return HexBytes(signature)
