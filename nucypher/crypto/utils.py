import json
from pathlib import Path
from secrets import SystemRandom
from typing import Dict, NamedTuple, Tuple, Union

import click
from bip44 import Wallet
from eth_account.account import Account
from eth_account.messages import encode_defunct
from eth_hash.auto import keccak
from eth_keys import KeyAPI as EthKeyAPI
from eth_typing import ChecksumAddress
from eth_utils.address import to_checksum_address
from mnemonic import Mnemonic
from nucypher_core.umbral import PublicKey

from nucypher.crypto.signing import SignatureStamp
from nucypher.utilities.emitters import StdoutEmitter

SYSTEM_RAND = SystemRandom()


class WalletGeneration(NamedTuple):
    address: ChecksumAddress
    derivation_path: str
    filepath: Path


def canonical_address_from_umbral_key(public_key: Union[PublicKey, SignatureStamp]) -> bytes:
    if isinstance(public_key, SignatureStamp):
        public_key = public_key.as_umbral_pubkey()
    pubkey_compressed_bytes = public_key.to_compressed_bytes()
    eth_pubkey = EthKeyAPI.PublicKey.from_compressed_bytes(pubkey_compressed_bytes)
    canonical_address = eth_pubkey.to_canonical_address()
    return canonical_address


def secure_random(num_bytes: int) -> bytes:
    """
    Returns an amount `num_bytes` of data from the OS's random device.
    If a randomness source isn't found, returns a `NotImplementedError`.
    In this case, a secure random source most likely doesn't exist and
    randomness will have to found elsewhere.

    :param num_bytes: Number of bytes to return.

    :return: bytes
    """
    # TODO: Should we just use os.urandom or avoid the import w/ this?
    return SYSTEM_RAND.getrandbits(num_bytes * 8).to_bytes(num_bytes, byteorder='big')


def secure_random_range(min: int, max: int) -> int:
    """
    Returns a number from a secure random source between the range of
    `min` and `max` - 1.

    :param min: Minimum number in the range
    :param max: Maximum number in the range

    :return: int
    """
    return SYSTEM_RAND.randrange(min, max)


def keccak_digest(*messages: bytes) -> bytes:
    """
    Accepts an iterable containing bytes and digests it returning a
    Keccak digest of 32 bytes (keccak_256).

    Uses `eth_hash`, which accepts bytearray/bytes only, to provide a consistent implementation.

    Although we use SHA256 in many cases, we keep keccak handy in order
    to provide compatibility with the Ethereum blockchain.

    :param bytes: Data to hash

    :rtype: bytes
    :return: bytestring of digested data
    """
    # TODO: There's a higher-level tool in eth-utils that will optionally also take a string.  Do we want to use that?
    # https://eth-utils.readthedocs.io/en/stable/utilities.html#keccak-bytes-int-bool-text-str-hexstr-str-bytes
    joined_bytes = bytes().join(messages)
    digest = keccak(joined_bytes)
    return digest


def recover_address_eip_191(message: bytes, signature: bytes) -> str:
    """
    Recover checksum address from EIP-191 signature
    """
    signable_message = encode_defunct(primitive=message)
    recovery = Account.recover_message(signable_message=signable_message, signature=signature)
    recovered_address = to_checksum_address(recovery)
    return recovered_address


def verify_eip_191(address: str, message: bytes, signature: bytes) -> bool:
    """
    EIP-191 Compatible signature verification for usage with w3.eth.sign.
    """
    recovered_address = recover_address_eip_191(message=message, signature=signature)
    signature_is_valid = recovered_address == to_checksum_address(address)
    return signature_is_valid


def _confirm_generate(__words: str) -> None:
    """
    Inform the caller of new keystore seed words generation the console
    and optionally perform interactive confirmation.
    """

    # notification
    emitter = StdoutEmitter()

    emitter.echo(
        "\nNOTE: Next, you will be assigned a taco node seed phase. This seed phase is used to\n"
        "generate your keystore. You will need this seed phase to recover your keystore\n"
        "in the future. Please write down the seed phase and keep it in a safe place.\n",
        color="cyan",
    )

    emitter.message(
        "IMPORTANT: Backup your seed phrase, you will not be able to view them again.\n"
        "You can use these words to restore your keystore in the future in case of loss of\n"
        "your keystore files or password. Do not share these words with anyone.\n",
        color="yellow",
    )

    emitter.message(
        "WARNING: If you lose your seed phase and also lose access to your keystore/password "
        "your stake will be slashed.\n",
        color="red",
    )
    click.confirm("Reveal seed phase?", default=False, abort=True)
    click.clear()

    formatted_words = "\n".join(
        f"{i} {w}" for i, w in enumerate(__words.split(), start=1)
    )
    emitter.message(f"{formatted_words}\n", color="green")
    if not click.confirm("Have you backed up your seed phrase?"):
        emitter.message("Keystore generation aborted.", color="red")
        raise click.Abort()
    click.clear()

    # confirmation
    while True:
        __response = click.prompt("Confirm seed words (space separated)")
        if __response != __words:
            emitter.message("Seed words do not match. Please try again.", color="red")
            continue
        break
    click.clear()
    emitter.echo("Seed phrase confirmed. Generating keystore...", color="green")


def _confirm_wallet(address: str, derivation_path: str, filepath: Path) -> None:
    emitter = StdoutEmitter()
    emitter.message(
        f"""
Operator wallet generated successfully!
Address: {address}
Derivation: {derivation_path}
Filepath: {filepath.absolute()}
    """,
        color="cyan",
    )


def _generate_mnemonic(
    entropy: int, language: str, interactive: bool
) -> Tuple[Mnemonic, str]:
    mnemonic = Mnemonic(language=language)
    __words = mnemonic.generate(strength=entropy)
    if interactive:
        _confirm_generate(__words)
    return mnemonic, __words


def _write_wallet(filepath: Path, data: Dict) -> None:
    if filepath.exists():
        raise FileExistsError(f"File {filepath} already exists.")
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f)


def _generate_wallet(
    phrase: str,
    language: str,
    password: str,
    filepath: Path,
    index: int = 0,
) -> WalletGeneration:
    """
    Generate an encrypted ethereum wallet from seed words using a bip44 derivation path.
    Uses the web3 secret storage definition for the keystore format.
    https://github.com/ethereum/wiki/wiki/Web3-Secret-Storage-Definition
    """
    if not isinstance(index, int):
        raise TypeError("Index must be an integer.")
    derivation_path = f"m/44'/60'/0'/0/{str(index)}"
    wallet = Wallet(mnemonic=phrase, language=language)
    private_key = wallet.derive_secret_key(path=derivation_path)
    account = Account.from_key(private_key)
    keystore = Account.encrypt(private_key, password)
    _write_wallet(filepath=filepath, data=keystore)
    wallet_generation = WalletGeneration(account.address, derivation_path, filepath)
    return wallet_generation
