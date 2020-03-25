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


class NetworksInventory:  # TODO: See #1564

    MAINNET = 'mainnet'
    MIRANDA = 'miranda'
    FRANCES = 'frances'
    CASSANDRA = 'cassandra'
    GEMINI = 'gemini'

    UNKNOWN = 'unknown'  # TODO: Is there a better way to signal an unknown network?
    DEFAULT = UNKNOWN  # TODO: This assumes we DON'T have a default. Is that OK?  - #1496

    __to_ethereum_chain_id = {
        MAINNET: 1,  # Ethereum Mainnet
        MIRANDA: 5,  # Goerli
        FRANCES: 5,  # Goerli
        CASSANDRA: 5,  # Goerli
        GEMINI: 5,  # Goerli
    }

    NETWORKS = tuple(__to_ethereum_chain_id.keys())

    @classmethod
    def get_ethereum_chain_id(cls, network):  # TODO: Use this (where?) to make sure we're in the right chain
        try:
            return cls.__to_ethereum_chain_id[network]
        except KeyError:
            return 1337  # TODO: what about chain id when testing?
