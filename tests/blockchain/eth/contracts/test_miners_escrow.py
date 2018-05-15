import pytest
from eth_tester.exceptions import TransactionFailed
import os
from web3.contract import Contract


VALUE_FIELD = 0
DECIMALS_FIELD = 1
CONFIRMED_PERIOD_1_FIELD = 2
CONFIRMED_PERIOD_2_FIELD = 3
LAST_ACTIVE_PERIOD_FIELD = 4


@pytest.fixture()
def token(chain):
    # Create an ERC20 token
    token, _ = chain.provider.deploy_contract('NuCypherToken', 2 * 10 ** 9)
    return token


@pytest.fixture(params=[False, True])
def escrow_contract(web3, chain, token, request):
    def make_escrow(max_allowed_locked_tokens):
        # Creator deploys the escrow
        contract, _ = chain.provider.deploy_contract(
            'MinersEscrow', token.address, 1, 4 * 2 * 10 ** 7, 4, 4, 2, 100, max_allowed_locked_tokens)

        if request.param:
            dispatcher, _ = chain.provider.deploy_contract('Dispatcher', contract.address)
            contract = web3.eth.contract(
                abi=contract.abi,
                address=dispatcher.address,
                ContractFactoryClass=Contract)
        return contract

    return make_escrow


@pytest.mark.slow
def test_escrow(web3, chain, token, escrow_contract):
    escrow = escrow_contract(1500)
    creator = web3.eth.accounts[0]
    ursula1 = web3.eth.accounts[1]
    ursula2 = web3.eth.accounts[2]
    deposit_log = escrow.events.Deposited.createFilter(fromBlock='latest')
    lock_log = escrow.events.Locked.createFilter(fromBlock='latest')
    activity_log = escrow.events.ActivityConfirmed.createFilter(fromBlock='latest')
    divides_log = escrow.events.Divided.createFilter(fromBlock='latest')
    withdraw_log = escrow.events.Withdrawn.createFilter(fromBlock='latest')

    policy_manager, _ = chain.provider.deploy_contract(
        'PolicyManagerForMinersEscrowMock', token.address, escrow.address
    )
    tx = escrow.functions.setPolicyManager(policy_manager.address).transact()
    chain.wait_for_receipt(tx)

    # Give Ursula and Ursula(2) some coins
    tx = token.functions.transfer(ursula1, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = token.functions.transfer(ursula2, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 10000 == token.functions.balanceOf(ursula1).call()
    assert 10000 == token.functions.balanceOf(ursula2).call()

    # Ursula and Ursula(2) give Escrow rights to transfer
    tx = token.functions.approve(escrow.address, 1100).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 1100 == token.functions.allowance(ursula1, escrow.address).call()
    tx = token.functions.approve(escrow.address, 500).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 500 == token.functions.allowance(ursula2, escrow.address).call()

    # Ursula's withdrawal attempt won't succeed because nothing to withdraw
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(100).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # And can't lock because nothing to lock
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.lock(500, 2).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Check that nothing is locked
    assert 0 == escrow.functions.getLockedTokens(ursula1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2).call()
    assert 0 == escrow.functions.getLockedTokens(web3.eth.accounts[3]).call()

    # Ursula can't deposit tokens before Escrow initialization
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(1, 1).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Initialize Escrow contract
    tx = escrow.functions.initialize().transact({'from': creator})
    chain.wait_for_receipt(tx)

    # Ursula can't deposit and lock too low value
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(1, 10).transact({'from': ursula1})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, 1, web3.toBytes(10)).transact({'from': ursula1})
        chain.wait_for_receipt(tx)
    # And can't deposit and lock too high value
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(1501, 10).transact({'from': ursula1})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, 1501, web3.toBytes(10)).transact({'from': ursula1})
        chain.wait_for_receipt(tx)
    # And can't deposit for too short a period
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(1000, 1).transact({'from': ursula1})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, 1000, web3.toBytes(1)).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Ursula and Ursula(2) transfer some tokens to the escrow and lock them
    tx = escrow.functions.deposit(1000, 2).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 1000 == token.functions.balanceOf(escrow.address).call()
    assert 9000 == token.functions.balanceOf(ursula1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 3).call()

    events = deposit_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['owner']
    assert 1000 == event_args['value']
    assert 2 == event_args['periods']
    events = lock_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['owner']
    assert 1000 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['firstPeriod']
    assert 2 == event_args['periods']
    events = activity_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['owner']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 1000 == event_args['value']

    tx = escrow.functions.deposit(500, 2).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 1500 == token.functions.balanceOf(escrow.address).call()
    assert 9500 == token.functions.balanceOf(ursula2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2).call()
    assert 500 == escrow.functions.getLockedTokens(ursula2, 1).call()

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
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['firstPeriod']
    assert 2 == event_args['periods']
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
        tx = escrow.functions.withdraw(100).transact({'from': ursula1})
        chain.wait_for_receipt(tx)
    assert 1500 == token.functions.balanceOf(escrow.address).call()
    assert 9000 == token.functions.balanceOf(ursula1).call()

    # Ursula can deposit more tokens
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 1000 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 2).call()
    events = activity_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert ursula1 == event_args['owner']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 1000 == event_args['value']

    tx = token.functions.approveAndCall(escrow.address, 500, web3.toBytes(2)).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 2000 == token.functions.balanceOf(escrow.address).call()
    assert 8500 == token.functions.balanceOf(ursula1).call()
    assert 1500 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 500 == escrow.functions.getLockedTokens(ursula1, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 3).call()

    events = activity_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert ursula1 == event_args['owner']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 500 == event_args['value']

    # But can't deposit too high value
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(100, 2).transact({'from': ursula1})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, 100, web3.toBytes(2)).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Wait 1 period and checks locking
    chain.time_travel(hours=1)
    assert 1500 == escrow.functions.getLockedTokens(ursula1).call()

    # Confirm activity and wait 1 period
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    chain.time_travel(hours=1)
    assert 500 == escrow.functions.getLockedTokens(ursula1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 1).call()

    events = activity_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[4]['args']
    assert ursula1 == event_args['owner']
    assert escrow.functions.getCurrentPeriod().call() == event_args['period']
    assert 500 == event_args['value']

    # And Ursula can withdraw some tokens
    tx = escrow.functions.withdraw(100).transact({'from': ursula1})
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
        tx = escrow.functions.withdraw(1400).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # And Ursula can't lock again too low value
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.lock(1, 1).transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Ursula can deposit and lock more tokens
    tx = token.functions.approveAndCall(escrow.address, 500, web3.toBytes(2)).transact({'from': ursula1})
    chain.wait_for_receipt(tx)

    events = activity_log.get_all_entries()
    assert 6 == len(events)
    event_args = events[5]['args']
    assert ursula1 == event_args['owner']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 500 == event_args['value']

    tx = escrow.functions.lock(100, 2).transact({'from': ursula1})
    chain.wait_for_receipt(tx)

    events = activity_log.get_all_entries()
    assert 7 == len(events)
    event_args = events[6]['args']
    assert ursula1 == event_args['owner']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 100 == event_args['value']

    # Locked tokens will be updated in next period
    # Release rate will be updated too because of the end of previous locking
    assert 500 == escrow.functions.getLockedTokens(ursula1).call()
    assert 600 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 600 == escrow.functions.getLockedTokens(ursula1, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 3).call()
    chain.time_travel(hours=1)
    assert 600 == escrow.functions.getLockedTokens(ursula1).call()
    assert 600 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 2).call()

    # Ursula can increase lock
    tx = escrow.functions.lock(500, 2).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 600 == escrow.functions.getLockedTokens(ursula1).call()
    assert 1100 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 500 == escrow.functions.getLockedTokens(ursula1, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 3).call()
    chain.time_travel(hours=1)
    assert 1100 == escrow.functions.getLockedTokens(ursula1).call()

    # Ursula(2) increases lock by deposit more tokens using approveAndCall
    tx = token.functions.approveAndCall(escrow.address, 500, web3.toBytes(2)).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(ursula2).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 500 == escrow.functions.getLockedTokens(ursula2, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 3).call()
    chain.time_travel(hours=1)
    assert 1000 == escrow.functions.getLockedTokens(ursula2).call()

    # And increases locked time
    chain.time_travel(hours=1)
    tx = escrow.functions.divideStake(500, escrow.functions.getCurrentPeriod().call() + 1, 200, 1).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(ursula2).call()
    assert 500 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 200 == escrow.functions.getLockedTokens(ursula2, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 3).call()

    events = lock_log.get_all_entries()
    assert 8 == len(events)
    event_args = events[7]['args']
    assert ursula2 == event_args['owner']
    assert 200 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() - 1 == event_args['firstPeriod']
    assert 2 == event_args['periods']
    events = divides_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula2 == event_args['owner']
    assert 500 == event_args['oldValue']
    assert 1 == event_args['periods']
    assert 200 == event_args['newValue']
    assert 1 == event_args['periods']

    chain.time_travel(hours=1)
    tx = escrow.functions.divideStake(300, escrow.functions.getCurrentPeriod().call() + 1, 200, 1).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(ursula2).call()
    assert 500 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 400 == escrow.functions.getLockedTokens(ursula2, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 3).call()

    events = divides_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula2 == event_args['owner']
    assert 300 == event_args['oldValue']
    assert 1 == event_args['periods']
    assert 200 == event_args['newValue']
    assert 1 == event_args['periods']

    tx = escrow.functions.divideStake(200, escrow.functions.getCurrentPeriod().call() + 2, 100, 1).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(ursula2).call()
    assert 500 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 400 == escrow.functions.getLockedTokens(ursula2, 2).call()
    assert 100 == escrow.functions.getLockedTokens(ursula2, 3).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 4).call()

    events = divides_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert ursula2 == event_args['owner']
    assert 200 == event_args['oldValue']
    assert 1 == event_args['periods']
    assert 100 == event_args['newValue']
    assert 1 == event_args['periods']

    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    chain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    chain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    chain.wait_for_receipt(tx)

    events = activity_log.get_all_entries()
    assert 12 == len(events)
    event_args = events[10]['args']
    assert ursula2 == event_args['owner']
    assert escrow.functions.getCurrentPeriod().call() == event_args['period']
    assert 400 == event_args['value']
    event_args = events[11]['args']
    assert ursula2 == event_args['owner']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 100 == event_args['value']

    assert 5 == len(deposit_log.get_all_entries())
    assert 10 == len(lock_log.get_all_entries())
    assert 1 == len(withdraw_log.get_all_entries())


