from kademlia.network import Server
from nkms.network.protocols import NuCypherSeedOnlyProtocol
from nkms.network.storage import SeedOnlyStorage


class NuCypherSeedOnlyDHTServer(Server):

    protocol_class = NuCypherSeedOnlyProtocol

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.storage = SeedOnlyStorage()