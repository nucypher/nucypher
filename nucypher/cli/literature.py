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

"""Text blobs that are implemented as part of nucypher CLI emitter messages."""


#
# Common
#

IS_THIS_CORRECT = "Is this correct?"

FORCE_MODE_WARNING = "WARNING: Force is enabled"

DEVELOPMENT_MODE_WARNING = "WARNING: Running in Development mode"

CONFIRM_SELECTED_ACCOUNT = "Selected {address} - Continue?"


#
# Blockchain
#

CONNECTING_TO_BLOCKCHAIN = "Reading Latest Chaindata..."

PRODUCTION_REGISTRY_ADVISORY = "Using latest published registry from {source}"

LOCAL_REGISTRY_ADVISORY = "Configured to registry filepath {registry_filepath}"

FEDERATED_WARNING = "WARNING: Running in Federated mode"

PERIOD_ADVANCED_WARNING = "Current period advanced before the action could be completed. Please try again."


#
# Staking
#

CONFIRM_STAGED_STAKE = """
* Ursula Node Operator Notice *
-------------------------------

By agreeing to stake {tokens} ({nunits} NuNits):

- Staked tokens will be locked for the stake duration.

- You are obligated to maintain a networked and available Ursula-Worker node
  bonded to the staker address {staker_address} for the duration
  of the stake(s) ({lock_periods} periods).

- Agree to allow NuCypher network users to carry out uninterrupted re-encryption
  work orders at-will without interference.

Failure to keep your node online or fulfill re-encryption work orders will result
in loss of staked NU as described in the NuCypher slashing protocol:
https://docs.nucypher.com/en/latest/architecture/slashing.html.

Keeping your Ursula node online during the staking period and successfully
producing correct re-encryption work orders will result in rewards
paid out in ethers retro-actively and on-demand.

Accept ursula node operator obligation?"""


CONFIRM_LARGE_STAKE_VALUE = "Wow, {value} - That's a lot of NU - Are you sure this is correct?"

CONFIRM_LARGE_STAKE_DURATION = "Woah, {lock_periods} periods ({lock_days} days) is a long time - Are you sure this is correct?"

PROMPT_STAKE_CREATE_VALUE = "Enter stake value in NU ({lower_limit} - {upper_limit})"

PROMPT_STAKE_CREATE_LOCK_PERIODS = "Enter stake duration ({min_locktime} - {max_locktime})"

CONFIRM_STAKE_USE_UNLOCKED = "Confirm only use uncollected staking rewards and unlocked sub-stakes; not tokens from staker address"

CONFIRM_BROADCAST_CREATE_STAKE = "Publish staged stake to the blockchain?"

CONFIRM_INCREASING_STAKE = "Confirm increase stake (index: {stake_index}) by {value}?"

CONFIRM_INCREASING_STAKE_DISCLAIMER = """
NOTE: Due to a known issue with the StakingEscrow contract, using the increase operation may lead to reduced staking
rewards for the first period after the increase (GitHub Issue: https://github.com/nucypher/nucypher/issues/2691).

The workaround to increase stake size without reduced staking rewards is the following:
1. Create a new sub-stake with the same duration as the current sub-stake
2. Wait until there has been a Worker node commitment made in the period after the sub-stake was created
3. Once there has been a commitment made in the period after the sub-stake was created, merge the sub-stakes at any time afterwards

For example,
- If you created a sub-stake in period 10
- Wait until there has been a commitment made in the period after the sub-stake was created (i.e. in period 11)
- Then merge the sub-stake in period 11 after the commitment, or during any period afterwards

Are you sure you want to use the increase operation instead of the workaround?
"""

INSUFFICIENT_BALANCE_TO_INCREASE = "There are no tokens to increase stake"

INSUFFICIENT_BALANCE_TO_CREATE = "Insufficient NU for stake creation."

MAXIMUM_STAKE_REACHED = "Maximum stake reached, can't lock more"

PROMPT_STAKE_INCREASE_VALUE = "Enter stake value in NU (up to {upper_limit})"

SUCCESSFUL_STAKE_INCREASE = 'Successfully increased stake'

NO_STAKING_ACCOUNTS = "No staking accounts found."

SELECT_STAKING_ACCOUNT_INDEX = "Select index of staking account"

NO_ACTIVE_STAKES = "No active stakes found\n"

NO_STAKES_AT_ALL = "No Stakes found"

SELECT_STAKE = "Select Stake"

NO_STAKES_FOUND = "No stakes found."

