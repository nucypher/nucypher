from kademlia.network import Server
from nkms.network.protocols import NuCypherSeedOnlyProtocol


class NuCypherSeedOnlyDHTServer(Server):

    protocol_class = NuCypherSeedOnlyProtocol