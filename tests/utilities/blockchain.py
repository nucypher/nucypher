import asyncio
import random

from constant_sorrow import constants
from typing import Set

from nucypher.characters import Ursula
from tests.utilities.network import _ALL_URSULAS


def make_ursulas(ether_addresses: list, ursula_starting_port: int,
                 miner_agent=None, miners=False, bare=False, threaded=False) -> Set[Ursula]:
    """
    :param ether_addresses: Ethereum addresses to create ursulas with.
    :param ursula_starting_port: The port of the first created Ursula; subsequent Ursulas will increment the port number by 1.


    :param miner_agent: A miner agent instance to use when creating ursulas.
    :param miners: If True, create staking ursulas on the blockchain from the addresses
    :param bare: If True, Create an non-learning Ursula without a rest app, dht server or database attached,
                 for testing mining functionality when network transport is not needed. "Just a miner"

    :return: A list of created Ursulas
    """

    event_loop = asyncio.get_event_loop()

    ursulas = set()
    for port, ether_address in enumerate(ether_addresses, start=ursula_starting_port):

        if bare:
            ursula = Ursula(is_me=False,            # do not attach dht server
                            rest_host="127.0.0.1",  # TODO: remove rest interface
                            rest_port=port + 100,
                            checksum_address=ether_address,
                            always_be_learning=False,
                            miner_agent=miner_agent,
                            abort_on_learning_error=True)

            ursula.is_me = True  # Patch to allow execution of transacting methods in tests

        else:
            federated_only = not miners
            if federated_only:
                ether_address = None
            ursula = Ursula(is_me=True,
                            checksum_address=ether_address,
                            dht_host="127.0.0.1",
                            dht_port=port,
                            db_name="test-{}".format(port),
                            rest_host="127.0.0.1",
                            rest_port=port+100,
                            always_be_learning=False,
                            miner_agent=miner_agent,
                            federated_only=federated_only)

            ursula.attach_rest_server()

            class MockDatastoreThreadPool(object):
                def callInThread(self, f, *args, **kwargs):
                    return f(*args, **kwargs)

            ursula.datastore_threadpool = MockDatastoreThreadPool()
            ursula.dht_listen()

            for ursula_to_teach in ursulas:
                # Add other Ursulas as known nodes.
                for ursula_to_learn_about in ursulas:
                    ursula_to_teach.remember_node(ursula_to_learn_about)

                event_loop.run_until_complete(
                    ursula.dht_server.bootstrap(
                        [("127.0.0.1", ursula_starting_port + _c) for _c in range(len(ursulas))]))
                ursula.publish_dht_information()

        if miners is True:
            # TODO: 309
            # stake a random amount
            min_stake, balance = int(constants.MIN_ALLOWED_LOCKED), ursula.token_balance
            amount = random.randint(min_stake, balance)

            # for a random lock duration
            min_locktime, max_locktime = int(constants.MIN_LOCKED_PERIODS), int(constants.MAX_MINTING_PERIODS)
            periods = random.randint(min_locktime, max_locktime)

            ursula.stake(amount=amount, lock_periods=periods)
        else:
            ursula.federated_only = True

        ursulas.add(ursula)
        _ALL_URSULAS[ursula.rest_interface.port] = ursula

    return ursulas