CONFIRM_MANUAL_MIGRATION = "Confirm manual migration for staker {address}"

MIGRATION_ALREADY_PERFORMED = 'Staker {address} has already migrated.'


POST_STAKING_ADVICE = """
View your stakes by running 'nucypher stake list'
or set your Ursula worker node address by running 'nucypher stake bond-worker'.

See https://docs.nucypher.com/en/latest/staking/running_a_worker.html
"""

#
# Events
#

CONFIRM_OVERWRITE_EVENTS_CSV_FILE = "Overwrite existing CSV events file - {csv_file}?"

#
# Remove Inactive
#


FETCHING_INACTIVE_STAKES = 'Fetching inactive stakes'

NO_INACTIVE_STAKES = "No inactive stakes found\n"

CONFIRM_REMOVE_ALL_INACTIVE_SUBSTAKES = """
This action will perform a series of transactions to remove all unused sub-stakes
(Indices {stakes}).  It is recommended that you verify each staker transaction was successful (https://etherscan.io/address/{staker_address}).

Confirm removal of {quantity} unused sub-stakes?"""


#
# Minting
#

NO_MINTABLE_PERIODS = "There are no periods that can be rewarded."

STILL_LOCKED_TOKENS = """
WARNING: Some amount of tokens still locked. 
It is *recommended* to run worker node until all tokens will be unlocked
and only after that call `mint`.
"""

CONFIRM_MINTING = "Confirm mint tokens for {mintable_periods} previous periods?"

SUCCESSFUL_MINTING = 'Reward successfully minted'

#
# Wind Down
#

WINDING_DOWN_AGREEMENT = """
Over time, as the locked stake duration decreases
i.e. `winds down`, you will receive decreasing inflationary rewards.

Instead, by disabling `wind down` (default) the locked stake duration
can remain constant until you specify that `wind down` should begin. By
keeping the locked stake duration constant, it ensures that you will
receive maximum inflation compensation.

If `wind down` was previously disabled, you can enable it at any point
and the locked duration will decrease after each period.

For more information see https://docs.nucypher.com/en/latest/architecture/sub_stakes.html#winding-down.
"""

CONFIRM_ENABLE_WINDING_DOWN = "Confirm enable automatic winding down for staker {staking_address}?"

SUCCESSFUL_ENABLE_WIND_DOWN = 'Successfully enabled winding down for {staking_address}'

CONFIRM_DISABLE_WIND_DOWN = "Confirm disable winding down for staker {staking_address}?"

SUCCESSFUL_DISABLE_WIND_DOWN = 'Successfully disabled winding down for {staking_address}'


#
# Restaking
#

RESTAKING_AGREEMENT = """
By enabling the re-staking for {staking_address}, all staking rewards will be automatically added to your existing stake.
"""

CONFIRM_ENABLE_RESTAKING = "Confirm enable automatic re-staking for staker {staking_address}?"

SUCCESSFUL_ENABLE_RESTAKING = 'Successfully enabled re-staking for {staking_address}'

CONFIRM_DISABLE_RESTAKING = "Confirm disable re-staking for staker {staking_address}?"

SUCCESSFUL_DISABLE_RESTAKING = 'Successfully disabled re-staking for {staking_address}'


#
# Snapshots
#

SNAPSHOTS_DISABLING_AGREEMENT = """
By disabling snapshots, staker {staking_address} will be excluded from all future DAO validations
until snapshots are enabled.
"""

CONFIRM_ENABLE_SNAPSHOTS = "Confirm enable automatic snapshots for staker {staking_address}?"

SUCCESSFUL_ENABLE_SNAPSHOTS = 'Successfully enabled snapshots for staker {staking_address}'

CONFIRM_DISABLE_SNAPSHOTS = "Confirm disable snapshots for staker {staking_address}?"

SUCCESSFUL_DISABLE_SNAPSHOTS = 'Successfully disabled snapshots for staker {staking_address}'

#
# Bonding
#

PROMPT_WORKER_ADDRESS = "Enter worker address"

CONFIRM_WORKER_AND_STAKER_ADDRESSES_ARE_EQUAL = """

{address}
The worker address provided is the same as the staker.
It is *highly recommended* to use a different accounts for staker and worker roles.

Continue using the same account for worker and staker?"""

SUCCESSFUL_WORKER_BONDING = "\nWorker {worker_address} successfully bonded to staker {staking_address}"

BONDING_DETAILS = "Bonded at period #{current_period} ({bonded_date})"

