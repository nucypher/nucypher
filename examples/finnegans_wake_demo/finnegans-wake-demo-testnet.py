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
    SIGNER_URI = os.environ['DEMO_SIGNER_URI']

    # Replace with alice's ethereum address
    ALICE_ETH_ADDRESS = os.environ['DEMO_ALICE_ETH_ADDRESS']

except KeyError:
    raise RuntimeError('Missing environment variables to run demo.')

####################
# NuCypher Network #
####################

# Ursulas are running on the testnet.
# Get an initial 'seednode' to start discovering the network later...
DOMAIN = 'lynx'
SEEDNODE = Ursula.seednode_for_network(DOMAIN)

#####################
# Bob the BUIDLer  ##
#####################

# Then, there was bob. Bob learns about the
# rest of the network from the seednode.
LOCAL_BOB = Bob(domain=DOMAIN, known_nodes=[SEEDNODE])

# Bob puts his public keys somewhere alice can find them.
verifying_key = LOCAL_BOB.public_keys(SigningPower)
encrypting_key = LOCAL_BOB.public_keys(DecryptingPower)
print(verifying_key.hex())
print(encrypting_key.hex())

######################################
# Alice, the Authority of the Policy #
######################################

# Connect to the ethereum provider now so that
# alice does not have to do it later.
print("Connecting to ethereum provider...")
connect_web3_provider(provider_uri=PROVIDER_URI)
print("Connected!")

# Alice has an ethereum wallet to pay for a PRE policy.
# In this demo a software wallet is used, but hardware
# wallets can also be used.  Unlock it with the password.
wallet = Signer.from_signer_uri(SIGNER_URI)
password = getpass(f"Enter password to unlock alice's wallet {ALICE_ETH_ADDRESS[:8]}: ")
wallet.unlock_account(account=ALICE_ETH_ADDRESS, password=password)
print(f'Unlocked {ALICE_ETH_ADDRESS[:8]}')

LOCAL_ALICE = Alice(
    domain=DOMAIN,
    known_nodes=[SEEDNODE],
    checksum_address=ALICE_ETH_ADDRESS,
    signer=wallet
)

# Here are the policy details.
expiration = maya.now() + datetime.timedelta(days=1)
label = b"secret/files/and/stuff"
m, n = 2, 3  # threshold, shares

# Alice can get the policy's public key even before creating the policy.
policy_public_key = LOCAL_ALICE.get_policy_encrypting_key_from_label(label)

# From this moment on, anyone that knows the public key
# can encrypt data originally intended for Alice, but that
# can be shared with any Bob that Alice grants access.

# Alice already knows Bob's public keys from a side-channel.
remote_bob = Bob.from_public_keys(encrypting_key=encrypting_key,
                                  verifying_key=verifying_key)

# Alice grants access to Bob by generating kfrags
# and publishing the policy.  In this example Alice
# pays each node 50 gwei per period.
input('Press RETURN to grant ')
policy = LOCAL_ALICE.grant(
    bob=remote_bob,
    label=label,
    m=m,
    n=n,
    rate=Web3.toWei(50, 'gwei'),
    expiration=expiration
)
print(f"Granted Bob access to policy {policy.public_key}")

# Alice puts her public key somewhere for Bob to find later...
alice_verifying_key = bytes(LOCAL_ALICE.stamp)

# ...and then disappears from the internet.
#
# Note that local characters (alice and bob), as opposed to objects representing
# remote characters constructed from public data (remote_alice and remote_bob)
# run a learning loop in a background thread and need to be stopped explicitly.
LOCAL_ALICE.disenchant()
del LOCAL_ALICE

#####################
# some time passes. #
# ...               #
#                   #
# ...               #
# And now for Bob.  #
#####################

LOCAL_BOB.join_policy(label, alice_verifying_key)

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

    # In this case, the plaintext is a single passage from James Joyce's Finnegan's Wake.
    # The matter of whether encryption makes the passage more or less readable
    # is left to the reader to determine.
    single_passage_ciphertext, _signature = enrico.encrypt_message(plaintext)
    enrico_public_key = bytes(enrico.stamp)
    del enrico

    ###############
    # Back to Bob #
    ###############

    # Now Bob can retrieve the original message by requesting re-encryption from nodes.
    delivered_cleartexts = LOCAL_BOB.retrieve(single_passage_ciphertext,
                                              policy_encrypting_key=policy_public_key,
                                              alice_verifying_key=alice_verifying_key,
                                              label=label)

    # We show that indeed this is the passage originally encrypted by Enrico.
    assert plaintext == delivered_cleartexts[0]
    print(f"Retrieved: {delivered_cleartexts[0]}")

LOCAL_BOB.disenchant()
