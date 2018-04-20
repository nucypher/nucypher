import pytest
from eth_tester.exceptions import TransactionFailed
from web3.contract import Contract


NULL_ADDR = '0x' + '0' * 40

ACTIVE_STATE = 0
UPGRADE_WAITING_STATE = 1
FINISHED_STATE = 2

UPGRADE_GOVERNMENT = 0
UPGRADE_ESCROW = 1
UPGRADE_POLICY_MANAGER = 2
ROLLBACK_GOVERNMENT = 3
ROLLBACK_ESCROW = 4
ROLLBACK_POLICY_MANAGER = 5


@pytest.fixture()
def escrow(web3, chain):
    creator = web3.eth.accounts[0]
    node1 = web3.eth.accounts[1]
    node2 = web3.eth.accounts[2]
    node3 = web3.eth.accounts[3]

    # Creator deploys the escrow
    escrow_library, _ = chain.provider.get_or_deploy_contract(
        'MinersEscrowV1Mock', [node1, node2, node3], [1, 2, 3]
    )

    escrow_dispatcher, _ = chain.provider.get_or_deploy_contract(
        'Dispatcher', escrow_library.address
    )
    escrow = web3.eth.contract(
        abi=escrow_library.abi,
        address=escrow_dispatcher.address,
        ContractFactoryClass=Contract)
    return escrow


@pytest.fixture()
def policy_manager(web3, chain):
    creator = web3.eth.accounts[0]
    # Creator deploys the escrow
    policy_manager, _ = chain.provider.get_or_deploy_contract('PolicyManagerV1Mock')
    dispatcher, _ = chain.provider.deploy_contract('Dispatcher', policy_manager.address)
    return dispatcher


