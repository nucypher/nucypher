import time

from eth_utils import encode_hex
from twisted.internet import reactor

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.domains import LYNX
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.blockchain.eth.signers import InMemorySigner
from nucypher.blockchain.eth.trackers.dkg import TransactionTracker
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.logging import GlobalLoggerSettings
from tests.constants import DEFAULT_TEST_ENRICO_PRIVATE_KEY

LOG_LEVEL = "debug"
GlobalLoggerSettings.set_log_level(log_level_name=LOG_LEVEL)
GlobalLoggerSettings.start_console_logging()

signer = InMemorySigner(private_key=DEFAULT_TEST_ENRICO_PRIVATE_KEY)
address = signer.accounts[0]
transacting_power = TransactingPower(signer=signer, account=address)
print(address)

endpoint = "https://polygon-mumbai.infura.io/v3/YOUR_INFURA_KEY_HERE"
registry = ContractRegistry.from_latest_publication(
    domain=LYNX,
)
coordinator_agent = CoordinatorAgent(
    blockchain_endpoint=endpoint,
    registry=registry
)
w3 = coordinator_agent.blockchain.w3


def send_underpriced():
    nonce = w3.eth.get_transaction_count(address, 'pending')
    cancel_tx = {
        'nonce': nonce,
        'to': address,
        'value': 0,
        'gas': 21000,
        'maxPriorityFeePerGas': 1,
        'maxFeePerGas': 1,
        'chainId': 80001,
        'type': '0x2',
        'from': address
    }
    signed_tx = signer.sign_transaction(cancel_tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx)
    print(f"Underpriced transaction sent | txhash: {encode_hex(tx_hash)}")
    return tx_hash, nonce


tracker = TransactionTracker(
    w3=coordinator_agent.blockchain.w3,
    transacting_power=transacting_power,
)

track = set()
for i in range(3):
    txhash, nonce = send_underpriced()
    track.add((nonce, txhash))
tracker.track(txs=track)

tracker.start()
reactor.run()
