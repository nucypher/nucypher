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
    pass


class LocalAccount(EthLocalAccount):
    __HD_PATH = "m/44'/60'/0'/0/0"

    def sign_message(self, message: bytes, standardize: bool = True) -> HexBytes:
        signature = super().sign_message(signable_message=encode_defunct(primitive=message)).signature
        if standardize:
            # This signature will need to be passed to Rust, so we are cleaning the chain identifier
            # from the recovery byte, bringing it to the standard choice of {0, 1}.
            signature = to_standard_signature_bytes(signature)
        return HexBytes(signature)

    def sign_transaction(self, transaction_dict: dict) -> HexBytes:
        if not transaction_dict['to']:
            # Edge case: do not include a 'to' field when deploying a contract.
            transaction_dict = dissoc(transaction_dict, 'to')
        signed_raw_transaction = super().sign_transaction(transaction_dict=transaction_dict).rawTransaction
        return HexBytes(signed_raw_transaction)

    @classmethod
    def from_mnemonic(cls, mnemonic: str, password: str, filepath: Path,) -> Tuple['LocalAccount', Path]:
        account = EthAccount.from_mnemonic(mnemonic=mnemonic, account_path=cls.__HD_PATH)
        account = cls(key=PrivateKey(account.key), account=EthAccount)
        filepath = account.to_keystore(path=filepath, password=password)
        return account, filepath

    @classmethod
    def from_keystore(cls, path: Path, password: str) -> 'LocalAccount':
        metadata = cls._read_wallet(filepath=path)
        private_key = EthAccount.decrypt(metadata, password=password)
        account = EthAccount.from_key(private_key=private_key)
        return cls(key=PrivateKey(account.key), account=EthAccount)

    def to_keystore(self, path: Path, password: str) -> Path:
        keyfile_json = self.encrypt(password=password)
        self._write_wallet(filepath=path, data=keyfile_json)
        return Path(path)

    @staticmethod
    def _read(filepath: Path) -> str:
        with open(filepath, 'r') as f:
            data = f.read()
        return data

    @staticmethod
    def _write(filepath: Path, data: str) -> None:
        with open(filepath, 'w') as f:
            f.write(data)

    @classmethod
    def _read_wallet(cls, filepath: Path) -> Dict:
        data = cls._read(filepath=filepath)
        try:
            metadata = json.loads(data)
        except JSONDecodeError:
            raise InvalidKeystore(f'Invalid JSON in wallet keystore at {filepath}.')
        return metadata

    @classmethod
    def _write_wallet(cls, filepath: Path, data: Dict) -> None:
        if filepath.exists():
            raise FileExistsError(f'File {filepath} already exists.')
        filepath.parent.mkdir(parents=True, exist_ok=True)
        cls._write(filepath=filepath, data=json.dumps(data))
