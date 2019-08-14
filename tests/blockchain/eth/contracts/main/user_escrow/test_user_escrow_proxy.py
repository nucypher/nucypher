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
def test_proxy(testerchain, policy_manager, user_escrow):
    """
    Test that proxy executes only predefined methods
    """
    user = testerchain.client.accounts[1]

    # Create fake instance of the user escrow contract
    fake_user_escrow = testerchain.client.get_contract(
        abi=policy_manager.abi,
        address=user_escrow.address,
        ContractFactoryClass=Contract)

    # Can't execute method that not in the proxy
    with pytest.raises((TransactionFailed, ValueError)):
        tx = fake_user_escrow.functions.additionalMethod(1).transact({'from': user})
        testerchain.wait_for_receipt(tx)

    # And can't send ETH to the user escrow without payable fallback function
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': user, 'value': 1})
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.client.send_transaction(
            {'from': user, 'to': user_escrow.address, 'value': 1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)


@pytest.mark.slow
def test_upgrading(testerchain, token):
    creator = testerchain.client.accounts[0]
    user = testerchain.client.accounts[1]
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': user, 'value': 1})
    testerchain.wait_for_receipt(tx)

    secret = os.urandom(32)
    secret2 = os.urandom(32)
    secret_hash = keccak(secret)
    secret2_hash = keccak(secret2)

    library_v1, _ = deploy_contract('UserEscrowLibraryMockV1')
    library_v2, _ = deploy_contract('UserEscrowLibraryMockV2')
    linker_contract, _ = deploy_contract(
        'UserEscrowLibraryLinker', library_v1.address, secret_hash)
    user_escrow_contract, _ = deploy_contract(
        'UserEscrow', linker_contract.address, token.address)
    # Transfer ownership
    tx = user_escrow_contract.functions.transferOwnership(user).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    user_escrow_library_v1 = testerchain.client.get_contract(
        abi=library_v1.abi,
        address=user_escrow_contract.address,
        ContractFactoryClass=Contract)
    user_escrow_library_v2 = testerchain.client.get_contract(
        abi=library_v2.abi,
        address=user_escrow_contract.address,
        ContractFactoryClass=Contract)

    # Check existed methods and that only user can call them
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_library_v1.functions.firstMethod().transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    tx = user_escrow_library_v1.functions.firstMethod().transact({'from': user})
    testerchain.wait_for_receipt(tx)
    assert 20 == user_escrow_library_v1.functions.secondMethod().call({'from': user})

    # Nonexistent methods can't be called
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_library_v2.functions.thirdMethod().transact({'from': user})
        testerchain.wait_for_receipt(tx)

    # Can't send ETH to this version of the library
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.client.send_transaction(
            {'from': user, 'to': user_escrow_contract.address, 'value': 1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Only creator can update a library
    with pytest.raises((TransactionFailed, ValueError)):
        tx = linker_contract.functions.upgrade(library_v2.address, secret, secret2_hash).transact({'from': user})
        testerchain.wait_for_receipt(tx)

    # Creator must know the secret
    with pytest.raises((TransactionFailed, ValueError)):
        tx = linker_contract.functions.upgrade(library_v2.address, secret2, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Creator can't use the same secret again because it's insecure
    with pytest.raises((TransactionFailed, ValueError)):
        tx = linker_contract.functions.upgrade(library_v2.address, secret, secret_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    assert library_v1.address == linker_contract.functions.target().call()
    tx = linker_contract.functions.upgrade(library_v2.address, secret, secret2_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert library_v2.address == linker_contract.functions.target().call()

    # Method with old signature is not working
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_library_v1.functions.firstMethod().transact({'from': user})
        testerchain.wait_for_receipt(tx)
    # Method with old signature that available in new ABI is working
    assert 15 == user_escrow_library_v1.functions.secondMethod().call({'from': user})

    # New ABI is working
    assert 15 == user_escrow_library_v2.functions.secondMethod().call({'from': user})
    tx = user_escrow_library_v2.functions.firstMethod(10).transact({'from': user})
    testerchain.wait_for_receipt(tx)
    tx = user_escrow_library_v2.functions.thirdMethod().transact({'from': user})
    testerchain.wait_for_receipt(tx)

    # And can send and withdraw ETH
    tx = testerchain.client.send_transaction(
        {'from': user, 'to': user_escrow_contract.address, 'value': 1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 1 == testerchain.client.get_balance(user_escrow_contract.address)
    # Only user can send ETH
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.client.send_transaction(
            {'from': testerchain.client.coinbase,
             'to': user_escrow_contract.address,
             'value': 1,
             'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    assert 1 == testerchain.client.get_balance(user_escrow_contract.address)

    rewards = user_escrow_contract.events.ETHWithdrawn.createFilter(fromBlock='latest')
    user_balance = testerchain.client.get_balance(user)
    tx = user_escrow_contract.functions.withdrawETH().transact({'from': user, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert user_balance + 1 == testerchain.client.get_balance(user)
    assert 0 == testerchain.client.get_balance(user_escrow_contract.address)

    events = rewards.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert user == event_args['owner']
    assert 1 == event_args['value']


@pytest.mark.slow
def test_proxy_selfdestruct(testerchain, token):
    creator = testerchain.client.accounts[0]
    account = testerchain.client.accounts[1]

    secret = os.urandom(32)
    secret_hash = keccak(secret)
    secret2 = os.urandom(32)
    secret2_hash = keccak(secret2)

    # Deploy proxy and destroy it
    contract1_lib, _ = deploy_contract('DestroyableUserEscrowLibrary')
    assert 15 == contract1_lib.functions.method().call()
    tx = contract1_lib.functions.destroy().transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((BadFunctionCallOutput, ValueError)):
        contract1_lib.functions.method().call()

    # Can't create linker using staker_address without contract
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('UserEscrowLibraryLinker', BlockchainInterface.NULL_ADDRESS, secret_hash)
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('UserEscrowLibraryLinker', account, secret_hash)
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('UserEscrowLibraryLinker', contract1_lib.address, secret_hash)

    # Deploy contract again with a linker targeting it
    contract2_lib, _ = deploy_contract('DestroyableUserEscrowLibrary')
    linker_contract, _ = deploy_contract(
        'UserEscrowLibraryLinker', contract2_lib.address, secret_hash)
    assert contract2_lib.address == linker_contract.functions.target().call()

    # Can't create user escrow using wrong contracts
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('UserEscrow', linker_contract.address, linker_contract.address)
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('UserEscrow', token.address, token.address)

    # Deploy user escrow
    user_escrow_contract, _ = deploy_contract(
        'UserEscrow', linker_contract.address, token.address)
    user_escrow_library = testerchain.client.get_contract(
        abi=contract1_lib.abi,
        address=user_escrow_contract.address,
        ContractFactoryClass=Contract)
    assert 15 == user_escrow_library.functions.method().call()

    # Can't upgrade to an staker_address without contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = linker_contract.functions.upgrade(BlockchainInterface.NULL_ADDRESS, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = linker_contract.functions.upgrade(account, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = linker_contract.functions.upgrade(contract1_lib.address, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Destroy library
    tx = contract2_lib.functions.destroy().transact()
    testerchain.wait_for_receipt(tx)
    # User escrow must determine that there is no contract
    with pytest.raises((TransactionFailed, ValueError)):
        user_escrow_library.functions.method().call()

    # Can't upgrade to an staker_address without contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = linker_contract.functions.upgrade(BlockchainInterface.NULL_ADDRESS, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = linker_contract.functions.upgrade(account, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = linker_contract.functions.upgrade(contract1_lib.address, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Deploy the same contract again and upgrade to this contract
    contract3_lib, _ = deploy_contract('DestroyableUserEscrowLibrary')
    tx = linker_contract.functions.upgrade(contract3_lib.address, secret, secret2_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 15 == user_escrow_library.functions.method().call()
