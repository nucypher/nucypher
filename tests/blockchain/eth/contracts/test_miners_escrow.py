import pytest
from eth_tester.exceptions import TransactionFailed
import os
from web3.contract import Contract


MINERS_LENGTH = 0
MINER = 1
VALUE_FIELD = 2
DECIMALS_FIELD = 3
LOCKED_VALUE_FIELD = 4
RELEASE_FIELD = 5
MAX_RELEASE_PERIODS_FIELD = 6
RELEASE_RATE_FIELD = 7
CONFIRMED_PERIODS_FIELD_LENGTH = 8
CONFIRMED_PERIOD_FIELD = 9
CONFIRMED_PERIOD_LOCKED_VALUE_FIELD = 10
LAST_ACTIVE_PERIOD_FIELD = 11
DOWNTIME_FIELD_LENGTH = 12
DOWNTIME_START_PERIOD_FIELD = 13
DOWNTIME_END_PERIOD_FIELD = 14
MINER_IDS_FIELD_LENGTH = 15
MINER_ID_FIELD = 16


@pytest.fixture()
def token(web3, chain):
    creator = web3.eth.accounts[0]
    # Create an ERC20 token
    token, _ = chain.provider.deploy_contract('NuCypherKMSToken', 2 * 10 ** 9)
    return token


@pytest.fixture(params=[False, True])
def escrow_contract(web3, chain, token, request):
    def make_escrow(max_allowed_locked_tokens):
        creator = web3.eth.accounts[0]
        # Creator deploys the escrow
        contract, _ = chain.provider.deploy_contract(
            'MinersEscrow', token.address, 1, 4 * 2 * 10 ** 7, 4, 4, 2, 100, max_allowed_locked_tokens)

        if request.param:
            dispatcher, _ = chain.provider.deploy_contract('Dispatcher', contract.address)

            # Deploy second version of the government contract
            contract = web3.eth.contract(
                abi=contract.abi,
                address=dispatcher.address,
                ContractFactoryClass=Contract)
        return contract

    return make_escrow


