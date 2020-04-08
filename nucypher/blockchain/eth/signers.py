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

import sys
import json
from abc import ABC, abstractmethod
from typing import List
from urllib.parse import urlparse

from eth_utils import to_checksum_address, apply_formatters_to_dict
from hexbytes import HexBytes
from twisted.logger import Logger
from web3 import Web3, IPCProvider
from eth_account import Account
from eth_account.messages import encode_defunct

from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.decorators import validate_checksum_address


class Signer(ABC):

    class InvalidSignerURI(ValueError):
        """Raised when an invalid signer URI is detected"""
        def __init__(self, uri=None, text=None):
            args = []
            if uri:
                if text:
                    text = ': ' + text
                else:
                    text = ' is not a valid signer URI'
                text = f"'{uri}'{text}"
            if text:
                args.append(text)
            super().__init__(*args)

    IS_SIGNER_LOCAL = False

    def __init__(self):
        self.log = Logger(self.__class__.__name__)

    @classmethod
    def from_signer_uri(cls, uri: str, local_signers_allowed: bool = False) -> 'Signer':
        scheme = urlparse(uri).scheme

        if scheme == 'clef':
            signer_cls = ClefSigner
        elif scheme.startswith('key'):
            signer_cls = KeyStoreSigner
        else:
            signer_cls = Web3Signer

        if not local_signers_allowed and signer_cls.IS_SIGNER_LOCAL:
            raise cls.InvalidSignerURI(uri=uri, text='local signers are not allowed for this operation')

        return signer_cls.from_signer_uri(uri=uri)

    @abstractmethod
    def is_device(self, account: str) -> bool:
        """Some signing client support both software and hardware wallets,
        this method is implemented as a boolean to tell the difference."""
        return NotImplemented

    @abstractmethod
    def accounts(self) -> List[str]:
        return NotImplemented

    @abstractmethod
    def unlock_account(self, account: str, password: str, duration: int = None) -> bytes:
        return NotImplemented

    @abstractmethod
    def lock_account(self, account: str) -> str:
        return NotImplemented

    @abstractmethod
    def sign_transaction(self, transaction_dict: dict) -> HexBytes:
        return NotImplemented

    @abstractmethod
    def sign_message(self, account: str, message: bytes, **kwargs) -> HexBytes:
        return NotImplemented


class Web3Signer(Signer):

    def __init__(self, client):
        super().__init__()
        self.__client = client

    @classmethod
    def from_signer_uri(cls, uri: str) -> 'Web3Signer':
        from nucypher.blockchain.eth.interfaces import BlockchainInterface, BlockchainInterfaceFactory

        try:
            blockchain = BlockchainInterfaceFactory.get_or_create_interface(provider_uri=uri)
        except BlockchainInterface.UnsupportedProvider:
            raise cls.InvalidSignerURI(uri)
        signer = cls(client=blockchain.client)
        return signer

    def is_connected(self) -> bool:
        return self.__client.w3.isConnected()

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

    def __init__(self, ipc_path: str = DEFAULT_IPC_PATH):
        super().__init__()
        self.w3 = Web3(provider=IPCProvider(ipc_path=ipc_path))  # TODO: Unify with clients or build error handling
        self.ipc_path = ipc_path

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
    def from_signer_uri(cls, uri: str) -> 'ClefSigner':
        uri_breakdown = urlparse(uri)
        signer = cls(ipc_path=uri_breakdown.path)
        return signer

    def is_connected(self) -> bool:
        return self.w3.isConnected()

    @validate_checksum_address
    def is_device(self, account: str):
        return True  # TODO: Detect HW v. SW Wallets via clef API - #1772
    
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
        transaction_dict = apply_formatters_to_dict(formatters, transaction_dict)
        signed = self.__ipc_request("account_signTransaction", transaction_dict)
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
    def lock_account(self, account: str):
        return True


class KeyStoreSigner(Signer):

    IS_SIGNER_LOCAL = True

    def __init__(self, uri: str):
        super().__init__()

        decoded_uri = urlparse(uri)
        if decoded_uri.scheme not in ('key', 'keystore') or decoded_uri.netloc:
            raise cls.InvalidSignerURI(uri)

        with open(decoded_uri.path) as file_obj:
            key = json.load(file_obj)

        address = key['address']
        if not Web3.isAddress(address):
            raise ValueError(f"'{decoded_uri.path}' does not contain a valid address")

        self.key = key
        self.account = Web3.toChecksumAddress(address)
        self._private_key = None

    @classmethod
    def from_signer_uri(cls, uri: str) -> 'Signer':
        return cls(uri)

    def _is_my_account(self, account) -> bool:
        return Web3.isAddress(account) and \
            self.account == Web3.toChecksumAddress(account)

    @validate_checksum_address
    def is_device(self, account: str) -> bool:
        return False

    def accounts(self) -> List[str]:
        return [self.account]

    @validate_checksum_address
    def unlock_account(self, account: str, password: str, duration: int = None) -> bytes:
        if not self._is_my_account(account):
            return False

        if self._private_key is None:
            try:
                self._private_key = Account.decrypt(self.key, password)
            except ValueError:
                return False

        return True

    @validate_checksum_address
    def lock_account(self, account: str) -> str:
        if not self._is_my_account(account):
            return False

        self._private_key = None
        return True

    @validate_checksum_address
    def sign_transaction(self, transaction_dict: dict) -> HexBytes:
        # Do not include a 'to' field for contract creation.
        if not transaction_dict['to']:
            transaction_dict = dissoc(transaction_dict, 'to')

        return Account.sign_transaction(
                transaction=transaction_dict,
                key=self._private_key,
            ).raw

    @validate_checksum_address
    def sign_message(self, account: str, message: bytes, **kwargs) -> HexBytes:
        if not self._is_my_account(account):
            return None

        return Account.sign_message(
                signable_message=encode_defunct(primitive=message),
                private_key=self._private_key,
            )['signature']
