import pytest
from ethereum.tester import TransactionFailed


@pytest.fixture()
def token(web3, chain):
    creator = web3.eth.accounts[0]
    # Create an ERC20 token
    token, _ = chain.provider.get_or_deploy_contract(
        'HumanStandardToken', deploy_args=[
            10 ** 9, 2 * 10 ** 9, 'NuCypher KMS', 6, 'KMS'],
        deploy_transaction={'from': creator})
    return token


@pytest.fixture()
def escrow(web3, chain, token):
    creator = web3.eth.accounts[0]
    # Creator deploys the escrow
    escrow, _ = chain.provider.get_or_deploy_contract(
        'Escrow', deploy_args=[token.address, 10 ** 5, 10 ** 7],
        deploy_transaction={'from': creator})
    return escrow


def test_escrow(web3, chain, token, escrow):
    creator = web3.eth.accounts[0]
    ursula = web3.eth.accounts[1]
    alice = web3.eth.accounts[2]

    # Give Ursula and Alice some coins
    tx = token.transact({'from': creator}).transfer(ursula, 10000)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(alice, 10000)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula) == 10000
    assert token.call().balanceOf(alice) == 10000

    # Ursula and Alice give Escrow rights to transfer
    tx = token.transact({'from': ursula}).approve(escrow.address, 2500)
    chain.wait.for_receipt(tx)
    assert token.call().allowance(ursula, escrow.address) == 2500
    tx = token.transact({'from': alice}).approve(escrow.address, 1000)
    chain.wait.for_receipt(tx)
    assert token.call().allowance(alice, escrow.address) == 1000

    # Ursula's withdrawal attempt won't succeed because nothing to withdraw
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).withdraw(100)
        chain.wait.for_receipt(tx)

    # And can't lock because nothing to lock
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).lock(500, 100)
        chain.wait.for_receipt(tx)

    # Ursula and Alice transfer some tokens to the escrow
    tx = escrow.transact({'from': ursula}).deposit(1500)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 1500
    assert token.call().balanceOf(ursula) == 8500
    tx = escrow.transact({'from': alice}).deposit(500)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 2000
    assert token.call().balanceOf(alice) == 9500

    # Ursula asks for refund
    tx = escrow.transact({'from': ursula}).withdraw(500)
    chain.wait.for_receipt(tx)
    # and it works
    assert token.call().balanceOf(escrow.address) == 1500
    assert token.call().balanceOf(ursula) == 9000

    # Check that nothing is locked
    assert escrow.call().getLockedTokens(ursula) == 0
    assert escrow.call().getLockedTokens(alice) == 0
    assert escrow.call().getAllLockedTokens() == 0

    # Ursula and Alice lock some tokens for 100 and 200 blocks
    tx = escrow.transact({'from': ursula}).lock(1000, 100)
    chain.wait.for_receipt(tx)
    assert escrow.call().getLockedTokens(ursula) == 1000
    assert escrow.call().getLockedTokens(alice) == 0
    assert escrow.call().getAllLockedTokens() == 1000
    tx = escrow.transact({'from': alice}).lock(500, 200)
    chain.wait.for_receipt(tx)
    assert escrow.call().getLockedTokens(ursula) == 1000
    assert escrow.call().getLockedTokens(alice) == 500
    assert escrow.call().getAllLockedTokens() == 1500

    # Ursula's withdrawal attempt won't succeed
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).withdraw(100)
        chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 1500
    assert token.call().balanceOf(ursula) == 9000

    # And can't penalize anyone
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).penalize(ursula, 100)
        chain.wait.for_receipt(tx)

    # Creator can't penalize Ursula by burning tokens which exceeded her locked value
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': creator}).penalize(ursula, 1500)
        chain.wait.for_receipt(tx)

    # But can penalize Ursula by burning some locked tokens
    tx = escrow.transact({'from': creator}).penalize(ursula, 100)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 1400
    assert escrow.call().getLockedTokens(ursula) == 900
    assert escrow.call().getAllLockedTokens() == 1400
    assert escrow.call().tokenInfo(ursula)[0] == 900

    # Wait 100 blocks
    chain.wait.for_block(web3.eth.blockNumber + 100)
    assert escrow.call().getLockedTokens(ursula) == 0
    assert escrow.call().getAllLockedTokens() == 500

    # And Ursula can withdraw some tokens
    tx = escrow.transact({'from': ursula}).withdraw(100)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 1300
    assert token.call().balanceOf(ursula) == 9100

    # But Ursula can't withdraw all without mining for locked value
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).withdrawAll()
        chain.wait.for_receipt(tx)
    # assert token.call().balanceOf(escrow.address) == 500
    # assert token.call().balanceOf(ursula) == 10000
    # assert escrow.call().getLockedTokens(ursula) == 0
    # assert escrow.call().getAllLockedTokens() == 100

    # Ursula transfers some tokens to the escrow
    tx = escrow.transact({'from': ursula}).deposit(1000)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 2300
    # But can't lock some of them without mining for already locked value
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).lock(500, 100)
        chain.wait.for_receipt(tx)

    # Ursula can't destroy contract
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).destroy()
        chain.wait.for_receipt(tx)

    # Destroy contract from creator and refund all to Ursula and Alice
    tx = escrow.transact({'from': creator}).destroy()
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(escrow.address) == 0
    assert token.call().balanceOf(ursula) == 9900
    assert token.call().balanceOf(alice) == 10000


