import json
from json.decoder import JSONDecodeError
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from cytoolz.dicttoolz import dissoc
from eth_account.account import Account
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount
from eth_utils.address import is_address, to_checksum_address
from hexbytes.main import BytesLike, HexBytes

from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.signers.base import Signer


class Web3Signer(Signer):
    def __init__(self, client):
        super().__init__()
        self.__client = client

    @validate_checksum_address
    def _get_signer(self, account: str):
        raise NotImplementedError(
            "Can't sign via external blockchain clients; provide an explicit Signer"
        )

    @classmethod
    def uri_scheme(cls) -> str:
        return NotImplemented  # web3 signer uses a "passthrough" scheme

    @classmethod
    def from_signer_uri(cls, uri: str, testnet: bool = False) -> "Web3Signer":
        from nucypher.blockchain.eth.interfaces import (
            BlockchainInterface,
            BlockchainInterfaceFactory,
        )

        try:
            blockchain = BlockchainInterfaceFactory.get_or_create_interface(
                endpoint=uri
            )
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
        return False

    @validate_checksum_address
    def unlock_account(self, account: str, password: str, duration: int = None):
        raise NotImplementedError(
            "Can't manage accounts via external blockchain clients; provide an explicit Signer"
        )

    @validate_checksum_address
    def lock_account(self, account: str):
        raise NotImplementedError(
            "Can't manage accounts via external blockchain clients; provide an explicit Signer"
        )

    @validate_checksum_address
    def sign_message(self, account: str, message: bytes, **kwargs) -> HexBytes:
        raise NotImplementedError(
            "Can't sign via external blockchain clients; provide an explicit Signer"
        )

    def sign_transaction(self, transaction_dict: dict) -> bytes:
        raise NotImplementedError(
            "Can't sign via external blockchain clients; provide an explicit Signer"
        )


class KeystoreSigner(Signer):
    """Local Web3 signer implementation supporting keystore files"""

    __keys: Dict[str, dict]
    __signers: Dict[str, LocalAccount]

    class InvalidKeyfile(Signer.SignerError, RuntimeError):
        """
        Raised when a keyfile is corrupt or otherwise invalid.
        Keystore must be in the geth wallet format.
        """

    def __init__(self, path: Path, testnet: bool = False):
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
        return "keystore"

    def __read_keystore(self, path: Path) -> None:
        """Read the keystore directory from the disk and populate accounts."""
        try:
            if path.is_dir():
                paths = (entry for entry in path.iterdir() if entry.is_file())
            elif path.is_file():
                paths = (path,)
            else:
                raise self.InvalidSignerURI(
                    f'Invalid keystore file or directory "{path}"'
                )
        except FileNotFoundError:
            raise self.InvalidSignerURI(f'No such keystore file or directory "{path}"')
        except OSError as exc:
            raise self.InvalidSignerURI(
                f'Error accessing keystore file or directory "{path}": {exc}'
            )
        for path in paths:
            account, key_metadata = self.__handle_keyfile(path=path)
            self.__keys[account] = key_metadata

    @staticmethod
    def __read_keyfile(path: Path) -> tuple:
        """Read an individual keystore key file from the disk"""
        with open(path, "r") as keyfile:
            key_metadata = json.load(keyfile)
        address = key_metadata["address"]
        return address, key_metadata

    def __handle_keyfile(self, path: Path) -> Tuple[str, dict]:
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
                try:
                    address = to_checksum_address(address)
                except ValueError:
                    raise self.InvalidKeyfile(
                        f"'{path}' does not contain a valid ethereum address"
                    )
            address = to_checksum_address(address)
        return address, key_metadata

    @validate_checksum_address
    def _get_signer(self, account: str) -> LocalAccount:
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
    def path(self) -> Path:
        """Read only access to the keystore path"""
        return self.__path

    @classmethod
    def from_signer_uri(cls, uri: str, testnet: bool = False) -> "Signer":
        """Return a keystore signer from URI string i.e. keystore:///my/path/keystore"""
        decoded_uri = urlparse(uri)
        if decoded_uri.scheme != cls.uri_scheme() or decoded_uri.netloc:
            raise cls.InvalidSignerURI(uri)
        path = decoded_uri.path
        if not path:
            raise cls.InvalidSignerURI("Blank signer URI - No keystore path provided")
        return cls(path=Path(path), testnet=testnet)

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
                    raise self.AuthenticationFailed(
                        "No password supplied to unlock account."
                    )
                raise
            except ValueError as e:
                raise self.AuthenticationFailed(
                    "Invalid or incorrect ethereum account password."
                ) from e
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
    def sign_transaction(self, transaction_dict: dict) -> bytes:
        """
        Produce a raw signed ethereum transaction signed by the account specified
        in the 'from' field of the transaction dictionary.
        """

        sender = transaction_dict["from"]
        signer = self._get_signer(account=sender)

        # TODO: Handle this at a higher level?
        # Do not include a 'to' field for contract creation.
        if not transaction_dict["to"]:
            transaction_dict = dissoc(transaction_dict, "to")

        raw_transaction = signer.sign_transaction(
            transaction_dict=transaction_dict
        ).rawTransaction
        return raw_transaction

    @validate_checksum_address
    def sign_message(self, account: str, message: bytes, **kwargs) -> HexBytes:
        signer = self._get_signer(account=account)
        signature = signer.sign_message(
            signable_message=encode_defunct(primitive=message)
        ).signature
        return HexBytes(signature)


