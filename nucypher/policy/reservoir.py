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
from typing import Iterable, Optional, List

from eth_typing import ChecksumAddress

from nucypher.blockchain.eth.agents import StakersReservoir, StakingEscrowAgent


def make_federated_staker_reservoir(learner: 'Learner',
                                    exclude_addresses: List[str] = None,
                                    include_addresses: List[str] = None):
    """
    Get a sampler object containing the federated stakers.
    """
    # needs to not include both exclude and include addresses
    # so that they aren't included in reservoir, include_address will be re-added to reservoir afterwards
    exclude_addresses = exclude_addresses or []
    include_addresses = include_addresses or []
    exclusion_set = set()
    exclusion_set.update(exclude_addresses)
    exclusion_set.update(include_addresses)

    addresses = {}
    for ursula in learner.known_nodes:
        if ursula.checksum_address in exclusion_set:
            continue
        addresses[ursula.checksum_address] = 1

    include_addresses = include_addresses or []
    # add include addresses
    return MergedReservoir(include_addresses, StakersReservoir(addresses))


def make_decentralized_staker_reservoir(staking_agent: StakingEscrowAgent,
                                        duration_periods: int,
                                        exclude_addresses: List[str] = None,
                                        include_addresses: List[str] = None):
    """
    Get a sampler object containing the currently registered stakers.
    """

    # needs to not include both exclude and include addresses
    # so that they aren't included in reservoir, include_address will be re-added to reservoir afterwards
    exclude_addresses = exclude_addresses or []
    include_addresses = include_addresses or []
    without_set = set()
    without_set.update(exclude_addresses)
    without_set.update(include_addresses)
    try:
        reservoir = staking_agent.get_stakers_reservoir(duration=duration_periods,
                                                        without=without_set)
    except StakingEscrowAgent.NotEnoughStakers:
        # TODO: do that in `get_stakers_reservoir()`?
        reservoir = StakersReservoir({})

    # add include addresses
    return MergedReservoir(include_addresses, reservoir)


class MergedReservoir:
    """
    A reservoir made of a list of addresses and a StakersReservoir.
    Draws the values from the list first, then from StakersReservoir,
    then returns None on subsequent calls.
    """

    def __init__(self, values: Iterable, reservoir: StakersReservoir):
        self.values = list(values)
        self.reservoir = reservoir

    def __call__(self) -> Optional[ChecksumAddress]:
        if self.values:
            return self.values.pop(0)
        elif len(self.reservoir) > 0:
            return self.reservoir.draw(1)[0]
        else:
            return None


class PrefetchStrategy:
    """
    Encapsulates the batch draw strategy from a reservoir.
    Determines how many values to draw based on the number of values
    that have already led to successes.
    """

    def __init__(self, reservoir: MergedReservoir, need_successes: int):
        self.reservoir = reservoir
        self.need_successes = need_successes

    def __call__(self, successes: int) -> Optional[List[ChecksumAddress]]:
        batch = []
        for i in range(self.need_successes - successes):
            value = self.reservoir()
            if value is None:
                break
            batch.append(value)
        if not batch:
            return None
        return batch
