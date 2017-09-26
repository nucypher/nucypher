import asyncio
# Kademlia emits a bunch of useful logging info; uncomment below to see it.
import logging

from nkms.network.server import NuCypherSeedOnlyDHTServer, NuCypherDHTServer

logging.basicConfig(level=logging.DEBUG)
import pytest


@pytest.mark.skip(reason="Strange.  This appeared to be fixed in ab6cbaead69c9e0073de13c36078b09997d2a6ff, but still sometimes fails.")
def test_seed_only_node_does_not_store_anything():
    """
    Shows that when we set up two nodes, a "full" node and a "seed-only" node,
    that the "seed-only" node can set key-value pairs that the "full" node will store,
    but not vice-versa.
    """

    # First, let's set up two servers:
    # A full node...
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)

    full_server = NuCypherDHTServer()
    full_server.listen(8468)
    event_loop.run_until_complete(full_server.bootstrap([("127.0.0.1", 8468)]))

    # ...and a seed-only node.
    seed_only_server = NuCypherSeedOnlyDHTServer()
    seed_only_server.listen(8471)
    event_loop.run_until_complete(seed_only_server.bootstrap([("127.0.0.1", 8468)]))

    # The seed-only node is able to set a key...
    key_to_store = "llamas"
    value_to_store = "tons_of_things_keyed_llamas"
    setter = seed_only_server.set(key_to_store, value_to_store)
    event_loop.run_until_complete(setter)

    # ...and retrieve it again.
    getter = seed_only_server.get(key_to_store)
    value = event_loop.run_until_complete(getter)
    assert value == value_to_store

    # The item is stored on the full server.
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
    event_loop.run_until_complete(setter)

    # ...it is *not* stored on the seed-only server.
    assert len(list(seed_only_server.storage.items())) == 0

    # annnnd stop.
    seed_only_server.stop()
    full_server.stop()
    event_loop.close()


@pytest.mark.skip(reason="Strange.  This appeared to be fixed in ab6cbaead69c9e0073de13c36078b09997d2a6ff, but still sometimes fails.")
def test_full_node_does_not_try_to_store_on_seed_only_node():
    """
    A full node is able to determine that a seed-only node does not have the capability
    to store.  It doesn't waste its time trying.
    """
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)

    full_server = NuCypherDHTServer()
    full_server.listen(8468)
    event_loop.run_until_complete(full_server.bootstrap([("127.0.0.1", 8468)]))

    seed_only_server = NuCypherSeedOnlyDHTServer()
    seed_only_server.listen(8471)
    event_loop.run_until_complete(seed_only_server.bootstrap([("127.0.0.1", 8468)]))

    key_that_is_not_stored = b"european_swallow"
    value_that_is_not_stored = b"grip_it_by_the_husk"
    setter = full_server.set(key_that_is_not_stored, value_that_is_not_stored)

    # Here's the interesting part.
    result = event_loop.run_until_complete(setter)
    assert not result
    assert full_server.digests_set == 0

    # annnnd stop.
    seed_only_server.stop()
    full_server.stop()
    event_loop.close()


def test_seed_only_node_knows_it_can_store_on_full_node():
    """
    On the other hand, a seed-only node knows that it can store on a full node.
    """

    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)

    full_server = NuCypherDHTServer()
    full_server.listen(8468)
    event_loop.run_until_complete(full_server.bootstrap([("127.0.0.1", 8468)]))

    seed_only_server = NuCypherSeedOnlyDHTServer()
    seed_only_server.listen(8471)
    event_loop.run_until_complete(seed_only_server.bootstrap([("127.0.0.1", 8468)]))

    # The seed-only will try to store a value.
    key_to_store = "llamas"
    value_to_store = "tons_of_things_keyed_llamas"
    setter = seed_only_server.set(key_to_store, value_to_store)

    # But watch - unlike before, this node knows it can set values.
    result = event_loop.run_until_complete(setter)
    assert result
    assert seed_only_server.digests_set == 1

    # annnnd stop.
    seed_only_server.stop()
    full_server.stop()
    event_loop.close()
