
#
# Staking
#

RESTAKING_LOCK_AGREEMENT = """
By enabling the re-staking lock for {staking_address}, you are committing to automatically
re-stake all rewards until a future period.  You will not be able to disable re-staking until {release_period}.
"""

RESTAKING_AGREEMENT = "By enabling the re-staking for {staking_address}, all staking rewards will be automatically added to your existing stake."

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

CONFIRM_STAGED_STAKE = """
* Ursula Node Operator Notice *
-------------------------------

By agreeing to stake {str(value)} ({str(value.to_nunits())} NuNits):

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

CONFIRM_RESTAKING_LOCK = "Confirm enable re-staking lock for staker {staking_address} until {release_period}?"

CONFIRM_ENABLE_RESTAKING = "Confirm enable automatic re-staking for staker {staking_address}?"

CONFIRM_ENABLE_WINDING_DOWN = "Confirm enable automatic winding down for staker {staking_address}?"

CONFIRM_LARGE_STAKE_VALUE = "Wow, {value} - That's a lot of NU - Are you sure this is correct?"

CONFIRM_LARGE_STAKE_DURATION = "Woah, {lock_periods} is a long time - Are you sure this is correct?"

#
# Configuration
#

CHARACTER_DESTRUCTION = '''
Delete all {name} character files including:
    - Private and Public Keys ({keystore})
    - Known Nodes             ({nodestore})
    - Node Configuration File ({config})
    - Database                ({database})

Are you sure?'''

SUCCESSFUL_DESTRUCTION = "Successfully destroyed NuCypher configuration"


CONFIRM_FORGET_NODES = "Permanently delete all known node data?"

SUCCESSFUL_FORGET_NODES = "Removed all stored known nodes metadata and certificates"


#
#  Authentication
#

COLLECT_ETH_PASSWORD = "Enter password to unlock account {checksum_address}"

COLLECT_NUCYPHER_PASSWORD = "Enter NuCypher keyring password"

#
# Ursula Networking
#

CONFIRM_URSULA_IPV4_ADDRESS = "Is this the public-facing IPv4 address ({rest_host}) you want to use for Ursula?"

COLLECT_URSULA_IPV4_ADDRESS = "Please enter Ursula's public-facing IPv4 address here:"

#
# Seednodes
#

FORCE_DETECT_URSULA_IP_WARNING = "WARNING: --force is set, using auto-detected IP '{rest_host}'"

NO_DOMAIN_PEERS = "WARNING - No Peers Available for domains: {domains}"

SEEDNODE_NOT_STAKING_WARNING = "Teacher: {uri} is not actively staking, skipping"


#
# Deployment
#

ABORT_DEPLOYMENT = "Aborting Deployment"
