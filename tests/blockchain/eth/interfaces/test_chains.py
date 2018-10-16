def test_testerchain_creation(testerchain):
    # Ensure we are testing on the correct network...
    assert 'tester' in testerchain.interface.provider_uri

    # ... and that there are already some blocks mined
    assert testerchain.interface.w3.eth.blockNumber >= 0