def test_voting(web3, chain, escrow, policy_manager):
    creator = web3.eth.accounts[0]
    node1 = web3.eth.accounts[1]
    node2 = web3.eth.accounts[2]
    node3 = web3.eth.accounts[3]

    # Deploy contract
    government_library, _ = chain.provider.get_or_deploy_contract(
        'Government', escrow.address, policy_manager.address, 1,
    )
    government_dispatcher, _ = chain.provider.deploy_contract(
        'Dispatcher', government_library.address
    )
    government = web3.eth.contract(
        abi=government_library.abi,
        address=government_dispatcher.address,
        ContractFactoryClass=Contract
    )

    voting_created_log = government.eventFilter('VotingCreated')
    upgrade_committed_log = government.eventFilter('UpgradeCommitted')

    # Transfer ownership
    tx = government.transact({'from': creator}).transferOwnership(government.address)
    chain.wait_for_receipt(tx)

    # Check that there are no voting before it's creation
    assert FINISHED_STATE == government.call().getVotingState()
    with pytest.raises(TransactionFailed):
        tx = government.transact({'from': node1}).vote(True)
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = government.transact({'from': creator}).commitUpgrade()
        chain.wait_for_receipt(tx)

    # Deploy second version of the government contract
    government_library_v2, _ = chain.provider.deploy_contract(
        'Government', escrow.address, policy_manager.address, 1,
    )
    assert government_library.address != government_library_v2.address

    # Only tokens owner can create voting
    with pytest.raises(TransactionFailed):
        tx = government.transact({'from': creator}).createVoting(
            UPGRADE_GOVERNMENT, government_library_v2.address)
        chain.wait_for_receipt(tx)

    # Create voting for update Government contract
    tx = government.transact({'from': node1}).createVoting(
        UPGRADE_GOVERNMENT, government_library_v2.address)
    chain.wait_for_receipt(tx)
    assert 1 == government.call().votingNumber()
    assert UPGRADE_GOVERNMENT == government.call().votingType()
    assert government_library_v2.address == government.call().newAddress()
    assert ACTIVE_STATE == government.call().getVotingState()
    assert 0 == government.call().votesFor()
    assert 0 == government.call().votesAgainst()

    # Can't commit upgrade before end of voting
    with pytest.raises(TransactionFailed):
        tx = government.transact({'from': creator}).commitUpgrade()
        chain.wait_for_receipt(tx)
    # Can't create new voting before end of previous voting
    with pytest.raises(TransactionFailed):
        tx = government.transact({'from': creator}).createVoting(
            UPGRADE_GOVERNMENT, government_library_v2.address)
        chain.wait_for_receipt(tx)

    # Nodes vote against update
    tx = government.transact({'from': node1}).vote(True)
    chain.wait_for_receipt(tx)
    assert 1 == government.call().votesFor()
    assert 0 == government.call().votesAgainst()
    tx = government.transact({'from': node2}).vote(False)
    chain.wait_for_receipt(tx)
    assert 1 == government.call().votesFor()
    assert 2 == government.call().votesAgainst()
    assert ACTIVE_STATE == government.call().getVotingState()

    # Can't vote again
    with pytest.raises(TransactionFailed):
        tx = government.transact({'from': node2}).vote(False)
        chain.wait_for_receipt(tx)

    # Wait until the end of voting
    chain.wait_time(1)
    assert FINISHED_STATE == government.call().getVotingState()
    assert government_library.address == government_dispatcher.call().target()
    assert 1 == government.call().votingNumber()

    # Can't vote after the ending
    with pytest.raises(TransactionFailed):
        tx = government.transact({'from': node3}).vote(False)
        chain.wait_for_receipt(tx)
    # Can't commit upgrade because nodes votes against upgrade
    with pytest.raises(TransactionFailed):
        tx = government.transact({'from': creator}).commitUpgrade()
        chain.wait_for_receipt(tx)

    # Create voting for update Government contract again
    tx = government.transact({'from': node1}).createVoting(
        UPGRADE_GOVERNMENT, government_library_v2.address)
    chain.wait_for_receipt(tx)
    assert 2 == government.call().votingNumber()
    assert UPGRADE_GOVERNMENT == government.call().votingType()
    assert government_library_v2.address == government.call().newAddress()
    assert ACTIVE_STATE == government.call().getVotingState()
    assert 0 == government.call().votesFor()
    assert 0 == government.call().votesAgainst()

    # Nodes vote for update
    tx = government.transact({'from': node1}).vote(False)
    chain.wait_for_receipt(tx)
    tx = government.transact({'from': node2}).vote(True)
    chain.wait_for_receipt(tx)
    assert 2 == government.call().votesFor()
    assert 1 == government.call().votesAgainst()
    assert ACTIVE_STATE == government.call().getVotingState()

    # Wait until the end of voting
    chain.wait_time(1)
    assert UPGRADE_WAITING_STATE == government.call().getVotingState()
    assert government_library.address == government_dispatcher.call().target()
    assert 2 == government.call().votingNumber()

    # Can't vote after the ending
    with pytest.raises(TransactionFailed):
        tx = government.transact({'from': node3}).vote(True)
        chain.wait_for_receipt(tx)
    # Can't create new voting before upgrading
    with pytest.raises(TransactionFailed):
        tx = government.transact({'from': creator}).createVoting(
            UPGRADE_GOVERNMENT, government_library_v2.address)
        chain.wait_for_receipt(tx)

    # Commit upgrade
    tx = government.transact({'from': node2}).commitUpgrade()
    chain.wait_for_receipt(tx)
    assert FINISHED_STATE == government.call().getVotingState()
    assert government_library_v2.address == government_dispatcher.call().target()

    # Create voting for update Government contract again without voting
    tx = government.transact({'from': node2}).createVoting(
        UPGRADE_GOVERNMENT, government_library.address)
    chain.wait_for_receipt(tx)
    assert 3 == government.call().votingNumber()
    assert ACTIVE_STATE == government.call().getVotingState()
    assert 0 == government.call().votesFor()
    assert 0 == government.call().votesAgainst()

    # Wait until the end of voting
    chain.wait_time(1)
    assert FINISHED_STATE == government.call().getVotingState()

    # Create voting for update Government contract again with equal voting
    tx = government.transact({'from': node3}).createVoting(
        UPGRADE_GOVERNMENT, government_library.address)
    chain.wait_for_receipt(tx)
    assert 4 == government.call().votingNumber()
    assert ACTIVE_STATE == government.call().getVotingState()
    tx = government.transact({'from': node1}).vote(False)
    chain.wait_for_receipt(tx)
    tx = government.transact({'from': node2}).vote(False)
    chain.wait_for_receipt(tx)
    tx = government.transact({'from': node3}).vote(True)
    chain.wait_for_receipt(tx)
    assert 3 == government.call().votesFor()
    assert 3 == government.call().votesAgainst()

    # Wait until the end of voting
    chain.wait_time(1)
    assert FINISHED_STATE == government.call().getVotingState()

    # Check events
    events = voting_created_log.get_all_entries()
    assert 4 == len(events)
    events = upgrade_committed_log.get_all_entries()
    assert 1 == len(events)