BONDING_RELEASE_INFO = "This worker can be replaced or detached after period #{release_period} ({release_date})"

SUCCESSFUL_DETACH_WORKER = "Successfully detached worker {worker_address} from staker {staking_address}"

DETACH_DETAILS = "Detached at period #{current_period} ({bonded_date})"


#
# Worker Rate
#

PROMPT_STAKER_MIN_POLICY_RATE = "Enter new value (in GWEI) so the minimum fee rate falls within global fee range"

CONFIRM_NEW_MIN_POLICY_RATE = "Commit new value {min_rate} GWEI for minimum fee rate?"

SUCCESSFUL_SET_MIN_POLICY_RATE = "\nMinimum fee rate {min_rate} GWEI successfully set by staker {staking_address}"


#
# Divide, Prolong and Merge
#


ONLY_DISPLAYING_DIVISIBLE_STAKES_NOTE = "NOTE: Showing divisible stakes only"

ONLY_DISPLAYING_MERGEABLE_STAKES_NOTE = "NOTE: Showing stakes with {final_period} final period only"

CONFIRM_BROADCAST_STAKE_DIVIDE = "Publish stake division to the blockchain?"

PROMPT_STAKE_EXTEND_VALUE = "Enter number of periods to extend"

PROMPT_STAKE_DIVIDE_VALUE = "Enter target value ({minimum} - {maximum})"

SUCCESSFUL_STAKE_DIVIDE = 'Successfully divided stake'

PROMPT_PROLONG_VALUE = "Enter number of periods to extend ({minimum}-{maximum})"

CONFIRM_PROLONG = "Publish stake extension of {lock_periods} period(s) to the blockchain?"

SUCCESSFUL_STAKE_PROLONG = 'Successfully Prolonged Stake'

CONFIRM_MERGE = "Publish merging of {stake_index_1} and {stake_index_2} stakes?"

CONFIRM_MERGE_DISCLAIMER = """
NOTE: Due to a known issue with the StakingEscrow contract, using the merge operation may lead to reduced staking
rewards for the first period after the merge (GitHub Issue: https://github.com/nucypher/nucypher/issues/2691).

Before merging a sub-stake, ensure that there has been a Worker node commitment that occurred in the period after the
sub-stake was created. For example,
- If you created a sub-stake in period 10
- Wait until there has been a Worker node commitment made in the period after the sub-stake was created (i.e. in period 11)
- Merge the sub-stake in period 11 after the commitment, or any time afterwards

Are you sure you want to merge now instead of waiting?
"""

SUCCESSFUL_STAKES_MERGE = 'Successfully Merged Stakes'

CONFIRM_REMOVE_SUBSTAKE = "Publish removal of {stake_index} stake?"

SUCCESSFUL_STAKE_REMOVAL = 'Successfully Removed Stake'

#
# Rewards
#

COLLECTING_TOKEN_REWARD = 'Collecting {reward_amount} from staking rewards...'

CONFIRM_COLLECTING_WITHOUT_MINTING = """
There will still be a period to reward after withdrawing this portion of NU. 
It is *recommended* to call `mint` before.

Continue?
"""

COLLECTING_ETH_FEE = 'Collecting {fee_amount} ETH from policy fees...'

COLLECTING_PREALLOCATION_REWARD = 'Collecting {unlocked_tokens} from PreallocationEscrow contract {staking_address}...'

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
    - Database                ({database})

Are you sure?"""

SUCCESSFUL_DESTRUCTION = "Successfully destroyed nucypher configuration"

CONFIRM_FORGET_NODES = "Permanently delete all known node data?"

SUCCESSFUL_FORGET_NODES = "Removed all stored known nodes metadata and certificates"

CONFIRM_OVERWRITE_DATABASE = "Overwrite existing database?"

SUCCESSFUL_DATABASE_DESTRUCTION = "Destroyed existing database {path}"

SUCCESSFUL_DATABASE_CREATION = "\nCreated new database at {path}"

SUCCESSFUL_NEW_STAKEHOLDER_CONFIG = """
Configured new stakeholder!
Wrote JSON configuration to {filepath}

* Review configuration     -> nucypher stake config
* View connected accounts  -> nucypher stake accounts
* Create a new stake       -> nucypher stake create
* Bond a worker            -> nucypher stake bond-worker
* List active stakes       -> nucypher stake list

