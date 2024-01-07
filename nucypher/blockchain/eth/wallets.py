import json
from json.decoder import JSONDecodeError
from pathlib import Path
from typing import Dict

from cytoolz.dicttoolz import dissoc
from eth_account.account import Account
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount
from eth_typing import ChecksumAddress
from eth_utils.address import to_checksum_address, to_canonical_address
from hexbytes.main import HexBytes
from eth_account._utils.signing import to_standard_signature_bytes

# AttributeError: The use of the Mnemonic features of Account is disabled by default until its API stabilizes.
# To use these features, please enable them by running `Account.enable_unaudited_hdwallet_features()` and try again.
Account.enable_unaudited_hdwallet_features()


class Wallet:
    """LocalAccount wrapper"""

    _HD_PATH = "m/44'/60'/0'/0/{index}"  # BIP44 HD Wallet path

    class WalletError(Exception):
        """Base exception class for wallet errors"""

    class InvalidKeystore(WalletError, RuntimeError):
        """
        Raised when a web3 secret storage keystore wallet cannot
        be read, decrypted, or otherwise invalid.
        """

    def __init__(self, account: LocalAccount):
        self.__account = account

    def __eq__(self, other):
        try:
            return self.address == other.address
        except AttributeError:
            raise TypeError(f"Cannot compare {type(self)} to {type(other)}")

    def __hash__(self) -> int:
        return hash(to_canonical_address(self.address))

    def __repr__(self):
        return f"<Wallet {self.address}>"

    @property
    def address(self) -> ChecksumAddress:
        return ChecksumAddress(to_checksum_address(self.__account.address))

    @classmethod
    def random(cls) -> 'Wallet':
        account = Account.create()
        instance = cls(account=account)
        return instance

    @classmethod
    def from_key(cls, key: str) -> 'Wallet':
        account = Account.from_key(key)
        instance = cls(account=account)
        return instance

    @classmethod
    def from_mnemonic(cls, mnemonic: str, index: int = 0) -> 'Wallet':
        full_path = cls._HD_PATH.format(index=index)
        account = Account.from_mnemonic(mnemonic=mnemonic, account_path=full_path)
        instance = cls(account=account)
        return instance

    @staticmethod
    def __read_keystore(path: Path) -> Dict:
        with open(path, 'r') as keyfile:
            metadata = json.load(keyfile)
        return metadata

    @classmethod
    def from_keystore(cls, path: Path, password: str) -> 'Wallet':
        try:
            metadata = cls.__read_keystore(path=path)
        except FileNotFoundError:
            error = f"No such keyfile '{path}'"
            raise cls.InvalidKeystore(error)
        except JSONDecodeError:
            error = f"Invalid JSON in keyfile at {path}"
            raise cls.InvalidKeystore(error)
        except KeyError:
            error = f"Keyfile does not contain address field at '{path}'"
            raise cls.InvalidKeystore(error)
        instance = cls.from_key(Account.decrypt(metadata, password=password))
        return instance

    def to_keystore(self, path: Path, password: str) -> Path:
        keyfile_json = self.__account.encrypt(password=password)
        with open(path, 'w') as keyfile:
            json.dump(obj=keyfile_json, fp=keyfile)
        return Path(path)

    def sign_transaction(self, transaction_dict: dict) -> HexBytes:
        if not transaction_dict['to']:
            # edge case: do not include a 'to' field when deploying a contract.
            transaction_dict = dissoc(transaction_dict, 'to')
        raw_transaction = self.__account.sign_transaction(transaction_dict=transaction_dict).rawTransaction
        return raw_transaction

    def sign_message(self, message: bytes, standardize: bool = True) -> HexBytes:
        signature = self.__account.sign_message(signable_message=encode_defunct(primitive=message)).signature
        if standardize:
            # This signature will need to be passed to Rust, so we are cleaning the chain identifier
            # from the recovery byte, bringing it to the standard choice of {0, 1}.
            signature = to_standard_signature_bytes(signature)
        return HexBytes(signature)
