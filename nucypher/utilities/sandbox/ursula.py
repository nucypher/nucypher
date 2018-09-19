import random
from typing import Set

from constant_sorrow import constants
from eth_utils import to_checksum_address
from twisted.internet import protocol

from nucypher.characters.lawful import Ursula
from nucypher.crypto.api import secure_random
from nucypher.utilities.sandbox.constants import (DEFAULT_NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK,
                                                  TEST_URSULA_STARTING_PORT,
                                                  TEST_KNOWN_URSULAS_CACHE)


def make_federated_ursulas(quantity=DEFAULT_NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK,
                           know_each_other=True,
                           **ursula_kwargs) -> Set[Ursula]:

    if not TEST_KNOWN_URSULAS_CACHE:
        starting_port = TEST_URSULA_STARTING_PORT
    else:
        starting_port = max(TEST_KNOWN_URSULAS_CACHE.keys()) + 1

    federated_ursulas = set()
    for port in range(starting_port, starting_port+quantity):

        ursula = Ursula(is_me=True,
                        db_name="test-{}".format(port),
                        rest_host="localhost",
                        rest_port=port + 100,
                        always_be_learning=False,
                        federated_only=True,
                        **ursula_kwargs)

        class MockDatastoreThreadPool(object):
            def callInThread(self, f, *args, **kwargs):
                return f(*args, **kwargs)

        ursula.datastore_threadpool = MockDatastoreThreadPool()

        federated_ursulas.add(ursula)
        # Store this Ursula in our global cache.
        port = ursula.rest_information()[0].port
        TEST_KNOWN_URSULAS_CACHE[port] = ursula

    if know_each_other:

        for ursula_to_teach in federated_ursulas:
            # Add other Ursulas as known nodes.
            for ursula_to_learn_about in federated_ursulas:
                ursula_to_teach.remember_node(ursula_to_learn_about)

    return federated_ursulas


def make_decentralized_ursulas(ether_addresses: list,
                               miner_agent=None,
                               stake=False,
                               know_each_other=True,
                               **ursula_kwargs) -> Set[Ursula]:

    if isinstance(ether_addresses, int):
        ether_addresses = [to_checksum_address(secure_random(20)) for _ in range(ether_addresses)]

    if not TEST_KNOWN_URSULAS_CACHE:
        starting_port = TEST_URSULA_STARTING_PORT
    else:
        starting_port = max(TEST_KNOWN_URSULAS_CACHE.keys()) + 1

    ursulas = set()
    for port, checksum_address in enumerate(ether_addresses, start=starting_port):

        ursula = Ursula(is_me=True,
                        checksum_address=checksum_address,
                        db_name="test-{}".format(port),
                        rest_host="localhost",
                        rest_port=port + 100,
                        always_be_learning=False,
                        miner_agent=miner_agent,
                        federated_only=False,
                        **ursula_kwargs)

        class MockDatastoreThreadPool(object):
            def callInThread(self, f, *args, **kwargs):
                return f(*args, **kwargs)

        ursula.datastore_threadpool = MockDatastoreThreadPool()

        if stake is True:

            min_stake, balance = int(constants.MIN_ALLOWED_LOCKED), ursula.token_balance
            amount = random.randint(min_stake, balance)

            # for a random lock duration
            min_locktime, max_locktime = int(constants.MIN_LOCKED_PERIODS), int(constants.MAX_MINTING_PERIODS)
            periods = random.randint(min_locktime, max_locktime)

            ursula.initialize_stake(amount=amount, lock_periods=periods)

        ursulas.add(ursula)
        # Store this Ursula in our global cache.
        port = ursula.rest_information()[0].port
        TEST_KNOWN_URSULAS_CACHE[port] = ursula

    if know_each_other:

        for ursula_to_teach in ursulas:
            # Add other Ursulas as known nodes.
            for ursula_to_learn_about in ursulas:
                ursula_to_teach.remember_node(ursula_to_learn_about)

    return ursulas


def spawn_random_staking_ursulas(miner_agent, addresses: list) -> list:
    """
    Deposit and lock a random amount of tokens in the miner escrow
    from each address, "spawning" new Miners.
    """
    from nucypher.blockchain.eth.actors import Miner

    miners = list()
    for address in addresses:
        miner = Miner(miner_agent=miner_agent, checksum_address=address)
        miners.append(miner)

        # stake a random amount
        min_stake, balance = constants.MIN_ALLOWED_LOCKED, miner.token_balance
        amount = random.randint(min_stake, balance)

        # for a random lock duration
        min_locktime, max_locktime = constants.MIN_LOCKED_PERIODS, constants.MAX_MINTING_PERIODS
        periods = random.randint(min_locktime, max_locktime)

        miner.initialize_stake(amount=amount, lock_periods=periods)

    return miners


class UrsulaProcessProtocol(protocol.ProcessProtocol):

    def __init__(self, command):
        self.command = command

    def connectionMade(self):
        print("connectionMade!")
        self.transport.closeStdin()  # tell them we're done

    def outReceived(self, data):
        print(data)

    def errReceived(self, data):
        print(data)

    def inConnectionLost(self):
        print("inConnectionLost! stdin is closed! (we probably did it)")

    def outConnectionLost(self):
        print("outConnectionLost! The child closed their stdout!")

    def errConnectionLost(self):
        print("errConnectionLost! The child closed their stderr.")

    def processEnded(self, status_object):
        print("processEnded, status %d" % status_object.value.exitCode)
        print("quitting")