def test_escrow(web3, chain, token, escrow_contract):
    escrow = escrow_contract(1500)
    creator = web3.eth.accounts[0]
    ursula1 = web3.eth.accounts[1]
    ursula2 = web3.eth.accounts[2]
    deposit_log = escrow.eventFilter('Deposited')
    lock_log = escrow.eventFilter('Locked')
    activity_log = escrow.eventFilter('ActivityConfirmed')
    switching_lock_log = escrow.eventFilter('LockSwitched')
    withdraw_log = escrow.eventFilter('Withdrawn')

    # Give Ursula and Ursula(2) some coins
    tx = token.transact({'from': creator}).transfer(ursula1, 10000)
    chain.wait_for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(ursula2, 10000)
    chain.wait_for_receipt(tx)
    assert 10000 == token.call().balanceOf(ursula1)
    assert 10000 == token.call().balanceOf(ursula2)

    # Ursula and Ursula(2) give Escrow rights to transfer
    tx = token.transact({'from': ursula1}).approve(escrow.address, 3000)
    chain.wait_for_receipt(tx)
    assert 3000 == token.call().allowance(ursula1, escrow.address)
    tx = token.transact({'from': ursula2}).approve(escrow.address, 1100)
    chain.wait_for_receipt(tx)
    assert 1100 == token.call().allowance(ursula2, escrow.address)

    # Ursula's withdrawal attempt won't succeed because nothing to withdraw
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).withdraw(100)
        chain.wait_for_receipt(tx)

    # And can't lock because nothing to lock
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).lock(500, 2)
        chain.wait_for_receipt(tx)

    # Check that nothing is locked
    assert 0 == escrow.call().getLockedTokens(ursula1)
    assert 0 == escrow.call().getLockedTokens(ursula2)
    assert 0 == escrow.call().getLockedTokens(web3.eth.accounts[3])

    # Ursula can't deposit tokens before Escrow initialization
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).deposit(1, 1)
        chain.wait_for_receipt(tx)

    # Initialize Escrow contract
    tx = escrow.transact().initialize()
    chain.wait_for_receipt(tx)

    # Ursula can't deposit and lock too low value
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).deposit(1, 1)
        chain.wait_for_receipt(tx)

    # And can't deposit and lock too high value
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).deposit(1501, 1)
        chain.wait_for_receipt(tx)

    # Ursula and Ursula(2) transfer some tokens to the escrow and lock them
    tx = escrow.transact({'from': ursula1}).deposit(1000, 1)
    chain.wait_for_receipt(tx)
    assert 1000 == token.call().balanceOf(escrow.address)
    assert 9000 == token.call().balanceOf(ursula1)
    assert 1000 == escrow.call().getLockedTokens(ursula1)
    assert 1000 == escrow.call().calculateLockedTokens(ursula1, 1)
    assert 1000 == escrow.call().calculateLockedTokens(ursula1, 2)

    events = deposit_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['owner']
    assert 1000 == event_args['value']
    assert 1 == event_args['periods']
    events = lock_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['owner']
    assert 1000 == event_args['value']
    assert 500 == event_args['releaseRate']
    events = activity_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['owner']
    assert escrow.call().getCurrentPeriod() + 1 == event_args['period']
    assert 1000 == event_args['value']

    tx = escrow.transact({'from': ursula1}).switchLock()
    chain.wait_for_receipt(tx)
    assert 500 == escrow.call().calculateLockedTokens(ursula1, 2)
    events = switching_lock_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['owner']
    assert event_args['release']

    tx = escrow.transact({'from': ursula1}).switchLock()
    chain.wait_for_receipt(tx)
    assert 1000 == escrow.call().calculateLockedTokens(ursula1, 2)
    events = switching_lock_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula1 == event_args['owner']
    assert not event_args['release']

    tx = escrow.transact({'from': ursula2}).deposit(500, 2)
    chain.wait_for_receipt(tx)
    assert 1500 == token.call().balanceOf(escrow.address)
    assert 9500 == token.call().balanceOf(ursula2)
    assert 500 == escrow.call().getLockedTokens(ursula2)
    assert 500 == escrow.call().calculateLockedTokens(ursula2, 1)

    events = deposit_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula2 == event_args['owner']
    assert 500 == event_args['value']
    assert 2 == event_args['periods']
    events = lock_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula2 == event_args['owner']
    assert 500 == event_args['value']
    assert 250 == event_args['releaseRate']
    events = activity_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula2 == event_args['owner']
    assert escrow.call().getCurrentPeriod() + 1 == event_args['period']
    assert 500 == event_args['value']

    # Checks locked tokens in next period
    chain.wait_time(hours=1)
    assert 1000 == escrow.call().getLockedTokens(ursula1)
    assert 500 == escrow.call().getLockedTokens(ursula2)
    assert 1500 == escrow.call().getAllLockedTokens()

    # Ursula's withdrawal attempt won't succeed
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).withdraw(100)
        chain.wait_for_receipt(tx)
    assert 1500 == token.call().balanceOf(escrow.address)
    assert 9000 == token.call().balanceOf(ursula1)

    # Ursula can deposit more tokens
    tx = escrow.transact({'from': ursula1}).confirmActivity()
    chain.wait_for_receipt(tx)
    events = activity_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert ursula1 == event_args['owner']
    assert escrow.call().getCurrentPeriod() + 1 == event_args['period']
    assert 1000 == event_args['value']

    tx = escrow.transact({'from': ursula1}).deposit(500, 0)
    chain.wait_for_receipt(tx)
    assert 2000 == token.call().balanceOf(escrow.address)
    assert 8500 == token.call().balanceOf(ursula1)
    events = activity_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert ursula1 == event_args['owner']
    assert escrow.call().getCurrentPeriod() + 1 == event_args['period']
    assert 1500 == event_args['value']

    # But can't deposit too high value
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).deposit(1, 0)
        chain.wait_for_receipt(tx)

    # Ursula starts unlocking
    tx = escrow.transact({'from': ursula1}).switchLock()
    chain.wait_for_receipt(tx)
    assert 750 == escrow.call().calculateLockedTokens(ursula1, 2)

    # Wait 1 period and checks locking
    chain.wait_time(hours=1)
    assert 1500 == escrow.call().getLockedTokens(ursula1)

    # Confirm activity and wait 1 period
    tx = escrow.transact({'from': ursula1}).confirmActivity()
    chain.wait_for_receipt(tx)
    chain.wait_time(hours=1)
    assert 750 == escrow.call().getLockedTokens(ursula1)
    assert 0 == escrow.call().calculateLockedTokens(ursula1, 1)

    # And Ursula can withdraw some tokens
    tx = escrow.transact({'from': ursula1}).withdraw(100)
    chain.wait_for_receipt(tx)
    assert 1900 == token.call().balanceOf(escrow.address)
    assert 8600 == token.call().balanceOf(ursula1)
    events = withdraw_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['owner']
    assert 100 == event_args['value']

    # But Ursula can't withdraw all without mining for locked value
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).withdraw(1400)
        chain.wait_for_receipt(tx)

    # And Ursula can't lock again too low value
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).lock(1, 1)
        chain.wait_for_receipt(tx)

    # Ursula can deposit and lock more tokens
    tx = escrow.transact({'from': ursula1}).deposit(500, 0)
    chain.wait_for_receipt(tx)
    tx = escrow.transact({'from': ursula1}).lock(100, 0)
    chain.wait_for_receipt(tx)

    # Locked tokens will be updated in next period
    # Release rate will be updated too because of the end of previous locking
    assert 750 == escrow.call().getLockedTokens(ursula1)
    assert 600 == escrow.call().calculateLockedTokens(ursula1, 1)
    assert 600 == escrow.call().calculateLockedTokens(ursula1, 2)
    tx = escrow.transact({'from': ursula1}).switchLock()
    chain.wait_for_receipt(tx)
    assert 300 == escrow.call().calculateLockedTokens(ursula1, 2)
    assert 0 == escrow.call().calculateLockedTokens(ursula1, 3)
    chain.wait_time(hours=1)
    assert 600 == escrow.call().getLockedTokens(ursula1)
    assert 300 == escrow.call().calculateLockedTokens(ursula1, 1)
    assert 0 == escrow.call().calculateLockedTokens(ursula1, 2)

    # Ursula can increase lock
    tx = escrow.transact({'from': ursula1}).lock(500, 2)
    chain.wait_for_receipt(tx)
    assert 600 == escrow.call().getLockedTokens(ursula1)
    assert 800 == escrow.call().calculateLockedTokens(ursula1, 1)
    assert 500 == escrow.call().calculateLockedTokens(ursula1, 2)
    assert 200 == escrow.call().calculateLockedTokens(ursula1, 3)
    assert 0 == escrow.call().calculateLockedTokens(ursula1, 4)
    chain.wait_time(hours=1)
    assert 800 == escrow.call().getLockedTokens(ursula1)

    # Ursula(2) starts unlocking and increases lock by deposit more tokens
    tx = escrow.transact({'from': ursula2}).deposit(500, 0)
    chain.wait_for_receipt(tx)
    tx = escrow.transact({'from': ursula2}).switchLock()
    chain.wait_for_receipt(tx)
    assert 1000 == escrow.call().getLockedTokens(ursula2)
    assert 1000 == escrow.call().calculateLockedTokens(ursula2, 1)
    assert 500 == escrow.call().calculateLockedTokens(ursula2, 2)
    assert 0 == escrow.call().calculateLockedTokens(ursula2, 3)
    chain.wait_time(hours=1)
    assert 1000 == escrow.call().getLockedTokens(ursula2)

    # And increases locked time
    tx = escrow.transact({'from': ursula2}).lock(0, 2)
    chain.wait_for_receipt(tx)
    assert 1000 == escrow.call().getLockedTokens(ursula2)
    assert 500 == escrow.call().calculateLockedTokens(ursula2, 1)
    assert 0 == escrow.call().calculateLockedTokens(ursula2, 2)

    # Ursula(2) increases lock by small amount of tokens
    tx = escrow.transact({'from': ursula2}).deposit(100, 0)
    chain.wait_for_receipt(tx)
    assert 600 == escrow.call().calculateLockedTokens(ursula2, 1)
    assert 100 == escrow.call().calculateLockedTokens(ursula2, 2)
    assert 0 == escrow.call().calculateLockedTokens(ursula2, 3)

    assert 6 == len(deposit_log.get_all_entries())
    assert 9 == len(lock_log.get_all_entries())
    assert 5 == len(switching_lock_log.get_all_entries())
    assert 1 == len(withdraw_log.get_all_entries())
    assert 11 == len(activity_log.get_all_entries())


