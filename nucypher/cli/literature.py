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

Failure to keep your node online, or violation of re-encryption work orders
will result in the loss of staked tokens as described in the NuCypher slashing protocol.

Keeping your Ursula node online during the staking period and successfully
producing correct re-encryption work orders will result in rewards
paid out in ethers retro-actively and on-demand.

Accept ursula node operator obligation?"""


CONFIRM_LARGE_STAKE_VALUE = "Wow, {value} - That's a lot of NU - Are you sure this is correct?"

CONFIRM_LARGE_STAKE_DURATION = "Woah, {lock_periods} is a long time - Are you sure this is correct?"

PREALLOCATION_STAKE_ADVISORY = "Beneficiary {client_account} will use preallocation contract {staking_address} to stake."

NO_STAKING_ACCOUNTS = "No staking accounts found."

SELECT_STAKING_ACCOUNT_INDEX = "Select index of staking account"

NO_ACTIVE_STAKES = "There are no active stakes\n"

NO_STAKES_AT_ALL = "No Stakes found"

SELECT_STAKE = "Select Stake"

NO_STAKES_FOUND = "No stakes found."

POST_STAKING_ADVICE = """
View your stakes by running 'nucypher stake list'
or set your Ursula worker node address by running 'nucypher stake set-worker'.

See https://docs.nucypher.com/en/latest/guides/staking_guide.html
"""

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

RESTAKING_LOCK_AGREEMENT = """
By enabling the re-staking lock for {staking_address}, you are committing to automatically
re-stake all rewards until a future period.  You will not be able to disable re-staking until {release_period}.
"""

CONFIRM_RESTAKING_LOCK = "Confirm enable re-staking lock for staker {staking_address} until {release_period}?"

SUCCESSFUL_ENABLE_RESTAKE_LOCK = 'Successfully enabled re-staking lock for {staking_address} until {lock_until}'

RESTAKING_AGREEMENT = """
By enabling the re-staking for {staking_address}, all staking rewards will be automatically added to your existing stake.
"""

CONFIRM_ENABLE_RESTAKING = "Confirm enable automatic re-staking for staker {staking_address}?"

SUCCESSFUL_ENABLE_RESTAKING = 'Successfully enabled re-staking for {staking_address}'

CONFIRM_DISABLE_RESTAKING = "Confirm disable re-staking for staker {staking_address}?"

SUCCESSFUL_DISABLE_RESTAKING = 'Successfully disabled re-staking for {staking_address}'


#
# Bonding
#

PROMPT_WORKER_ADDRESS = "Enter worker address"

CONFIRM_WORKER_AND_STAKER_ADDRESSES_ARE_EQUAL = """

{address}
The worker address provided is the same as the staking account.
It is *highly recommended* to use a different accounts for staker and worker roles.

Continue?
"""

SUCCESSFUL_WORKER_BONDING = "\nWorker {worker_address} successfully bonded to staker {staking_address}"

BONDING_DETAILS = "Bonded at period #{current_period} ({bonded_date})"

BONDING_RELEASE_INFO = "This worker can be replaced or detached after period #{release_period} ({release_date})"

SUCCESSFUL_DETACH_WORKER = "Successfully detached worker {worker_address} from staker {staking_address}"

DETACH_DETAILS = "Detached at period #{current_period} ({bonded_date})"


#
# Worker Rate
#

PROMPT_STAKER_MIN_POLICY_RATE = "Enter new value so the minimum fee rate falls within global fee range"

CONFIRM_NEW_MIN_POLICY_RATE = "Commit new value {min_rate} for minimum fee rate?"

SUCCESSFUL_SET_MIN_POLICY_RATE = "\nMinimum fee rate {min_rate} successfully set by staker {staking_address}"


#
# Divide and Prolong
#


ONLY_DISPLAYING_DIVISIBLE_STAKES_NOTE = "NOTE: Showing divisible stakes only"

NO_DIVISIBLE_STAKES = "No divisible stakes found."

CONFIRM_BROADCAST_STAKE_DIVIDE = "Publish stake division to the blockchain?"

PROMPT_STAKE_EXTEND_VALUE = "Enter number of periods to extend"

PROMPT_STAKE_DIVIDE_VALUE = "Enter target value ({minimum} - {maximum})"

SUCCESSFUL_STAKE_DIVIDE = 'Successfully divided stake'

PROMPT_PROLONG_VALUE = "Enter number of periods to extend ({minimum}-{maximum})"

CONFIRM_PROLONG = "Publish stake extension of {lock_periods} period(s) to the blockchain?"

SUCCESSFUL_STAKE_PROLONG = 'Successfully Prolonged Stake'

#
# Rewards
#

COLLECTING_TOKEN_REWARD = 'Collecting {reward_amount} from staking rewards...'

COLLECTING_ETH_REWARD = 'Collecting {reward_amount} ETH from policy rewards...'

COLLECTING_PREALLOCATION_REWARD = 'Collecting {unlocked_tokens} from PreallocationEscrow contract {staking_address}...'


#
# Configuration
#

MISSING_CONFIGURATION_FILE = """No {name} configuration file found. 'To create a new persistent {name} run:
nucypher {init_command}
"""


SELECT_NETWORK = "Select Network"

NO_CONFIGURATIONS_ON_DISK = "No {name} configurations found.  run 'nucypher {command} init' then try again."

SUCCESSFUL_UPDATE_CONFIGURATION_VALUES = "Updated configuration values: {fields}"

INVALID_JSON_IN_CONFIGURATION_WARNING = "Invalid JSON in Configuration File at {filepath}."

INVALID_CONFIGURATION_FILE_WARNING = "Invalid Configuration at {filepath}."

NO_ETH_ACCOUNTS = "No ETH accounts were found."

GENERIC_SELECT_ACCOUNT = "Select index of account"

CHARACTER_DESTRUCTION = """
Delete all {name} character files including:
    - Private and Public Keys ({keystore})
    - Known Nodes             ({nodestore})
    - Node Configuration File ({config})
    - Database                ({database})

