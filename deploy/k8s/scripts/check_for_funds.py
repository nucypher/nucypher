import os
import sys
import time
from nucypher.blockchain.economics import TokenEconomics
from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.chains import Blockchain

ROOT_DIR = os.getenv('ROOT_DIR')
ADDRESS = os.getenv('ACCOUNT_ADDRESS')
POA = os.getenv('NUCYPHER_USE_POA_MIDDLEWARE') is not None

ipc_path = 'file://' + os.path.join(ROOT_DIR, 'geth/geth.ipc')
blockchain = Blockchain.connect(
    provider_uri=ipc_path,
    poa=POA,
)

agent = NucypherTokenAgent(blockchain=blockchain)

while not (
    agent.get_balance(ADDRESS) > int(TokenEconomics.minimum_allowed_locked) and
    agent.get_eth_balance(ADDRESS) > 0.01
):
    sys.stdout.write("\ninsufficient NU/eth balance at {}".format(ADDRESS))
    time.sleep(5)
    sys.stdout.flush()