def test_locked_distribution(web3, chain, token, escrow_contract):
    escrow = escrow_contract(5 * 10 ** 8)
    NULL_ADDR = '0x' + '0' * 40
    creator = web3.eth.accounts[0]

    # Give Escrow tokens for reward and initialize contract
    tx = token.transact({'from': creator}).transfer(escrow.address, 10 ** 9)
    chain.wait_for_receipt(tx)
    tx = escrow.transact().initialize()
    chain.wait_for_receipt(tx)

    miners = web3.eth.accounts[1:]
    amount = token.call().balanceOf(creator) // 2
    largest_locked = amount

    # Airdrop
    for miner in miners:
        tx = token.transact({'from': creator}).transfer(miner, amount)
        chain.wait_for_receipt(tx)
        amount = amount // 2

    # Lock
    for index, miner in enumerate(miners):
        balance = token.call().balanceOf(miner)
        tx = token.transact({'from': miner}).approve(escrow.address, balance)
        chain.wait_for_receipt(tx)
        tx = escrow.transact({'from': miner}).deposit(balance, index + 2)
        chain.wait_for_receipt(tx)

    # Check current period
    address_stop, index_stop, shift = escrow.call().findCumSum(0, 1, 1)
    assert NULL_ADDR == address_stop
    assert 0 == index_stop
    assert 0 == shift

    # Wait next period
    chain.wait_time(hours=1)
    n_locked = escrow.call().getAllLockedTokens()
    assert n_locked > 0

    # And confirm activity
    for miner in miners:
        tx = escrow.transact({'from': miner}).confirmActivity()
        chain.wait_for_receipt(tx)

    address_stop, index_stop, shift = escrow.call().findCumSum(0, n_locked // 3, 1)
    assert miners[0] == address_stop
    assert 0 == index_stop
    assert n_locked // 3 == shift

    address_stop, index_stop, shift = escrow.call().findCumSum(0, largest_locked, 1)
    assert miners[1] == address_stop
    assert 1 == index_stop
    assert 0 == shift

    address_stop, index_stop, shift = escrow.call().findCumSum(
        1, largest_locked // 2 + 1, 1)
    assert miners[2] == address_stop
    assert 2 == index_stop
    assert 1 == shift

    address_stop, index_stop, shift = escrow.call().findCumSum(0, 1, 10)
    assert NULL_ADDR != address_stop
    assert 0 != shift
    address_stop, index_stop, shift = escrow.call().findCumSum(0, 1, 11)
    assert NULL_ADDR == address_stop
    assert 0 == index_stop
    assert 0 == shift

    for index, _ in enumerate(miners[:-1]):
        address_stop, index_stop, shift = escrow.call().findCumSum(0, 1, index + 3)
        assert miners[index + 1] == address_stop
        assert index + 1 == index_stop
        assert 1 == shift

    # Test miners iteration
    assert len(miners) == web3.toInt(escrow.call().getMinerInfo(MINERS_LENGTH, NULL_ADDR, 0))
    for index, miner in enumerate(miners):
        assert miners[index] == \
               web3.toChecksumAddress(escrow.call().getMinerInfo(MINER, NULL_ADDR, index)[12:])


def test_mining(web3, chain, token, escrow_contract):
    escrow = escrow_contract(1500)
    creator = web3.eth.accounts[0]
    ursula1 = web3.eth.accounts[1]
    ursula2 = web3.eth.accounts[2]
    mining_log = escrow.eventFilter('Mined')
    deposit_log = escrow.eventFilter('Deposited')
    lock_log = escrow.eventFilter('Locked')
    activity_log = escrow.eventFilter('ActivityConfirmed')
    switching_lock_log = escrow.eventFilter('LockSwitched')
    withdraw_log = escrow.eventFilter('Withdrawn')

    # Give Escrow tokens for reward and initialize contract
    tx = token.transact({'from': creator}).transfer(escrow.address, 10 ** 9)
    chain.wait_for_receipt(tx)
    tx = escrow.transact().initialize()
    chain.wait_for_receipt(tx)

    policy_manager, _ = chain.provider.deploy_contract(
        'PolicyManagerForMinersEscrowMock', token.address, escrow.address
    )
    tx = escrow.transact({'from': creator}).setPolicyManager(policy_manager.address)
    chain.wait_for_receipt(tx)
    assert policy_manager.address == escrow.call().policyManager()

    # Give Ursula and Ursula(2) some coins
    tx = token.transact({'from': creator}).transfer(ursula1, 10000)
    chain.wait_for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(ursula2, 10000)
    chain.wait_for_receipt(tx)

    # Ursula can't confirm and mint because no locked tokens
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).mint()
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).confirmActivity()
        chain.wait_for_receipt(tx)

    # Ursula and Ursula(2) give Escrow rights to transfer
    tx = token.transact({'from': ursula1}).approve(escrow.address, 2000)
    chain.wait_for_receipt(tx)
    tx = token.transact({'from': ursula2}).approve(escrow.address, 500)
    chain.wait_for_receipt(tx)

    # Ursula and Ursula(2) transfer some tokens to the escrow and lock them
    tx = escrow.transact({'from': ursula1}).deposit(1000, 1)
    chain.wait_for_receipt(tx)
    tx = escrow.transact({'from': ursula2}).deposit(500, 2)
    chain.wait_for_receipt(tx)

    # Using locked tokens starts from next period
    assert 0 == escrow.call().getAllLockedTokens()

    # Ursula can't use method from Issuer contract
    with pytest.raises(Exception):
        tx = escrow.transact({'from': ursula1}).mint(1, 1, 1, 1, 1)
        chain.wait_for_receipt(tx)

    # Only Ursula confirm next period
    chain.wait_time(hours=1)
    assert 1500 == escrow.call().getAllLockedTokens()
    tx = escrow.transact({'from': ursula1}).confirmActivity()
    chain.wait_for_receipt(tx)

    # Checks that no error
    tx = escrow.transact({'from': ursula1}).confirmActivity()
    chain.wait_for_receipt(tx)

    # Ursula and Ursula(2) mint tokens for last periods
    chain.wait_time(hours=1)
    assert 1000 == escrow.call().getAllLockedTokens()
    tx = escrow.transact({'from': ursula1}).mint()
    chain.wait_for_receipt(tx)
    tx = escrow.transact({'from': ursula2}).mint()

    chain.wait_for_receipt(tx)
    assert 1050 == web3.toInt(escrow.call().getMinerInfo(VALUE_FIELD, ursula1, 0))
    assert 521 == web3.toInt(escrow.call().getMinerInfo(VALUE_FIELD, ursula2, 0))

    events = mining_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['owner']
    assert 50 == event_args['value']
    assert escrow.call().getCurrentPeriod() - 1 == event_args['period']
    event_args = events[1]['args']
    assert ursula2 == event_args['owner']
    assert 21 == event_args['value']
    assert escrow.call().getCurrentPeriod() - 1 == event_args['period']

    assert 1 == policy_manager.call().getPeriodsLength(ursula1)
    assert 1 == policy_manager.call().getPeriodsLength(ursula2)
    period = escrow.call().getCurrentPeriod() - 1
    assert period == policy_manager.call().getPeriod(ursula1, 0)
    assert period == policy_manager.call().getPeriod(ursula2, 0)

    # Only Ursula confirm activity for next period
    tx = escrow.transact({'from': ursula1}).switchLock()
    chain.wait_for_receipt(tx)
    tx = escrow.transact({'from': ursula1}).confirmActivity()
    chain.wait_for_receipt(tx)

    # Ursula can't confirm next period because end of locking
    chain.wait_time(hours=1)
    assert 500 == escrow.call().getAllLockedTokens()
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).confirmActivity()
        chain.wait_for_receipt(tx)

    # But Ursula(2) can
    tx = escrow.transact({'from': ursula2}).confirmActivity()
    chain.wait_for_receipt(tx)

    # Ursula mint tokens for next period
    chain.wait_time(hours=1)
    assert 500 == escrow.call().getAllLockedTokens()
    tx = escrow.transact({'from': ursula1}).mint()
    chain.wait_for_receipt(tx)
    # But Ursula(2) can't get reward because she did not confirmed activity
    tx = escrow.transact({'from': ursula2}).mint()

    chain.wait_for_receipt(tx)
    assert 1163 == web3.toInt(escrow.call().getMinerInfo(VALUE_FIELD, ursula1, 0))
    assert 521 == web3.toInt(escrow.call().getMinerInfo(VALUE_FIELD, ursula2, 0))

    assert 3 == policy_manager.call().getPeriodsLength(ursula1)
    assert 1 == policy_manager.call().getPeriodsLength(ursula2)
    assert period + 1 == policy_manager.call().getPeriod(ursula1, 1)
    assert period + 2 == policy_manager.call().getPeriod(ursula1, 2)

    events = mining_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert ursula1 == event_args['owner']
    assert 113 == event_args['value']
    assert escrow.call().getCurrentPeriod() - 1 == event_args['period']

    # Ursula(2) confirm next period and mint tokens
    tx = escrow.transact({'from': ursula2}).switchLock()
    chain.wait_for_receipt(tx)
    tx = escrow.transact({'from': ursula2}).confirmActivity()
    chain.wait_for_receipt(tx)
    chain.wait_time(hours=2)
    assert 0 == escrow.call().getAllLockedTokens()
    tx = escrow.transact({'from': ursula2}).mint()

    chain.wait_for_receipt(tx)
    assert 1163 == web3.toInt(escrow.call().getMinerInfo(VALUE_FIELD, ursula1, 0))
    assert 634 == web3.toInt(escrow.call().getMinerInfo(VALUE_FIELD, ursula2, 0))

    assert 3 == policy_manager.call().getPeriodsLength(ursula1)
    assert 3 == policy_manager.call().getPeriodsLength(ursula2)
    assert period + 3 == policy_manager.call().getPeriod(ursula2, 1)
    assert period + 4 == policy_manager.call().getPeriod(ursula2, 2)

    events = mining_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert ursula2 == event_args['owner']
    assert 113 == event_args['value']
    assert escrow.call().getCurrentPeriod() - 1 == event_args['period']

    # Ursula can't confirm and get reward because no locked tokens
    tx = escrow.transact({'from': ursula1}).mint()

    chain.wait_for_receipt(tx)
    assert 1163 == web3.toInt(escrow.call().getMinerInfo(VALUE_FIELD, ursula1, 0))

    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': ursula1}).confirmActivity()
        chain.wait_for_receipt(tx)

    # Ursula can lock some tokens again
    tx = escrow.transact({'from': ursula1}).lock(500, 4)
    chain.wait_for_receipt(tx)
    tx = escrow.transact({'from': ursula1}).switchLock()
    chain.wait_for_receipt(tx)
    assert 500 == escrow.call().getLockedTokens(ursula1)
    assert 500 == escrow.call().calculateLockedTokens(ursula1, 1)
    assert 375 == escrow.call().calculateLockedTokens(ursula1, 2)
    assert 250 == escrow.call().calculateLockedTokens(ursula1, 3)
    assert 0 == escrow.call().calculateLockedTokens(ursula1, 5)
    # And can increase lock
    tx = escrow.transact({'from': ursula1}).lock(100, 0)
    chain.wait_for_receipt(tx)
    assert 600 == escrow.call().getLockedTokens(ursula1)
    assert 600 == escrow.call().calculateLockedTokens(ursula1, 1)
    assert 450 == escrow.call().calculateLockedTokens(ursula1, 2)
    assert 0 == escrow.call().calculateLockedTokens(ursula1, 5)
    tx = escrow.transact({'from': ursula1}).lock(0, 2)
    chain.wait_for_receipt(tx)
    assert 600 == escrow.call().getLockedTokens(ursula1)
    assert 600 == escrow.call().calculateLockedTokens(ursula1, 1)
    assert 450 == escrow.call().calculateLockedTokens(ursula1, 2)
    assert 0 == escrow.call().calculateLockedTokens(ursula1, 5)
    tx = escrow.transact({'from': ursula1}).deposit(800, 1)
    chain.wait_for_receipt(tx)
    assert 1400 == escrow.call().getLockedTokens(ursula1)
    assert 1400 == escrow.call().calculateLockedTokens(ursula1, 1)
    assert 1000 == escrow.call().calculateLockedTokens(ursula1, 3)
    assert 400 == escrow.call().calculateLockedTokens(ursula1, 6)
    assert 0 == escrow.call().calculateLockedTokens(ursula1, 8)

    # Ursula(2) can withdraw all
    tx = escrow.transact({'from': ursula2}).withdraw(634)
    chain.wait_for_receipt(tx)
    assert 10134 == token.call().balanceOf(ursula2)

    events = withdraw_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula2 == event_args['owner']
    assert 634 == event_args['value']

    assert 3 == len(deposit_log.get_all_entries())
    assert 6 == len(lock_log.get_all_entries())
    assert 3 == len(switching_lock_log.get_all_entries())
    assert 10 == len(activity_log.get_all_entries())

    # TODO test max miners


