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

from getpass import getpass

from hdwallet.cryptocurrencies import EthereumMainnet
from hdwallet.hdwallet import HDWallet
from hdwallet.utils import generate_entropy

# Choose strength 128, 160, 192, 224 or 256
STRENGTH: int = 160  # Default is 128

# Choose language english, french, italian, spanish, chinese_simplified, chinese_traditional, japanese or korean
LANGUAGE: str = "english"  # Default is english

ACCOUNTS = 10


def generate(prompt=False):
    if passphrase := prompt:
        passphrase = getpass('Enter passphrase (optional): ')
    entropy: str = generate_entropy(strength=STRENGTH)
    hdwallet = HDWallet()
    hdwallet.from_entropy(
        entropy=entropy,
        language=LANGUAGE,
        passphrase=passphrase
    )
    return hdwallet


def derive(wallet: HDWallet, quantity: int = ACCOUNTS):
    wallet.clean_derivation()
    for index in range(quantity):
        wallet.from_index(index)
        yield (wallet.public_key(), wallet.private_key())


def restore(words: str, prompt=False):
    if passphrase := prompt:
        passphrase = getpass('Enter passphrase (optional): ')
    wallet = HDWallet()
    wallet.from_mnemonic(
        mnemonic=words,
        language=LANGUAGE,
        passphrase=passphrase
    )
    return wallet


if __name__ == "__main__":

    # Generate
    wallet = generate()
    print(wallet.mnemonic())
    derive(wallet)

    # Restore
    # mnemonic = 'doctor office heavy general mercy romance narrow profit ice grief cushion punch fall together clever'
    mnemonic = wallet.mnemonic()
    wallet = restore(words=mnemonic)
    derive(wallet)
