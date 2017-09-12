from kademlia.node import Node
from kademlia.protocol import KademliaProtocol


class NuCypherHashProtocol(KademliaProtocol):
    pass


class NuCypherSeedOnlyProtocol(NuCypherHashProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def rpc_store(self, sender, nodeid, key, value):
        source = Node(nodeid, sender[0], sender[1])
        self.welcomeIfNewNode(source)
        self.log.debug(
            "got a store request from %s, but THIS VALUE WILL NOT BE STORED as this is a seed-only node." % str(
                sender))
        return True