def test_pre_deposit(web3, chain, token, escrow_contract):
    escrow = escrow_contract(1500)
    creator = web3.eth.accounts[0]
    deposit_log = escrow.eventFilter('Deposited')

    # Initialize Escrow contract
    tx = escrow.transact().initialize()
    chain.wait_for_receipt(tx)

    # Grant access to transfer tokens
    tx = token.transact({'from': creator}).approve(escrow.address, 10000)
    chain.wait_for_receipt(tx)

    # Deposit tokens for 1 owner
    owner = web3.eth.accounts[1]
    tx = escrow.transact({'from': creator}).preDeposit([owner], [1000], [10])
    chain.wait_for_receipt(tx)
    assert 1000 == token.call().balanceOf(escrow.address)
    assert 1000 == web3.toInt(escrow.call().getMinerInfo(VALUE_FIELD, owner, 0))
    assert 1000 == escrow.call().getLockedTokens(owner)
    assert 10 == web3.toInt(escrow.call().getMinerInfo(MAX_RELEASE_PERIODS_FIELD, owner, 0))

    # Can't pre-deposit tokens again for same owner
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': creator}).preDeposit(
            [web3.eth.accounts[1]], [1000], [10])
        chain.wait_for_receipt(tx)

    # Can't pre-deposit tokens with too low or too high value
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': creator}).preDeposit(
            [web3.eth.accounts[2]], [1], [10])
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': creator}).preDeposit(
            [web3.eth.accounts[2]], [1501], [10])
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = escrow.transact({'from': creator}).preDeposit(
            [web3.eth.accounts[2]], [500], [1])
        chain.wait_for_receipt(tx)

    # Deposit tokens for multiple owners
    owners = web3.eth.accounts[2:7]
    tx = escrow.transact({'from': creator}).preDeposit(
        owners, [100, 200, 300, 400, 500], [50, 100, 150, 200, 250])
    chain.wait_for_receipt(tx)
    assert 2500 == token.call().balanceOf(escrow.address)
    for index, owner in enumerate(owners):
        assert 100 * (index + 1) == web3.toInt(escrow.call().getMinerInfo(VALUE_FIELD, owner, 0))
        assert 100 * (index + 1) == escrow.call().getLockedTokens(owner)
        assert 50 * (index + 1) == \
            web3.toInt(escrow.call().getMinerInfo(MAX_RELEASE_PERIODS_FIELD, owner, 0))

    events = deposit_log.get_all_entries()
    assert 6 == len(events)
    event_args = events[0]['args']
    assert web3.eth.accounts[1] == event_args['owner']
    assert 1000 == event_args['value']
    assert 10 == event_args['periods']
    event_args = events[1]['args']
    assert owners[0] == event_args['owner']
    assert 100 == event_args['value']
    assert 50 == event_args['periods']
    event_args = events[2]['args']
    assert owners[1] == event_args['owner']
    assert 200 == event_args['value']
    assert 100 == event_args['periods']
    event_args = events[3]['args']
    assert owners[2] == event_args['owner']
    assert 300 == event_args['value']
    assert 150 == event_args['periods']
    event_args = events[4]['args']
    assert owners[3] == event_args['owner']
    assert 400 == event_args['value']
    assert 200 == event_args['periods']
    event_args = events[5]['args']
    assert owners[4] == event_args['owner']
    assert 500 == event_args['value']
    assert 250 == event_args['periods']


