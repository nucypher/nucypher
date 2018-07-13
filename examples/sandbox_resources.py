import requests

from nucypher.characters import Ursula
from nucypher.network.middleware import RestMiddleware


class SandboxRestMiddleware(RestMiddleware):

    def __init__(self, ursulas):
        self.ursulas = ursulas

    def consider_arrangement(self, arrangement):
        ursula = Ursula.from_rest_url(
            self,
            host=arrangement.ursula.rest_interface.host,
            port=arrangement.ursula.rest_interface.port,
            federated_only=True,
        )  # TODO: Make this the Ursula to whom we connect.
        response = requests.post("https://localhost:3601/consider_arrangement", bytes(arrangement), verify=False)
        if response.status_code == 200:
            response.was_accepted = True
        else:
            raise RuntimeError("Something went terribly wrong.  What'd you do?!")
        return response

    def enact_policy(self, ursula, arrangement_id, payload):
        endpoint = 'https://{}:{}/kFrag/{}'.format(ursula.rest_interface.host,
                                                   ursula.rest_interface.port,
                                                   arrangement_id.hex())
        response = requests.post(endpoint, payload, verify=False)
        return response.status_code == 200
