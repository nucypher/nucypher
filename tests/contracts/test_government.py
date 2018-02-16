import pytest
from ethereum.tester import TransactionFailed
from populus.contracts.contract import PopulusContract


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
    escrow, _ = chain.provider.get_or_deploy_contract(
        'MinersEscrowV1Test', deploy_args=[
            [node1, node2, node3], [1, 2, 3]],
        deploy_transaction={'from': creator})
    dispatcher, _ = chain.provider.deploy_contract(
        'Dispatcher', deploy_args=[escrow.address],
        deploy_transaction={'from': creator})
    return dispatcher


@pytest.fixture()
def policy_manager(web3, chain):
    creator = web3.eth.accounts[0]
    # Creator deploys the escrow
    policy_manager, _ = chain.provider.get_or_deploy_contract(
        'PolicyManagerV1Test', deploy_transaction={'from': creator})
    dispatcher, _ = chain.provider.deploy_contract(
        'Dispatcher', deploy_args=[policy_manager.address],
        deploy_transaction={'from': creator})
    return dispatcher


def test_government(web3, chain, escrow, policy_manager):
    creator = web3.eth.accounts[0]
    node1 = web3.eth.accounts[1]
    node2 = web3.eth.accounts[2]
    node3 = web3.eth.accounts[3]

    # Deploy contract
    government_library, _ = chain.provider.get_or_deploy_contract(
        'Government', deploy_args=[escrow.address, policy_manager.address],
        deploy_transaction={'from': creator})
    government_dispatcher, _ = chain.provider.deploy_contract(
        'Dispatcher', deploy_args=[government_library.address],
        deploy_transaction={'from': creator})
    government = web3.eth.contract(
        government_library.abi,
        government_dispatcher.address,
        ContractFactoryClass=PopulusContract)

    # Transfer ownership
    tx = government.transact({'from': creator}).transferOwnership(government.address)
    chain.wait.for_receipt(tx)
    tx = escrow.transact({'from': creator}).transferOwnership(government.address)
    chain.wait.for_receipt(tx)
    tx = policy_manager.transact({'from': creator}).transferOwnership(government.address)
    chain.wait.for_receipt(tx)

    # Check that there are no voting before it's creation
    assert FINISHED_STATE == government.call().getVotingState()
    with pytest.raises(TransactionFailed):
        tx = government.transact({'from': node1}).vote(True)
        chain.wait.for_receipt(tx)
    with pytest.raises(TransactionFailed):
        tx = government.transact({'from': creator}).commitUpgrade()
        chain.wait.for_receipt(tx)

    # Create voting for update Government contract
    tx = government.transact({'from': creator}).createVoting(UPGRADE_GOVERNMENT, government_library.address)
    chain.wait.for_receipt(tx)