def test_miner_id(web3, chain, token, escrow_contract):
    escrow = escrow_contract(5 * 10 ** 8)
    creator = web3.eth.accounts[0]
    miner = web3.eth.accounts[1]

    # Initialize contract and miner
    tx = escrow.transact().initialize()
    chain.wait_for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(miner, 1000)
    chain.wait_for_receipt(tx)
    balance = token.call().balanceOf(miner)
    tx = token.transact({'from': miner}).approve(escrow.address, balance)
    chain.wait_for_receipt(tx)
    tx = escrow.transact({'from': miner}).deposit(balance, 1)
    chain.wait_for_receipt(tx)

    # Set miner ids
    miner_id = os.urandom(32)
    tx = escrow.transact({'from': miner}).setMinerId(miner_id)

    chain.wait_for_receipt(tx)
    assert 1 == web3.toInt(escrow.call().getMinerInfo(MINER_IDS_FIELD_LENGTH, miner, 0))
    
    assert miner_id == escrow.call().getMinerInfo(MINER_ID_FIELD, miner, 0)
    miner_id = os.urandom(32)
    tx = escrow.transact({'from': miner}).setMinerId(miner_id)
    chain.wait_for_receipt(tx)
    assert 2 == web3.toInt(escrow.call().getMinerInfo(MINER_IDS_FIELD_LENGTH, miner, 0))
    
    assert miner_id == escrow.call().getMinerInfo(MINER_ID_FIELD, miner, 1)


