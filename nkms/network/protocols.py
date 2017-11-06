import msgpack

from kademlia.node import Node
from kademlia.protocol import KademliaProtocol
from kademlia.utils import digest
from nkms.network.constants import NODE_HAS_NO_STORAGE
from nkms.network.node import NuCypherNode
from nkms.network.routing import NuCypherRoutingTable
from nkms.crypto import api as API, _alpha


class NuCypherHashProtocol(KademliaProtocol):
    def __init__(self, sourceNode, storage, ksize, *args, **kwargs):
        super().__init__(sourceNode, storage, ksize, *args, **kwargs)
        self.router = NuCypherRoutingTable(self, ksize, sourceNode)

    def check_node_for_storage(self, node):
        try:
            return node.can_store()
        except AttributeError:
            return True

    def rpc_ping(self, sender, nodeid, node_capabilities=[]):
        source = NuCypherNode(nodeid, sender[0], sender[1], capabilities_as_strings=node_capabilities)
        self.welcomeIfNewNode(source)
        return self.sourceNode.id

    async def callStore(self, nodeToAsk, key, value):
        # nodeToAsk = NuCypherNode
        if self.check_node_for_storage(nodeToAsk):
            address = (nodeToAsk.ip, nodeToAsk.port)
            # TODO: encrypt `value` with public key of nodeToAsk
            store_future = self.store(address, self.sourceNode.id, key, value)
            result = await store_future
            success, data = self.handleCallResponse(result, nodeToAsk)
            return success, data
        else:
            return NODE_HAS_NO_STORAGE, False

    def rpc_store(self, sender, nodeid, key, value):
        source = NuCypherNode(nodeid, sender[0], sender[1])
        self.welcomeIfNewNode(source)
        self.log.debug("got a store request from %s" % str(sender))
        if value.startswith(b"uaddr"):
            signature, ursula_pubkey_sig, interface_info = msgpack.loads(value.lstrip(b"uaddr-"))
            proper_key = digest(ursula_pubkey_sig)
            verified = _alpha.verify(signature, interface_info, ursula_pubkey_sig)
            if not verified or not proper_key == key:
                # TODO: What exactly to do in this scenario?
                self.log.warning("Possible Vladimir detected - tried to set incorrect Ursula interface key.")
                return
        self.storage[key] = value
        return True






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
