"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import os
import random
from collections import OrderedDict
from typing import Set

import maya

from nucypher.characters.lawful import Ursula
from nucypher.network.middleware import RestMiddleware
from nucypher.policy.policies import Arrangement, Policy


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
    _ether_address = None
    tx_hash = "THIS HAS BEEN A TRANSACTION!"

    def __init__(self, *args, **kwargs):
        # TODO: Test that proper arguments are passed here once 316 is closed.
        pass

    def transact(self, payload):
        # TODO: Make a meaningful assertion regarding the value.
        assert payload['from'] == self._ether_address
        return self.tx_hash

    @classmethod
    def wait_for_receipt(cls, tx_hash):
        assert tx_hash == cls.tx_hash
        cls.waited_for_receipt = True


def generate_random_label() -> bytes:
    """
    Generates a random bytestring for use as a test label.
    :return: bytes
    """
    adjs = ('my', 'sesame-street', 'black', 'cute')
    nouns = ('lizard', 'super-secret', 'data', 'coffee')
    combinations = list('-'.join((a, n)) for a in adjs for n in nouns)
    selection = random.choice(combinations)
    random_label = f'label://{selection}-{os.urandom(4).hex()}'
    return bytes(random_label, encoding='utf-8')