def test_upgrade(web3, chain, escrow, policy_manager):
    creator = web3.eth.accounts[0]
    node1 = web3.eth.accounts[1]

    # Deploy contract
    government_library_v1, _ = chain.provider.deploy_contract(
        'Government', escrow.address, policy_manager.address, 1,
    )
    government_dispatcher, _ = chain.provider.deploy_contract(
        'Dispatcher', government_library_v1.address,
    )
    government = web3.eth.contract(
        abi=government_library_v1.abi,
        address=government_dispatcher.address,
        ContractFactoryClass=Contract
    )

    # Deploy second version of the government contract
    government_library_v2, _ = chain.provider.deploy_contract(
        'Government', escrow.address, policy_manager.address, 1,
    )
    # Get first version of the escrow contract
    escrow_library_v1 = chain.provider.get_contract(
        'MinersEscrowV1Mock'
    )
    # Deploy second version of the escrow contract
    escrow_library_v2, _ = chain.provider.deploy_contract(
        'MinersEscrowV1Mock', [node1], [1]
    )
    # Get first version of the policy manager contract
    policy_manager_library_v1 = chain.provider.get_contract('PolicyManagerV1Mock')
    # Deploy second version of the policy manager contract
    policy_manager_library_v2, _ = chain.provider.deploy_contract('PolicyManagerV1Mock')

    voting_created_log = government.eventFilter('VotingCreated')
    upgrade_committed_log = government.eventFilter('UpgradeCommitted')

    # Transfer ownership
    tx = government.transact({'from': creator}).transferOwnership(government.address)
    chain.wait_for_receipt(tx)
    tx = escrow.transact({'from': creator}).transferOwnership(government.address)
    chain.wait_for_receipt(tx)
    tx = policy_manager.transact({'from': creator}).transferOwnership(government.address)
    chain.wait_for_receipt(tx)

    # Vote and upgrade government contract
    tx = government.transact({'from': node1}).createVoting(
        UPGRADE_GOVERNMENT, government_library_v2.address)
    chain.wait_for_receipt(tx)

    events = voting_created_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert 1 == event_args['votingNumber']
    assert UPGRADE_GOVERNMENT == event_args['votingType']
    assert government_library_v2.address == event_args['newAddress']

    tx = government.transact({'from': node1}).vote(True)
    chain.wait_for_receipt(tx)
    chain.wait_time(1)
    tx = government.transact({'from': node1}).commitUpgrade()
    chain.wait_for_receipt(tx)
    assert government_library_v2.address == government_dispatcher.call().target()

    events = government.events.UpgradeCommitted()
    events = upgrade_committed_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert 1 == event_args['votingNumber']
    assert UPGRADE_GOVERNMENT == event_args['votingType']
    assert government_library_v2.address == event_args['newAddress']

    # Vote and rollback government contract
    tx = government.transact({'from': node1}).createVoting(ROLLBACK_GOVERNMENT, NULL_ADDR)
    chain.wait_for_receipt(tx)

    events = voting_created_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert 2 == event_args['votingNumber']
    assert ROLLBACK_GOVERNMENT == event_args['votingType']
    assert NULL_ADDR == event_args['newAddress']

    tx = government.transact({'from': node1}).vote(True)
    chain.wait_for_receipt(tx)
    chain.wait_time(1)
    tx = government.transact({'from': node1}).commitUpgrade()
    chain.wait_for_receipt(tx)
    assert government_library_v1.address == government_dispatcher.call().target()

    events = upgrade_committed_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert 2 == event_args['votingNumber']
    assert ROLLBACK_GOVERNMENT == event_args['votingType']
    assert NULL_ADDR == event_args['newAddress']

    # Vote and upgrade escrow contract
    tx = government.transact({'from': node1}).createVoting(
        UPGRADE_ESCROW, escrow_library_v2.address)
    chain.wait_for_receipt(tx)

    events = voting_created_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert 3 == event_args['votingNumber']
    assert UPGRADE_ESCROW == event_args['votingType']
    assert escrow_library_v2.address == event_args['newAddress']

    tx = government.transact({'from': node1}).vote(True)
    chain.wait_for_receipt(tx)
    chain.wait_time(1)
    tx = government.transact({'from': node1}).commitUpgrade()
    chain.wait_for_receipt(tx)
    assert escrow_library_v2.address == escrow.call().target()

    events = upgrade_committed_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert 3 == event_args['votingNumber']
    assert UPGRADE_ESCROW == event_args['votingType']
    assert escrow_library_v2.address == event_args['newAddress']

    # Vote and rollback escrow contract
    tx = government.transact({'from': node1}).createVoting(ROLLBACK_ESCROW, NULL_ADDR)
    chain.wait_for_receipt(tx)

    events = voting_created_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert 4 == event_args['votingNumber']
    assert ROLLBACK_ESCROW == event_args['votingType']
    assert NULL_ADDR == event_args['newAddress']

    tx = government.transact({'from': node1}).vote(True)
    chain.wait_for_receipt(tx)
    chain.wait_time(1)
    tx = government.transact({'from': node1}).commitUpgrade()
    chain.wait_for_receipt(tx)

    assert escrow_library_v1.address == escrow.call().target()

    events = upgrade_committed_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert 4 == event_args['votingNumber']
    assert ROLLBACK_ESCROW == event_args['votingType']
    assert NULL_ADDR == event_args['newAddress']

    # Vote and upgrade policy manager contract
    tx = government.transact({'from': node1}).createVoting(
        UPGRADE_POLICY_MANAGER, policy_manager_library_v2.address)
    chain.wait_for_receipt(tx)

    events = voting_created_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[4]['args']
    assert 5 == event_args['votingNumber']
    assert UPGRADE_POLICY_MANAGER == event_args['votingType']
    assert policy_manager_library_v2.address == event_args['newAddress']

    tx = government.transact({'from': node1}).vote(True)
    chain.wait_for_receipt(tx)
    chain.wait_time(1)
    tx = government.transact({'from': node1}).commitUpgrade()
    chain.wait_for_receipt(tx)
    assert policy_manager_library_v2.address == policy_manager.call().target()

    events = upgrade_committed_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[4]['args']
    assert 5 == event_args['votingNumber']
    assert UPGRADE_POLICY_MANAGER == event_args['votingType']
    assert policy_manager_library_v2.address == event_args['newAddress']

    # Vote and rollback policy manager contract
    tx = government.transact({'from': node1}).createVoting(ROLLBACK_POLICY_MANAGER, NULL_ADDR)
    chain.wait_for_receipt(tx)

    events = voting_created_log.get_all_entries()
    assert 6 == len(events)
    event_args = events[5]['args']
    assert 6 == event_args['votingNumber']
    assert ROLLBACK_POLICY_MANAGER == event_args['votingType']
    assert NULL_ADDR == event_args['newAddress']

    tx = government.transact({'from': node1}).vote(True)
    chain.wait_for_receipt(tx)
    chain.wait_time(1)
    tx = government.transact({'from': node1}).commitUpgrade()
    chain.wait_for_receipt(tx)
    assert policy_manager_library_v1.address == policy_manager.call().target()

    events = upgrade_committed_log.get_all_entries()
    assert 6 == len(events)
    event_args = events[5]['args']
    assert 6 == event_args['votingNumber']
    assert ROLLBACK_POLICY_MANAGER == event_args['votingType']
    assert NULL_ADDR == event_args['newAddress']


