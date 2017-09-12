from kademlia.node import Node
from kademlia.protocol import KademliaProtocol
from nkms.network.routing import NuCypherRoutingTable


class NuCypherHashProtocol(KademliaProtocol):

    def __init__(self, sourceNode, storage, ksize, *args, **kwargs):
        super().__init__(sourceNode, storage, ksize, *args, **kwargs):
        self.router = NuCypherRoutingTable(self, ksize, sourceNode)

    def rpc_ping(self, sender, nodeid, node_properties={}):
        source = Node(nodeid, sender[0], sender[1])
        self.welcomeIfNewNode(source, node_properties)
        return self.sourceNode.id

    def welcomeIfNewNode(self, node, node_properties):
        if not self.router.isNewNode(node):
            return

        self.log.info("never seen %s before, adding to router and setting nearby " % node)
        for key, value in self.storage.items():
            keynode = Node(digest(key))
            neighbors = self.router.findNeighbors(keynode)
            if len(neighbors) > 0:
                newNodeClose = node.distanceTo(keynode) < neighbors[-1].distanceTo(keynode)
                thisNodeClosest = self.sourceNode.distanceTo(keynode) < neighbors[0].distanceTo(keynode)
            if len(neighbors) == 0 or (newNodeClose and thisNodeClosest):
                asyncio.ensure_future(self.callStore(node, key, value))
        self.router.addContact(node, seed_only=node_properties.get("seed_only", False))


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
