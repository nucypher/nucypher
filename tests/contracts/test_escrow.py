import pytest
from ethereum.tester import TransactionFailed


@pytest.fixture()
def token(web3, chain):
    creator = web3.eth.accounts[0]
    # Create an ERC20 token
    token, _ = chain.provider.get_or_deploy_contract(
        'NuCypherKMSToken', deploy_args=[10 ** 9, 2 * 10 ** 9],
        deploy_transaction={'from': creator})
    return token


@pytest.fixture()
def escrow(web3, chain, token):
    creator = web3.eth.accounts[0]
    # Creator deploys the escrow
    escrow, _ = chain.provider.get_or_deploy_contract(
        'Escrow', deploy_args=[token.address, 10 ** 9, 50],
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

    # Check that nothing is locked
    assert 0 == escrow.call().getLockedTokens(ursula)
    assert 0 == escrow.call().getLockedTokens(alice)

    # Ursula can't lock too low value
    # TODO uncomment after completing logic
    # with pytest.raises(TransactionFailed):
    #     tx = escrow.transact({'from': ursula}).deposit(1000, 10)
    #     chain.wait.for_receipt(tx)

    # Ursula and Alice transfer some tokens to the escrow and lock them
    tx = escrow.transact({'from': ursula}).deposit(1000, 2)
    chain.wait.for_receipt(tx)
    assert 1000 == token.call().balanceOf(escrow.address)
    assert 9000 == token.call().balanceOf(ursula)
    assert 1000 == escrow.call().getLockedTokens(ursula)
    tx = escrow.transact({'from': alice}).deposit(500, 6)
    chain.wait.for_receipt(tx)
    assert 500 == escrow.call().getLockedTokens(alice)
    assert 1500 == token.call().balanceOf(escrow.address)
    assert 9500 == token.call().balanceOf(alice)

    # Checks locked tokens in next period
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 1000 == escrow.call().getLockedTokens(ursula)
    assert 500 == escrow.call().getLockedTokens(alice)
    assert 1500 == escrow.call().getAllLockedTokens()

    # Ursula's withdrawal attempt won't succeed
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).withdraw(100)
        chain.wait.for_receipt(tx)
    assert 1500 == token.call().balanceOf(escrow.address)
    assert 9000 == token.call().balanceOf(ursula)

    # Ursula can deposit more tokens
    tx = escrow.transact({'from': alice}).confirmActivity()
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': ursula}).deposit(500, 0)
    chain.wait.for_receipt(tx)
    assert 2000 == token.call().balanceOf(escrow.address)
    assert 8500 == token.call().balanceOf(ursula)

    # Wait 50 blocks and checks locking
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 1500 == escrow.call().getLockedTokens(ursula)

    # Wait 100 blocks
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 0 == escrow.call().getLockedTokens(ursula)

    # And Ursula can withdraw some tokens
    tx = escrow.transact({'from': ursula}).withdraw(100)
    chain.wait.for_receipt(tx)
    assert 1900 == token.call().balanceOf(escrow.address)
    assert 8600 == token.call().balanceOf(ursula)

    # But Ursula can't withdraw all without mining for locked value
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).withdrawAll()
        chain.wait.for_receipt(tx)

    # Ursula can deposit more tokens
    tx = escrow.transact({'from': ursula}).deposit(500, 0)
    chain.wait.for_receipt(tx)
    assert 2400 == token.call().balanceOf(escrow.address)

    # Locked tokens will be updated in next period
    assert 1500 == escrow.call().getLockedTokens(ursula)
    assert 500 == escrow.call().getLockedTokens(ursula, web3.eth.blockNumber + 50)
    assert 0 == escrow.call().getLockedTokens(ursula, web3.eth.blockNumber + 100)
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 500 == escrow.call().getLockedTokens(ursula)

    # And can increase lock
    tx = escrow.transact({'from': ursula}).lock(500, 2)
    chain.wait.for_receipt(tx)
    assert 500 == escrow.call().getLockedTokens(ursula)
    assert 1000 == escrow.call().getLockedTokens(ursula, web3.eth.blockNumber + 50)
    assert 0 == escrow.call().getLockedTokens(ursula, web3.eth.blockNumber + 150)
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 1000 == escrow.call().getLockedTokens(ursula)

    # Alice can't deposit too low value (less then rate)
    # TODO uncomment after completing logic
    # with pytest.raises(TransactionFailed):
    #     tx = escrow.transact({'from': ursula}).deposit(100, 100)
    #     chain.wait.for_receipt(tx)

    # Alice increases lock by deposit more tokens
    tx = escrow.transact({'from': alice}).deposit(500, 0)
    chain.wait.for_receipt(tx)
    assert 500 == escrow.call().getLockedTokens(alice)
    assert 1000 == escrow.call().getLockedTokens(alice, web3.eth.blockNumber + 50)
    assert 0 == escrow.call().getLockedTokens(alice, web3.eth.blockNumber + 100)
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 1000 == escrow.call().getLockedTokens(alice)

    # And increases locked blocks
    tx = escrow.transact({'from': alice}).lock(0, 2)
    chain.wait.for_receipt(tx)
    assert 1000 == escrow.call().getLockedTokens(alice)
    assert 1000 == escrow.call().getLockedTokens(alice, web3.eth.blockNumber + 50)
    # Last period is not release period but can't confirm activity so tokens are not locked
    assert 0 == escrow.call().getLockedTokens(alice, web3.eth.blockNumber + 100)

    # Ursula can't destroy contract
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).destroy()
        chain.wait.for_receipt(tx)

    # Destroy contract from creator and refund all to Ursula and Alice
    tx = escrow.transact({'from': creator}).destroy()
    chain.wait.for_receipt(tx)
    assert 0 == token.call().balanceOf(escrow.address)
    assert 10000 == token.call().balanceOf(ursula)
    assert 10000 == token.call().balanceOf(alice)


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
        tx = escrow.transact({'from': addr}).deposit(balance, 100)
        chain.wait.for_receipt(tx)

    # Wait next period
    chain.wait.for_block(web3.eth.blockNumber + 50)
    n_locked = escrow.call().getAllLockedTokens()
    assert n_locked > 0

    address_stop, shift = escrow.call().findCumSum(NULL_ADDR, n_locked // 3)
    assert address_stop.lower() == web3.eth.accounts[1].lower()
    assert shift == n_locked // 3

    address_stop, shift = escrow.call().findCumSum(NULL_ADDR, largest_locked)
    assert address_stop.lower() == web3.eth.accounts[2].lower()
    assert shift == 0

    address_stop, shift = escrow.call().findCumSum(
            web3.eth.accounts[2], largest_locked // 2 + 1)
    assert address_stop.lower() == web3.eth.accounts[3].lower()
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

    # Ursula can't confirm and mint because no locked tokens
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).mint()
        chain.wait.for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).confirmActivity()
        chain.wait.for_receipt(tx)

    # Ursula and Alice give Escrow rights to transfer
    tx = token.transact({'from': ursula}).approve(escrow.address, 1000)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': alice}).approve(escrow.address, 500)
    chain.wait.for_receipt(tx)

    # Ursula and Alice transfer some tokens to the escrow and lock them
    tx = escrow.transact({'from': ursula}).deposit(1000, 2)
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': alice}).deposit(500, 4)
    chain.wait.for_receipt(tx)

    # Using locked tokens starts from next period
    assert 0 == escrow.call().getAllLockedTokens()

    # Give rights for mining
    tx = token.transact({'from': creator}).addMiner(escrow.address)
    chain.wait.for_receipt(tx)
    assert token.call().isMiner(escrow.address)

    # Ursula can't use method from Miner contract
    with pytest.raises(TypeError):
        tx = escrow.transact({'from': ursula}).mint(ursula, 1000, 1000, 1000, 1000)
        chain.wait.for_receipt(tx)

    # Only Ursula confirm next period
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 1500 == escrow.call().getAllLockedTokens()
    tx = escrow.transact({'from': ursula}).confirmActivity()
    chain.wait.for_receipt(tx)

    # Checks that no error
    tx = escrow.transact({'from': ursula}).confirmActivity()
    chain.wait.for_receipt(tx)

    # Ursula can't confirm next period because end of locking
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 1000 == escrow.call().getAllLockedTokens()
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).confirmActivity()
        chain.wait.for_receipt(tx)

    # But Alice can
    tx = escrow.transact({'from': alice}).confirmActivity()
    chain.wait.for_receipt(tx)

    # Ursula and Alice mint tokens for last period
    tx = escrow.transact({'from': ursula}).mint()
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': alice}).mint()
    chain.wait.for_receipt(tx)
    assert 9033 == token.call().balanceOf(ursula)
    assert 9517 == token.call().balanceOf(alice)

    # Ursula mint tokens for next period
    chain.wait.for_block(web3.eth.blockNumber + 50)
    assert 500 == escrow.call().getAllLockedTokens()
    tx = escrow.transact({'from': ursula}).mint()
    chain.wait.for_receipt(tx)
    # But Alice can't mining because she did not confirmed activity
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': alice}).mint()
        chain.wait.for_receipt(tx)
    assert 9083 == token.call().balanceOf(ursula)
    assert 9517 == token.call().balanceOf(alice)

    # Alice confirm 2 periods and mint tokens
    tx = escrow.transact({'from': alice}).confirmActivity()
    chain.wait.for_receipt(tx)
    chain.wait.for_block(web3.eth.blockNumber + 100)
    assert 0 == escrow.call().getAllLockedTokens()
    tx = escrow.transact({'from': alice}).mint()
    chain.wait.for_receipt(tx)
    assert 9083 == token.call().balanceOf(ursula)
    assert 9617 == token.call().balanceOf(alice)

    # Ursula can't confirm and mint because no locked tokens
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).mint()
        chain.wait.for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).confirmActivity()
        chain.wait.for_receipt(tx)

    # Ursula can lock some tokens again
    tx = escrow.transact({'from': ursula}).lock(500, 4)
    chain.wait.for_receipt(tx)
    assert escrow.call().getLockedTokens(ursula) == 500
    assert escrow.call().getLockedTokens(ursula, web3.eth.blockNumber + 100) == 500
    assert escrow.call().getLockedTokens(ursula, web3.eth.blockNumber + 200) == 0
    # And can increase lock
    tx = escrow.transact({'from': ursula}).lock(100, 0)
    chain.wait.for_receipt(tx)
    assert escrow.call().getLockedTokens(ursula) == 600
    assert escrow.call().getLockedTokens(ursula, web3.eth.blockNumber + 100) == 600
    assert escrow.call().getLockedTokens(ursula, web3.eth.blockNumber + 200) == 0
    tx = escrow.transact({'from': ursula}).lock(0, 2)
    chain.wait.for_receipt(tx)
    assert escrow.call().getLockedTokens(ursula) == 600
    assert escrow.call().getLockedTokens(ursula, web3.eth.blockNumber + 200) == 600
    assert escrow.call().getLockedTokens(ursula, web3.eth.blockNumber + 300) == 0
    tx = escrow.transact({'from': ursula}).lock(100, 2)
    chain.wait.for_receipt(tx)
    assert escrow.call().getLockedTokens(ursula) == 700
    assert escrow.call().getLockedTokens(ursula, web3.eth.blockNumber + 300) == 700
    assert escrow.call().getLockedTokens(ursula, web3.eth.blockNumber + 400) == 0

    # Alice can withdraw all
    tx = escrow.transact({'from': alice}).withdrawAll()
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(alice) == 10117

    # TODO test max confirmed periods