"""

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


#
# Networking
#


CONFIRM_URSULA_IPV4_ADDRESS = "Detected IPv4 address ({rest_host}) - Is this the public-facing address of Ursula?"

COLLECT_URSULA_IPV4_ADDRESS = "Enter Ursula's public-facing IPv4 address"


#
# Seednodes
#

START_LOADING_SEEDNODES = "Connecting to preferred teacher nodes..."

UNREADABLE_SEEDNODE_ADVISORY = "Failed to connect to teacher: {uri}"

NO_DOMAIN_PEERS = "WARNING: No Peers Available for domain: {domain}"

SEEDNODE_NOT_STAKING_WARNING = "Teacher ({uri}) is not actively staking, skipping"


#
# Deployment
#

PROMPT_NEW_MIN_RANGE_VALUE = "Enter new minimum value for range"

PROMPT_NEW_MAXIMUM_RANGE_VALUE = "Enter new maximum value for range"

PROMPT_NEW_OWNER_ADDRESS = "Enter new owner's checksum address"

PROMPT_NEW_DEFAULT_VALUE_FOR_RANGE = "Enter new default value for range"

CONFIRM_MANUAL_REGISTRY_DOWNLOAD = "Fetch and download latest contract registry from {source}?"

MINIMUM_POLICY_RATE_EXCEEDED_WARNING = """
The staker's fee rate was set to the default value {default} such that it falls within the range [{minimum}, {maximum}].
"""

CONTRACT_IS_NOT_OWNABLE = "Contract {contract_name} is not ownable."

CONFIRM_TOKEN_ALLOWANCE = "Approve allowance of {value} from {deployer_address} to {spender_address}?"

CONFIRM_TOKEN_TRANSFER = "Transfer {value} from {deployer_address} to {target_address}?"

PROMPT_TOKEN_VALUE = "Enter value in NU"

PROMPT_RECIPIENT_CHECKSUM_ADDRESS = "Enter recipient's checksum address"

DISPLAY_SENDER_TOKEN_BALANCE_BEFORE_TRANSFER = "Deployer NU balance: {token_balance}"

PROMPT_FOR_ALLOCATION_DATA_FILEPATH = "Enter allocations data filepath"

SUCCESSFUL_SAVE_DEPLOY_RECEIPTS = "Saved deployment receipts to {receipts_filepath}"

SUCCESSFUL_REGISTRY_CREATION = 'Wrote to registry {registry_outfile}'

CONFIRM_LOCAL_REGISTRY_DESTRUCTION = "*DESTROY* existing local registry and continue?"

EXISTING_REGISTRY_FOR_DOMAIN = """
There is an existing contract registry at {registry_filepath}.

Did you mean 'nucypher-deploy upgrade'?
"""

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

IDENTICAL_REGISTRY_WARNING = "Local registry ({local_registry.id}) is identical to the one on GitHub ({github_registry.id})."

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

CONFIRMING_ACTIVITY_NOW = "Making a commitment to period {committed_period}"

SUCCESSFUL_CONFIRM_ACTIVITY = '\nCommitment was made to period #{committed_period} (starting at {date})'

SUCCESSFUL_MANUALLY_SAVE_METADATA = "Successfully saved node metadata to {metadata_path}."


#
# Porter
#

PORTER_RUN_MESSAGE = "Running Porter Web Controller at {http_scheme}://127.0.0.1:{http_port}"

PORTER_BASIC_AUTH_ENABLED = "Basic Authentication enabled"

PORTER_CORS_ALLOWED_ORIGINS = "CORS Allow Origins: {allow_origins}"

PORTER_BOTH_TLS_KEY_AND_CERTIFICATION_MUST_BE_PROVIDED = "Both --tls-key-filepath and --tls-certificate-filepath must be provided to launch porter with TLS; only one specified"

PORTER_BASIC_AUTH_REQUIRES_HTTPS = "Basic authentication can only be used with HTTPS. --tls-key-filepath and --tls-certificate-filepath must also be provided"


#
# PREApplication
#

STAKING_PROVIDER_UNAUTHORIZED = '{provider} is not authorized.'

CONFIRM_BONDING = 'Are you sure you want to bond staking provider {provider} to operator {operator}?'

BONDING_TIME = 'Bonding not permitted until {date}'

ALREADY_BONDED = '{provider} is already bonded to {operator}'

BONDING = 'Bonding operator {operator}'

UNEXPECTED_HUMAN_OPERATOR = 'Operation not permitted'

UNBONDING = 'Unbonding operator {operator}'

CONFIRM_UNBONDING = 'Are you sure you want to unbond {operator} from {provider}?'

NOT_BONDED = '{provider} is not bonded to any operator'
