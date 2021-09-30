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

import datetime
import maya
import os
from pathlib import Path
from web3.main import Web3

from nucypher.blockchain.eth.signers.base import Signer
from nucypher.characters.lawful import Alice, Bob, Ursula
from nucypher.characters.lawful import Enrico as Enrico
from nucypher.crypto.powers import SigningPower, DecryptingPower
from nucypher.utilities.ethereum import connect_web3_provider
from nucypher.utilities.logging import GlobalLoggerSettings


######################
# Boring setup stuff #
######################

GlobalLoggerSettings.set_log_level(log_level_name='debug')
GlobalLoggerSettings.start_console_logging()

BOOK_PATH = Path('finnegans-wake-excerpt.txt')

try:

    # Replace with ethereum RPC endpoint
    PROVIDER_URI = os.environ['DEMO_PROVIDER_URI']

    # Replace with wallet filepath.
    WALLET_FILEPATH = os.environ['DEMO_WALLET_FILEPATH']
    SIGNER_URI = f'keystore://{WALLET_FILEPATH}'

    # Replace with alice's ethereum address
    ALICE_ADDRESS = os.environ['DEMO_ALICE_ADDRESS']

except KeyError:
    raise RuntimeError('Missing environment variables to run demo.')


####################
# NuCypher Network #
####################

TESTNET = 'lynx'

#####################
# Bob the BUIDLer  ##
#####################

# Then, there was bob. Bob learns about the
# rest of the network from the seednode.
bob = Bob(domain=TESTNET)

# Bob puts his public keys somewhere alice can find them.
verifying_key = bob.public_keys(SigningPower)
encrypting_key = bob.public_keys(DecryptingPower)

######################################
# Alice, the Authority of the Policy #
######################################

# Connect to the ethereum provider.
connect_web3_provider(provider_uri=PROVIDER_URI)

# Setup and unlock alice's ethereum wallet.
# WARNING: Never give your mainnet password or mnemonic phrase to anyone.
# Do not use mainnet keys, create a dedicated software wallet to use for this demo.
wallet = Signer.from_signer_uri(SIGNER_URI)
password = os.environ.get('DEMO_ALICE_PASSWORD') or getpass(f"Enter password to unlock {ALICE_ADDRESS[:8]}: ")
wallet.unlock_account(account=ALICE_ADDRESS, password=password)

# This is Alice.
alice = Alice(checksum_address=ALICE_ADDRESS, signer=wallet, domain=TESTNET, provider_uri=PROVIDER_URI)

# Alice puts her public key somewhere for Bob to find later...
alice_verifying_key = bytes(alice.stamp)

# Alice can get the policy's public key even before creating the policy.
label = b"secret/files/42"
policy_public_key = alice.get_policy_encrypting_key_from_label(label)

# From this moment on, anyone that knows the public key
# can encrypt data originally intended for Alice, but that
# can be shared with any Bob that Alice grants access.

# Alice already knows Bob's public keys from a side-channel.
remote_bob = Bob.from_public_keys(encrypting_key=encrypting_key, verifying_key=verifying_key)

# These are the policy details for bob.
# In this example bob will be granted access for 1 day,
# trusting 2 of 3 nodes paying each of them 50 gwei per period.
expiration = maya.now() + datetime.timedelta(days=1)
rate = Web3.toWei(50, 'gwei')
threshold, shares = 2, 3

# Alice grants access to Bob...
policy = alice.grant(remote_bob, label, threshold=threshold, shares=shares, rate=rate, expiration=expiration)

# ...and then disappears from the internet.
#
# Note that local characters (alice and bob), as opposed to objects representing
# remote characters constructed from public data (remote_alice and remote_bob)
# run node discovery in a background thread and must be stopped explicitly.
alice.disenchant()
del alice

#########################
# Enrico, the Encryptor #
#########################

# Now that Bob has access to the policy, let's show how Enrico the Encryptor
# can share data with the members of this Policy and then how Bob retrieves it.
with open(BOOK_PATH, 'rb') as file:
    finnegans_wake = file.readlines()

print("\n**************James Joyce's Finnegan's Wake (Excerpt)**************\n")

for counter, plaintext in enumerate(finnegans_wake):

    # Enrico knows the policy's public key from a side-channel.
    enrico = Enrico(policy_encrypting_key=policy_public_key)

    # In this case, the plaintext is a single passage from James Joyce's Finnegan's Wake.
    # The matter of whether encryption makes the passage more or less readable
    # is left to the reader to determine.  Many data sources (Enricos) can
    # encrypt fot the policy's public key.
    message_kit = enrico.encrypt_message(plaintext)
    enrico_public_key = bytes(enrico.stamp)
    del enrico

    ###############
    # Back to Bob #
    ###############

    # Now Bob can retrieve the original message by requesting re-encryption from nodes.
    cleartexts = bob.retrieve_and_decrypt([message_kit],
                                          alice_verifying_key=alice_verifying_key,
                                          encrypted_treasure_map=policy.treasure_map)

    # We show that indeed this is the passage originally encrypted by Enrico.
    assert plaintext == cleartexts[0]

bob.disenchant()
