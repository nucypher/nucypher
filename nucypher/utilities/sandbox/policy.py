from collections import OrderedDict
from typing import List, Set

import maya

from nucypher.characters.lawful import Ursula
from nucypher.network.middleware import RestMiddleware
from nucypher.policy.models import Arrangement, Policy


class MockArrangement(Arrangement):
    _arrangements = OrderedDict()

    def publish(self) -> None:
        self._arrangements[self.id()] = self

    def revoke(self):
        del self._arrangements[self.id()]


class MockPolicy(Policy):
    def make_arrangements(self,
                          network_middleware: RestMiddleware,
                          deposit: int,
                          expiration: maya.MayaDT,
                          ursulas: Set[Ursula] = None
                          ) -> None:
        """
        Create and consider n Arangement objects from all known nodes.
        """

        for ursula in self.alice.known_nodes:
            arrangement = MockArrangement(alice=self.alice, ursula=ursula,
                                          hrac=self.hrac(),
                                          expiration=expiration)

            self.consider_arrangement(network_middleware=network_middleware,
                                      ursula=ursula,
                                      arrangement=arrangement)


class MockPolicyCreation:
    """
    Simple mock logic to avoid repeated hammering of blockchain policies.
    """
    waited_for_receipt = False
    tx_hash = "THIS HAS BEEN A TRANSACTION!"

    def __init__(self, *args, **kwargs):
        # TODO: Test that proper arguments are passed here once 316 is closed.
        pass

    def transact(self, alice, payload):
        # TODO: Make a meaningful assertion regarding the value.
        assert payload['from'] == alice._ether_address
        return self.tx_hash

    @classmethod
    def wait_for_receipt(cls, tx_hash):
        assert tx_hash == cls.tx_hash
        cls.waited_for_receipt = True

