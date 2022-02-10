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
NUCYPHER_TOKEN_CONTRACT_NAME = 'NuCypherToken'
STAKING_ESCROW_CONTRACT_NAME = 'StakingEscrow'
STAKING_ESCROW_STUB_CONTRACT_NAME = 'StakingEscrowStub'
ADJUDICATOR_CONTRACT_NAME = 'Adjudicator'
PRE_APPLICATION_CONTRACT_NAME = 'SimplePREApplication'  # TODO: Use the real PREApplication
SUBSCRIPTION_MANAGER_CONTRACT_NAME = 'SubscriptionManager'

NUCYPHER_CONTRACT_NAMES = (
    NUCYPHER_TOKEN_CONTRACT_NAME,
    STAKING_ESCROW_CONTRACT_NAME,
    ADJUDICATOR_CONTRACT_NAME,
    DISPATCHER_CONTRACT_NAME,
    PRE_APPLICATION_CONTRACT_NAME,
    SUBSCRIPTION_MANAGER_CONTRACT_NAME
)


# Ethereum

AVERAGE_BLOCK_TIME_IN_SECONDS = 14
ETH_ADDRESS_BYTE_LENGTH = 20
ETH_ADDRESS_STR_LENGTH = 40
ETH_HASH_BYTE_LENGTH = 32
LENGTH_ECDSA_SIGNATURE_WITH_RECOVERY = 65
MAX_UINT16 = 65535
NULL_ADDRESS = '0x' + '0' * 40

# NuCypher
# TODO: this is equal to HRAC.SIZE.
POLICY_ID_LENGTH = 16