@pytest.mark.slow
def test_locked_distribution(web3, chain, token, escrow_contract):
    escrow = escrow_contract(5 * 10 ** 8)
    NULL_ADDR = '0x' + '0' * 40
    creator = web3.eth.accounts[0]

    # Give Escrow tokens for reward and initialize contract
    tx = token.functions.transfer(escrow.address, 10 ** 9).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.initialize().transact({'from': creator})
    chain.wait_for_receipt(tx)

    miners = web3.eth.accounts[1:]
    amount = token.functions.balanceOf(creator).call() // 2
    largest_locked = amount

    # Airdrop
    for miner in miners:
        tx = token.functions.transfer(miner, amount).transact({'from': creator})
        chain.wait_for_receipt(tx)
        amount = amount // 2

    # Lock
    for index, miner in enumerate(miners):
        balance = token.functions.balanceOf(miner).call()
        tx = token.functions.approve(escrow.address, balance).transact({'from': miner})
        chain.wait_for_receipt(tx)
        tx = escrow.functions.deposit(balance, index + 2).transact({'from': miner})
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

    address_stop, index_stop, shift = escrow.functions.findCumSum(0, 1, len(miners)).call()
    assert NULL_ADDR != address_stop
    assert 0 != shift
    address_stop, index_stop, shift = escrow.functions.findCumSum(0, 1, len(miners) + 1).call()
    assert NULL_ADDR == address_stop
    assert 0 == index_stop
    assert 0 == shift

    for index, _ in enumerate(miners[:-1]):
        address_stop, index_stop, shift = escrow.functions.findCumSum(0, 1, index + 2).call()
        assert miners[index + 1] == address_stop
        assert index + 1 == index_stop
        assert 1 == shift

    # Test miners iteration
    assert len(miners) == escrow.functions.getMinersLength().call()
    for index, miner in enumerate(miners):
        assert miners[index] == escrow.functions.miners(index).call()


