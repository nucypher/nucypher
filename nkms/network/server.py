from kademlia.network import Server
from nkms.network.protocols import NuCypherSeedOnlyProtocol, NuCypherHashProtocol
from nkms.network.storage import SeedOnlyStorage


class NuCypherDHTServer(Server):

    protocol_class = NuCypherHashProtocol


class NuCypherSeedOnlyDHTServer(NuCypherDHTServer):

    protocol_class = NuCypherSeedOnlyProtocol

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.storage = SeedOnlyStorage()

    async def bootstrap_node(self, addr):
        """
        Announce ourselves as seed-only.
        """
        result = await self.protocol.ping(addr, self.node.id, {"seed_only":True})
        return Node(result[1], addr[0], addr[1]) if result[0] else None