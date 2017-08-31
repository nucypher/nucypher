from kademlia.protocol import KademliaProtocol
import asyncio


class NuCypherHashProtocol(KademliaProtocol):
    pass


class NuCypherSeedOnlyProtocol(NuCypherHashProtocol):

    @asyncio.coroutine
    def _acceptRequest(self, msgID, data, address):
        pass