def test_locked_distribution(web3, chain, token, escrow):
    NULL_ADDR = '0x' + '0' * 40
    creator = web3.eth.accounts[0]
    amount = token.call().balanceOf(creator) // 2
    largest_locked = amount

    # Airdrop
    for miner in web3.eth.accounts[1:]:
        tx = token.transact({'from': creator}).transfer(miner, amount)
        chain.wait.for_receipt(tx)
        amount = amount // 2

    # Lock
    for addr in web3.eth.accounts[1:][::-1]:
        balance = token.call().balanceOf(addr)
        tx = token.transact({'from': addr}).approve(escrow.address, balance)
        chain.wait.for_receipt(tx)
        tx = escrow.transact({'from': addr}).deposit(balance)
        chain.wait.for_receipt(tx)
        tx = escrow.transact({'from': addr}).lock(balance, 100)
        chain.wait.for_receipt(tx)

    n_locked = escrow.call().getAllLockedTokens()
    assert n_locked > 0

    address_stop, shift = escrow.call().findCumSum(NULL_ADDR, n_locked // 3)
    assert address_stop.lower() == web3.eth.accounts[1]
    assert shift == n_locked // 3

    address_stop, shift = escrow.call().findCumSum(NULL_ADDR, largest_locked)
    assert address_stop.lower() == web3.eth.accounts[2]
    assert shift == 0

    address_stop, shift = escrow.call().findCumSum(
            web3.eth.accounts[2], largest_locked // 2 + 1)
    assert address_stop.lower() == web3.eth.accounts[3]
    assert shift == 1


def test_mining(web3, chain, token, escrow):
    creator = web3.eth.accounts[0]
    ursula = web3.eth.accounts[1]
    alice = web3.eth.accounts[2]

    # Give Ursula and Alice some coins
    tx = token.transact({'from': creator}).transfer(ursula, 10000)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(alice, 10000)
    chain.wait.for_receipt(tx)

    # Ursula can't mint because no locked tokens
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).mint()
        chain.wait.for_receipt(tx)

    # Ursula and Alice give Escrow rights to transfer
    tx = token.transact({'from': ursula}).approve(escrow.address, 1000)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': alice}).approve(escrow.address, 500)
    chain.wait.for_receipt(tx)

    # Ursula and Alice transfer some tokens to the escrow
    tx = escrow.transact({'from': ursula}).deposit(1000)
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': alice}).deposit(500)
    chain.wait.for_receipt(tx)

    # Ursula and Alice lock some tokens for 100 and 200 blocks
    tx = escrow.transact({'from': ursula}).lock(1000, 100)
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': alice}).lock(500, 200)
    chain.wait.for_receipt(tx)

    # Give rights for mining
    tx = token.transact({'from': creator}).addMiner(escrow.address)
    chain.wait.for_receipt(tx)
    assert token.call().isMiner(escrow.address)

    # Wait 150 blocks and mint tokens
    chain.wait.for_block(web3.eth.blockNumber + 150)
    tx = escrow.transact({'from': ursula}).mint()
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': alice}).mint()
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula) == 9099
    assert token.call().balanceOf(alice) == 9500
    assert escrow.call().getAllLockedTokens() == 500

    # Wait 100 blocks and mint tokens
    chain.wait.for_block(web3.eth.blockNumber + 100)
    tx = escrow.transact({'from': alice}).mint()
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula) == 9099
    # Problem with accuracy
    assert token.call().balanceOf(alice) == 9600
    assert escrow.call().getAllLockedTokens() == 0

    # Ursula and Alice can withdraw all
    tx = escrow.transact({'from': ursula}).withdrawAll()
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': alice}).withdrawAll()
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(ursula) == 10099
    assert token.call().balanceOf(alice) == 10100
