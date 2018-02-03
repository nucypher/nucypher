
def test_chain_network(testerchain):
    with testerchain as blockchain:
        assert blockchain.web3.eth.blockNumber >= 0