class InMemorySigner(Signer):
    """Local signer implementation for in-memory-only keys"""

    def __init__(self, private_key: Optional[BytesLike] = None):
        super().__init__()
        if private_key:
            account = Account.from_key(private_key)
        else:
            account = Account.create()
        self.__keys = {account.address: account.key.hex()}
        self.__signers = {account.address: account}

    @classmethod
    def from_signer_uri(cls, uri: str, testnet: bool = False) -> "Signer":
        """Return an in-memory signer from URI string i.e. memory://"""
        decoded_uri = urlparse(uri)
        if decoded_uri.scheme != cls.uri_scheme() or decoded_uri.netloc:
            raise cls.InvalidSignerURI(uri)
        return cls()

    @classmethod
    def uri_scheme(cls) -> str:
        return "memory"

    def lock_account(self, account: str) -> bool:
        return True

    @property
    def accounts(self) -> List[str]:
        """Return a list of known in-memory accounts read from"""
        return list(self.__keys.keys())

    @validate_checksum_address
    def is_device(self, account: str) -> bool:
        return False  # In-memory accounts are never devices.

    @validate_checksum_address
    def unlock_account(self, account: str, password: str, duration: int = None) -> bool:
        return True

    @validate_checksum_address
    def _get_signer(self, account: str) -> LocalAccount:
        """Lookup a known keystore account by its checksum address or raise an error"""
        try:
            return self.__signers[account]
        except KeyError:
            if account not in self.__keys:
                raise self.UnknownAccount(account=account)
            else:
                raise self.AccountLocked(account=account)

    @validate_checksum_address
    def sign_transaction(self, transaction_dict: dict) -> bytes:
        sender = transaction_dict["from"]
        signer = self._get_signer(account=sender)
        if not transaction_dict["to"]:
            transaction_dict = dissoc(transaction_dict, "to")
        raw_transaction = signer.sign_transaction(
            transaction_dict=transaction_dict
        ).rawTransaction
        return raw_transaction

    @validate_checksum_address
    def sign_message(self, account: str, message: bytes, **kwargs) -> HexBytes:
        signer = self._get_signer(account=account)
        signature = signer.sign_message(
            signable_message=encode_defunct(primitive=message)
        ).signature
        return HexBytes(signature)
