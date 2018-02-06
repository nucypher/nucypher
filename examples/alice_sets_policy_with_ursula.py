# WIP w/ hendrix@8227c4abcb37ee6d27528a13ec22d55ee106107f

import datetime

import requests

from nkms.characters import Alice, Bob, Ursula, congregate
from nkms.network.node import NetworkyStuff
from nkms.policy.models import AgreementResponse

ALICE = Alice()
BOB = Bob()
URSULA = Ursula.from_rest_url("http://localhost:3500/public_keys")

ALICE.learn_about_actor(URSULA)


class SandboxNetworkyStuff(NetworkyStuff):
    def find_ursula(self, agreement=None):
        ursula = Ursula.as_discovered_on_network(None, None, pubkey_sig_bytes=bytes(URSULA.seal),
                                                 rest_address="localhost", rest_port=3500)
        response = ursula.consider_agreement(agreement)  # TODO: This needs to be a REST call.
        response.was_accepted = True
        return ursula, response

    def enact_policy(self, ursula, hrac, payload):
        response = requests.post('http://{}:{}/kFrag/{}'.format(ursula.rest_address, ursula.rest_port, hrac.hex()), payload)
        return True, ursula.interface_dht_key()  # TODO: Something useful here and it's probably ready to go down into NetworkyStuff.

networky_stuff = SandboxNetworkyStuff()

policy_end_datetime = datetime.datetime.now() + datetime.timedelta(days=5)
n = 1
uri = b"secret/files/and/stuff"
policy = ALICE.grant(BOB, uri, networky_stuff, m=1, n=n,
                     expiration=policy_end_datetime)

