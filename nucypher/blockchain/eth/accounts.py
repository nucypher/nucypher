import json
from json import JSONDecodeError
from pathlib import Path
from typing import Dict, Tuple

from cytoolz.dicttoolz import dissoc
from eth_account._utils.signing import to_standard_signature_bytes
from eth_account.account import Account as EthAccount
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount as EthLocalAccount
from eth_keys.datatypes import PrivateKey
from hexbytes.main import HexBytes

# AttributeError: The use of the Mnemonic features of Account is disabled by default until its API stabilizes.
# To use these features, please enable them by running `Account.enable_unaudited_hdwallet_features()` and try again.
EthAccount.enable_unaudited_hdwallet_features()


class InvalidKeystore(Exception):
    """Raised when the keystore file is invalid."""


class LocalAccount(EthLocalAccount):
    """
    Subclass of eth_account.signers.local.LocalAccount with additional
    functionality for managing keystore files, defaulting to the HD path
    and standardizing signatures.
    """

    __HD_PATH = "m/44'/60'/0'/0/0"

    def sign_message(self, message: bytes, standardize: bool = True) -> HexBytes:
        """Sign a message with the private key of this account."""
        signature = super().sign_message(signable_message=encode_defunct(primitive=message)).signature
        if standardize:
            # This signature will need to be passed to Rust, so we are cleaning the chain identifier
            # from the recovery byte, bringing it to the standard choice of {0, 1}.
            signature = to_standard_signature_bytes(signature)
        return HexBytes(signature)

    def sign_transaction(self, transaction_dict: dict) -> HexBytes:
        """Sign a transaction with the private key of this account."""
        if not transaction_dict['to']:
            # Edge case: do not include a 'to' field when deploying a contract.
            transaction_dict = dissoc(transaction_dict, 'to')
        signed_raw_transaction = super().sign_transaction(transaction_dict=transaction_dict).rawTransaction
        return HexBytes(signed_raw_transaction)

    @classmethod
    def from_mnemonic(cls, mnemonic: str, password: str, filepath: Path) -> Tuple['LocalAccount', Path]:
        """Derive an account from a mnemonic phrase and save the resulting keystore to the disk."""
        account = EthAccount.from_mnemonic(mnemonic=mnemonic, account_path=cls.__HD_PATH)
        account = cls(key=PrivateKey(account.key), account=EthAccount)
        filepath = account.to_keystore(path=filepath, password=password)
        return account, filepath

    @classmethod
    def from_keystore(cls, path: Path, password: str) -> 'LocalAccount':
        """
        Decrypt a keystore file using its password and return the resulting account.
        Keystore files must be in web3 secret storage format.
        """
        metadata = cls._read_wallet(filepath=path)
        private_key = EthAccount.decrypt(metadata, password=password)
        account = EthAccount.from_key(private_key=private_key)
        return cls(key=PrivateKey(account.key), account=EthAccount)

    def to_keystore(self, path: Path, password: str) -> Path:
        """
        Encrypt this account with a password and save the resulting keystore to the disk.
        Keystore files are produced in web3 secret storage format.
        """
        keyfile_json = self.encrypt(password=password)
        self._write_wallet(filepath=path, data=keyfile_json)
        return Path(path)

    @staticmethod
    def _read(filepath: Path) -> str:
        """
        Read a file and return its contents.
        This method is discrete from for testing & mocking purposes
        ."""
        with open(filepath, 'r') as f:
            data = f.read()
        return data

    @staticmethod
    def _write(filepath: Path, data: str) -> None:
        """
        Write data to a file.
        This method is discrete from for testing & mocking purposes.
        """
        with open(filepath, 'w') as f:
            f.write(data)

    @classmethod
    def _read_wallet(cls, filepath: Path) -> Dict:
        """Read a keystore file and return its contents."""
        data = cls._read(filepath=filepath)
        try:
            metadata = json.loads(data)
        except JSONDecodeError:
            raise InvalidKeystore(f'Invalid JSON in wallet keystore at {filepath}.')
        return metadata

    @classmethod
    def _write_wallet(cls, filepath: Path, data: Dict) -> None:
        """Write keystore data to a file."""
        if filepath.exists():
            raise FileExistsError(f'File {filepath} already exists.')
        filepath.parent.mkdir(parents=True, exist_ok=True)
        cls._write(filepath=filepath, data=json.dumps(data))
