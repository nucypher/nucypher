from abc import ABC, abstractmethod
from typing import List
from urllib.parse import urlparse

from eth_utils import to_checksum_address, to_normalized_address, apply_formatters_to_dict
from hexbytes import HexBytes
from twisted.logger import Logger
from web3 import Web3, IPCProvider

from nucypher.blockchain.eth.interfaces import BlockchainInterface, BlockchainInterfaceFactory


class Signer(ABC):

    class AccountLocked(RuntimeError):
        pass

    def __init__(self):
        self.log = Logger(self.__class__.__name__)
        self._unlocked = False

    @classmethod
    def from_signer_uri(cls, uri: str) -> 'Signer':
        if 'clef' in uri:
            signer = ClefSigner.from_signer_uri(uri=uri)
        else:
            try:
                signer = Web3Signer.from_signer_uri(uri=uri)
            except Exception:
                raise ValueError(f"{uri} is an unsupported signer URI")
        return signer

    @abstractmethod
    def accounts(self) -> List[str]:
        return NotImplemented

    @property
    def is_unlocked(self) -> bool:
        return self._unlocked

    @abstractmethod
    def unlock_account(self, account: str, password: str, duration: int = None) -> bytes:
        return NotImplemented

    @abstractmethod
    def lock_account(self, account: str) -> str:
        return NotImplemented

    @abstractmethod
    def sign_transaction(self, account: str, transaction: dict) -> HexBytes:
        return NotImplemented

    @abstractmethod
    def sign_message(self, account: str, message: bytes, **kwargs) -> HexBytes:
        return NotImplemented


class Web3Signer(Signer):

    def __init__(self, client=None):
        super().__init__()
        if not client:
            from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
            blockchain = BlockchainInterfaceFactory.get_interface()
            client = blockchain.client
        self.__client = client

    @classmethod
    def from_signer_uri(cls, uri: str) -> 'Web3Signer':
        blockchain = BlockchainInterfaceFactory.get_or_create_interface(provider_uri=uri)
        signer = cls(client=blockchain.client)
        return signer

    def accounts(self) -> List[str]:
        return self.__client.accounts

    @staticmethod
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

    def unlock_account(self, account: str, password: str, duration: int = None):
        if self.is_device:
            unlocked = True
        else:
            unlocked = self.__client.unlock_account(account=account, password=password, duration=duration)
        self._unlocked = unlocked
        return self._unlocked

    def lock_account(self, account: str):
        if self.is_device:
            pass  # TODO: Force Disconnect Devices?
        else:
            self.__client.lock_account(account=account)
        self._unlocked = False
        return self._unlocked

    def sign_message(self, account: str, message: bytes, **kwargs) -> HexBytes:
        """
        Signs the message with the private key of the TransactingPower.
        """
        if not self.is_unlocked:
            raise self.AccountLocked("Failed to unlock account {}".format(account))
        signature = self.__client.sign_message(account=account, message=message)
        return HexBytes(signature)

    def sign_transaction(self, account: str, transaction: dict) -> HexBytes:
        """
        Signs the transaction with the private key of the TransactingPower.
        """
        if not self.is_unlocked:
            raise self.AccountLocked("Failed to unlock account {}".format(account))
        signed_raw_transaction = self.__client.sign_transaction(transaction=transaction)
        return signed_raw_transaction


class ClefSigner(Signer):

    DEFAULT_IPC_PATH = '~/.clef/clef.ipc'

    SIGN_DATA_FOR_VALIDATOR = 'data/validator'   # a.k.a. EIP 191 version 0
    SIGN_DATA_FOR_CLIQUE = 'application/clique'  # not relevant for us
    SIGN_DATA_FOR_ECRECOVER = 'text/plain'       # a.k.a. geth's `personal_sign`, EIP-191 version 45 (E)

    DEFAULT_CONTENT_TYPE = SIGN_DATA_FOR_ECRECOVER
    SIGN_DATA_CONTENT_TYPES = (SIGN_DATA_FOR_VALIDATOR, SIGN_DATA_FOR_CLIQUE, SIGN_DATA_FOR_ECRECOVER)

    def __init__(self, ipc_path: str = DEFAULT_IPC_PATH):
        super().__init__()
        w3 = Web3(provider=IPCProvider(ipc_path=ipc_path))  # TODO: Unify with clients or build error handling
        self.w3 = w3

    @classmethod
    def from_signer_uri(cls, uri: str) -> 'Web3Signer':
        uri_breakdown = urlparse(uri)
        signer = cls(ipc_path=uri_breakdown.path)
        return signer

    def is_connected(self) -> bool:
        return self.w3.isConnected()

    def accounts(self) -> List[str]:
        normalized_addresses = self.w3.manager.request_blocking("account_list", [])
        checksum_addresses = [to_checksum_address(addr) for addr in normalized_addresses]
        return checksum_addresses

    def sign_transaction(self, account: str, transaction: dict) -> HexBytes:
        formatters = {
            'nonce': Web3.toHex,
            'gasPrice': Web3.toHex,
            'gas': Web3.toHex,
            'value': Web3.toHex,
            'chainId': Web3.toHex,
            'from': to_normalized_address
        }
        transaction = apply_formatters_to_dict(formatters, transaction)
        signed = self.w3.manager.request_blocking("account_signTransaction", [transaction])
        return HexBytes(signed.raw)

    def sign_message(self, account: str, message: bytes, content_type: str = None, validator_address: str = None, **kwargs) -> str:
        """
        See https://github.com/ethereum/go-ethereum/blob/a32a2b933ad6793a2fe4172cd46c5c5906da259a/signer/core/signed_data.go#L185
        """
        if not content_type:
            content_type = self.DEFAULT_CONTENT_TYPE
        elif content_type not in self.SIGN_DATA_CONTENT_TYPES:
            raise ValueError(f'{content_type} is not a valid content type. '
                             f'Valid types are {self.SIGN_DATA_CONTENT_TYPES}')
        if content_type == self.SIGN_DATA_FOR_VALIDATOR:
            if not validator_address or validator_address == BlockchainInterface.NULL_ADDRESS:
                raise ValueError('When using the intended validator type, a validator address is required.')
            data = [validator_address, message]
        elif content_type == self.SIGN_DATA_FOR_ECRECOVER:
            data = message
        else:
            raise NotImplementedError

        return self.w3.manager.request_blocking("account_signData", [content_type, account, data])

    def unlock_account(self, account: str, password: str, duration: int = None) -> bool:
        return True

    def lock_account(self, account: str):
        return True
