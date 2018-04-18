import requests
from nkms.characters import Ursula
from nkms.network.node import NetworkyStuff
from nkms.crypto.powers import SigningPower, EncryptingPower


class SandboxNetworkyStuff(NetworkyStuff):

    def __init__(self, ursulas):
        self.ursulas = ursulas

    def find_ursula(self, contract=None):
        ursula = Ursula.as_discovered_on_network(dht_port=None,
                                                 ip_address="localhost",
                                                 rest_port=3601,
                                                 powers_and_keys={
                                                    SigningPower: self.ursulas[0].stamp.as_umbral_pubkey(),
                                                    EncryptingPower: self.ursulas[0].public_key(EncryptingPower)
                                                 }
                                                 )
        response = requests.post("https://localhost:3601/consider_arrangement", bytes(contract), verify=False)
        if response.status_code == 200:
            response.was_accepted = True
        else:
            raise RuntimeError("Something went terribly wrong.  What'd you do?!")
        return ursula, response

    def enact_policy(self, ursula, hrac, payload):
        endpoint = 'https://{}:{}/kFrag/{}'.format(ursula.ip_address, ursula.rest_port, hrac.hex())
        response = requests.post(endpoint, payload, verify=False)
        # TODO: Something useful here and it's probably ready to go down into NetworkyStuff.
        return response.status_code == 200
