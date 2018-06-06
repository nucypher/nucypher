import requests

from nucypher.characters import Ursula
from nucypher.network.middleware import NetworkMiddleware


class SandboxNetworkMiddleware(NetworkMiddleware):

    def __init__(self, ursulas):
        self.ursulas = ursulas

    def consider_arrangement(self, contract=None):
        ursula = Ursula.from_rest_url(
            self,
            ip_address="localhost",
            port=3601,
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
