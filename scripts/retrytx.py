import os

from twisted.internet import reactor

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.domains import LYNX
from nucypher.blockchain.eth.interfaces import BlockchainInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.blockchain.eth.signers import InMemorySigner
from nucypher.blockchain.eth.trackers.transactions import TransactionTracker
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.logging import GlobalLoggerSettings
from tests.constants import DEFAULT_TEST_ENRICO_PRIVATE_KEY


#
# Configuration
#

LOG_LEVEL = "debug"
ENDPOINT = os.environ["WEB3_PROVIDER_URI"]
PRIVATE_KEY = DEFAULT_TEST_ENRICO_PRIVATE_KEY
DOMAIN = LYNX


#
# Setup
#

GlobalLoggerSettings.set_log_level(log_level_name=LOG_LEVEL)
GlobalLoggerSettings.start_console_logging()

signer = InMemorySigner(private_key=PRIVATE_KEY)
address = signer.accounts[0]
transacting_power = TransactingPower(signer=signer, account=address)

blockchain = BlockchainInterfaceFactory.get_or_create_interface(endpoint=ENDPOINT)


#
# Prepare Tx
#


base_fee = blockchain.w3.eth.get_block("latest")["baseFeePerGas"]
tip = blockchain.w3.eth.max_priority_fee
nonce = blockchain.w3.eth.get_transaction_count(address, 'pending')

tx = {
    'type': '0x2',
    'chainId': 80001,
    'nonce': nonce,
    'from': address,
    'to': address,
    'value': 0,
    'gas': 21000,
    'maxPriorityFeePerGas': tip,
    'maxFeePerGas': base_fee + tip,
    'data': b'',
}

#
# Queue Tx
#

tracker = TransactionTracker(w3=blockchain.w3)
_future_tx = tracker.queue_transaction(
    tx=tx,
    signer=transacting_power.sign_transaction,  # callable
    info={"message": f"This is transaction {nonce}"},  # optional
)

tracker.start(now=True)
reactor.run()
