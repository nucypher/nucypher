import pytest

from nucypher.blockchain.eth.clients import EthereumClient
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower
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
    testerchain = _TesterBlockchain(eth_airdrop=True, free_transactions=True, light=True)
    testerchain.deployer_address = testerchain.etherbase_account
    assert testerchain.is_light
    yield testerchain


def test_testerchain_creation(testerchain, another_testerchain):

    chains = (testerchain, another_testerchain)

    for chain in chains:

        # Ensure we are testing on the correct network...
        assert 'tester' in chain.eth_provider_uri

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


# TODO: Move to integrations tests
@pytest.mark.skip("This test need to be refactored to use some other transaction")
def test_block_confirmations(testerchain, test_registry, mocker):
    origin = testerchain.etherbase_account
    transacting_power = TransactingPower(account=origin, signer=Web3Signer(testerchain.client))

    # Mocks and test adjustments
    testerchain.TIMEOUT = 5  # Reduce timeout for tests, for the moment
    mocker.patch.object(testerchain.client, '_calculate_confirmations_timeout', return_value=1)
    EthereumClient.BLOCK_CONFIRMATIONS_POLLING_TIME = 0.1
    EthereumClient.COOLING_TIME = 0

    # Let's try to deploy a simple contract (ReceiveApprovalMethodMock) with 1 confirmation.
    # Since the testerchain doesn't mine new blocks automatically, this fails.
    with pytest.raises(EthereumClient.TransactionTimeout):
        _ = testerchain.deploy_contract(transacting_power=transacting_power,
                                        registry=test_registry,
                                        contract_name='ReceiveApprovalMethodMock',
                                        confirmations=1)

    # Trying again with no confirmation succeeds.
    contract, _ = testerchain.deploy_contract(transacting_power=transacting_power,
                                              registry=test_registry,
                                              contract_name='ReceiveApprovalMethodMock')

    # Trying a simple function of the contract with 1 confirmations fails too, for the same reason
    tx_function = contract.functions.receiveApproval(origin, 0, origin, b'')
    with pytest.raises(EthereumClient.TransactionTimeout):
        _ = testerchain.send_transaction(contract_function=tx_function,
                                         transacting_power=transacting_power,
                                         confirmations=1)

    # Trying again with no confirmation succeeds.
    receipt = testerchain.send_transaction(contract_function=tx_function,
                                           transacting_power=transacting_power,
                                           confirmations=0)
    assert receipt['status'] == 1
