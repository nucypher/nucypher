import asyncio
import logging

from kademlia.network import Server
from nkms.network.protocols import NuCypherSeedOnlyProtocol

key = "llamas"
value = "tons_of_things_keyed_llamas"

logging.basicConfig(level=logging.DEBUG)
loop = asyncio.get_event_loop()
loop.set_debug(True)

server = Server(protocol_class=NuCypherSeedOnlyProtocol)
server.listen(8469)
loop.run_until_complete(server.bootstrap([("127.0.0.1", 8468)]))
set = server.set(key, value)
loop.run_until_complete(set)
server.stop()
loop.close()
