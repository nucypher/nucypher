import os

from eth_account import Account
from twisted.internet import reactor
from web3 import Web3, HTTPProvider
from web3.middleware import geth_poa_middleware

from nucypher.blockchain.eth.domains import LYNX
from nucypher.blockchain.eth.trackers.transactions import TransactionTracker
from nucypher.blockchain.eth.trackers.transactions.tx import FinalizedTx, PendingTx
from nucypher.utilities.logging import GlobalLoggerSettings
from tests.constants import DEFAULT_TEST_ENRICO_PRIVATE_KEY

GlobalLoggerSettings.set_log_level(log_level_name='debug')
GlobalLoggerSettings.start_console_logging()


#
# Configuration
#

LOG_LEVEL = "debug"
CHAIN_ID = 80001
ENDPOINT = os.environ["WEB3_PROVIDER_URI"]
PRIVATE_KEY = DEFAULT_TEST_ENRICO_PRIVATE_KEY
DOMAIN = LYNX

#
# Setup
#

account = Account.from_key(PRIVATE_KEY)
provider = HTTPProvider(endpoint_uri=ENDPOINT)

w3 = Web3(provider)
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

#
# Prepare Transaction
#

nonce = w3.eth.get_transaction_count(account.address, 'pending')

# Legacy transaction
gas_price = w3.eth.gas_price
legacy_transaction = {
    'chainId': CHAIN_ID,
    'nonce': nonce,
    'to': account.address,
    'value': 0,
    'gas': 21000,
    'gasPrice': gas_price,
    'data': b'',
}

# EIP-1559 transaction
base_fee = w3.eth.get_block("latest")["baseFeePerGas"]
tip = w3.eth.max_priority_fee
transaction_eip1559 = {
    'chainId': CHAIN_ID,
    'nonce': nonce + 1,
    'to': account.address,
    'value': 0,
    'gas': 21000,
    'maxPriorityFeePerGas': tip,
    'maxFeePerGas': base_fee + tip,
    'data': b'',
}

#
# Define Hooks
#


def on_transaction_finalized(tx: FinalizedTx):
    txhash = tx.receipt['transactionHash'].hex()
    mumbai_polygonscan = f"https://mumbai.polygonscan.com/tx/{txhash}"
    print(f"[alert] Transaction has been finalized ({txhash})!")
    print(f"View on PolygonScan: {mumbai_polygonscan}")


def on_transaction_capped(tx: PendingTx):
    txhash = tx.txhash.hex()
    print(f"[alert] Transaction has been capped ({txhash})!")


def on_transaction_timeout(tx: PendingTx):
    txhash = tx.txhash.hex()
    print(f"[alert] Transaction has timed out ({txhash})!")


#
# Queue Transaction(s)
#

tracker = TransactionTracker(w3=w3, signer=account)
_future_txs = tracker.queue_transactions(
    params=[
        legacy_transaction,
        transaction_eip1559
    ],
    info={"message": f"something wonderful is happening..."},  # optional
    on_finalized=on_transaction_finalized,
    on_capped=on_transaction_capped,
    on_timeout=on_transaction_timeout
)

tracker.start(now=True)
reactor.run()
