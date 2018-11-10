# This is an example of Alice setting a Policy on the NuCypher network.
# In this example, Alice uses n=3.

# WIP w/ hendrix@3.1.0

import datetime
import os
import shutil
import sys

import maya
from twisted.logger import ILogObserver
from twisted.logger import globalLogPublisher
from umbral.keys import UmbralPublicKey
######################
# Boring setup stuff #
######################
from zope.interface import provider

from nucypher.characters.lawful import Alice, Bob
from nucypher.config.constants import SeednodeMetadata
from nucypher.data_sources import DataSource
# This is already running in another process.
from nucypher.network.middleware import RestMiddleware


@provider(ILogObserver)
def simpleObserver(event):
    print(event)

globalLogPublisher.addObserver(simpleObserver)

# Temporary storage area for demo
SHARED_CRUFTSPACE = "{}/examples-runtime-cruft".format(os.path.dirname(os.path.abspath(__file__)))
CRUFTSPACE = "{}/finnegans-wake-demo".format(SHARED_CRUFTSPACE)
CERTIFICATE_DIR = "{}/certs".format(CRUFTSPACE)
shutil.rmtree(CRUFTSPACE, ignore_errors=True)
os.mkdir(CRUFTSPACE)
os.mkdir(CERTIFICATE_DIR)

ursula_seed_node = SeednodeMetadata(checksum_address="0x154d9c2062a2Fd6f1a4eE827308634547ce84810",
                                    rest_host="18.184.168.218",
                                    rest_port=9151)

#########
# Alice #
#########


ALICE = Alice(network_middleware=RestMiddleware(),
              seed_nodes=[ursula_seed_node],
              learn_on_same_thread=True,
              federated_only=True,
              known_certificates_dir=CERTIFICATE_DIR,
              )

# Here are our Policy details.
policy_end_datetime = maya.now() + datetime.timedelta(days=5)
m = 2
n = 3
label = b"secret/files/and/stuff"

# Alice grants to Bob.
BOB = Bob(
    seed_nodes=[ursula_seed_node],
    network_middleware=RestMiddleware(),
    federated_only=True,
    start_learning_now=True,
    learn_on_same_thread=True,
    known_certificates_dir=CERTIFICATE_DIR)

ALICE.start_learning_loop(now=True)

policy = ALICE.grant(BOB, label, m=m, n=n,
                     expiration=policy_end_datetime)

# Alice puts her public key somewhere for Bob to find later...
alices_pubkey_bytes_saved_for_posterity = bytes(ALICE.stamp)

# ...and then disappears from the internet.
del ALICE
# (this is optional of course - she may wish to remain in order to create
# new policies in the future.  The point is - she is no longer obligated.

#####################
# some time passes. #
# ...               #
#                   #
# ...               #
# And now for Bob.  #
#####################

# Bob wants to join the policy so that he can receive any future
# data shared on it.
# He needs a few pieces of knowledge to do that.
BOB.join_policy(label,  # The label - he needs to know what data he's after.
                alices_pubkey_bytes_saved_for_posterity,  # To verify the signature, he'll need Alice's public key.
                )

# Now that Bob has joined the Policy, let's show how DataSources
# can share data with the members of this Policy and then how Bob retrieves it.
finnegans_wake = open(sys.argv[1], 'rb')

# We'll also keep track of some metadata to gauge performance.
# You can safely ignore from here until...
################################################################################

start_time = datetime.datetime.now()

for counter, plaintext in enumerate(finnegans_wake):
    if counter % 20 == 0:
        now_time = datetime.datetime.now()
        time_delta = now_time - start_time
        seconds = time_delta.total_seconds()
        print("********************************")
        print("Performed {} PREs".format(counter))
        print("Elapsed: {}".format(time_delta.total_seconds()))
        print("PREs per second: {}".format(counter / seconds))
        print("********************************")

    ################################################################################
    # ...here.  OK, pay attention again.
    # Now it's time for...

    #####################
    # Using DataSources #
    #####################

    # Now Alice has set a Policy and Bob has joined it.
    # You're ready to make some DataSources and encrypt for Bob.

    # It may also be helpful to imagine that you have multiple Bobs,
    # multiple Labels, or both.

    # First we make a DataSource for this policy.
    data_source = DataSource(policy_pubkey_enc=policy.public_key)

    # Here's how we generate a MessageKit for the Policy.  We also get a signature
    # here, which can be passed via a side-channel (or posted somewhere public as
    # testimony) and verified if desired.
    #
    # In this case, the plaintext is a
    # single passage from James Joyce's Finnegan's Wake.
    # The matter of whether encryption makes the passage more or less readable
    # is left to the reader to determine.
    message_kit, _signature = data_source.encapsulate_single_message(plaintext)

    # The DataSource will want to be able to be verified by Bob, so it leaves
    # its Public Key somewhere.
    data_source_public_key = bytes(data_source.stamp)

    # It can save the MessageKit somewhere (IPFS, etc) and then it too can
    # choose to disappear (although it may also opt to continue transmitting
    # as many messages as may be appropriate).
    del data_source

    ###############
    # Back to Bob #
    ###############

    # Bob needs to reconstruct the DataSource.
    datasource_as_understood_by_bob = DataSource.from_public_keys(
        policy_public_key=policy.public_key,
        datasource_public_key=data_source_public_key,
        label=label
    )

    # Now Bob can retrieve the original message.  He just needs the MessageKit
    # and the DataSource which produced it.
    alice_pubkey_restored_from_ancient_scroll = UmbralPublicKey.from_bytes(alices_pubkey_bytes_saved_for_posterity)
    delivered_cleartexts = BOB.retrieve(message_kit=message_kit,
                                        data_source=datasource_as_understood_by_bob,
                                        alice_verifying_key=alice_pubkey_restored_from_ancient_scroll)

    # We show that indeed this is the passage originally encrypted by the DataSource.
    assert plaintext == delivered_cleartexts[0]
    print("Retrieved: {}".format(delivered_cleartexts[0]))
