import time

from eth_utils import encode_hex
from twisted.internet import reactor

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
    transacting_power=transacting_power,
)
tracker.start()
reactor.run()