def test_verifying_state(web3, chain, token):
    creator = web3.eth.accounts[0]
    miner = web3.eth.accounts[1]

    # Deploy contract
    contract_library_v1, _ = chain.provider.deploy_contract(
        'MinersEscrow', token.address, 1, int(8e7), 4, 4, 2, 100, 1500
    )
    dispatcher, _ = chain.provider.deploy_contract('Dispatcher', contract_library_v1.address)

    # Deploy second version of the contract
    contract_library_v2, _ = chain.provider.deploy_contract(
        'MinersEscrowV2Mock', token.address, 2, 2, 2, 2, 2, 2, 2, 2
    )

    contract = web3.eth.contract(
        abi=contract_library_v2.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    assert 1500 == contract.call().maxAllowableLockedTokens()

    # Initialize contract and miner
    policy_manager, _ = chain.provider.deploy_contract('PolicyManagerForMinersEscrowMock', token.address, contract.address)

    tx = contract.transact({'from': creator}).setPolicyManager(policy_manager.address)
    chain.wait_for_receipt(tx)
    tx = contract.transact().initialize()
    chain.wait_for_receipt(tx)
    tx = token.transact({'from': creator}).transfer(miner, 1000)
    chain.wait_for_receipt(tx)
    balance = token.call().balanceOf(miner)
    tx = token.transact({'from': miner}).approve(contract.address, balance)
    chain.wait_for_receipt(tx)
    tx = contract.transact({'from': miner}).deposit(balance, 1000)
    chain.wait_for_receipt(tx)

    # Upgrade to the second version
    tx = dispatcher.transact({'from': creator}).upgrade(contract_library_v2.address)

    chain.wait_for_receipt(tx)
    assert contract_library_v2.address == dispatcher.call().target()
    assert 1500 == contract.call().maxAllowableLockedTokens()
    assert 2 == contract.call().valueToCheck()
    tx = contract.transact({'from': creator}).setValueToCheck(3)
    chain.wait_for_receipt(tx)
    assert 3 == contract.call().valueToCheck()

    # Can't upgrade to the previous version or to the bad version
    contract_library_bad, _ = chain.provider.deploy_contract(
        'MinersEscrowBad', token.address, 2, 2, 2, 2, 2, 2, 2
    )

    with pytest.raises(TransactionFailed):
        tx = dispatcher.transact({'from': creator}).upgrade(contract_library_v1.address)
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = dispatcher.transact({'from': creator}).upgrade(contract_library_bad.address)
        chain.wait_for_receipt(tx)

    # But can rollback
    tx = dispatcher.transact({'from': creator}).rollback()

    chain.wait_for_receipt(tx)
    assert contract_library_v1.address == dispatcher.call().target()
    with pytest.raises(TransactionFailed):
        tx = contract.transact({'from': creator}).setValueToCheck(2)
        chain.wait_for_receipt(tx)

    # Try to upgrade to the bad version
    with pytest.raises(TransactionFailed):
        tx = dispatcher.transact({'from': creator}).upgrade(contract_library_bad.address)
        chain.wait_for_receipt(tx)
