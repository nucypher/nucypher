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

import os
import sys

import datetime
import maya
from umbral.keys import UmbralPublicKey

from nucypher.characters.lawful import Alice, Bob, Ursula
from nucypher.characters.lawful import Enrico as Enrico
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.logging import GlobalLoggerSettings

######################
# Boring setup stuff #
######################

# Execute the download script (download_finnegans_wake.sh) to retrieve the book
BOOK_PATH = os.path.join('.', 'finnegans-wake.txt')

# Change this value to to perform more or less total re-encryptions
# in order to avoid processing the entire book's text. (it's long)
NUMBER_OF_LINES_TO_REENCRYPT = 25

# Twisted Logger
GlobalLoggerSettings.set_log_level(log_level_name='debug')
GlobalLoggerSettings.start_console_logging()


#######################################
# Finnegan's Wake on NuCypher Testnet #
# (will fail with bad connection) #####
#######################################

# if your ursulas are NOT running on your current host,
# run like this: python finnegans-wake-demo.py 172.28.1.3:11500
# otherwise the default will be fine.

try:
    SEEDNODE_URI = sys.argv[1]
except IndexError:
    SEEDNODE_URI = "localhost:11500"

##############################################
# Ursula, the Untrusted Re-Encryption Proxy  #
##############################################
ursula = Ursula.from_seed_and_stake_info(seed_uri=SEEDNODE_URI,
                                         federated_only=True,
                                         minimum_stake=0)

# Here are our Policy details.
policy_end_datetime = maya.now() + datetime.timedelta(days=5)
m, n = 2, 3
label = b"secret/files/and/stuff"

######################################
# Alice, the Authority of the Policy #
######################################

ALICE = Alice(network_middleware=RestMiddleware(),
              domain=TEMPORARY_DOMAIN,
              known_nodes=[ursula],
              learn_on_same_thread=True,
              federated_only=True)

# Alice can get the public key even before creating the policy.
# From this moment on, any Data Source that knows the public key
# can encrypt data originally intended for Alice, but that can be shared with
# any Bob that Alice grants access.
policy_pubkey = ALICE.get_policy_encrypting_key_from_label(label)

BOB = Bob(known_nodes=[ursula],
          domain=TEMPORARY_DOMAIN,
          network_middleware=RestMiddleware(),
          federated_only=True,
          start_learning_now=True,
          learn_on_same_thread=True)

ALICE.start_learning_loop(now=True)
ALICE.block_until_number_of_known_nodes_is(8, timeout=30, learn_on_this_thread=True)  # In case the fleet isn't fully spun up yet, as sometimes happens on CI.

policy = ALICE.grant(BOB,
                     label,
                     m=m, n=n,
                     expiration=policy_end_datetime)

assert policy.public_key == policy_pubkey
policy.treasure_map_publisher.block_until_complete()

# Alice puts her public key somewhere for Bob to find later...
alices_pubkey_bytes_saved_for_posterity = bytes(ALICE.stamp)

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

#####################
# Bob the BUIDLer  ##
#####################

BOB.join_policy(label, alices_pubkey_bytes_saved_for_posterity)

# Now that Bob has joined the Policy, let's show how Enrico the Encryptor
# can share data with the members of this Policy and then how Bob retrieves it.
# In order to avoid re-encrypting the entire book in this demo, we only read some lines.
with open(BOOK_PATH, 'rb') as file:
    finnegans_wake = file.readlines()[:NUMBER_OF_LINES_TO_REENCRYPT]

print()
print("**************James Joyce's Finnegan's Wake**************")
print()
print("---------------------------------------------------------")

for counter, plaintext in enumerate(finnegans_wake):

    #########################
    # Enrico, the Encryptor #
    #########################
    enrico = Enrico(policy_encrypting_key=policy_pubkey)

    # In this case, the plaintext is a
    # single passage from James Joyce's Finnegan's Wake.
    # The matter of whether encryption makes the passage more or less readable
    # is left to the reader to determine.
    single_passage_ciphertext, _signature = enrico.encrypt_message(plaintext)
    data_source_public_key = bytes(enrico.stamp)
    del enrico

    ###############
    # Back to Bob #
    ###############

    enrico_as_understood_by_bob = Enrico.from_public_keys(
        verifying_key=data_source_public_key,
        policy_encrypting_key=policy_pubkey
    )

    # Now Bob can retrieve the original message.
    alice_pubkey_restored_from_ancient_scroll = UmbralPublicKey.from_bytes(alices_pubkey_bytes_saved_for_posterity)
    delivered_cleartexts = BOB.retrieve(single_passage_ciphertext,
                                        enrico=enrico_as_understood_by_bob,
                                        alice_verifying_key=alice_pubkey_restored_from_ancient_scroll,
                                        label=label)

    # We show that indeed this is the passage originally encrypted by Enrico.
    assert plaintext == delivered_cleartexts[0]
    print("Retrieved: {}".format(delivered_cleartexts[0]))

BOB.disenchant()
