
def test_testerchain_create(testerchain):
    with testerchain as chain:
        assert chain.web3.eth.blockNumber >= 0
