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

#
# Contract Names
#

DISPATCHER_CONTRACT_NAME = 'Dispatcher'
STAKING_INTERFACE_ROUTER_CONTRACT_NAME = "StakingInterfaceRouter"
NUCYPHER_TOKEN_CONTRACT_NAME = 'NuCypherToken'
STAKING_ESCROW_CONTRACT_NAME = 'StakingEscrow'
POLICY_MANAGER_CONTRACT_NAME = 'PolicyManager'
STAKING_INTERFACE_CONTRACT_NAME = 'StakingInterface'
PREALLOCATION_ESCROW_CONTRACT_NAME = 'PreallocationEscrow'
ADJUDICATOR_CONTRACT_NAME = 'Adjudicator'
WORKLOCK_CONTRACT_NAME = 'WorkLock'
MULTISIG_CONTRACT_NAME = 'MultiSig'
SEEDER_CONTRACT_NAME = 'Seeder'

NUCYPHER_CONTRACT_NAMES = (
    DISPATCHER_CONTRACT_NAME,
    STAKING_INTERFACE_ROUTER_CONTRACT_NAME,
    NUCYPHER_TOKEN_CONTRACT_NAME,
    STAKING_ESCROW_CONTRACT_NAME,
    POLICY_MANAGER_CONTRACT_NAME,
    STAKING_INTERFACE_CONTRACT_NAME,
    PREALLOCATION_ESCROW_CONTRACT_NAME,
    ADJUDICATOR_CONTRACT_NAME,
    WORKLOCK_CONTRACT_NAME,
    MULTISIG_CONTRACT_NAME,
    SEEDER_CONTRACT_NAME
)


# Ethereum

AVERAGE_BLOCK_TIME_IN_SECONDS = 14
ETH_ADDRESS_BYTE_LENGTH = 20
ETH_ADDRESS_STR_LENGTH = 40
MAX_UINT16 = 65535
