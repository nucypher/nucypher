

"""Text blobs that are implemented as part of nucypher CLI emitter messages."""


#
# Common
#

FORCE_MODE_WARNING = "WARNING: Force is enabled"

DEVELOPMENT_MODE_WARNING = "WARNING: Running in Development mode"

CONFIRM_SELECTED_ACCOUNT = "Selected {address} - Continue?"


#
# Blockchain
#

CONNECTING_TO_BLOCKCHAIN = "Reading Latest Chaindata..."

PRODUCTION_REGISTRY_ADVISORY = "Using latest published registry from {source}"

LOCAL_REGISTRY_ADVISORY = "Configured to registry filepath {registry_filepath}"

PERIOD_ADVANCED_WARNING = "Current period advanced before the action could be completed. Please try again."

#
# Events
#

CONFIRM_OVERWRITE_EVENTS_CSV_FILE = "Overwrite existing CSV events file - {csv_file}?"


#
# Bonding
#

PROMPT_OPERATOR_ADDRESS = "Enter operator address"

CONFIRM_PROVIDER_AND_OPERATOR_ADDRESSES_ARE_EQUAL = """

{address}
The operator address provided is the same as the staking provider.
Continue using the same account for operator and staking provider?"""

SUCCESSFUL_OPERATOR_BONDING = "\nOperator {operator_address} successfully bonded to staking provider {staking_provider_address}"

BONDING_DETAILS = "Bonded at {bonded_date}"

BONDING_RELEASE_INFO = "This operator can be replaced or detached after {release_date}"

SUCCESSFUL_UNBOND_OPERATOR = "Successfully unbonded operator {operator_address} from staking provider {staking_provider_address}"

DETACH_DETAILS = "Unbonded at {bonded_date}"


#
# Rewards
#

COLLECTING_TOKEN_REWARD = 'Collecting {reward_amount} from staking rewards...'

COLLECTING_ETH_FEE = 'Collecting {fee_amount} ETH from policy fees...'

NO_TOKENS_TO_WITHDRAW = "No tokens can be withdrawn."

NO_FEE_TO_WITHDRAW = "No policy fee can be withdrawn."

TOKEN_REWARD_CURRENT = 'Available staking rewards: {reward_amount}.'

TOKEN_REWARD_PAST_HEADER = 'Staking rewards in the last {periods} periods ({days} days):'

TOKEN_REWARD_PAST = 'Total staking rewards: {reward_amount}.'

TOKEN_REWARD_NOT_FOUND = "No staking rewards found."

#
# Configuration
#

MISSING_CONFIGURATION_FILE = """

No {name} configuration file found. To create a new {name} configuration run:

nucypher {init_command}
"""


SELECT_NETWORK = "Select Network"

SELECT_PAYMENT_NETWORK = "Select Payment Network"

NO_CONFIGURATIONS_ON_DISK = "No {name} configurations found. Run 'nucypher {command} init' then try again."

SUCCESSFUL_UPDATE_CONFIGURATION_VALUES = "Updated configuration values: {fields}"

INVALID_JSON_IN_CONFIGURATION_WARNING = "Invalid JSON in Configuration File at {filepath}."

INVALID_CONFIGURATION_FILE_WARNING = "Invalid Configuration at {filepath}."

NO_ETH_ACCOUNTS = "No ETH accounts were found."

GENERIC_SELECT_ACCOUNT = "Select index of account"

SELECTED_ACCOUNT = "Selected {choice}: {chosen_account}"

CHARACTER_DESTRUCTION = """
Delete all {name} character files including:
    - Private and Public Keys ({keystore})
    - Known Nodes             ({nodestore})
    - Node Configuration File ({config})

Are you sure?"""

SUCCESSFUL_DESTRUCTION = "Successfully destroyed nucypher configuration"

CONFIRM_FORGET_NODES = "Permanently delete all known node data?"

SUCCESSFUL_FORGET_NODES = "Removed all stored known nodes metadata and certificates"

IGNORE_OLD_CONFIGURATION = "Ignoring configuration file '{config_file}' - version is too old"

DEFAULT_TO_LONE_CONFIG_FILE = "Defaulting to {config_class} configuration file: '{config_file}'"

#
#  Authentication
#

PASSWORD_COLLECTION_NOTICE = f"""
Please provide a password to lock Operator keys.
Do not forget this password, and ideally store it using a password manager.
"""

COLLECT_ETH_PASSWORD = "Enter ethereum account password ({checksum_address})"

COLLECT_NUCYPHER_PASSWORD = 'Enter nucypher keystore password'

GENERIC_PASSWORD_PROMPT = "Enter password"

DECRYPTING_CHARACTER_KEYSTORE = 'Authenticating {name}'

REPEAT_FOR_CONFIRMATION = "Repeat for confirmation:"


#
# Networking
#

CONFIRM_IPV4_ADDRESS_QUESTION = "Is this the public-facing address of Ursula?"

