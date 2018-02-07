
def test_testerchain_create(testerchain):
    assert testerchain.chain.web3.eth.blockNumber >= 0
