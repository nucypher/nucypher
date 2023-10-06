import pytest

from tests.constants import (
    DEVELOPMENT_ETH_AIRDROP_AMOUNT,
    NUMBER_OF_ETH_TEST_ACCOUNTS,
    NUMBER_OF_STAKING_PROVIDERS_IN_BLOCKCHAIN_TESTS,
    NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS,
)

# Prevents TesterBlockchain to be picked up by py.test as a test class
from tests.utils.blockchain import TesterBlockchain as _TesterBlockchain


@pytest.fixture()
def another_testerchain():
    testerchain = _TesterBlockchain(eth_airdrop=True, light=True)
    testerchain.deployer_address = testerchain.etherbase_account
    assert testerchain.is_light
    yield testerchain


def test_testerchain_creation(testerchain, another_testerchain):

    chains = (testerchain, another_testerchain)

    for chain in chains:

        # Ensure we are testing on the correct network...
        assert "tester" in chain.endpoint

        # ... and that there are already some blocks mined
        chain.w3.eth.w3.testing.mine(1)
        assert chain.w3.eth.block_number > 0

        # Check that we have enough test accounts
        assert len(chain.client.accounts) >= NUMBER_OF_ETH_TEST_ACCOUNTS

        # Check that distinguished accounts are assigned
        etherbase = chain.etherbase_account
        assert etherbase == chain.client.accounts[0]

        alice = chain.alice_account
        assert alice == chain.client.accounts[1]

        bob = chain.bob_account
        assert bob == chain.client.accounts[2]

        stakers = [chain.stake_provider_account(i) for i in range(NUMBER_OF_STAKING_PROVIDERS_IN_BLOCKCHAIN_TESTS)]
        assert stakers == chain.stake_providers_accounts

        ursulas = [chain.ursula_account(i) for i in range(NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS)]
        assert ursulas == chain.ursulas_accounts

        # Check that the remaining accounts are different from the previous ones:
        assert set([etherbase, alice, bob] + ursulas + stakers).isdisjoint(set(chain.unassigned_accounts))

        # Check that accounts are funded
        for account in chain.client.accounts:
            assert chain.client.get_balance(account) >= DEVELOPMENT_ETH_AIRDROP_AMOUNT

        # Check that accounts can send transactions
        for account in chain.client.accounts:
            balance = chain.client.get_balance(account)
            assert balance

            tx = {'to': etherbase, 'from': account, 'value': 100}
            txhash = chain.client.send_transaction(tx)
            _receipt = chain.wait_for_receipt(txhash)
