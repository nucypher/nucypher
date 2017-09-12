import asyncio

from kademlia.network import Server
from nkms.network.server import NuCypherSeedOnlyDHTServer, NuCypherDHTServer


# Kademlia emits a bunch of useful logging info; uncomment below to see it.
# import logging
# logging.basicConfig(level=logging.DEBUG)


def test_seed_only_node():
    """
    Shows that when we set up two nodes, a "full" node and a "seed-only" node,
    that the "seed-only" node can set key-value pairs that the "full" node will store,
    but not vice-versa.
    """
    loop = asyncio.get_event_loop()

    # First, let's set up two servers:
    # A full node...
    full_server = NuCypherDHTServer()
    full_server.listen(8468)
    loop.run_until_complete(full_server.bootstrap([("127.0.0.1", 8468)]))

    # ...and a seed-only node.
    seed_only_server = NuCypherSeedOnlyDHTServer()
    seed_only_server.listen(8471)
    loop.run_until_complete(seed_only_server.bootstrap([("127.0.0.1", 8468)]))

    # The seed-only node is able to set a key and retrieve it again.
    key_to_store = "llamas"
    value_to_store = "tons_of_things_keyed_llamas"
    setter = seed_only_server.set(key_to_store, value_to_store)
    loop.run_until_complete(setter)

    # Now, the item is stored on the full server.
    full_server_stored_items = list(full_server.storage.items())
    assert len(full_server_stored_items) == 1
    assert full_server_stored_items[0][1] == value_to_store

    # ...but nothing is stored on the seed-only server.
    seed_only_server_stored_items = list(seed_only_server.storage.items())
    assert len(seed_only_server_stored_items) == 0

    # If the full server tries to store something...
    key_that_is_not_stored = b"european_swallow"
    value_that_is_not_stored = b"grip_it_by_the_husk"
    setter = full_server.set(key_that_is_not_stored, value_that_is_not_stored)
    loop.run_until_complete(setter)

    # ...it is *not* stored on the seed-only server.
    assert len(list(seed_only_server.storage.items())) == 0

    # annnnd stop.
    seed_only_server.stop()
    full_server.stop()
    loop.close()