CONFIRM_URSULA_IPV4_ADDRESS = (
    "Detected IPv4 address ({rest_host}) - " + CONFIRM_IPV4_ADDRESS_QUESTION
)

COLLECT_URSULA_IPV4_ADDRESS = "Enter Ursula's public-facing IPv4 address"


#
# Deployment
#

PROMPT_NEW_OWNER_ADDRESS = "Enter new owner's checksum address"

CONFIRM_MANUAL_REGISTRY_DOWNLOAD = "Fetch and download latest contract registry from {source}?"

MINIMUM_POLICY_RATE_EXCEEDED_WARNING = """
The staker's fee rate was set to the default value {default} such that it falls within the range [{minimum}, {maximum}].
"""

CONTRACT_IS_NOT_OWNABLE = "Contract {contract_name} is not ownable."

SUCCESSFUL_REGISTRY_CREATION = 'Wrote to registry {registry_outfile}'


CONTRACT_DEPLOYMENT_SERIES_BEGIN_ADVISORY = "Deploying {contract_name}"

CONFIRM_NETWORK_ACTIVATION = "Activate {staking_escrow_name} at {staking_escrow_address}?"

UNKNOWN_CONTRACT_NAME = "No such contract {contract_name}. Available contracts are {contracts}"

CONFIRM_RETARGET = "Confirm re-target {contract_name}'s proxy to {target_address}?"

SUCCESSFUL_UPGRADE = "Successfully deployed and upgraded {contract_name}"

CONFIRM_BEGIN_UPGRADE = "Confirm deploy new version of {contract_name} and retarget proxy?"

SUCCESSFUL_RETARGET = "Successfully re-targeted {contract_name} proxy to {target_address}"

SUCCESSFUL_RETARGET_TX_BUILT = "Successfully built transaction to retarget {contract_name} proxy to {target_address}:"

CONFIRM_BUILD_RETARGET_TRANSACTION = """
Confirm building a re-target transaction for {contract_name}'s proxy to {target_address}?
"""

SUCCESSFUL_REGISTRY_DOWNLOAD = "Successfully downloaded latest registry to {output_filepath}"

CANNOT_OVERWRITE_REGISTRY = "Can't overwrite existing registry. Use '--force' to overwrite."

REGISTRY_NOT_AVAILABLE = "Registry not available."

DEPLOYER_BALANCE = "\n\nDeployer ETH balance: {eth_balance}"

SELECT_DEPLOYER_ACCOUNT = "Select deployer account" 

DEPLOYER_ADDRESS_ZERO_ETH = "Deployer address has no ETH."

ABORT_DEPLOYMENT = "Aborting Deployment"

NO_HARDWARE_WALLET_WARNING = "WARNING: --no-hw-wallet is enabled."

ETHERSCAN_FLAG_ENABLED_WARNING = """
WARNING: --etherscan is enabled. A browser tab will be opened with deployed contracts and TXs as provided by Etherscan.
"""

ETHERSCAN_FLAG_DISABLED_WARNING = """
WARNING: --etherscan is disabled. If you want to see deployed contracts and TXs in your browser, activate --etherscan.
"""

#
# Upgrade
#

DEPLOYER_IS_NOT_OWNER = "Address {deployer_address} is not the owner of {contract_name}'s Dispatcher ({agent.contract_address}). Aborting."

CONFIRM_VERSIONED_UPGRADE = "Confirm upgrade {contract_name} from version {old_version} to version {new_version}?"

REGISTRY_PUBLICATION_HINT = '''
Remember to commit and/or publish the new registry!

* cp {local_registry.filepath} nucypher/blockchain/eth/contract_registry/{network}/contract_registry.json
* git add nucypher/blockchain/eth/contract_registry/{network}/contract_registry.json
* git commit -m "Update contract registry for {contract_name}"
* Push to the appropriate branch and open a pull request!

'''
ETHERSCAN_VERIFY_HINT = '''
Remember to record deployment parameters for etherscan verification
Compiled with solc version {solc_version}

'''


#
# Ursula
#

SUCCESSFUL_MANUALLY_SAVE_METADATA = "Successfully saved node metadata to {metadata_path}."


#
# PREApplication
#

STAKING_PROVIDER_UNAUTHORIZED = '{provider} is not authorized.'

SELECT_OPERATOR_ACCOUNT = "Select operator account"

CONFIRM_BONDING = 'Are you sure you want to bond staking provider {provider} to operator {operator}?'

BONDING_TIME = 'Bonding/Unbonding not permitted until {date}.'

ALREADY_BONDED = '{operator} is already bonded to {provider}'

BONDING = 'Bonding operator {operator}'

UNEXPECTED_HUMAN_OPERATOR = 'Operation not permitted'

UNBONDING = 'Unbonding operator {operator}'

CONFIRM_UNBONDING = 'Are you sure you want to unbond {operator} from {provider}?'

NOT_BONDED = '{provider} is not bonded to any operator'