@pytest.mark.slow
def test_mining(web3, chain, token, escrow_contract):
    escrow = escrow_contract(1500)
    creator = web3.eth.accounts[0]
    ursula1 = web3.eth.accounts[1]
    ursula2 = web3.eth.accounts[2]

    mining_log = escrow.events.Mined.createFilter(fromBlock='latest')
    deposit_log = escrow.events.Deposited.createFilter(fromBlock='latest')
    lock_log = escrow.events.Locked.createFilter(fromBlock='latest')
    activity_log = escrow.events.ActivityConfirmed.createFilter(fromBlock='latest')
    divides_log = escrow.events.Divided.createFilter(fromBlock='latest')
    withdraw_log = escrow.events.Withdrawn.createFilter(fromBlock='latest')

    # Give Escrow tokens for reward and initialize contract
    tx = token.functions.transfer(escrow.address, 10 ** 9).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.initialize().transact({'from': creator})
    chain.wait_for_receipt(tx)

    policy_manager, _ = chain.provider.deploy_contract(
        'PolicyManagerForMinersEscrowMock', token.address, escrow.address
    )
    tx = escrow.functions.setPolicyManager(policy_manager.address).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert policy_manager.address == escrow.functions.policyManager().call()

    # Give Ursula and Ursula(2) some coins
    tx = token.functions.transfer(ursula1, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = token.functions.transfer(ursula2, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)

    # Ursula can't confirm and mint because no locked tokens
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.mint().transact({'from': ursula1})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmActivity().transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Ursula and Ursula(2) give Escrow rights to transfer
    tx = token.functions.approve(escrow.address, 2000).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = token.functions.approve(escrow.address, 750).transact({'from': ursula2})
    chain.wait_for_receipt(tx)

    # Ursula and Ursula(2) transfer some tokens to the escrow and lock them
    tx = escrow.functions.deposit(1000, 2).transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.deposit(500, 2).transact({'from': ursula2})
    chain.wait_for_receipt(tx)

    # Ursula divides her stake
    tx = escrow.functions.divideStake(1000, escrow.functions.getCurrentPeriod().call() + 2, 500, 1).transact({'from': ursula1})
    chain.wait_for_receipt(tx)

    # Using locked tokens starts from next period
    assert 0 == escrow.functions.getAllLockedTokens().call()

    # Ursula can't use method from Issuer contract
    with pytest.raises(Exception):
        tx = escrow.functions.mint(1, 1, 1, 1, 1).transact({'from': ursula1})
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
    # And only Ursula confirm activity for next period
    chain.time_travel(hours=1)
    assert 1000 == escrow.functions.getAllLockedTokens().call()
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.mint().transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 1046 == escrow.functions.minerInfo(ursula1).call()[VALUE_FIELD]
    assert 525 == escrow.functions.minerInfo(ursula2).call()[VALUE_FIELD]

    events = mining_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['owner']
    assert 46 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() - 1 == event_args['period']
    event_args = events[1]['args']
    assert ursula2 == event_args['owner']
    assert 25 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() - 1 == event_args['period']

    assert 1 == policy_manager.functions.getPeriodsLength(ursula1).call()
    assert 1 == policy_manager.functions.getPeriodsLength(ursula2).call()
    period = escrow.functions.getCurrentPeriod().call() - 1
    assert period == policy_manager.functions.getPeriod(ursula1, 0).call()
    assert period == policy_manager.functions.getPeriod(ursula2, 0).call()

    # Ursula try to mint again
    tx = escrow.functions.mint().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 1046 == escrow.functions.minerInfo(ursula1).call()[VALUE_FIELD]
    events = mining_log.get_all_entries()
    assert 2 == len(events)

    # Ursula can't confirm next period
    chain.time_travel(hours=1)
    assert 500 == escrow.functions.getAllLockedTokens().call()
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmActivity().transact({'from': ursula1})
        chain.wait_for_receipt(tx)
    # But Ursula(2) can
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    chain.wait_for_receipt(tx)

    # Ursula mint tokens
    chain.time_travel(hours=1)
    assert 500 == escrow.functions.getAllLockedTokens().call()
    tx = escrow.functions.mint().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    # But Ursula(2) can't get reward because she did not confirm activity
    tx = escrow.functions.mint().transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 1152 == escrow.functions.minerInfo(ursula1).call()[VALUE_FIELD]
    assert 525 == escrow.functions.minerInfo(ursula2).call()[VALUE_FIELD]

    events = mining_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert ursula1 == event_args['owner']
    assert 106 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() - 1 == event_args['period']

    assert 3 == policy_manager.functions.getPeriodsLength(ursula1).call()
    assert 1 == policy_manager.functions.getPeriodsLength(ursula2).call()
    assert period + 1 == policy_manager.functions.getPeriod(ursula1, 1).call()
    assert period + 2 == policy_manager.functions.getPeriod(ursula1, 2).call()

    # Ursula(2) mint tokens
    chain.time_travel(hours=1)
    assert 0 == escrow.functions.getAllLockedTokens().call()
    tx = escrow.functions.mint().transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 1152 == escrow.functions.minerInfo(ursula1).call()[VALUE_FIELD]
    assert 575 == escrow.functions.minerInfo(ursula2).call()[VALUE_FIELD]

    events = mining_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert ursula2 == event_args['owner']
    assert 50 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() - 1 == event_args['period']

    period = escrow.functions.getCurrentPeriod().call() - 1
    assert 3 == policy_manager.functions.getPeriodsLength(ursula1).call()
    assert 2 == policy_manager.functions.getPeriodsLength(ursula2).call()
    assert period == policy_manager.functions.getPeriod(ursula2, 1).call()

    # Ursula(2) can't more confirm activity
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmActivity().transact({'from': ursula2})
        chain.wait_for_receipt(tx)

    # Ursula can't confirm and get reward because no locked tokens
    tx = escrow.functions.mint().transact({'from': ursula1})
    chain.wait_for_receipt(tx)
    assert 1152 == escrow.functions.minerInfo(ursula1).call()[VALUE_FIELD]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmActivity().transact({'from': ursula1})
        chain.wait_for_receipt(tx)

    # Ursula(2) deposits and locks more tokens
    tx = escrow.functions.deposit(250, 4).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.lock(500, 2).transact({'from': ursula2})
    chain.wait_for_receipt(tx)

    # Ursula(2) mint only one period (by using deposit/approveAndCall function)
    chain.time_travel(hours=5)
    tx = token.functions.approveAndCall(escrow.address, 100, web3.toBytes(2)).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 1152 == escrow.functions.minerInfo(ursula1).call()[VALUE_FIELD]
    assert 1025 == escrow.functions.minerInfo(ursula2).call()[VALUE_FIELD]

    period = escrow.functions.getCurrentPeriod().call() - 4
    assert 3 == policy_manager.functions.getPeriodsLength(ursula2).call()
    assert period == policy_manager.functions.getPeriod(ursula2, 2).call()

    events = mining_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[4]['args']
    assert ursula2 == event_args['owner']
    assert 100 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() - 1 == event_args['period']

    # Ursula(2) confirm activity for remaining periods
    chain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    chain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    chain.wait_for_receipt(tx)

    # Ursula(2) can withdraw all
    chain.time_travel(hours=2)
    assert 0 == escrow.functions.getLockedTokens(ursula2).call()
    tx = escrow.functions.withdraw(1083).transact({'from': ursula2})
    chain.wait_for_receipt(tx)
    assert 0 == escrow.functions.minerInfo(ursula2).call()[VALUE_FIELD]
    assert 10233 == token.functions.balanceOf(ursula2).call()

    events = withdraw_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula2 == event_args['owner']
    assert 1083 == event_args['value']

    assert 4 == len(deposit_log.get_all_entries())
    assert 6 == len(lock_log.get_all_entries())
    assert 1 == len(divides_log.get_all_entries())
    assert 10 == len(activity_log.get_all_entries())


@pytest.mark.slow
def test_pre_deposit(web3, chain, token, escrow_contract):
    escrow = escrow_contract(1500)
    creator = web3.eth.accounts[0]
    deposit_log = escrow.events.Deposited.createFilter(fromBlock='latest')

    # Initialize Escrow contract
    tx = escrow.functions.initialize().transact({'from': creator})
    chain.wait_for_receipt(tx)

    # Grant access to transfer tokens
    tx = token.functions.approve(escrow.address, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)

    # Deposit tokens for 1 owner
    owner = web3.eth.accounts[1]
    tx = escrow.functions.preDeposit([owner], [1000], [10]).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 1000 == token.functions.balanceOf(escrow.address).call()
    assert 1000 == escrow.functions.minerInfo(owner).call()[VALUE_FIELD]
    assert 0 == escrow.functions.getLockedTokens(owner).call()
    assert 1000 == escrow.functions.getLockedTokens(owner, 1).call()
    assert 1000 == escrow.functions.getLockedTokens(owner, 10).call()
    assert 0 == escrow.functions.getLockedTokens(owner, 11).call()

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
        assert 100 * (index + 1) == escrow.functions.minerInfo(owner).call()[VALUE_FIELD]
        assert 100 * (index + 1) == escrow.functions.getLockedTokens(owner, 1).call()
        assert 100 * (index + 1) == escrow.functions.getLockedTokens(owner, 50 * (index + 1)).call()
        assert 0 == escrow.functions.getLockedTokens(owner, 50 * (index + 1) + 1).call()

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


@pytest.mark.slow
def test_miner_id(web3, chain, token, escrow_contract):
    escrow = escrow_contract(5 * 10 ** 8)
    creator = web3.eth.accounts[0]
    miner = web3.eth.accounts[1]

    # Initialize contract and miner
    tx = escrow.functions.initialize().transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = token.functions.transfer(miner, 1000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    balance = token.functions.balanceOf(miner).call()
    tx = token.functions.approve(escrow.address, balance).transact({'from': miner})
    chain.wait_for_receipt(tx)
    tx = escrow.functions.deposit(balance, 2).transact({'from': miner})
    chain.wait_for_receipt(tx)

    # Set miner ids
    miner_id = os.urandom(32)
    tx = escrow.functions.setMinerId(miner_id).transact({'from': miner})
    chain.wait_for_receipt(tx)
    assert 1 == escrow.functions.getMinerIdsLength(miner).call()

    assert miner_id == escrow.functions.getMinerId(miner, 0).call()
    miner_id = os.urandom(32)
    tx = escrow.functions.setMinerId(miner_id).transact({'from': miner})
    chain.wait_for_receipt(tx)
    assert 2 == escrow.functions.getMinerIdsLength(miner).call()

    assert miner_id == escrow.functions.getMinerId(miner, 1).call()


@pytest.mark.slow
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

    tx = contract.functions.setPolicyManager(policy_manager.address).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = contract.functions.initialize().transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx = token.functions.transfer(miner, 1000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    balance = token.functions.balanceOf(miner).call()
    tx = token.functions.approve(contract.address, balance).transact({'from': miner})
    chain.wait_for_receipt(tx)
    tx = contract.functions.deposit(balance, 1000).transact({'from': miner})
    chain.wait_for_receipt(tx)

    # Upgrade to the second version
    tx = dispatcher.functions.upgrade(contract_library_v2.address).transact({'from': creator})

    chain.wait_for_receipt(tx)
    assert contract_library_v2.address == dispatcher.functions.target().call()
    assert 1500 == contract.functions.maxAllowableLockedTokens().call()
    assert policy_manager.address == contract.functions.policyManager().call()
    assert 2 == contract.functions.valueToCheck().call()
    tx = contract.functions.setValueToCheck(3).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 3 == contract.functions.valueToCheck().call()

    # Can't upgrade to the previous version or to the bad version
    contract_library_bad, _ = chain.provider.deploy_contract(
        'MinersEscrowBad', token.address, 2, 2, 2, 2, 2, 2, 2
    )

    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_v1.address).transact({'from': creator})
        chain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address).transact({'from': creator})
        chain.wait_for_receipt(tx)

    # But can rollback
    tx = dispatcher.functions.rollback().transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_library_v1.address == dispatcher.functions.target().call()
    assert policy_manager.address == contract.functions.policyManager().call()

    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract.functions.setValueToCheck(2).transact({'from': creator})
        chain.wait_for_receipt(tx)

    # Try to upgrade to the bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address).transact({'from': creator})
        chain.wait_for_receipt(tx)
