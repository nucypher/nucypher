import os

import datetime
import maya
import shutil
from twisted.logger import globalLogPublisher
from umbral.keys import UmbralPublicKey

from nucypher.characters.lawful import Alice, Bob, Ursula
from nucypher.characters.lawful import Enrico as Enrico
from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.logging import SimpleObserver

######################
# Boring setup stuff #
######################

# Execute the download script (download_finnegans_wake.sh) to retrieve the book
BOOK_PATH = os.path.join('.', 'finnegans-wake.txt')

# Twisted Logger
globalLogPublisher.addObserver(SimpleObserver())


#######################################
# Finnegan's Wake on NuCypher Testnet #
# (will fail with bad connection) #####
#######################################

SEEDNODE_URI = "https://localhost:11501"

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
              known_nodes=[ursula],
              learn_on_same_thread=True,
              federated_only=True)

# Alice can get the public key even before creating the policy.
# From this moment on, any Data Source that knows the public key
# can encrypt data originally intended for Alice, but that can be shared with
# any Bob that Alice grants access.
policy_pubkey = ALICE.get_policy_pubkey_from_label(label)

BOB = Bob(known_nodes=[ursula],
          network_middleware=RestMiddleware(),
          federated_only=True,
          start_learning_now=True,
          learn_on_same_thread=True)

ALICE.start_learning_loop(now=True)

policy = ALICE.grant(BOB,
                     label,
                     m=m, n=n,
                     expiration=policy_end_datetime)

assert policy.public_key == policy_pubkey

# Alice puts her public key somewhere for Bob to find later...
alices_pubkey_bytes_saved_for_posterity = bytes(ALICE.stamp)

# ...and then disappears from the internet.
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
with open(BOOK_PATH, 'rb') as file:
    finnegans_wake = file.readlines()

print()
print("**************James Joyce's Finnegan's Wake**************")
print()
print("---------------------------------------------------------")

for counter, plaintext in enumerate(finnegans_wake):

    #########################
    # Enrico, the Encryptor #
    #########################
    enrico = Enrico(policy_pubkey_enc=policy_pubkey)

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
        policy_public_key=policy_pubkey,
        enrico_public_key=data_source_public_key,
        label=label
    )

    # Now Bob can retrieve the original message.
    alice_pubkey_restored_from_ancient_scroll = UmbralPublicKey.from_bytes(alices_pubkey_bytes_saved_for_posterity)
    delivered_cleartexts = BOB.retrieve(message_kit=single_passage_ciphertext,
                                        data_source=enrico_as_understood_by_bob,
                                        alice_verifying_key=alice_pubkey_restored_from_ancient_scroll)

    # We show that indeed this is the passage originally encrypted by Enrico.
    assert plaintext == delivered_cleartexts[0]
    print("Retrieved: {}".format(delivered_cleartexts[0]))
