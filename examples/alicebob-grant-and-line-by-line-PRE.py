# This is an example of Alice setting a Policy on the NuCypher network.
# In this example, Alice uses n=1, which is almost always a bad idea.  Don't do it.

# WIP w/ hendrix@8227c4abcb37ee6d27528a13ec22d55ee106107f

import datetime
import sys

from examples.sandbox_resources import SandboxNetworkyStuff
from nkms.characters import Alice, Bob, Ursula
from nkms.crypto.kits import MessageKit
from nkms.crypto.powers import SigningPower, EncryptingPower
from nkms.network.node import NetworkyStuff
from umbral import pre

ALICE = Alice()
BOB = Bob()
URSULA = Ursula.from_rest_url(address="https://localhost", port="3550")

networky_stuff = SandboxNetworkyStuff()

policy_end_datetime = datetime.datetime.now() + datetime.timedelta(days=5)
n = 1
uri = b"secret/files/and/stuff"

# Alice gets on the network and discovers Ursula, presumably from the blockchain.
ALICE.learn_about_nodes(address="https://localhost", port="3550")

# Alice grants to Bob.
policy = ALICE.grant(BOB, uri, networky_stuff, m=1, n=n,
                     expiration=policy_end_datetime)
policy.publish_treasure_map(networky_stuff, use_dht=False)
hrac, treasure_map = policy.hrac(), policy.treasure_map

# Bob learns about Ursula, gets the TreasureMap, and follows it.
BOB.learn_about_nodes(address="https://localhost", port="3550")
networky_stuff = NetworkyStuff()
BOB.get_treasure_map(policy, networky_stuff)
BOB.follow_treasure_map(hrac)

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

    ciphertext, capsule = pre.encrypt(ALICE.public_key(EncryptingPower), plaintext)

    message_kit = MessageKit(ciphertext=ciphertext, capsule=capsule,
                      alice_pubkey=ALICE.public_key(EncryptingPower))

    work_orders = BOB.generate_work_orders(hrac, capsule)
    print(plaintext)
    cfrags = BOB.get_reencrypted_c_frags(networky_stuff, work_orders[bytes(URSULA.stamp)])

    capsule.attach_cfrag(cfrags[0])
    delivered_cleartext = pre.decrypt(capsule, BOB._crypto_power._power_ups[EncryptingPower].keypair._privkey, ciphertext, ALICE.public_key(EncryptingPower))
    assert plaintext == delivered_cleartext
    print("Retrieved: {}".format(delivered_cleartext))
