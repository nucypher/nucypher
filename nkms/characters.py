from kademlia.network import Server
from nkms.crypto.keyring import KeyRing
from nkms.network.server import NuCypherDHTServer, NuCypherSeedOnlyDHTServer


class Character(object):
    """
    A base-class for any character in our cryptography protocol narrative.
    """
    _server = None
    _server_class = Server

    def __init__(self, attach_server=True):
        if attach_server:
            self.attach_server()

    def attach_server(self, ksize=20, alpha=3, id=None, storage=None,
                      *args, **kwargs) -> None:
        self._server = self._server_class(ksize, alpha, id, storage, *args, **kwargs)

    @property
    def server(self) -> Server:
        if self._server:
            return self._server
        else:
            raise RuntimeError("Server hasn't been attached.")


class Ursula(Character):
    _server_class = NuCypherDHTServer


class Alice(Character):
    _server_class = NuCypherSeedOnlyDHTServer

    def __init__(self):
        # TODO: Handle loading keypairs from config
        self.keyring = KeyRing()

    def find_best_ursula(self):
        # TODO: Right now this just finds the nearest node and returns its ip and port.  Make it do something useful.
        return self.server.bootstrappableNeighbors()[0]
