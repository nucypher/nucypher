from nkms_eth import blockchain


def test_chain(chain):
    assert blockchain.DEFAULT_NETWORK == 'tester'
    web3 = blockchain.web3()
    assert web3.eth.blockNumber >= 0
