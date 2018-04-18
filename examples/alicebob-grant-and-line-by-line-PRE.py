# This is an example of Alice setting a Policy on the NuCypher network.
# In this example, Alice uses n=1, which is almost always a bad idea.  Don't do it.

# WIP w/ hendrix@8227c4abcb37ee6d27528a13ec22d55ee106107f

import datetime
import sys

from examples.sandbox_resources import SandboxNetworkyStuff
from nkms.characters import Alice, Bob, Ursula
from nkms.crypto.api import keccak_digest
from nkms.data_sources import DataSource
from nkms.network.node import NetworkyStuff
import maya

# Some basic setup.

ALICE = Alice()
BOB = Bob()
URSULA = Ursula.from_rest_url(NetworkyStuff(), address="localhost", port=3601)
network_middleware = SandboxNetworkyStuff([URSULA])

# Here are our Policy details.
policy_end_datetime = maya.now() + datetime.timedelta(days=5)
m = 1
n = 1
label = b"secret/files/and/stuff"


# Alice gets on the network and, knowing about at least one Ursula,
# Is able to discover all Ursulas.
ALICE.network_bootstrap([("localhost", 3601)])

# Alice grants to Bob.
policy = ALICE.grant(BOB, label, network_middleware, m=m, n=n,
                     expiration=policy_end_datetime)
hrac, treasure_map = policy.hrac(), policy.treasure_map

# Bob can re-assemble the hrac himself with knowledge he already has.
hrac = keccak_digest(bytes(ALICE.stamp) + bytes(BOB.stamp) + label)
BOB.join_policy(ALICE, hrac, node_list=[("localhost", 3601)])

# Now, Alice and Bob are ready for some throughput.
finnegans_wake = open(sys.argv[1], 'rb')

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

    data_source = DataSource(policy_pubkey_enc=policy.public_key())
    message_kit, _signature = data_source.encapsulate_single_message(plaintext)

    delivered_cleartext = BOB.retrieve(hrac=hrac, message_kit=message_kit, data_source=data_source)

    assert plaintext == delivered_cleartext
    print("Retrieved: {}".format(delivered_cleartext))
