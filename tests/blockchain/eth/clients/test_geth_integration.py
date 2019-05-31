import os

import pytest

from nucypher.blockchain.eth.chains import Blockchain
from nucypher.crypto.api import verify_eip_191

#
# NOTE: This module is skipped on CI
#

# TODO: # 1037 This marker is not working.
@pytest.mark.skipif(os.environ.get('CIRCLECI'), reason='Do not run geth nodes on CircleCI')
def test_geth_EIP_191_client_signature_integration(geth_dev_node):

    # Start a geth process
    blockchain = Blockchain.connect(provider_process=geth_dev_node, sync=False)

    # Sign a message (RPC) and verify it.
    etherbase = blockchain.interface.accounts[0]
    stamp = b'STAMP-' + os.urandom(64)
    signature = blockchain.interface.client.sign_message(account=etherbase, message=stamp)
    is_valid = verify_eip_191(address=etherbase,
                              signature=signature,
                              message=stamp)
    assert is_valid
