import asyncio

import kademlia
from kademlia.node import Node
from kademlia.protocol import KademliaProtocol
from kademlia.utils import digest

from bytestring_splitter import VariableLengthBytestring
from constant_sorrow import default_constant_splitter, constants
from nucypher.network.routing import NucypherRoutingTable


class SuspiciousActivity(RuntimeError):
    """raised when an action appears to amount to malicious conduct."""


class NucypherHashProtocol(KademliaProtocol):
    def __init__(self, sourceNode, storage, ksize, *args, **kwargs):
        super().__init__(sourceNode, storage, ksize, *args, **kwargs)

        self.router = NucypherRoutingTable(self, ksize, sourceNode)
        self.illegal_keys_seen = []  # TODO: 340

    @property
    def ursulas(self):
        raise NotImplementedError("This approach is deprecated.  Find a way to use _known_nodes instead.  See #227.")

    @property
    def storage(self):
        raise NotImplementedError("This approach is deprecated.  Find a way to use _known_nodes instead.  See #227.")

    @storage.setter
    def storage(self, not_gonna_use_this):
        # TODO: 331
        pass

    def check_node_for_storage(self, node):
        try:
            return node.can_store()
        except AttributeError:
            return True

    async def callStore(self, nodeToAsk, key, value):
        # nodeToAsk = NucypherNode
        if self.check_node_for_storage(nodeToAsk):
            address = (nodeToAsk.ip, nodeToAsk.port)
            # TODO: encrypt `value` with public key of nodeToAsk
            store_future = self.store(address, self.sourceNode.id, key, value)
            result = await store_future
            success, data = self.handleCallResponse(result, nodeToAsk)
            return success, data
        else:
            return constants.NODE_HAS_NO_STORAGE, False

    def rpc_store(self, sender, nodeid, key, value):
        source = kademlia.node.Node(nodeid, sender[0], sender[1])
        self.welcomeIfNewNode(source)
        self.log.debug("got a store request from %s" % str(sender))

        header, payload = default_constant_splitter(value, return_remainder=True)

        if header == constants.BYTESTRING_IS_URSULA_IFACE_INFO:
            from nucypher.characters import Ursula
            stranger_ursula = Ursula.from_bytes(payload,
                                                federated_only=self.sourceNode.federated_only)  # TODO: Is federated_only the right thing here?

            if stranger_ursula.interface_is_valid() and key == digest(stranger_ursula.canonical_public_address):
                self.sourceNode._node_storage[key] = stranger_ursula  # TODO: 340
                return True
            else:
                self.log.warning("Got request to store invalid node: {} / {}".format(key, value))
                self.illegal_keys_seen.append(key)
                return False
        elif header == constants.BYTESTRING_IS_TREASURE_MAP:
            from nucypher.policy.models import TreasureMap
            try:
                treasure_map = TreasureMap.from_bytes(payload)
                self.log.info("Storing TreasureMap: {} / {}".format(key, value))
                self.sourceNode._treasure_maps[treasure_map.public_id()] = value
                return True
            except TreasureMap.InvalidSignature:
                self.log.warning("Got request to store invalid TreasureMap: {} / {}".format(key, value))
                self.illegal_keys_seen.append(key)
                return False
        else:
            self.log.info(
                "Got request to store bad k/v: {} / {}".format(key, value))
            return False

    def welcomeIfNewNode(self, node):
        """
        Given a new node, send it all the keys/values it should be storing,
        then add it to the routing table.

        @param node: A new node that just joined (or that we just found out
        about).

        Process:
        For each key in storage, get k closest nodes.  If newnode is closer
        than the furtherst in that list, and the node for this server
        is closer than the closest in that list, then store the key/value
        on the new node (per section 2.5 of the paper)
        """
        if not self.router.isNewNode(node):
            return

        self.log.info("never seen %s before, adding to router and setting nearby " % node)
        # TODO: 331 and 340 next two lines
        ursulas = [(id, bytes(node)) for id, node in self.sourceNode._node_storage.items()]
        for key, value in tuple(self.sourceNode._treasure_maps.items()) + tuple(ursulas):
            keynode = Node(digest(key))
            neighbors = self.router.findNeighbors(keynode)
            if len(neighbors) > 0:
                newNodeClose = node.distanceTo(keynode) < neighbors[-1].distanceTo(keynode)
                thisNodeClosest = self.sourceNode.distanceTo(keynode) < neighbors[0].distanceTo(keynode)
            if len(neighbors) == 0 or (newNodeClose and thisNodeClosest):
                asyncio.ensure_future(self.callStore(node, key, value))
        self.router.addContact(node)


class NucypherSeedOnlyProtocol(NucypherHashProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def rpc_store(self, sender, nodeid, key, value):
        source = Node(nodeid, sender[0], sender[1])
        self.welcomeIfNewNode(source)
        self.log.debug(
            "got a store request from %s, but THIS VALUE WILL NOT BE STORED as this is a seed-only node." % str(
                sender))
        return True


class InterfaceInfo:
    expected_bytes_length = lambda: VariableLengthBytestring

    def __init__(self, host, port):
        self.host = host
        self.port = port

    @classmethod
    def from_bytes(cls, url_string):
        host_bytes, port_bytes = url_string.split(b":")
        port = int.from_bytes(port_bytes, "big")
        host = host_bytes.decode("utf-8")
        return cls(host=host, port=port)

    def __bytes__(self):
        return bytes(self.host, encoding="utf-8") + b":" + self.port.to_bytes(4, "big")

    def __add__(self, other):
        return bytes(self) + bytes(other)

    def __radd__(self, other):
        return bytes(other) + bytes(self)
