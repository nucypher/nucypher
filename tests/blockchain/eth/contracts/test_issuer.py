import pytest
from web3.contract import Contract
from eth_tester.exceptions import TransactionFailed


@pytest.fixture()
def token(web3, chain):
    creator = web3.eth.accounts[0]
    # Create an ERC20 token
    token, _ = chain.provider.deploy_contract('NuCypherKMSToken', 2 * 10 ** 40)
    return token


def test_issuer(web3, chain, token):
    creator = web3.eth.accounts[0]
    ursula = web3.eth.accounts[1]

    # Creator deploys the issuer
    issuer, _ = chain.provider.get_or_deploy_contract(
        'IssuerMock', token.address, 1, 10 ** 46, int(1e7), int(1e7)
    )

    # Give Miner tokens for reward and initialize contract
    reserved_reward = 2 * 10 ** 40 - 10 ** 30
    tx = token.transact({'from': creator}).transfer(issuer.address, reserved_reward)
    chain.wait_for_receipt(tx)

    events = issuer.eventFilter('Initialized')
    tx = issuer.transact().initialize()
    chain.wait_for_receipt(tx)
    events = events.get_all_entries()

    assert 1 == len(events)
    assert reserved_reward == events[0]['args']['reservedReward']
    balance = token.call().balanceOf(issuer.address)

    # Can't initialize second time
    with pytest.raises(TransactionFailed):
        tx = issuer.transact().initialize()
        chain.wait_for_receipt(tx)

    # Mint some tokens
    tx = issuer.transact({'from': ursula}).testMint(0, 1000, 2000, 0, 0)
    chain.wait_for_receipt(tx)
    assert 10 == token.call().balanceOf(ursula)
    assert balance - 10 == token.call().balanceOf(issuer.address)

    # Mint more tokens
    tx = issuer.transact({'from': ursula}).testMint(0, 500, 500, 0, 0)
    chain.wait_for_receipt(tx)
    assert 30 == token.call().balanceOf(ursula)
    assert balance - 30 == token.call().balanceOf(issuer.address)

    tx = issuer.transact({'from': ursula}).testMint(0, 500, 500, 10 ** 7, 0)
    chain.wait_for_receipt(tx)
    assert 70 == token.call().balanceOf(ursula)
    assert balance - 70 == token.call().balanceOf(issuer.address)

    tx = issuer.transact({'from': ursula}).testMint(0, 500, 500, 2 * 10 ** 7, 0)
    chain.wait_for_receipt(tx)
    assert 110 == token.call().balanceOf(ursula)
    assert balance - 110 == token.call().balanceOf(issuer.address)


def test_inflation_rate(web3, chain, token):
    creator = web3.eth.accounts[0]
    ursula = web3.eth.accounts[1]

    # Creator deploys the miner
    issuer, _ = chain.provider.deploy_contract(
        'IssuerMock', token.address, 1, 2 * 10 ** 19, 1, 1
    )

    # Give Miner tokens for reward and initialize contract
    tx = token.transact({'from': creator}).transfer(issuer.address, 2 * 10 ** 40 - 10 ** 30)
    chain.wait_for_receipt(tx)
    tx = issuer.transact().initialize()
    chain.wait_for_receipt(tx)

    # Mint some tokens
    period = issuer.call().getCurrentPeriod()
    tx = issuer.transact({'from': ursula}).testMint(period + 1, 1, 1, 0, 0)
    chain.wait_for_receipt(tx)
    one_period = token.call().balanceOf(ursula)

    # Mint more tokens in the same period
    tx = issuer.transact({'from': ursula}).testMint(period + 1, 1, 1, 0, 0)
    chain.wait_for_receipt(tx)
    assert 2 * one_period == token.call().balanceOf(ursula)

    # Mint tokens in the next period
    tx = issuer.transact({'from': ursula}).testMint(period + 2, 1, 1, 0, 0)
    chain.wait_for_receipt(tx)
    assert 3 * one_period > token.call().balanceOf(ursula)
    minted_amount = token.call().balanceOf(ursula) - 2 * one_period

    # Mint tokens in the next period
    tx = issuer.transact({'from': ursula}).testMint(period + 1, 1, 1, 0, 0)
    chain.wait_for_receipt(tx)
    assert 2 * one_period + 2 * minted_amount == token.call().balanceOf(ursula)

    # Mint tokens in the next period
    tx = issuer.transact({'from': ursula}).testMint(period + 3, 1, 1, 0, 0)
    chain.wait_for_receipt(tx)
    assert 2 * one_period + 3 * minted_amount > token.call().balanceOf(ursula)


def test_verifying_state(web3, chain, token):
    creator = web3.eth.accounts[0]

    # Deploy contract
    contract_library_v1, _ = chain.provider.get_or_deploy_contract(
        'Issuer', token.address, 1, 1, 1, 1
    )
    dispatcher, _ = chain.provider.deploy_contract('Dispatcher', contract_library_v1.address)

    # Deploy second version of the contract
    contract_library_v2, _ = chain.provider.deploy_contract('IssuerV2Mock', token.address, 2, 2, 2, 2)
    contract = web3.eth.contract(
        abi=contract_library_v2.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    # Give Miner tokens for reward and initialize contract
    tx = token.transact({'from': creator}).transfer(contract.address, 10000)
    chain.wait_for_receipt(tx)
    tx = contract.transact().initialize()
    chain.wait_for_receipt(tx)

    # Upgrade to the second version
    assert 1 == contract.call().miningCoefficient()
    tx = dispatcher.transact({'from': creator}).upgrade(contract_library_v2.address)
    chain.wait_for_receipt(tx)
    assert contract_library_v2.address.lower() == dispatcher.call().target().lower()
    assert 2 == contract.call().miningCoefficient()
    assert 2 * 3600 == contract.call().secondsPerPeriod()
    assert 2 == contract.call().lockedPeriodsCoefficient()
    assert 2 == contract.call().awardedPeriods()
    tx = contract.transact({'from': creator}).setValueToCheck(3)
    chain.wait_for_receipt(tx)
    assert 3 == contract.call().valueToCheck()

    # Can't upgrade to the previous version or to the bad version
    contract_library_bad, _ = chain.provider.deploy_contract('IssuerBad', token.address, 2, 2, 2, 2)
    with pytest.raises(TransactionFailed):
        tx = dispatcher.transact({'from': creator}).upgrade(contract_library_v1.address)
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = dispatcher.transact({'from': creator}).upgrade(contract_library_bad.address)
        chain.wait_for_receipt(tx)

    # But can rollback
    tx = dispatcher.transact({'from': creator}).rollback()
    chain.wait_for_receipt(tx)
    assert contract_library_v1.address.lower() == dispatcher.call().target().lower()
    assert 1 == contract.call().miningCoefficient()
    assert 3600 == contract.call().secondsPerPeriod()
    assert 1 == contract.call().lockedPeriodsCoefficient()
    assert 1 == contract.call().awardedPeriods()
    with pytest.raises(TransactionFailed):
        tx = contract.transact({'from': creator}).setValueToCheck(2)
        chain.wait_for_receipt(tx)

    # Try to upgrade to the bad version
    with pytest.raises(TransactionFailed):
        tx = dispatcher.transact({'from': creator}).upgrade(contract_library_bad.address)
        chain.wait_for_receipt(tx)
