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
STAKING_ESCROW_STUB_CONTRACT_NAME = 'StakingEscrowStub'
POLICY_MANAGER_CONTRACT_NAME = 'PolicyManager'
STAKING_INTERFACE_CONTRACT_NAME = 'StakingInterface'
ADJUDICATOR_CONTRACT_NAME = 'Adjudicator'
WORKLOCK_CONTRACT_NAME = 'WorkLock'
MULTISIG_CONTRACT_NAME = 'MultiSig'

NUCYPHER_CONTRACT_NAMES = (
    NUCYPHER_TOKEN_CONTRACT_NAME,
    STAKING_ESCROW_CONTRACT_NAME,
    POLICY_MANAGER_CONTRACT_NAME,
    ADJUDICATOR_CONTRACT_NAME,
    DISPATCHER_CONTRACT_NAME,
    STAKING_INTERFACE_CONTRACT_NAME,
    STAKING_INTERFACE_ROUTER_CONTRACT_NAME,
    WORKLOCK_CONTRACT_NAME,
    MULTISIG_CONTRACT_NAME,
)


# Ethereum

AVERAGE_BLOCK_TIME_IN_SECONDS = 14
ETH_ADDRESS_BYTE_LENGTH = 20
ETH_ADDRESS_STR_LENGTH = 40
ETH_HASH_BYTE_LENGTH = 32
LENGTH_ECDSA_SIGNATURE_WITH_RECOVERY = 65
MAX_UINT16 = 65535
NULL_ADDRESS = '0x' + '0' * 40

# Aragon DAO contract names

DAO_AGENT_CONTRACT_NAME = 'Agent'
TOKEN_MANAGER_CONTRACT_NAME = 'TokenManager'
VOTING_AGGREGATOR_CONTRACT_NAME = 'VotingAggregator'
VOTING_CONTRACT_NAME = 'Voting'
KERNEL_CONTRACT_NAME = 'Kernel'
FORWARDER_INTERFACE_NAME = 'IForwarder'


# DAO Instances names (as one contract may be instantiated multiple times, with different uses)

DAO_AGENT = 'DAOAgent'
STANDARD_AGGREGATOR = 'StandardAggregator'
STANDARD_VOTING = 'StandardVoting'
EMERGENCY_VOTING = 'EmergencyVoting'
EMERGENCY_MANAGER = 'EmergencyManager'
DAO_KERNEL = 'DAOKernel'

DAO_INSTANCES_NAMES = (
    DAO_AGENT,
    STANDARD_AGGREGATOR,
    STANDARD_VOTING,
    EMERGENCY_VOTING,
    EMERGENCY_MANAGER,
    DAO_KERNEL
)

DAO_INSTANCES_CONTRACT_TYPE = {
    DAO_AGENT: DAO_AGENT_CONTRACT_NAME,
    STANDARD_AGGREGATOR: VOTING_AGGREGATOR_CONTRACT_NAME,
    STANDARD_VOTING: VOTING_CONTRACT_NAME,
    EMERGENCY_VOTING: VOTING_CONTRACT_NAME,
    EMERGENCY_MANAGER: TOKEN_MANAGER_CONTRACT_NAME,
    DAO_KERNEL: KERNEL_CONTRACT_NAME,
}