Are you sure?"""

SUCCESSFUL_DESTRUCTION = "Successfully destroyed NuCypher configuration"

CONFIRM_FORGET_NODES = "Permanently delete all known node data?"

SUCCESSFUL_FORGET_NODES = "Removed all stored known nodes metadata and certificates"

CONFIRM_OVERWRITE_DATABASE = "Overwrite existing database?"

SUCCESSFUL_DATABASE_DESTRUCTION = "Destroyed existing database {path}"

SUCCESSFUL_DATABASE_CREATION = "\nCreated new database at {path}"

SUCCESSFUL_NEW_STAKEHOLDER_CONFIG = "Wrote new stakeholder configuration to {filepath}"


#
#  Authentication
#

COLLECT_ETH_PASSWORD = "Enter password to unlock account {checksum_address}"

COLLECT_NUCYPHER_PASSWORD = "Enter NuCypher keyring password"

GENERIC_PASSWORD_PROMPT = "Enter password"

DECRYPTING_CHARACTER_KEYRING = 'Decrypting {name} keyring...'


#
# Networking
#


CONFIRM_URSULA_IPV4_ADDRESS = "Is this the public-facing IPv4 address ({rest_host}) you want to use for Ursula?"

COLLECT_URSULA_IPV4_ADDRESS = "Please enter Ursula's public-facing IPv4 address here:"


#
# Seednodes
#

START_LOADING_SEEDNODES = "Connecting to preferred teacher nodes..."

UNREADABLE_SEEDNODE_ADVISORY = "Failed to connect to teacher: {uri}"

FORCE_DETECT_URSULA_IP_WARNING = "WARNING: --force is set, using auto-detected IP '{rest_host}'"

NO_DOMAIN_PEERS = "WARNING - No Peers Available for domains: {domains}"

SEEDNODE_NOT_STAKING_WARNING = "Teacher: {uri} is not actively staking, skipping"


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

CONFIRM_TOKEN_TRANSFER = "Transfer {value} from {deployer_address} to {target_address}?"

PROMPT_TOKEN_VALUE = "Enter value in NU"

PROMPT_RECIPIENT_CHECKSUM_ADDRESS = "Enter recipient's checksum address"

DISPLAY_SENDER_TOKEN_BALANCE_BEFORE_TRANSFER = "Deployer NU balance: {token_balance}"

PROMPT_FOR_ALLOCATION_DATA_FILEPATH = "Enter allocations data filepath"

SUCCESSFUL_SAVE_BATCH_DEPOSIT_RECEIPTS = "Saved batch deposits receipts to {receipts_filepath}"

SUCCESSFUL_SAVE_DEPLOY_RECEIPTS = "Saved deployment receipts to {receipts_filepath}"

SUCCESSFUL_REGISTRY_CREATION = 'Generated registry {registry_outfile}'

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

SUCCESSFUL_RETARGET_TX_BUILT = "Transaction to retarget {contract_name} proxy to {target_address} was built:"

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
# Multisig
#

SUCCESSFUL_SAVE_MULTISIG_TX_PROPOSAL = "✅ Saved proposal to {filepath}"

PROMPT_NEW_MULTISIG_THRESHOLD = "New threshold"

PROMPT_FOR_RAW_SIGNATURE = "Signature"

SUCCESSFUL_MULTISIG_AUTHORIZATION = "Added authorization from executive {executive_address}"

CONFIRM_EXECUTE_MULTISIG_TRANSACTION = "\nCollected required authorizations. Proceed with execution?"

PROMPT_CONFIRM_MULTISIG_SIGNATURE = "Proceed with signing?"

MULTISIG_SIGNATURE_RECEIVED = "\nSignature received from {recovered_address}:\n"


#
# Worklock
#

WORKLOCK_AGREEMENT = """
* WorkLock Participant Notice *
-------------------------------

