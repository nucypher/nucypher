

#
# Contract Names
#

# Legacy
NUCYPHER_TOKEN_CONTRACT_NAME = "NuCypherToken"
STAKING_ESCROW_CONTRACT_NAME = "StakingEscrow"
STAKING_ESCROW_STUB_CONTRACT_NAME = "StakingEscrowStub"

# TACo
TACO_APPLICATION_CONTRACT_NAME = "TACoApplication"
TACO_CHILD_APPLICATION_CONTRACT_NAME = "TACoChildApplication"
COORDINATOR_CONTRACT_NAME = "Coordinator"
SUBSCRIPTION_MANAGER_CONTRACT_NAME = "SubscriptionManager"


TACO_CONTRACT_NAMES = (
    TACO_APPLICATION_CONTRACT_NAME,
    TACO_CHILD_APPLICATION_CONTRACT_NAME,
    COORDINATOR_CONTRACT_NAME,
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