def test_verifying_state(web3, chain):
    creator = web3.eth.accounts[0]
    address1 = web3.eth.accounts[1]
    address2 = web3.eth.accounts[2]

    # Deploy contract
    government_library_v1, _ = chain.provider.deploy_contract(
        'Government', address1, address2, 1,
    )
    government_dispatcher, _ = chain.provider.deploy_contract(
        'Dispatcher', government_library_v1.address
    )

    # Deploy second version of the government contract
    government_library_v2, _ = chain.provider.deploy_contract(
        'GovernmentV2Mock', address2, address1, 2,
    )
    government = web3.eth.contract(
        abi=government_library_v2.abi,
        address=government_dispatcher.address,
        ContractFactoryClass=Contract)

    # Upgrade to the second version
    tx = government_dispatcher.transact({'from': creator}).upgrade(government_library_v2.address)
    chain.wait_for_receipt(tx)
    assert government_library_v2.address == government_dispatcher.call().target()
    assert address2 == government.call().escrow()
    assert address1 == government.call().policyManager()
    assert 2 * 60 * 60 == government.call().votingDurationSeconds()
    tx = government.transact({'from': creator}).setValueToCheck(3)
    chain.wait_for_receipt(tx)
    assert 3 == government.call().valueToCheck()

    # Can't upgrade to the previous version or to the bad version
    government_library_bad, _ = chain.provider.deploy_contract('GovernmentBad')
    with pytest.raises(TransactionFailed):
        tx = government_dispatcher.transact({'from': creator}).upgrade(government_library_v1.address)
        chain.wait_for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = government_dispatcher.transact({'from': creator}).upgrade(government_library_bad.address)
        chain.wait_for_receipt(tx)

    # But can rollback
    tx = government_dispatcher.transact({'from': creator}).rollback()
    chain.wait_for_receipt(tx)
    assert government_library_v1.address == government_dispatcher.call().target()
    assert address1 == government.call().escrow()
    assert address2 == government.call().policyManager()
    assert 60 * 60 == government.call().votingDurationSeconds()
    with pytest.raises(TransactionFailed):
        tx = government.transact({'from': creator}).setValueToCheck(2)
        chain.wait_for_receipt(tx)

    # Try to upgrade to the bad version
    with pytest.raises(TransactionFailed):
        tx = government_dispatcher.transact({'from': creator}).upgrade(government_library_bad.address)
        chain.wait_for_receipt(tx)
