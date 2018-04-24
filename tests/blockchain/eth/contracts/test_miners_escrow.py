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
    # Create an ERC20 token
    token, _ = chain.provider.deploy_contract('NuCypherKMSToken', 2 * 10 ** 9)
    return token


@pytest.fixture(params=[False, True])
def escrow_contract(web3, chain, token, request):
    def make_escrow(max_allowed_locked_tokens):
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
    deposit_log = escrow.events.Deposited.createFilter(fromBlock=0)
    lock_log = escrow.events.Locked.createFilter(fromBlock=0)
    activity_log = escrow.events.ActivityConfirmed.createFilter(fromBlock=0)
    switching_lock_log = escrow.events.LockSwitched.createFilter(fromBlock=0)
    withdraw_log = escrow.events.Withdrawn.createFilter(fromBlock=0)

    # Give Ursula and Ursula(2) some coins
    tx =  token.functions.transfer(ursula1, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx =  token.functions.transfer(ursula2, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 10000 == token.functions.balanceOf(ursula1).call()
    assert 10000 == token.functions.balanceOf(ursula2).call()

    # Ursula and Ursula(2) give Escrow rights to transfer
    tx =  token.functions.approve(escrow.address, 3000).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 3000 == token.functions.allowance(ursula1, escrow.address).call()
    tx =  token.functions.approve(escrow.address, 1100).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 1100 == token.functions.allowance(ursula2, escrow.address).call()

    # Ursula's withdrawal attempt won't succeed because nothing to withdraw
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  escrow.functions.withdraw(100).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # And can't lock because nothing to lock
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  escrow.functions.lock(500, 2).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Check that nothing is locked
    assert 0 == escrow.functions.getLockedTokens(ursula1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2).call()
    assert 0 == escrow.functions.getLockedTokens(web3.eth.accounts[3]).call()

    # Ursula can't deposit tokens before Escrow initialization
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  escrow.functions.deposit(1, 1).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Initialize Escrow contract
    tx = escrow.functions.initialize().transact({'from': creator})
    chain.wait_for_receipt(tx)

    # Ursula can't deposit and lock too low value
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  escrow.functions.deposit(1, 1).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # And can't deposit and lock too high value
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  escrow.functions.deposit(1501, 1).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Ursula and Ursula(2) transfer some tokens to the escrow and lock them
    tx =  escrow.functions.deposit(1000, 1).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 1000 == token.functions.balanceOf(escrow.address).call()
    assert 9000 == token.functions.balanceOf(ursula1).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1).call()
    assert 1000 == escrow.functions.calculateLockedTokens(ursula1, 1).call()
    assert 1000 == escrow.functions.calculateLockedTokens(ursula1, 2).call()

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
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 1000 == event_args['value']

    tx = escrow.functions.switchLock().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 500 == escrow.functions.calculateLockedTokens(ursula1, 2).call()
    events = switching_lock_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['owner']
    assert event_args['release']

    tx = escrow.functions.switchLock().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 1000 == escrow.functions.calculateLockedTokens(ursula1, 2).call()
    events = switching_lock_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula1 == event_args['owner']
    assert not event_args['release']

    tx =  escrow.functions.deposit(500, 2).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 1500 == token.functions.balanceOf(escrow.address).call()
    assert 9500 == token.functions.balanceOf(ursula2).call()
    assert 500 == escrow.functions.getLockedTokens(ursula2).call()
    assert 500 == escrow.functions.calculateLockedTokens(ursula2, 1).call()

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
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 500 == event_args['value']

    # Checks locked tokens in next period
    chain.time_travel(hours=1)
    assert 1000 == escrow.functions.getLockedTokens(ursula1).call()
    assert 500 == escrow.functions.getLockedTokens(ursula2).call()
    assert 1500 == escrow.functions.getAllLockedTokens().call()

    # Ursula's withdrawal attempt won't succeed
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  escrow.functions.withdraw(100).transact({'from': ursula1})
        chain.wait_for_receipt(tx)
    assert 1500 == token.functions.balanceOf(escrow.address).call()
    assert 9000 == token.functions.balanceOf(ursula1).call()

    # Ursula can deposit more tokens
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    events = activity_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert ursula1 == event_args['owner']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 1000 == event_args['value']

    tx =  escrow.functions.deposit(500, 0).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 2000 == token.functions.balanceOf(escrow.address).call()
    assert 8500 == token.functions.balanceOf(ursula1).call()
    events = activity_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert ursula1 == event_args['owner']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 1500 == event_args['value']

    # But can't deposit too high value
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  escrow.functions.deposit(1, 0).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Ursula starts unlocking
    tx = escrow.functions.switchLock().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 750 == escrow.functions.calculateLockedTokens(ursula1, 2).call()

    # Wait 1 period and checks locking
    chain.time_travel(hours=1)
    assert 1500 == escrow.functions.getLockedTokens(ursula1).call()

    # Confirm activity and wait 1 period
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    chain.time_travel(hours=1)
    assert 750 == escrow.functions.getLockedTokens(ursula1).call()
    assert 0 == escrow.functions.calculateLockedTokens(ursula1, 1).call()

    # And Ursula can withdraw some tokens
    tx =  escrow.functions.withdraw(100).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 1900 == token.functions.balanceOf(escrow.address).call()
    assert 8600 == token.functions.balanceOf(ursula1).call()
    events = withdraw_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['owner']
    assert 100 == event_args['value']

    # But Ursula can't withdraw all without mining for locked value
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  escrow.functions.withdraw(1400).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # And Ursula can't lock again too low value
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  escrow.functions.lock(1, 1).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Ursula can deposit and lock more tokens
    tx =  escrow.functions.deposit(500, 0).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx =  escrow.functions.lock(100, 0).transact({'from': ursula1})
    chain.wait_for_receipt(tx)

    # Locked tokens will be updated in next period
    # Release rate will be updated too because of the end of previous locking
    assert 750 == escrow.functions.getLockedTokens(ursula1).call()
    assert 600 == escrow.functions.calculateLockedTokens(ursula1, 1).call()
    assert 600 == escrow.functions.calculateLockedTokens(ursula1, 2).call()
    tx = escrow.functions.switchLock().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 300 == escrow.functions.calculateLockedTokens(ursula1, 2).call()
    assert 0 == escrow.functions.calculateLockedTokens(ursula1, 3).call()
    chain.time_travel(hours=1)
    assert 600 == escrow.functions.getLockedTokens(ursula1).call()
    assert 300 == escrow.functions.calculateLockedTokens(ursula1, 1).call()
    assert 0 == escrow.functions.calculateLockedTokens(ursula1, 2).call()

    # Ursula can increase lock
    tx =  escrow.functions.lock(500, 2).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 600 == escrow.functions.getLockedTokens(ursula1).call()
    assert 800 == escrow.functions.calculateLockedTokens(ursula1, 1).call()
    assert 500 == escrow.functions.calculateLockedTokens(ursula1, 2).call()
    assert 200 == escrow.functions.calculateLockedTokens(ursula1, 3).call()
    assert 0 == escrow.functions.calculateLockedTokens(ursula1, 4).call()
    chain.time_travel(hours=1)
    assert 800 == escrow.functions.getLockedTokens(ursula1).call()

    # Ursula(2) starts unlocking and increases lock by deposit more tokens
    tx =  escrow.functions.deposit(500, 0).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.switchLock().transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(ursula2).call()
    assert 1000 == escrow.functions.calculateLockedTokens(ursula2, 1).call()
    assert 500 == escrow.functions.calculateLockedTokens(ursula2, 2).call()
    assert 0 == escrow.functions.calculateLockedTokens(ursula2, 3).call()
    chain.time_travel(hours=1)
    assert 1000 == escrow.functions.getLockedTokens(ursula2).call()

    # And increases locked time
    tx =  escrow.functions.lock(0, 2).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 1000 == escrow.functions.getLockedTokens(ursula2).call()
    assert 500 == escrow.functions.calculateLockedTokens(ursula2, 1).call()
    assert 0 == escrow.functions.calculateLockedTokens(ursula2, 2).call()

    # Ursula(2) increases lock by small amount of tokens
    tx =  escrow.functions.deposit(100, 0).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 600 == escrow.functions.calculateLockedTokens(ursula2, 1).call()
    assert 100 == escrow.functions.calculateLockedTokens(ursula2, 2).call()
    assert 0 == escrow.functions.calculateLockedTokens(ursula2, 3).call()

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
    tx =  token.functions.transfer(escrow.address, 10 ** 9).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.initialize().transact({'from': creator})
    chain.wait_for_receipt(tx)

    miners = web3.eth.accounts[1:]
    amount = token.functions.balanceOf(creator).call() // 2
    largest_locked = amount

    # Airdrop
    for miner in miners:
        tx =  token.functions.transfer(miner, amount).transact({'from': creator})
        chain.wait_for_receipt(tx)
        amount = amount // 2

    # Lock
    for index, miner in enumerate(miners):
        balance = token.functions.balanceOf(miner).call()
        tx =  token.functions.approve(escrow.address, balance).transact({'from': miner})
        chain.wait_for_receipt(tx)
        tx =  escrow.functions.deposit(balance, index + 2).transact({'from': miner})
        chain.wait_for_receipt(tx)

    # Check current period
    address_stop, index_stop, shift = escrow.functions.findCumSum(0, 1, 1).call()
    assert NULL_ADDR == address_stop
    assert 0 == index_stop
    assert 0 == shift

    # Wait next period
    chain.time_travel(hours=1)
    n_locked = escrow.functions.getAllLockedTokens().call()
    assert n_locked > 0

    # And confirm activity
    for miner in miners:
        tx = escrow.functions.confirmActivity().transact({'from': miner})
        chain.wait_for_receipt(tx)

    address_stop, index_stop, shift = escrow.functions.findCumSum(0, n_locked // 3, 1).call()
    assert miners[0] == address_stop
    assert 0 == index_stop
    assert n_locked // 3 == shift

    address_stop, index_stop, shift = escrow.functions.findCumSum(0, largest_locked, 1).call()
    assert miners[1] == address_stop
    assert 1 == index_stop
    assert 0 == shift

    address_stop, index_stop, shift = escrow.call().findCumSum(
        1, largest_locked // 2 + 1, 1)
    assert miners[2] == address_stop
    assert 2 == index_stop
    assert 1 == shift

    address_stop, index_stop, shift = escrow.functions.findCumSum(0, 1, 10).call()
    assert NULL_ADDR != address_stop
    assert 0 != shift
    address_stop, index_stop, shift = escrow.functions.findCumSum(0, 1, 11).call()
    assert NULL_ADDR == address_stop
    assert 0 == index_stop
    assert 0 == shift

    for index, _ in enumerate(miners[:-1]):
        address_stop, index_stop, shift = escrow.functions.findCumSum(0, 1, index + 3).call()
        assert miners[index + 1] == address_stop
        assert index + 1 == index_stop
        assert 1 == shift

    # Test miners iteration
    assert len(miners) == web3.toInt(escrow.functions.getMinerInfo(MINERS_LENGTH, NULL_ADDR, 0).call())
    for index, miner in enumerate(miners):
        assert miners[index] == web3.toChecksumAddress(escrow.functions.getMinerInfo(MINER, NULL_ADDR, index).call()[12:])


def test_mining(web3, chain, token, escrow_contract):
    escrow = escrow_contract(1500)
    creator = web3.eth.accounts[0]
    ursula1 = web3.eth.accounts[1]
    ursula2 = web3.eth.accounts[2]

    mining_log = escrow.events.Mined.createFilter(fromBlock=0)
    deposit_log = escrow.events.Deposited.createFilter(fromBlock=0)
    lock_log = escrow.events.Locked.createFilter(fromBlock=0)
    activity_log = escrow.events.ActivityConfirmed.createFilter(fromBlock=0)
    switching_lock_log = escrow.events.LockSwitched.createFilter(fromBlock=0)
    withdraw_log = escrow.events.Withdrawn.createFilter(fromBlock=0)

    # Give Escrow tokens for reward and initialize contract
    tx =  token.functions.transfer(escrow.address, 10 ** 9).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.initialize().transact({'from': creator})
    chain.wait_for_receipt(tx)

    policy_manager, _ = chain.provider.deploy_contract(
        'PolicyManagerForMinersEscrowMock', token.address, escrow.address
    )
    tx =  escrow.functions.setPolicyManager(policy_manager.address).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert policy_manager.address == escrow.functions.policyManager().call()

    # Give Ursula and Ursula(2) some coins
    tx =  token.functions.transfer(ursula1, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx =  token.functions.transfer(ursula2, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)

    # Ursula can't confirm and mint because no locked tokens
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.mint().transact({'from': ursula1})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmActivity().transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Ursula and Ursula(2) give Escrow rights to transfer
    tx =  token.functions.approve(escrow.address, 2000).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx =  token.functions.approve(escrow.address, 500).transact({'from': ursula2})
    chain.wait_for_receipt(tx)

    # Ursula and Ursula(2) transfer some tokens to the escrow and lock them
    tx =  escrow.functions.deposit(1000, 1).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx =  escrow.functions.deposit(500, 2).transact({'from': ursula2})
    chain.wait_for_receipt(tx)

    # Using locked tokens starts from next period
    assert 0 == escrow.functions.getAllLockedTokens().call()

    # Ursula can't use method from Issuer contract
    with pytest.raises(Exception):
        tx =  escrow.functions.mint(1, 1, 1, 1, 1).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Only Ursula confirm next period
    chain.time_travel(hours=1)
    assert 1500 == escrow.functions.getAllLockedTokens().call()
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    chain.wait_for_receipt(tx)

    # Checks that no error
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    chain.wait_for_receipt(tx)

    # Ursula and Ursula(2) mint tokens for last periods
    chain.time_travel(hours=1)
    assert 1000 == escrow.functions.getAllLockedTokens().call()
    tx = escrow.functions.mint().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.mint().transact({'from': ursula2})

    chain.wait_for_receipt(tx)
    assert 1050 == web3.toInt(escrow.functions.getMinerInfo(VALUE_FIELD, ursula1, 0)).call()
    assert 521 == web3.toInt(escrow.functions.getMinerInfo(VALUE_FIELD, ursula2, 0)).call()

    events = mining_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['owner']
    assert 50 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() - 1 == event_args['period']
    event_args = events[1]['args']
    assert ursula2 == event_args['owner']
    assert 21 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() - 1 == event_args['period']

    assert 1 == policy_manager.functions.getPeriodsLength(ursula1).call()
    assert 1 == policy_manager.functions.getPeriodsLength(ursula2).call()
    period = escrow.functions.getCurrentPeriod().call() - 1
    assert period == policy_manager.functions.getPeriod(ursula1, 0).call()
    assert period == policy_manager.functions.getPeriod(ursula2, 0).call()

    # Only Ursula confirm activity for next period
    tx = escrow.functions.switchLock().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    chain.wait_for_receipt(tx)

    # Ursula can't confirm next period because end of locking
    chain.time_travel(hours=1)
    assert 500 == escrow.functions.getAllLockedTokens().call()
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmActivity().transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # But Ursula(2) can
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    chain.wait_for_receipt(tx)

    # Ursula mint tokens for next period
    chain.time_travel(hours=1)
    assert 500 == escrow.functions.getAllLockedTokens().call()
    tx = escrow.functions.mint().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    # But Ursula(2) can't get reward because she did not confirmed activity
    tx = escrow.functions.mint().transact({'from': ursula2})

    chain.wait_for_receipt(tx)
    assert 1163 == web3.toInt(escrow.functions.getMinerInfo(VALUE_FIELD, ursula1, 0)).call()
    assert 521 == web3.toInt(escrow.functions.getMinerInfo(VALUE_FIELD, ursula2, 0)).call()

    assert 3 == policy_manager.functions.getPeriodsLength(ursula1).call()
    assert 1 == policy_manager.functions.getPeriodsLength(ursula2).call()
    assert period + 1 == policy_manager.functions.getPeriod(ursula1, 1).call()
    assert period + 2 == policy_manager.functions.getPeriod(ursula1, 2).call()

    events = mining_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert ursula1 == event_args['owner']
    assert 113 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() - 1 == event_args['period']

    # Ursula(2) confirm next period and mint tokens
    tx = escrow.functions.switchLock().transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    chain.time_travel(hours=2)
    assert 0 == escrow.functions.getAllLockedTokens().call()
    tx = escrow.functions.mint().transact({'from': ursula2})

    chain.wait_for_receipt(tx)
    assert 1163 == web3.toInt(escrow.functions.getMinerInfo(VALUE_FIELD, ursula1, 0)).call()
    assert 634 == web3.toInt(escrow.functions.getMinerInfo(VALUE_FIELD, ursula2, 0)).call()

    assert 3 == policy_manager.functions.getPeriodsLength(ursula1).call()
    assert 3 == policy_manager.functions.getPeriodsLength(ursula2).call()
    assert period + 3 == policy_manager.functions.getPeriod(ursula2, 1).call()
    assert period + 4 == policy_manager.functions.getPeriod(ursula2, 2).call()

    events = mining_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert ursula2 == event_args['owner']
    assert 113 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() - 1 == event_args['period']

    # Ursula can't confirm and get reward because no locked tokens
    tx = escrow.functions.mint().transact({'from': ursula1})

    chain.wait_for_receipt(tx)
    assert 1163 == web3.toInt(escrow.functions.getMinerInfo(VALUE_FIELD, ursula1, 0)).call()

    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmActivity().transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Ursula can lock some tokens again
    tx =  escrow.functions.lock(500, 4).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.switchLock().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(ursula1).call()
    assert 500 == escrow.functions.calculateLockedTokens(ursula1, 1).call()
    assert 375 == escrow.functions.calculateLockedTokens(ursula1, 2).call()
    assert 250 == escrow.functions.calculateLockedTokens(ursula1, 3).call()
    assert 0 == escrow.functions.calculateLockedTokens(ursula1, 5).call()
    # And can increase lock
    tx =  escrow.functions.lock(100, 0).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 600 == escrow.functions.getLockedTokens(ursula1).call()
    assert 600 == escrow.functions.calculateLockedTokens(ursula1, 1).call()
    assert 450 == escrow.functions.calculateLockedTokens(ursula1, 2).call()
    assert 0 == escrow.functions.calculateLockedTokens(ursula1, 5).call()
    tx =  escrow.functions.lock(0, 2).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 600 == escrow.functions.getLockedTokens(ursula1).call()
    assert 600 == escrow.functions.calculateLockedTokens(ursula1, 1).call()
    assert 450 == escrow.functions.calculateLockedTokens(ursula1, 2).call()
    assert 0 == escrow.functions.calculateLockedTokens(ursula1, 5).call()
    tx =  escrow.functions.deposit(800, 1).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 1400 == escrow.functions.getLockedTokens(ursula1).call()
    assert 1400 == escrow.functions.calculateLockedTokens(ursula1, 1).call()
    assert 1000 == escrow.functions.calculateLockedTokens(ursula1, 3).call()
    assert 400 == escrow.functions.calculateLockedTokens(ursula1, 6).call()
    assert 0 == escrow.functions.calculateLockedTokens(ursula1, 8).call()

    # Ursula(2) can withdraw all
    tx =  escrow.functions.withdraw(634).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 10134 == token.functions.balanceOf(ursula2).call()

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
    deposit_log = escrow.events.Deposited.createFilter(fromBlock=0)

    # Initialize Escrow contract
    tx = escrow.functions.initialize().transact({'from': creator})
    chain.wait_for_receipt(tx)

    # Grant access to transfer tokens
    tx = token.functions.approve(escrow.address, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)

    # Deposit tokens for 1 owner
    owner = web3.eth.accounts[1]
    tx =  escrow.functions.preDeposit([owner], [1000], [10]).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 1000 == token.functions.balanceOf(escrow.address).call()
    assert 1000 == web3.toInt(escrow.functions.getMinerInfo(VALUE_FIELD, owner, 0).call())
    assert 1000 == escrow.functions.getLockedTokens(owner).call()
    assert 10 == web3.toInt(escrow.functions.getMinerInfo(MAX_RELEASE_PERIODS_FIELD, owner, 0).call())

    # Can't pre-deposit tokens again for same owner
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([web3.eth.accounts[1]], [1000], [10]).transact({'from': creator})
        chain.wait_for_receipt(tx)

    # Can't pre-deposit tokens with too low or too high value
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([web3.eth.accounts[2]], [1], [10]).transact({'from': creator})

        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([web3.eth.accounts[2]], [1501], [10]).transact({'from': creator})
        chain.wait_for_receipt(tx)

    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([web3.eth.accounts[2]], [500], [1]).transact({'from': creator})
        chain.wait_for_receipt(tx)

    # Deposit tokens for multiple owners
    owners = web3.eth.accounts[2:7]
    tx = escrow.functions.preDeposit(
        owners, [100, 200, 300, 400, 500], [50, 100, 150, 200, 250]).transact({'from': creator})
    chain.wait_for_receipt(tx)

    assert 2500 == token.functions.balanceOf(escrow.address).call()
    for index, owner in enumerate(owners):
        assert 100 * (index + 1) == web3.toInt(escrow.functions.getMinerInfo(VALUE_FIELD, owner, 0).call())
        assert 100 * (index + 1) == escrow.functions.getLockedTokens(owner).call()
        assert 50 * (index + 1) == \
            web3.toInt(escrow.functions.getMinerInfo(MAX_RELEASE_PERIODS_FIELD, owner, 0).call())

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
    tx = escrow.functions.initialize().transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx =  token.functions.transfer(miner, 1000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    balance = token.functions.balanceOf(miner).call()
    tx =  token.functions.approve(escrow.address, balance).transact({'from': miner})
    chain.wait_for_receipt(tx)
    tx =  escrow.functions.deposit(balance, 1).transact({'from': miner})
    chain.wait_for_receipt(tx)

    # Set miner ids
    miner_id = os.urandom(32)
    tx =  escrow.functions.setMinerId(miner_id).transact({'from': miner})

    chain.wait_for_receipt(tx)
    assert 1 == web3.toInt(escrow.functions.getMinerInfo(MINER_IDS_FIELD_LENGTH, miner, 0).call())

    assert miner_id == escrow.functions.getMinerInfo(MINER_ID_FIELD, miner, 0).call()
    miner_id = os.urandom(32)
    tx =  escrow.functions.setMinerId(miner_id).transact({'from': miner})
    chain.wait_for_receipt(tx)
    assert 2 == web3.toInt(escrow.functions.getMinerInfo(MINER_IDS_FIELD_LENGTH, miner, 0).call())

    assert miner_id == escrow.functions.getMinerInfo(MINER_ID_FIELD, miner, 1).call()


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
    assert 1500 == contract.functions.maxAllowableLockedTokens().call()

    # Initialize contract and miner
    policy_manager, _ = chain.provider.deploy_contract('PolicyManagerForMinersEscrowMock', token.address, contract.address)

    tx =  contract.functions.setPolicyManager(policy_manager.address).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = contract.functions.initialize().transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx =  token.functions.transfer(miner, 1000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    balance = token.functions.balanceOf(miner).call()
    tx =  token.functions.approve(contract.address, balance).transact({'from': miner})
    chain.wait_for_receipt(tx)
    tx =  contract.functions.deposit(balance, 1000).transact({'from': miner})
    chain.wait_for_receipt(tx)

    # Upgrade to the second version
    tx =  dispatcher.functions.upgrade(contract_library_v2.address).transact({'from': creator})

    chain.wait_for_receipt(tx)
    assert contract_library_v2.address == dispatcher.functions.target().call()
    assert 1500 == contract.functions.maxAllowableLockedTokens().call()
    assert 2 == contract.functions.valueToCheck().call()
    tx =  contract.functions.setValueToCheck(3).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 3 == contract.functions.valueToCheck().call()

    # Can't upgrade to the previous version or to the bad version
    contract_library_bad, _ = chain.provider.deploy_contract(
        'MinersEscrowBad', token.address, 2, 2, 2, 2, 2, 2, 2
    )

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
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  contract.functions.setValueToCheck(2).transact({'from': creator})
        chain.wait_for_receipt(tx)

    # Try to upgrade to the bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  dispatcher.functions.upgrade(contract_library_bad.address).transact({'from': creator})
        chain.wait_for_receipt(tx)
