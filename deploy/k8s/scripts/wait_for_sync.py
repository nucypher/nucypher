import os
import sys
import time
import datetime
from web3 import Web3, IPCProvider
from web3.middleware import geth_poa_middleware

ROOT_DIR = os.getenv('ROOT_DIR')

w3 = Web3(IPCProvider(os.path.join(ROOT_DIR, 'geth/geth.ipc')))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)


def has_latest_block():
    # if we are not syncing, check that our local chain data is up to date
    return (
        datetime.datetime.now() -
        datetime.datetime.fromtimestamp(
            w3.eth.getBlock(w3.eth.blockNumber)['timestamp']
        )
    ).seconds < 30


while not has_latest_block():
    if w3.eth.syncing:
        sys.stdout.write(
            "\n{}/{}".format(
                w3.eth.syncing['highestBlock'],
                w3.eth.syncing['currentBlock']
            )
        )
    else:
        sys.stdout.write("\nsyncing...\n")
    time.sleep(5)
    sys.stdout.flush()