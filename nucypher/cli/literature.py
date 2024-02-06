"""Text blobs that are implemented as part of nucypher CLI emitter messages."""


# Common
FORCE_MODE_WARNING = "WARNING: Force is enabled"
DEVELOPMENT_MODE_WARNING = "WARNING: Running in Development mode"

# Events
CONFIRM_OVERWRITE_EVENTS_CSV_FILE = "Overwrite existing CSV events file - {csv_file}?"

# Configuration
MISSING_CONFIGURATION_FILE = """

No {name} configuration file found. To create a new {name} configuration run:

nucypher {init_command}
"""


SELECT_DOMAIN = "Select TACo Domain"
NO_CONFIGURATIONS_ON_DISK = "No {name} configurations found. Run 'nucypher {command} init' then try again."
SUCCESSFUL_UPDATE_CONFIGURATION_VALUES = "Updated configuration values: {fields}"
INVALID_JSON_IN_CONFIGURATION_WARNING = "Invalid JSON in Configuration File at {filepath}."
INVALID_CONFIGURATION_FILE_WARNING = "Invalid Configuration at {filepath}."
NO_ACCOUNTS = "No accounts were found."
GENERIC_SELECT_ACCOUNT = "Select index of account"
SELECT_OPERATOR_ACCOUNT = "Select operator account"
SELECTED_ACCOUNT = "Selected {choice}: {chosen_account}"

CHARACTER_DESTRUCTION = """
Delete all {name} character files including:
    - Private and Public Keys ({keystore})
    - Node Configuration File ({config})

Are you sure?"""

SUCCESSFUL_DESTRUCTION = "Successfully destroyed nucypher configuration"
CONFIRM_FORGET_NODES = "Permanently delete all known node data?"
SUCCESSFUL_FORGET_NODES = "Removed all stored known nodes metadata and certificates"

IGNORE_OLD_CONFIGURATION = """
Ignoring configuration file '{config_file}' whose version is too old ('{version}').
Run `nucypher ursula config migrate --config-file '{config_file}'` to update it.
"""
MIGRATE_OLD_CONFIGURATION = """
Migrating configuration file '{config_file}' whose version ('{version}') is too old.
"""
PROMPT_TO_MIGRATE = """
Detected configuration file '{config_file}' with old version ('{version}'). Would you 
like to migrate this file to the newest version? 
"""
DEFAULT_TO_LONE_CONFIG_FILE = "Defaulting to {config_class} configuration file: '{config_file}'"

#  Authentication
PASSWORD_COLLECTION_NOTICE = """
Please provide a password to lock Operator keys.
Do not forget this password, and ideally store it using a password manager.
"""

COLLECT_ETH_PASSWORD = "Enter ethereum account password ({checksum_address})"
COLLECT_NUCYPHER_PASSWORD = 'Enter nucypher keystore password'
GENERIC_PASSWORD_PROMPT = "Enter password"
DECRYPTING_CHARACTER_KEYSTORE = 'Authenticating {name}'
REPEAT_FOR_CONFIRMATION = "Repeat for confirmation:"

# Networking
CONFIRM_IPV4_ADDRESS_QUESTION = "Is this the public-facing address of Ursula?"
CONFIRM_URSULA_IPV4_ADDRESS = (
    "Detected IPv4 address ({rest_host}) - " + CONFIRM_IPV4_ADDRESS_QUESTION
)
COLLECT_URSULA_IPV4_ADDRESS = "Enter Ursula's public-facing IPv4 address"
