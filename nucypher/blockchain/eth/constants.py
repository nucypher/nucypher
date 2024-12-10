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


PUBLIC_CHAINS = {
    1: "Mainnet",
    137: "Polygon/Mainnet",
    11155111: "Sepolia",
    80002: "Polygon/Amoy",
}

POA_CHAINS = {
    4,  # Rinkeby
    5,  # Goerli
    42,  # Kovan
    77,  # Sokol
    100,  # xDAI
    10200,  # gnosis/chiado,
    137,  # Polygon/Mainnet
    80001,  # "Polygon/Mumbai"
    80002,  # "Polygon/Amoy"
}

CHAINLIST_URL = "https://raw.githubusercontent.com/nucypher/chainlist/main/"
