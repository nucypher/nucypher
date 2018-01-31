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
        'Escrow', deploy_args=[token.address, 1, 4 * 2 * 10 ** 7, 4, 4, 2],
        deploy_transaction={'from': creator})
    return escrow


# TODO extract method
def wait_time(chain, wait_hours):
    web3 = chain.web3
    step = 50
    end_timestamp = web3.eth.getBlock(web3.eth.blockNumber).timestamp + wait_hours * 60 * 60
    while web3.eth.getBlock(web3.eth.blockNumber).timestamp < end_timestamp:
        chain.wait.for_block(web3.eth.blockNumber + step)


def test_escrow(web3, chain, token, escrow):
    creator = web3.eth.accounts[0]
    ursula = web3.eth.accounts[1]
    alice = web3.eth.accounts[2]

    # Give Ursula and Alice some coins
    tx = token.transact({'from': creator}).transfer(ursula, 10000)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(alice, 10000)
    chain.wait.for_receipt(tx)
    assert 10000 == token.call().balanceOf(ursula)
    assert 10000 == token.call().balanceOf(alice)

    # Ursula and Alice give Escrow rights to transfer
    tx = token.transact({'from': ursula}).approve(escrow.address, 2500)
    chain.wait.for_receipt(tx)
    assert 2500 == token.call().allowance(ursula, escrow.address)
    tx = token.transact({'from': alice}).approve(escrow.address, 1100)
    chain.wait.for_receipt(tx)
    assert 1100 == token.call().allowance(alice, escrow.address)

    # Ursula's withdrawal attempt won't succeed because nothing to withdraw
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).withdraw(100)
        chain.wait.for_receipt(tx)

    # And can't lock because nothing to lock
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).lock(500, 2)
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
    tx = escrow.transact({'from': ursula}).deposit(1000, 1)
    chain.wait.for_receipt(tx)
    assert 1000 == token.call().balanceOf(escrow.address)
    assert 9000 == token.call().balanceOf(ursula)
    assert 1000 == escrow.call().getLockedTokens(ursula)
    assert 1000 == escrow.call().calculateLockedTokens(ursula, 1)
    assert 1000 == escrow.call().calculateLockedTokens(ursula, 2)
    tx = escrow.transact({'from': ursula}).switchLock()
    chain.wait.for_receipt(tx)
    assert 500 == escrow.call().calculateLockedTokens(ursula, 2)
    tx = escrow.transact({'from': ursula}).switchLock()
    chain.wait.for_receipt(tx)
    assert 1000 == escrow.call().calculateLockedTokens(ursula, 2)
    tx = escrow.transact({'from': alice}).deposit(500, 2)
    chain.wait.for_receipt(tx)
    assert 1500 == token.call().balanceOf(escrow.address)
    assert 9500 == token.call().balanceOf(alice)
    assert 500 == escrow.call().getLockedTokens(alice)
    assert 500 == escrow.call().calculateLockedTokens(alice, 1)

    # Checks locked tokens in next period
    wait_time(chain, 1)
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
    tx = escrow.transact({'from': ursula}).confirmActivity()
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': ursula}).deposit(500, 0)
    chain.wait.for_receipt(tx)
    assert 2000 == token.call().balanceOf(escrow.address)
    assert 8500 == token.call().balanceOf(ursula)

    # Ursula starts unlocking
    tx = escrow.transact({'from': ursula}).switchLock()
    chain.wait.for_receipt(tx)
    assert 750 == escrow.call().calculateLockedTokens(ursula, 2)

    # Wait 1 period and checks locking
    wait_time(chain, 1)
    assert 1500 == escrow.call().getLockedTokens(ursula)

    # Confirm activity and wait 1 period
    tx = escrow.transact({'from': ursula}).confirmActivity()
    chain.wait.for_receipt(tx)
    wait_time(chain, 1)
    assert 750 == escrow.call().getLockedTokens(ursula)
    assert 0 == escrow.call().calculateLockedTokens(ursula, 1)

    # And Ursula can withdraw some tokens
    tx = escrow.transact({'from': ursula}).withdraw(100)
    chain.wait.for_receipt(tx)
    assert 1900 == token.call().balanceOf(escrow.address)
    assert 8600 == token.call().balanceOf(ursula)

    # But Ursula can't withdraw all without mining for locked value
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).withdrawAll()
        chain.wait.for_receipt(tx)

    # Ursula can deposit and lock more tokens
    tx = escrow.transact({'from': ursula}).deposit(500, 0)
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': ursula}).lock(100, 0)
    chain.wait.for_receipt(tx)

    # Locked tokens will be updated in next period
    # Release rate will be updated too because of end of previous locking
    assert 750 == escrow.call().getLockedTokens(ursula)
    assert 600 == escrow.call().calculateLockedTokens(ursula, 1)
    assert 600 == escrow.call().calculateLockedTokens(ursula, 2)
    tx = escrow.transact({'from': ursula}).switchLock()
    chain.wait.for_receipt(tx)
    assert 300 == escrow.call().calculateLockedTokens(ursula, 2)
    assert 0 == escrow.call().calculateLockedTokens(ursula, 3)
    wait_time(chain, 1)
    assert 600 == escrow.call().getLockedTokens(ursula)
    assert 300 == escrow.call().calculateLockedTokens(ursula, 1)
    assert 0 == escrow.call().calculateLockedTokens(ursula, 2)

    # Ursula can increase lock
    tx = escrow.transact({'from': ursula}).lock(500, 2)
    chain.wait.for_receipt(tx)
    assert 600 == escrow.call().getLockedTokens(ursula)
    assert 800 == escrow.call().calculateLockedTokens(ursula, 1)
    assert 500 == escrow.call().calculateLockedTokens(ursula, 2)
    assert 200 == escrow.call().calculateLockedTokens(ursula, 3)
    assert 0 == escrow.call().calculateLockedTokens(ursula, 4)
    wait_time(chain, 1)
    assert 800 == escrow.call().getLockedTokens(ursula)

    # Alice can't deposit too low value (less then rate)
    # TODO uncomment after completing logic
    # with pytest.raises(TransactionFailed):
    #     tx = escrow.transact({'from': ursula}).deposit(100, 100)
    #     chain.wait.for_receipt(tx)

    # Alice starts unlocking and increases lock by deposit more tokens
    tx = escrow.transact({'from': alice}).deposit(500, 0)
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': alice}).switchLock()
    chain.wait.for_receipt(tx)
    assert 500 == escrow.call().getLockedTokens(alice)
    assert 1000 == escrow.call().calculateLockedTokens(alice, 1)
    assert 500 == escrow.call().calculateLockedTokens(alice, 2)
    assert 0 == escrow.call().calculateLockedTokens(alice, 3)
    wait_time(chain, 1)
    assert 1000 == escrow.call().getLockedTokens(alice)

    # And increases locked time
    tx = escrow.transact({'from': alice}).lock(0, 2)
    chain.wait.for_receipt(tx)
    assert 1000 == escrow.call().getLockedTokens(alice)
    assert 500 == escrow.call().calculateLockedTokens(alice, 1)
    assert 0 == escrow.call().calculateLockedTokens(alice, 2)

    # Alice increases lock by small amount of tokens
    tx = escrow.transact({'from': alice}).deposit(100, 0)
    chain.wait.for_receipt(tx)
    assert 600 == escrow.call().calculateLockedTokens(alice, 1)
    assert 100 == escrow.call().calculateLockedTokens(alice, 2)
    assert 0 == escrow.call().calculateLockedTokens(alice, 3)

    # # Ursula can't destroy contract
    # with pytest.raises(TransactionFailed):
    #     tx = escrow.transact({'from': ursula}).destroy()
    #     chain.wait.for_receipt(tx)
    #
    # # Destroy contract from creator and refund all to Ursula and Alice
    # tx = escrow.transact({'from': creator}).destroy()
    # chain.wait.for_receipt(tx)
    # assert 0 == token.call().balanceOf(escrow.address)
    # assert 10000 == token.call().balanceOf(ursula)
    # assert 10000 == token.call().balanceOf(alice)


