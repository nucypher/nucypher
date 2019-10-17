"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import os

import pytest
from eth_tester.exceptions import TransactionFailed
from eth_utils import keccak
from web3.contract import Contract
from web3.exceptions import BadFunctionCallOutput

from nucypher.blockchain.eth.interfaces import BlockchainInterface


@pytest.mark.slow
def test_staking_interface(testerchain, policy_manager, preallocation_escrow):
    """
    Test that interface executes only predefined methods
    """
    owner = testerchain.client.accounts[1]

    # Create fake instance of the user escrow contract
    fake_preallocation_escrow = testerchain.client.get_contract(
        abi=policy_manager.abi,
        address=preallocation_escrow.address,
        ContractFactoryClass=Contract)

    # Can't execute method that not in the interface
    with pytest.raises((TransactionFailed, ValueError)):
        tx = fake_preallocation_escrow.functions.additionalMethod(1).transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    # And can't send ETH to the preallocation escrow without payable fallback function
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': owner, 'value': 1})
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.client.send_transaction(
            {'from': owner, 'to': preallocation_escrow.address, 'value': 1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)


@pytest.mark.slow
def test_upgrading(testerchain, token, deploy_contract):
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': owner, 'value': 1})
    testerchain.wait_for_receipt(tx)

    secret = os.urandom(32)
    secret2 = os.urandom(32)
    secret_hash = keccak(secret)
    secret2_hash = keccak(secret2)

    interface_v1, _ = deploy_contract('StakingInterfaceMockV1')
    interface_v2, _ = deploy_contract('StakingInterfaceMockV2')
    router_contract, _ = deploy_contract(
        'StakingInterfaceRouter', interface_v1.address, secret_hash)
    preallocation_escrow_contract, _ = deploy_contract(
        'PreallocationEscrow', router_contract.address, token.address)
    # Transfer ownership
    tx = preallocation_escrow_contract.functions.transferOwnership(owner).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    preallocation_escrow_interface_v1 = testerchain.client.get_contract(
        abi=interface_v1.abi,
        address=preallocation_escrow_contract.address,
        ContractFactoryClass=Contract)
    preallocation_escrow_interface_v2 = testerchain.client.get_contract(
        abi=interface_v2.abi,
        address=preallocation_escrow_contract.address,
        ContractFactoryClass=Contract)

    # Check existed methods and that only owner can call them
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface_v1.functions.firstMethod().transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow_interface_v1.functions.firstMethod().transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert 20 == preallocation_escrow_interface_v1.functions.secondMethod().call({'from': owner})

    # Nonexistent methods can't be called
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface_v2.functions.thirdMethod().transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    # Can't send ETH to this version of the library
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.client.send_transaction(
            {'from': owner, 'to': preallocation_escrow_contract.address, 'value': 1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Only creator can update a library
    with pytest.raises((TransactionFailed, ValueError)):
        tx = router_contract.functions.upgrade(interface_v2.address, secret, secret2_hash).transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    # Creator must know the secret
    with pytest.raises((TransactionFailed, ValueError)):
        tx = router_contract.functions.upgrade(interface_v2.address, secret2, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Creator can't use the same secret again because it's insecure
    with pytest.raises((TransactionFailed, ValueError)):
        tx = router_contract.functions.upgrade(interface_v2.address, secret, secret_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    assert interface_v1.address == router_contract.functions.target().call()
    tx = router_contract.functions.upgrade(interface_v2.address, secret, secret2_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert interface_v2.address == router_contract.functions.target().call()

    # Method with old signature is not working
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface_v1.functions.firstMethod().transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    # Method with old signature that available in new ABI is working
    assert 15 == preallocation_escrow_interface_v1.functions.secondMethod().call({'from': owner})

    # New ABI is working
    assert 15 == preallocation_escrow_interface_v2.functions.secondMethod().call({'from': owner})
    tx = preallocation_escrow_interface_v2.functions.firstMethod(10).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow_interface_v2.functions.thirdMethod().transact({'from': owner})
    testerchain.wait_for_receipt(tx)

    # And can send and withdraw ETH
    tx = testerchain.client.send_transaction(
        {'from': owner, 'to': preallocation_escrow_contract.address, 'value': 1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 1 == testerchain.client.get_balance(preallocation_escrow_contract.address)
    # Only user can send ETH
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.client.send_transaction(
            {'from': testerchain.client.coinbase,
             'to': preallocation_escrow_contract.address,
             'value': 1,
             'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    assert 1 == testerchain.client.get_balance(preallocation_escrow_contract.address)

    rewards = preallocation_escrow_contract.events.ETHWithdrawn.createFilter(fromBlock='latest')
    owner_balance = testerchain.client.get_balance(owner)
    tx = preallocation_escrow_contract.functions.withdrawETH().transact({'from': owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert owner_balance + 1 == testerchain.client.get_balance(owner)
    assert 0 == testerchain.client.get_balance(preallocation_escrow_contract.address)

    events = rewards.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['owner']
    assert 1 == event_args['value']


@pytest.mark.slow
def test_interface_selfdestruct(testerchain, token, deploy_contract):
    creator = testerchain.client.accounts[0]
    account = testerchain.client.accounts[1]

    secret = os.urandom(32)
    secret_hash = keccak(secret)
    secret2 = os.urandom(32)
    secret2_hash = keccak(secret2)

    # Deploy interface and destroy it
    interface1, _ = deploy_contract('DestroyableStakingInterface')
    assert 15 == interface1.functions.method().call()
    tx = interface1.functions.destroy().transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((BadFunctionCallOutput, ValueError)):
        interface1.functions.method().call()

    # Can't create router using address without contract
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('StakingInterfaceRouter', BlockchainInterface.NULL_ADDRESS, secret_hash)
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('StakingInterfaceRouter', account, secret_hash)
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('StakingInterfaceRouter', interface1.address, secret_hash)

    # Deploy contract again with a router targeting it
    interface2, _ = deploy_contract('DestroyableStakingInterface')
    router_contract, _ = deploy_contract(
        'StakingInterfaceRouter', interface2.address, secret_hash)
    assert interface2.address == router_contract.functions.target().call()

    # Can't create user escrow using wrong contracts
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('PreallocationEscrow', router_contract.address, router_contract.address)
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('PreallocationEscrow', token.address, token.address)

    # Deploy preallocation escrow
    preallocation_escrow_contract, _ = deploy_contract(
        'PreallocationEscrow', router_contract.address, token.address)
    preallocation_escrow_interface = testerchain.client.get_contract(
        abi=interface1.abi,
        address=preallocation_escrow_contract.address,
        ContractFactoryClass=Contract)
    assert 15 == preallocation_escrow_interface.functions.method().call()

    # Can't upgrade to an address without contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = router_contract.functions.upgrade(BlockchainInterface.NULL_ADDRESS, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = router_contract.functions.upgrade(account, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = router_contract.functions.upgrade(interface1.address, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Destroy library
    tx = interface2.functions.destroy().transact()
    testerchain.wait_for_receipt(tx)
    # Preallocation escrow must determine that there is no contract
    with pytest.raises((TransactionFailed, ValueError)):
        preallocation_escrow_interface.functions.method().call()

    # Can't upgrade to an address without contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = router_contract.functions.upgrade(BlockchainInterface.NULL_ADDRESS, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = router_contract.functions.upgrade(account, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = router_contract.functions.upgrade(interface1.address, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Deploy the same contract again and upgrade to this contract
    contract3_lib, _ = deploy_contract('DestroyableStakingInterface')
    tx = router_contract.functions.upgrade(contract3_lib.address, secret, secret2_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 15 == preallocation_escrow_interface.functions.method().call()
