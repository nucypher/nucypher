from twisted.internet import reactor
from web3.types import TxParams

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.domains import LYNX
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.blockchain.eth.signers import InMemorySigner
from nucypher.blockchain.eth.trackers.transactions import TransactionTracker
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

tracker = TransactionTracker(
    w3=coordinator_agent.blockchain.w3,
)
tracker.start()

txs = []
for i in range(3):
    nonce = w3.eth.get_transaction_count(address, 'pending')
    base_fee = w3.eth.get_block("latest")["baseFeePerGas"]
    tip = w3.eth.max_priority_fee
    tx = TxParams({
        'nonce': nonce + i,
        'to': address,
        'value': 0,
        'gas': 21000,
        'maxPriorityFeePerGas': tip,
        'maxFeePerGas': base_fee + tip,
        'chainId': 80001,
        'type': '0x2',
        'from': address
    })
    future_tx = tracker.queue_transaction(
        tx=tx,
        signer=transacting_power.sign_transaction,
        info={"message": f"This is transaction {i}"},
    )
    txs.append(future_tx)

reactor.run()
