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
import sys
from pathlib import Path

from nucypher.characters.lawful import Alice, Bob, Ursula
from nucypher.characters.lawful import Enrico as Enrico
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import SigningPower, DecryptingPower
from nucypher.utilities.logging import GlobalLoggerSettings


######################
# Boring setup stuff #
######################

BOOK_PATH = Path(os.getenv('FINNEGANS_WAKE_PATH') or 'finnegans-wake-excerpt.txt')

# Twisted Logger
GlobalLoggerSettings.set_log_level(log_level_name='debug')
GlobalLoggerSettings.start_console_logging()

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
ursula = Ursula.from_seed_and_stake_info(seed_uri=SEEDNODE_URI, federated_only=True)

# Here are our Policy details.
policy_end_datetime = maya.now() + datetime.timedelta(days=1)
m, n = 2, 3
label = b"secret/files/and/stuff"


#####################
# Bob the BUIDLer  ##
#####################

# First there was Bob.
bob = Bob(federated_only=True, domain=TEMPORARY_DOMAIN, known_nodes=[ursula])

# Bob gives his public keys to alice.
verifying_key = bob.public_keys(SigningPower)
encrypting_key = bob.public_keys(DecryptingPower)

######################################
# Alice, the Authority of the Policy #
######################################

alice = Alice(federated_only=True, domain=TEMPORARY_DOMAIN, known_nodes=[ursula])


# Start node discovery and wait until 8 nodes are known in case
# the fleet isn't fully spun up yet, as sometimes happens on CI.
alice.start_learning_loop(now=True)
alice.block_until_number_of_known_nodes_is(8, timeout=30, learn_on_this_thread=True)

# Alice can get the public key even before creating the policy.
# From this moment on, any Data Source that knows the public key
# can encrypt data originally intended for Alice, but that can be shared with
# any Bob that Alice grants access.
policy_public_key = alice.get_policy_encrypting_key_from_label(label)

# Alice grant access to Bob. She already knows Bob's public keys from a side-channel.
remote_bob = Bob.from_public_keys(encrypting_key=encrypting_key, verifying_key=verifying_key)
policy = alice.grant(remote_bob, label, m=m, n=n, expiration=policy_end_datetime)

assert policy.public_key == policy_public_key
policy.treasure_map_publisher.block_until_complete()

# Alice puts her public key somewhere for Bob to find later...
alice_verifying_key = alice.stamp.as_umbral_pubkey()

# ...and then disappears from the internet.
#
# Note that local characters (alice and bob), as opposed to objects representing
# remote characters constructed from public data (remote_alice and remote_bob)
# run a learning loop in a background thread and need to be stopped explicitly.
alice.disenchant()
del alice

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

bob.join_policy(label, alice_verifying_key)

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
    data_source_public_key = enrico.stamp.as_umbral_pubkey()
    del enrico

    ###############
    # Back to Bob #
    ###############

    # Now Bob can retrieve the original message.
    delivered_cleartexts = bob.retrieve(single_passage_ciphertext,
                                        policy_encrypting_key=policy_public_key,
                                        alice_verifying_key=alice_verifying_key,
                                        label=label)

    # We show that indeed this is the passage originally encrypted by Enrico.
    assert plaintext == delivered_cleartexts[0]
    print("Retrieved: {}".format(delivered_cleartexts[0]))

bob.disenchant()