- By participating in NuCypher's WorkLock you are committing to operating a staking
  NuCypher node after the bidding window closes.

- WorkLock token rewards are claimed in the form of a stake and will be locked for
  the stake duration.

- WorkLock ETH deposits will be available for refund at a rate of {refund_rate} 
  per confirmed period. This rate may vary until {end_date}.

- Once claiming WorkLock tokens, you are obligated to maintain a networked and available
  Ursula-Worker node bonded to the staker address {bidder_address}
  for the duration of the stake(s) ({duration} periods).

- Allow NuCypher network users to carry out uninterrupted re-encryption work orders
  at-will without interference. Failure to keep your node online, or violation of
  re-encryption work orders will result in the loss of staked tokens as described
  in the NuCypher slashing protocol.

- Keeping your Ursula node online during the staking period and correctly servicing
  re-encryption work orders will result in rewards paid out in ethers retro-actively
  and on-demand.

Accept WorkLock terms and node operator obligation?"""  # TODO: Show a special message for first bidder, since there's no refund rate yet?

BIDDING_WINDOW_CLOSED = f"You can't bid, the bidding window is closed."

SUCCESSFUL_BID_CANCELLATION = "Bid canceled\n"

WORKLOCK_ADDITIONAL_COMPENSATION_AVAILABLE = """
Note that WorkLock did not use your entire bid due to a maximum claim limit.
Therefore, an unspent amount of {amount} is available for refund.
"""

CONFIRM_REQUEST_WORKLOCK_COMPENSATION = """
Before claiming your NU tokens for {bidder_address},
you will need to be refunded your unspent bid amount.
 
Would you like to proceed?
"""

REQUESTING_WORKLOCK_COMPENSATION = "Requesting refund of unspent bid amount..."

CLAIM_ALREADY_PLACED = "Claim was already placed for {bidder_address}"

AVAILABLE_CLAIM_NOTICE = "\nYou have an available claim of {tokens} 🎉 \n"

WORKLOCK_CLAIM_ADVISORY = """
Note: Claiming WorkLock NU tokens will initialize a new stake to be locked for {lock_duration} periods.
"""

CONFIRM_WORKLOCK_CLAIM = "Continue WorkLock claim for bidder {bidder_address}?"

SUBMITTING_WORKLOCK_CLAIM = "Submitting Claim..."

CONFIRM_COLLECT_WORKLOCK_REFUND = "Collect ETH refund for bidder {bidder_address}?"

SUBMITTING_WORKLOCK_REFUND_REQUEST = "Submitting WorkLock refund request..."

PROMPT_BID_VERIFY_GAS_LIMIT = "Enter gas limit per each verification transaction (at least {min_gas})"

COMPLETED_BID_VERIFICATION = "Bidding has been checked\n"

BIDS_VALID_NO_FORCE_REFUND_INDICATED = "All bids are correct, force refund is not needed\n"

CONFIRM_BID_VERIFICATION = """
Confirm verification of bidding from {bidder_address} using {gas_limit} gas 
for {bidders_per_transaction} bidders per each transaction?
"""

VERIFICATION_ESTIMATES = "Using {gas_limit} gas for {bidders_per_transaction} bidders per each transaction\n"

WHALE_WARNING = "At least {number} bidders got a force refund\n"

BIDDERS_ALREADY_VERIFIED = f"Bidders have already been checked\n"

SUCCESSFUL_WORKLOCK_CLAIM = """

Successfully claimed WorkLock tokens for {bidder_address}.

You can check that the stake was created correctly by running:

  nucypher status stakers --staking-address {bidder_address} --network {network} --provider {provider_uri}

Next Steps for WorkLock Winners
===============================

Congratulations! You're officially a Staker in the NuCypher network.

See the official NuCypher documentation for a comprehensive guide on next steps!

As a first step, you need to bond a worker to your stake by running:

  nucypher stake set-worker --worker-address <WORKER ADDRESS>

"""

#
# Felix
#

FELIX_RUN_MESSAGE = "Running Felix on {host}:{port}"

#
# Ursula
#

CONFIRMING_ACTIVITY_NOW = "Making a commitment to period {committed_period}"

SUCCESSFUL_CONFIRM_ACTIVITY = '\nCommitment was made to period #{committed_period} (starting at {date})'

SUCCESSFUL_MANUALLY_SAVE_METADATA = "Successfully saved node metadata to {metadata_path}."
