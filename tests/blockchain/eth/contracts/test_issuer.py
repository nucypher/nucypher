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
    issuer, _ = chain.provider.deploy_contract(
        'IssuerMock', token.address, 1, 10 ** 46, int(1e7), int(1e7)
    )

    events = issuer.events.Initialized.createFilter(fromBlock='latest')

    # Give Miner tokens for reward and initialize contract
    reserved_reward = 2 * 10 ** 40 - 10 ** 30
    tx =  token.functions.transfer(issuer.address, reserved_reward).transact({'from': creator})
    chain.wait_for_receipt(tx)

    tx = issuer.functions.initialize().transact({'from': creator})
    chain.wait_for_receipt(tx)
    events = events.get_all_entries()

    assert 1 == len(events)
    assert reserved_reward == events[0]['args']['reservedReward']
    balance = token.functions.balanceOf(issuer.address).call()

    # Can't initialize second time
    with pytest.raises((TransactionFailed, ValueError)):
        tx = issuer.functions.initialize().transact({'from': creator})
        chain.wait_for_receipt(tx)

    # Mint some tokens
    tx =  issuer.functions.testMint(0, 1000, 2000, 0, 0).transact({'from': ursula})
    chain.wait_for_receipt(tx)
    assert 10 == token.functions.balanceOf(ursula).call()
    assert balance - 10 == token.functions.balanceOf(issuer.address).call()

    # Mint more tokens
    tx =  issuer.functions.testMint(0, 500, 500, 0, 0).transact({'from': ursula})
    chain.wait_for_receipt(tx)
    assert 30 == token.functions.balanceOf(ursula).call()
    assert balance - 30 == token.functions.balanceOf(issuer.address).call()

    tx =  issuer.functions.testMint(0, 500, 500, 10 ** 7, 0).transact({'from': ursula})
    chain.wait_for_receipt(tx)
    assert 70 == token.functions.balanceOf(ursula).call()
    assert balance - 70 == token.functions.balanceOf(issuer.address).call()

    tx =  issuer.functions.testMint(0, 500, 500, 2 * 10 ** 7, 0).transact({'from': ursula})
    chain.wait_for_receipt(tx)
    assert 110 == token.functions.balanceOf(ursula).call()
    assert balance - 110 == token.functions.balanceOf(issuer.address).call()


def test_inflation_rate(web3, chain, token):
    creator = web3.eth.accounts[0]
    ursula = web3.eth.accounts[1]

    # Creator deploys the miner
    issuer, _ = chain.provider.deploy_contract(
        'IssuerMock', token.address, 1, 2 * 10 ** 19, 1, 1
    )

    # Give Miner tokens for reward and initialize contract
    tx =  token.functions.transfer(issuer.address, 2 * 10 ** 40 - 10 ** 30).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = issuer.functions.initialize().transact({'from': creator})
    chain.wait_for_receipt(tx)

    # Mint some tokens
    period = issuer.functions.getCurrentPeriod().call()
    tx =  issuer.functions.testMint(period + 1, 1, 1, 0, 0).transact({'from': ursula})
    chain.wait_for_receipt(tx)
    one_period = token.functions.balanceOf(ursula).call()

    # Mint more tokens in the same period
    tx =  issuer.functions.testMint(period + 1, 1, 1, 0, 0).transact({'from': ursula})
    chain.wait_for_receipt(tx)
    assert 2 * one_period == token.functions.balanceOf(ursula).call()

    # Mint tokens in the next period
    tx =  issuer.functions.testMint(period + 2, 1, 1, 0, 0).transact({'from': ursula})
    chain.wait_for_receipt(tx)
    assert 3 * one_period > token.functions.balanceOf(ursula).call()
    minted_amount = token.functions.balanceOf(ursula).call() - 2 * one_period

    # Mint tokens in the next period
    tx =  issuer.functions.testMint(period + 1, 1, 1, 0, 0).transact({'from': ursula})
    chain.wait_for_receipt(tx)
    assert 2 * one_period + 2 * minted_amount == token.functions.balanceOf(ursula).call()

    # Mint tokens in the next period
    tx =  issuer.functions.testMint(period + 3, 1, 1, 0, 0).transact({'from': ursula})
    chain.wait_for_receipt(tx)
    assert 2 * one_period + 3 * minted_amount > token.functions.balanceOf(ursula).call()


def test_verifying_state(web3, chain, token):
    creator = web3.eth.accounts[0]

    # Deploy contract
    contract_library_v1, _ = chain.provider.deploy_contract(
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
    tx =  token.functions.transfer(contract.address, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = contract.functions.initialize().transact({'from': creator})
    chain.wait_for_receipt(tx)

    # Upgrade to the second version
    assert 1 == contract.functions.miningCoefficient().call()
    tx =  dispatcher.functions.upgrade(contract_library_v2.address).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_library_v2.address == dispatcher.functions.target().call()
    assert 2 == contract.functions.miningCoefficient().call()
    assert 2 * 3600 == contract.functions.secondsPerPeriod().call()
    assert 2 == contract.functions.lockedPeriodsCoefficient().call()
    assert 2 == contract.functions.awardedPeriods().call()
    tx =  contract.functions.setValueToCheck(3).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 3 == contract.functions.valueToCheck().call()

    # Can't upgrade to the previous version or to the bad version
    contract_library_bad, _ = chain.provider.deploy_contract('IssuerBad', token.address, 2, 2, 2, 2)
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  dispatcher.functions.upgrade(contract_library_v1.address).transact({'from': creator})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  dispatcher.functions.upgrade(contract_library_bad.address).transact({'from': creator})
        chain.wait_for_receipt(tx)

    # But can rollback
    tx = dispatcher.functions.rollback().transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_library_v1.address == dispatcher.functions.target().call()
    assert 1 == contract.functions.miningCoefficient().call()
    assert 3600 == contract.functions.secondsPerPeriod().call()
    assert 1 == contract.functions.lockedPeriodsCoefficient().call()
    assert 1 == contract.functions.awardedPeriods().call()
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  contract.functions.setValueToCheck(2).transact({'from': creator})
        chain.wait_for_receipt(tx)

    # Try to upgrade to the bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  dispatcher.functions.upgrade(contract_library_bad.address).transact({'from': creator})
        chain.wait_for_receipt(tx)
