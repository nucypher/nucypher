import os

import pytest

from nucypher.blockchain.eth.interfaces import Blockchain
from nucypher.crypto.api import verify_eip_191


#
# NOTE: This module is skipped on CI
#

def test_geth_EIP_191_client_signature_integration(geth_dev_node):
    if 'CIRCLECI' in os.environ:
        pytest.skip("Do not run Geth nodes in CI")

    # Start a geth process
    blockchain = Blockchain(provider_process=geth_dev_node, sync_now=False)

    # Sign a message (RPC) and verify it.
    etherbase = blockchain.accounts[0]
    stamp = b'STAMP-' + os.urandom(64)
    signature = blockchain.client.sign_message(account=etherbase, message=stamp)
    is_valid = verify_eip_191(address=etherbase,
                              signature=signature,
                              message=stamp)
    assert is_valid
