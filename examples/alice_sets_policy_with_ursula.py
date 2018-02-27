# This is an example of Alice setting a Policy on the NuCypher network.
# In this example, Alice uses n=1, which is almost always a bad idea.  Don't do it.

# WIP w/ hendrix@8227c4abcb37ee6d27528a13ec22d55ee106107f

import datetime

import requests

from nkms.characters import Alice, Bob, Ursula
from nkms.crypto.kits import MessageKit
from nkms.crypto.powers import SigningPower, EncryptingPower
from nkms.network.node import NetworkyStuff
from umbral import pre

ALICE = Alice()
BOB = Bob()
URSULA = Ursula.from_rest_url(address="http://localhost", port="3500")


class SandboxNetworkyStuff(NetworkyStuff):
    def find_ursula(self, contract=None):
        ursula = Ursula.as_discovered_on_network(dht_port=None, dht_interface=None,
                                                 rest_address="localhost", rest_port=3500,
                                                 powers_and_keys={
                                                    SigningPower: URSULA.stamp.as_umbral_pubkey(),
                                                    EncryptingPower: URSULA.public_key(EncryptingPower)
                                                 }
                                                 )
        response = requests.post("http://localhost:3500/consider_contract", bytes(contract))
        response.was_accepted = True
        return ursula, response

    def enact_policy(self, ursula, hrac, payload):
        response = requests.post('http://{}:{}/kFrag/{}'.format(ursula.rest_address, ursula.rest_port, hrac.hex()),
                                 payload)
        # TODO: Something useful here and it's probably ready to go down into NetworkyStuff.
        return response.status_code == 200


networky_stuff = SandboxNetworkyStuff()

policy_end_datetime = datetime.datetime.now() + datetime.timedelta(days=5)
n = 1
uri = b"secret/files/and/stuff"
policy = ALICE.grant(BOB, uri, networky_stuff, m=1, n=n,
                     expiration=policy_end_datetime)
