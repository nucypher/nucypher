import time

from eth_utils import encode_hex
from twisted.internet import reactor

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.domains import LYNX
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.blockchain.eth.signers import InMemorySigner
from nucypher.blockchain.eth.trackers.dkg import DKGTracker
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.logging import GlobalLoggerSettings
from tests.constants import DEFAULT_TEST_ENRICO_PRIVATE_KEY

LOG_LEVEL = "info"
GlobalLoggerSettings.set_log_level(log_level_name=LOG_LEVEL)
GlobalLoggerSettings.start_console_logging()

signer = InMemorySigner(private_key=DEFAULT_TEST_ENRICO_PRIVATE_KEY)
address = signer.accounts[0]
transacting_power = TransactingPower(signer=signer, account=address)
print(address)

endpoint = "https://polygon-mumbai.infura.io/v3/YOUR-API-KEY"
registry = ContractRegistry.from_latest_publication(
    domain=LYNX,
)
coordinator_agent = CoordinatorAgent(
    blockchain_endpoint=endpoint,
    registry=registry
)

w3 = coordinator_agent.blockchain.w3


def cancel():
    # Get the latest confirmed transaction nonce and the nonce including pending transactions
    latest_nonce = w3.eth.get_transaction_count(address, 'latest')
    pending_nonce = w3.eth.get_transaction_count(address, 'pending')

    # Fetch the current base fee
    base_fee = w3.eth.get_block('latest')['baseFeePerGas']

    for nonce in range(latest_nonce, pending_nonce):
        # Calculate an increased priority fee and max fee for the cancellation transaction
        increased_priority_fee = w3.to_wei(1.5, 'gwei')  # Adjust based on network conditions
        new_max_fee = base_fee + increased_priority_fee

        # Create a cancellation transaction with the same nonce but higher fees
        cancel_tx = {
            'nonce': nonce,
            'to': address,  # Sending to your own address
            'value': 0,
            'gas': 21000,
            'maxPriorityFeePerGas': increased_priority_fee,
            'maxFeePerGas': new_max_fee,
            'chainId': 80001,
            'type': '0x2',  # Indicating EIP-1559 transaction
            'from': address
        }

        # Sign the transaction
        signed_tx = signer.sign_transaction(cancel_tx)

        # Send the transaction
        tx_hash = w3.eth.send_raw_transaction(signed_tx)
        print(f"Cancel transaction sent, tx hash: {encode_hex(tx_hash)}")

        # Wait a bit before sending the next cancellation transaction
        time.sleep(1)

    # After all cancellation transactions are sent
    print("All cancellation transactions sent")


def send_underpriced():
    nonce = w3.eth.get_transaction_count(address, 'pending')
    cancel_tx = {
        'nonce': nonce,
        'to': address,  # Sending to your own address
        'value': 0,
        'gas': 21000,
        'maxPriorityFeePerGas': 1,
        'maxFeePerGas': 1,
        'chainId': 80001,
        'type': '0x2',
        'from': address
    }

    # Sign the transaction
    signed_tx = signer.sign_transaction(cancel_tx)

    # Send the transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx)
    print(f"Underpriced transaction sent, tx hash: {encode_hex(tx_hash)}")
    return tx_hash


cancel()
time.sleep(3)

txhash = send_underpriced()
time.sleep(3)

# pending_nonce = w3.eth.get_transaction_count(address, 'pending')
# latest_nonce = w3.eth.get_transaction_count(address, 'latest')
# print(f'pending nonce: {pending_nonce}')
# print(f'latest nonce: {latest_nonce}')
# print(f'pending nonce - latest nonce: {pending_nonce - latest_nonce}')
# time.sleep(10)

tracker = DKGTracker(
    coordinator_agent=coordinator_agent,
    transacting_power=transacting_power
)
tracker.track(txhash=txhash)
tracker.start()
reactor.run()
