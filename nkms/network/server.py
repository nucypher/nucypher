import asyncio
import random

import msgpack

from kademlia.crawling import NodeSpiderCrawl
from kademlia.network import Server
from kademlia.utils import digest
from nkms.network.capabilities import SeedOnly, ServerCapability
from nkms.network.node import NuCypherNode
from nkms.network.protocols import NuCypherSeedOnlyProtocol, NuCypherHashProtocol
from nkms.network.storage import SeedOnlyStorage


class NuCypherDHTServer(Server):
    protocol_class = NuCypherHashProtocol
    capabilities = ()
    digests_set = 0

    def __init__(self, ksize=20, alpha=3, id=None, storage=None, *args, **kwargs):
        super().__init__(ksize=20, alpha=3, id=None, storage=None, *args, **kwargs)
        self.node = NuCypherNode(id or digest(random.getrandbits(255)))  # TODO: Assume that this can be attacked to get closer to desired kFrags.

    def serialize_capabilities(self):
        return [ServerCapability.stringify(capability) for capability in self.capabilities]

    async def bootstrap_node(self, addr):
        """
        Announce node including capabilities
        """
        result = await self.protocol.ping(addr, self.node.id, self.serialize_capabilities())
        return NuCypherNode(result[1], addr[0], addr[1]) if result[0] else None

    async def set_digest(self, dkey, value):
        """
        Set the given SHA1 digest key (bytes) to the given value in the network.

        Returns True if a digest was in fact set.
        """
        node = self.node_class(dkey)

        nearest = self.protocol.router.findNeighbors(node)
        if len(nearest) == 0:
            self.log.warning("There are no known neighbors to set key %s" % dkey.hex())
            return False

        spider = NodeSpiderCrawl(self.protocol, node, nearest, self.ksize, self.alpha)
        nodes = await spider.find()
        self.log.info("setting '%s' on %s" % (dkey.hex(), list(map(str, nodes))))

        # if this node is close too, then store here as well
        if self.node.distanceTo(node) < max([n.distanceTo(node) for n in nodes]):
            self.storage[dkey] = value
        ds = []
        for n in nodes:
            if self.node.id == n.id:
                # TOOD: Consider whether to store stuff locally.  We don't really know yet.  Probably at least some things.
                ds.append(False)
            else:
                disposition, value_was_set = await self.protocol.callStore(n, dkey, value)
                if value_was_set:
                    self.digests_set += 1
                ds.append(value_was_set)
        # return true only if at least one store call succeeded
        return any(ds)

    def get_now(self, key):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.get(key))


class NuCypherSeedOnlyDHTServer(NuCypherDHTServer):
    protocol_class = NuCypherSeedOnlyProtocol
    capabilities = (SeedOnly(),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.storage = SeedOnlyStorage()
