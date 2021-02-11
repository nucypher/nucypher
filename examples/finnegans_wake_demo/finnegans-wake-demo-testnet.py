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


import datetime
import maya
import os
from pathlib import Path
from umbral.keys import UmbralPublicKey
from web3.main import Web3

from nucypher.blockchain.eth.signers.base import Signer
from nucypher.characters.lawful import Alice, Bob, Ursula
from nucypher.characters.lawful import Enrico as Enrico
from nucypher.crypto.powers import SigningPower, DecryptingPower
from nucypher.utilities.logging import GlobalLoggerSettings

######################
# Boring setup stuff #
######################

# Twisted Logger
GlobalLoggerSettings.set_log_level(log_level_name='debug')
GlobalLoggerSettings.start_console_logging()

BOOK_PATH = Path('finnegans-wake-excerpt.txt')

# Configuration
DOMAIN = 'lynx'  # testnet

# Seednode
SEEDNODE = Ursula.seednode_for_network('lynx')

# Replace with ethereum RPC endpoint
ETH_PROVIDER = ''
PROVIDER_URI = os.environ.get('NUCYPHER_PROVIDER_URI', ETH_PROVIDER)

# Replace with wallet filepath.
WALLET_FILEPATH = ''
ETH_WALLET = f'keystore://{WALLET_FILEPATH}'
SIGNER_URI = os.environ.get('NUCYPHER_SIGNER_URI', ETH_WALLET)

# Replace with alice's ethereum address
ETH_ADDRESS = ''
ALICE_ETH_ADDRESS = os.environ.get('NUCYPHER_ALICE_ETH_ADDRESS', ETH_ADDRESS)

# Check for complete setup
if not all((PROVIDER_URI, SIGNER_URI, ALICE_ETH_ADDRESS)):
    raise RuntimeError('Missing environment variables to run demo.')

#####################
# Bob the BUIDLer  ##
#####################

# First there was Bob.
BOB = Bob(
    known_nodes=[SEEDNODE],
    domain=DOMAIN,
    provider_uri=PROVIDER_URI
)

# Bob gives his public keys to alice.
verifying_key = BOB.public_keys(SigningPower)
encrypting_key = BOB.public_keys(DecryptingPower)

######################################
# Alice, the Authority of the Policy #
######################################

# Alice ethereum wallet
wallet = Signer.from_signer_uri(SIGNER_URI)
password = input(f'Enter password to unlock {ALICE_ETH_ADDRESS}: ')
wallet.unlock_account(account=ALICE_ETH_ADDRESS, password=password)

ALICE = Alice(

    # Connection details
    domain=DOMAIN,
    known_nodes=[SEEDNODE],
    provider_uri=PROVIDER_URI,

    # Wallet details
    checksum_address=ALICE_ETH_ADDRESS,
    signer=wallet,
    client_password=password
)

# Here are the Policy details.
policy_end_datetime = maya.now() + datetime.timedelta(days=1)
m, n = 2, 3
label = b"secret/files/and/stuff"

# Alice can get the public key even before creating the policy.
# From this moment on, any Data Source that knows the public key
# can encrypt data originally intended for Alice, but that can be shared with
# any Bob that Alice grants access.
policy_public_key = ALICE.get_policy_encrypting_key_from_label(label)

# Alice already knows Bob's public keys from a side-channel.
stranger_bob = Bob.from_public_keys(encrypting_key=encrypting_key, verifying_key=verifying_key)

# Alice grants access to bob.
policy = ALICE.grant(
    bob=stranger_bob,
    label=label,
    m=m,
    n=n,
    rate=Web3.toWei(50, 'gwei'),
    expiration=policy_end_datetime
)

# Alice puts her public key somewhere for Bob to find later...
alice_public_key = bytes(ALICE.stamp)

# ...and then disappears from the internet.
ALICE.disenchant()
del ALICE

#####################
# some time passes. #
# ...               #
#                   #
# ...               #
# And now for Bob.  #
#####################

BOB.join_policy(label, alice_public_key)

# Now that Bob has joined the Policy, let's show how Enrico the Encryptor
# can share data with the members of this Policy and then how Bob retrieves it.
# In order to avoid re-encrypting the entire book in this demo, we only read some lines.
with open(BOOK_PATH, 'rb') as file:
    finnegans_wake = file.readlines()

print()
print("**************James Joyce's Finnegan's Wake (Excerpt)**************")
print()
print("---------------------------------------------------------")

for counter, plaintext in enumerate(finnegans_wake):

    #########################
    # Enrico, the Encryptor #
    #########################
    enrico = Enrico(policy_encrypting_key=policy_public_key)

    # In this case, the plaintext is a
    # single passage from James Joyce's Finnegan's Wake.
    # The matter of whether encryption makes the passage more or less readable
    # is left to the reader to determine.
    single_passage_ciphertext, _signature = enrico.encrypt_message(plaintext)
    enrico_public_key = bytes(enrico.stamp)
    del enrico

    ###############
    # Back to Bob #
    ###############

    enrico_as_understood_by_bob = Enrico.from_public_keys(
        verifying_key=enrico_public_key,
        policy_encrypting_key=policy_public_key
    )

    # Now Bob can retrieve the original message.
    alice_pubkey_restored_from_ancient_scroll = UmbralPublicKey.from_bytes(alice_public_key)
    delivered_cleartexts = BOB.retrieve(single_passage_ciphertext,
                                        enrico=enrico_as_understood_by_bob,
                                        alice_verifying_key=alice_pubkey_restored_from_ancient_scroll,
                                        label=label)

    # We show that indeed this is the passage originally encrypted by Enrico.
    assert plaintext == delivered_cleartexts[0]
    print("Retrieved: {}".format(delivered_cleartexts[0]))

BOB.disenchant()