def test_locked_distribution(web3, chain, token, escrow):
    NULL_ADDR = '0x' + '0' * 40
    creator = web3.eth.accounts[0]
    miners = web3.eth.accounts[1:]
    amount = token.call().balanceOf(creator) // 2
    largest_locked = amount

    # Airdrop
    for miner in miners:
        tx = token.transact({'from': creator}).transfer(miner, amount)
        chain.wait.for_receipt(tx)
        amount = amount // 2

    # Lock
    for index, miner in enumerate(miners[::-1]):
        balance = token.call().balanceOf(miner)
        tx = token.transact({'from': miner}).approve(escrow.address, balance)
        chain.wait.for_receipt(tx)
        tx = escrow.transact({'from': miner}).deposit(balance, len(miners) - index + 1)
        chain.wait.for_receipt(tx)

    # Check current period
    address_stop, shift = escrow.call().findCumSum(NULL_ADDR, 1, 1)
    assert NULL_ADDR == address_stop.lower()
    assert 0 == shift

    # Wait next period
    wait_time(chain, 1)
    n_locked = escrow.call().getAllLockedTokens()
    assert n_locked > 0

    # And confirm activity
    for miner in miners:
        tx = escrow.transact({'from': miner}).confirmActivity()
        chain.wait.for_receipt(tx)

    address_stop, shift = escrow.call().findCumSum(NULL_ADDR, n_locked // 3, 1)
    assert miners[0].lower() == address_stop.lower()
    assert n_locked // 3 == shift

    address_stop, shift = escrow.call().findCumSum(NULL_ADDR, largest_locked, 1)
    assert miners[1].lower() == address_stop.lower()
    assert 0 == shift

    address_stop, shift = escrow.call().findCumSum(
        miners[1], largest_locked // 2 + 1, 1)
    assert miners[2].lower() == address_stop.lower()
    assert 1 == shift

    address_stop, shift = escrow.call().findCumSum(NULL_ADDR, 1, 10)
    assert NULL_ADDR != address_stop.lower()
    assert 0 != shift
    address_stop, shift = escrow.call().findCumSum(NULL_ADDR, 1, 11)
    assert NULL_ADDR == address_stop.lower()
    assert 0 == shift

    for index, _ in enumerate(miners[:-1]):
        address_stop, shift = escrow.call().findCumSum(NULL_ADDR, 1, index + 3)
        assert miners[index + 1].lower() == address_stop.lower()
        assert 1 == shift


def test_mining(web3, chain, token, escrow):
    creator = web3.eth.accounts[0]
    ursula = web3.eth.accounts[1]
    alice = web3.eth.accounts[2]

    policy_manager, _ = chain.provider.get_or_deploy_contract(
        'PolicyManagerTest', deploy_args=[token.address, escrow.address],
        deploy_transaction={'from': creator})
    tx = escrow.transact({'from': creator}).setPolicyManager(policy_manager.address)
    chain.wait.for_receipt(tx)

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
    tx = token.transact({'from': ursula}).approve(escrow.address, 2000)
    chain.wait.for_receipt(tx)
    tx = token.transact({'from': alice}).approve(escrow.address, 500)
    chain.wait.for_receipt(tx)

    # Ursula and Alice transfer some tokens to the escrow and lock them
    tx = escrow.transact({'from': ursula}).deposit(1000, 1)
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': alice}).deposit(500, 2)
    chain.wait.for_receipt(tx)

    # Using locked tokens starts from next period
    assert 0 == escrow.call().getAllLockedTokens()

    # Give rights for mining
    tx = token.transact({'from': creator}).addMiner(escrow.address)
    chain.wait.for_receipt(tx)
    assert token.call().isMiner(escrow.address)

    # Ursula can't use method from Miner contract
    with pytest.raises(TypeError):
        tx = escrow.transact({'from': ursula}).mint(ursula, 1, 1, 1, 1, 1)
        chain.wait.for_receipt(tx)

    # Only Ursula confirm next period
    wait_time(chain, 1)
    assert 1500 == escrow.call().getAllLockedTokens()
    tx = escrow.transact({'from': ursula}).confirmActivity()
    chain.wait.for_receipt(tx)

    # Checks that no error
    tx = escrow.transact({'from': ursula}).confirmActivity()
    chain.wait.for_receipt(tx)

    # Ursula and Alice mint tokens for last periods
    wait_time(chain, 1)
    assert 1000 == escrow.call().getAllLockedTokens()
    tx = escrow.transact({'from': ursula}).mint()
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': alice}).mint()
    chain.wait.for_receipt(tx)
    assert 9050 == token.call().balanceOf(ursula)
    assert 9521 == token.call().balanceOf(alice)

    assert 1 == policy_manager.call().getPeriodsLength(ursula)
    assert 1 == policy_manager.call().getPeriodsLength(alice)
    period = escrow.call().getCurrentPeriod() - 1
    assert period == policy_manager.call().getPeriod(ursula, 0)
    assert period == policy_manager.call().getPeriod(alice, 0)

    # Only Ursula confirm activity for next period
    tx = escrow.transact({'from': ursula}).switchLock()
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': ursula}).confirmActivity()
    chain.wait.for_receipt(tx)

    # Ursula can't confirm next period because end of locking
    wait_time(chain, 1)
    assert 500 == escrow.call().getAllLockedTokens()
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula}).confirmActivity()
        chain.wait.for_receipt(tx)

    # But Alice can
    tx = escrow.transact({'from': alice}).confirmActivity()
    chain.wait.for_receipt(tx)

    # Ursula mint tokens for next period
    wait_time(chain, 1)
    assert 500 == escrow.call().getAllLockedTokens()
    tx = escrow.transact({'from': ursula}).mint()
    chain.wait.for_receipt(tx)
    # But Alice can't mining because she did not confirmed activity
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': alice}).mint()
        chain.wait.for_receipt(tx)
    assert 9163 == token.call().balanceOf(ursula)
    assert 9521 == token.call().balanceOf(alice)

    assert 3 == policy_manager.call().getPeriodsLength(ursula)
    assert 1 == policy_manager.call().getPeriodsLength(alice)
    assert period + 1 == policy_manager.call().getPeriod(ursula, 1)
    assert period + 2 == policy_manager.call().getPeriod(ursula, 2)

    # Alice confirm next period and mint tokens
    tx = escrow.transact({'from': alice}).switchLock()
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': alice}).confirmActivity()
    chain.wait.for_receipt(tx)
    wait_time(chain, 2)
    assert 0 == escrow.call().getAllLockedTokens()
    tx = escrow.transact({'from': alice}).mint()
    chain.wait.for_receipt(tx)
    assert 9163 == token.call().balanceOf(ursula)
    assert 9634 == token.call().balanceOf(alice)

    assert 3 == policy_manager.call().getPeriodsLength(ursula)
    assert 3 == policy_manager.call().getPeriodsLength(alice)
    assert period + 3 == policy_manager.call().getPeriod(alice, 1)
    assert period + 4 == policy_manager.call().getPeriod(alice, 2)

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
    tx = escrow.transact({'from': ursula}).switchLock()
    chain.wait.for_receipt(tx)
    assert 500 == escrow.call().getLockedTokens(ursula)
    assert 500 == escrow.call().calculateLockedTokens(ursula, 1)
    assert 375 == escrow.call().calculateLockedTokens(ursula, 2)
    assert 250 == escrow.call().calculateLockedTokens(ursula, 3)
    assert 0 == escrow.call().calculateLockedTokens(ursula, 5)
    # And can increase lock
    tx = escrow.transact({'from': ursula}).lock(100, 0)
    chain.wait.for_receipt(tx)
    assert 600 == escrow.call().getLockedTokens(ursula)
    assert 600 == escrow.call().calculateLockedTokens(ursula, 1)
    assert 450 == escrow.call().calculateLockedTokens(ursula, 2)
    assert 0 == escrow.call().calculateLockedTokens(ursula, 5)
    tx = escrow.transact({'from': ursula}).lock(0, 2)
    chain.wait.for_receipt(tx)
    assert 600 == escrow.call().getLockedTokens(ursula)
    assert 600 == escrow.call().calculateLockedTokens(ursula, 1)
    assert 450 == escrow.call().calculateLockedTokens(ursula, 2)
    assert 0 == escrow.call().calculateLockedTokens(ursula, 5)
    tx = escrow.transact({'from': ursula}).deposit(800, 1)
    chain.wait.for_receipt(tx)
    assert 1400 == escrow.call().getLockedTokens(ursula)
    assert 1400 == escrow.call().calculateLockedTokens(ursula, 1)
    assert 1000 == escrow.call().calculateLockedTokens(ursula, 3)
    assert 400 == escrow.call().calculateLockedTokens(ursula, 6)
    assert 0 == escrow.call().calculateLockedTokens(ursula, 8)

    # Alice can withdraw all
    tx = escrow.transact({'from': alice}).withdrawAll()
    chain.wait.for_receipt(tx)
    assert 10134 == token.call().balanceOf(alice)

    # TODO test max confirmed periods and miners
