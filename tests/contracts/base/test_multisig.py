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

import pytest
from eth_tester.exceptions import TransactionFailed
from eth_utils import to_canonical_address

from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.utilities.ethereum import to_32byte_hex


def sign_hash(testerchain, account: str, data_hash: bytes) -> dict:
    provider = testerchain.provider
    address = to_canonical_address(account)
    key = provider.ethereum_tester.backend._key_lookup[address]._raw_key
    signed_data = testerchain.w3.eth.account.signHash(data_hash, key)
    return signed_data


def test_execute(testerchain, deploy_contract):
    w3 = testerchain.w3
    accounts = sorted(w3.eth.accounts)
    owners = accounts[0:5]
    others = accounts[5:]
    token, _ = deploy_contract('NuCypherToken', 2 * 10 ** 40)

    # Can't create the contract with the address 0x0 (address 0x0 is restricted for use)
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('MultiSig', 3, owners + [NULL_ADDRESS])
    # Owners must be no less than the threshold value
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('MultiSig', 6, owners)
    # Can't use the same owners multiple times in the constructor (the owner array must contain unique values)
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('MultiSig', 2, [owners[0], owners[1], owners[1]])
    # The threshold must be greater than zero or the contract will be broken
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract('MultiSig', 0, owners)
    multisig, _ = deploy_contract('MultiSig', 3, owners)

    # Check owners status
    assert multisig.functions.isOwner(owners[0]).call()
    assert multisig.functions.isOwner(owners[1]).call()
    assert not multisig.functions.isOwner(others[0]).call()
    assert not multisig.functions.isOwner(others[1]).call()

    # Transfer ETH to the multisig contract
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': multisig.address, 'value': 200})
    testerchain.wait_for_receipt(tx)
    assert 200 == w3.eth.getBalance(multisig.address)

    # Prepare data
    nonce = multisig.functions.nonce().call()
    tx_hash = multisig.functions.getUnsignedTransactionHash(owners[0], others[0], 100, w3.toBytes(0), nonce).call()
    signed_tx_hash_0 = sign_hash(testerchain, owners[0], tx_hash)
    signed_tx_hash_1 = sign_hash(testerchain, owners[1], tx_hash)
    signed_tx_hash_2 = sign_hash(testerchain, owners[2], tx_hash)
    signed_tx_hash_bad = sign_hash(testerchain, others[0], tx_hash)
    balance = w3.eth.getBalance(others[0])

    # Must be 3 (threshold) or more signatures
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.execute(
            [signed_tx_hash_0.v, signed_tx_hash_1.v],
            [to_32byte_hex(signed_tx_hash_0.r), to_32byte_hex(signed_tx_hash_1.r)],
            [to_32byte_hex(signed_tx_hash_0.s), to_32byte_hex(signed_tx_hash_1.s)],
            others[0],
            100,
            w3.toBytes(0)
        ).transact({'from': owners[0]})
        testerchain.wait_for_receipt(tx)

    # Only owners can sign transactions
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.execute(
            [signed_tx_hash_0.v, signed_tx_hash_1.v, signed_tx_hash_bad.v],
            [to_32byte_hex(signed_tx_hash_0.r), to_32byte_hex(signed_tx_hash_1.r),
             to_32byte_hex(signed_tx_hash_bad.r)],
            [to_32byte_hex(signed_tx_hash_0.s), to_32byte_hex(signed_tx_hash_1.s),
             to_32byte_hex(signed_tx_hash_bad.s)],
            others[0],
            100,
            w3.toBytes(0)
        ).transact({'from': owners[0]})
        testerchain.wait_for_receipt(tx)

    # All owners must sign the same transaction
    tx_hash_bad = multisig.functions\
        .getUnsignedTransactionHash(owners[0], others[0], 100, w3.toBytes(0), nonce + 1).call()
    signed_tx_hash_bad = sign_hash(testerchain, owners[0], tx_hash_bad)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.execute(
            [signed_tx_hash_0.v, signed_tx_hash_1.v, signed_tx_hash_bad.v],
            [to_32byte_hex(signed_tx_hash_0.r), to_32byte_hex(signed_tx_hash_1.r),
             to_32byte_hex(signed_tx_hash_bad.r)],
            [to_32byte_hex(signed_tx_hash_0.s), to_32byte_hex(signed_tx_hash_1.s),
             to_32byte_hex(signed_tx_hash_bad.s)],
            others[0],
            100,
            w3.toBytes(0)
        ).transact({'from': owners[0]})
        testerchain.wait_for_receipt(tx)

    # The owner's signatures must be in ascending order of addresses (function restrictions)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.execute(
            [signed_tx_hash_1.v, signed_tx_hash_2.v, signed_tx_hash_0.v],
            [to_32byte_hex(signed_tx_hash_1.r), to_32byte_hex(signed_tx_hash_2.r),
             to_32byte_hex(signed_tx_hash_0.r)],
            [to_32byte_hex(signed_tx_hash_1.s), to_32byte_hex(signed_tx_hash_2.s),
             to_32byte_hex(signed_tx_hash_0.s)],
            others[0],
            100,
            w3.toBytes(0)
        ).transact({'from': owners[0]})
        testerchain.wait_for_receipt(tx)

    # Can't use wrong signatures (one of S value is wrong)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.execute(
            [signed_tx_hash_0.v, signed_tx_hash_1.v, signed_tx_hash_2.v],
            [to_32byte_hex(signed_tx_hash_0.r), to_32byte_hex(signed_tx_hash_1.r),
             to_32byte_hex(signed_tx_hash_2.r)],
            [to_32byte_hex(signed_tx_hash_0.s), to_32byte_hex(signed_tx_hash_1.s),
             to_32byte_hex(signed_tx_hash_bad.s)],
            others[0],
            100,
            w3.toBytes(0)
        ).transact({'from': owners[0]})
        testerchain.wait_for_receipt(tx)

    # Only the trustee that was used in the hash can execute the transaction
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.execute(
            [signed_tx_hash_0.v, signed_tx_hash_1.v, signed_tx_hash_2.v],
            [to_32byte_hex(signed_tx_hash_0.r), to_32byte_hex(signed_tx_hash_1.r),
             to_32byte_hex(signed_tx_hash_2.r)],
            [to_32byte_hex(signed_tx_hash_0.s), to_32byte_hex(signed_tx_hash_1.s),
             to_32byte_hex(signed_tx_hash_2.s)],
            others[0],
            100,
            w3.toBytes(0)
        ).transact({'from': owners[1]})
        testerchain.wait_for_receipt(tx)

    assert balance == w3.eth.getBalance(others[0])
    assert 200 == w3.eth.getBalance(multisig.address)
    tx = multisig.functions.execute(
        [signed_tx_hash_0.v, signed_tx_hash_1.v, signed_tx_hash_2.v],
        [to_32byte_hex(signed_tx_hash_0.r), to_32byte_hex(signed_tx_hash_1.r),
         to_32byte_hex(signed_tx_hash_2.r)],
        [to_32byte_hex(signed_tx_hash_0.s), to_32byte_hex(signed_tx_hash_1.s),
         to_32byte_hex(signed_tx_hash_2.s)],
        others[0],
        100,
        w3.toBytes(0)
    ).transact({'from': owners[0]})
    testerchain.wait_for_receipt(tx)
    assert balance + 100 == w3.eth.getBalance(others[0])
    assert 100 == w3.eth.getBalance(multisig.address)

    # Can't use the same signatures again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.execute(
            [signed_tx_hash_0.v, signed_tx_hash_1.v, signed_tx_hash_2.v],
            [to_32byte_hex(signed_tx_hash_0.r), to_32byte_hex(signed_tx_hash_1.r),
             to_32byte_hex(signed_tx_hash_2.r)],
            [to_32byte_hex(signed_tx_hash_0.s), to_32byte_hex(signed_tx_hash_1.s),
             to_32byte_hex(signed_tx_hash_2.s)],
            others[0],
            100,
            w3.toBytes(0)
        ).transact({'from': owners[0]})
        testerchain.wait_for_receipt(tx)

    # Transfer tokens to the multisig contract
    tx = token.functions.transfer(multisig.address, 100).transact()
    testerchain.wait_for_receipt(tx)
    assert 100 == token.functions.balanceOf(multisig.address).call()

    # Prepare transaction
    nonce = multisig.functions.nonce().call()
    tx = token.functions.transfer(owners[0], 100).buildTransaction()
    tx_hash = multisig.functions.getUnsignedTransactionHash(owners[0], token.address, 0, tx['data'], nonce).call()
    signed_tx_hash_0 = sign_hash(testerchain, owners[0], tx_hash)
    signed_tx_hash_1 = sign_hash(testerchain, owners[1], tx_hash)
    signed_tx_hash_2 = sign_hash(testerchain, owners[3], tx_hash)
    signed_tx_hash_3 = sign_hash(testerchain, owners[4], tx_hash)
    tx = multisig.functions.execute(
        [signed_tx_hash_0.v, signed_tx_hash_1.v, signed_tx_hash_2.v, signed_tx_hash_3.v],
        [to_32byte_hex(signed_tx_hash_0.r), to_32byte_hex(signed_tx_hash_1.r),
         to_32byte_hex(signed_tx_hash_2.r), to_32byte_hex(signed_tx_hash_3.r)],
        [to_32byte_hex(signed_tx_hash_0.s), to_32byte_hex(signed_tx_hash_1.s),
         to_32byte_hex(signed_tx_hash_2.s), to_32byte_hex(signed_tx_hash_3.s)],
        token.address,
        0,
        tx['data']
    ).transact({'from': owners[0]})
    testerchain.wait_for_receipt(tx)
    assert 100 == token.functions.balanceOf(owners[0]).call()
    assert 0 == token.functions.balanceOf(multisig.address).call()


def execute_transaction(testerchain, multisig, accounts, tx):
    nonce = multisig.functions.nonce().call()
    tx_hash = multisig.functions.getUnsignedTransactionHash(accounts[0], tx['to'], 0, tx['data'], nonce).call()
    signatures = [sign_hash(testerchain, account, tx_hash) for account in accounts]
    tx = multisig.functions.execute(
        [signature.v for signature in signatures],
        [to_32byte_hex(signature.r) for signature in signatures],
        [to_32byte_hex(signature.s) for signature in signatures],
        tx['to'],
        0,
        tx['data']
    ).transact({'from': accounts[0]})
    testerchain.wait_for_receipt(tx)


def test_owners_management(testerchain, deploy_contract):
    w3 = testerchain.w3
    accounts = sorted(w3.eth.accounts)
    owners = accounts[0:3]
    multisig, _ = deploy_contract('MultiSig', 2, owners)

    execution_log = multisig.events.Executed.createFilter(fromBlock='latest')
    owner_addition_log = multisig.events.OwnerAdded.createFilter(fromBlock='latest')
    owner_removal_log = multisig.events.OwnerRemoved.createFilter(fromBlock='latest')
    requirement_changes_log = multisig.events.RequirementChanged.createFilter(fromBlock='latest')

    # Methods for owners management are restricted for public use
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.addOwner(accounts[2]).transact()
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.removeOwner(owners[0]).transact()
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = multisig.functions.changeRequirement(1).transact()
        testerchain.wait_for_receipt(tx)

    # Add new owner
    nonce = multisig.functions.nonce().call()
    tx = multisig.functions.addOwner(accounts[3]).buildTransaction({'from': multisig.address, 'gasPrice': 0})
    assert not multisig.functions.isOwner(accounts[3]).call()
    execute_transaction(testerchain, multisig, [owners[0], owners[1]], tx)
    assert multisig.functions.isOwner(accounts[3]).call()

    # Check that all events are emitted
    events = execution_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owners[0] == event_args['sender']
    assert multisig.address == event_args['destination']
    assert 0 == event_args['value']
    assert 0 == event_args['nonce']

    events = owner_addition_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert accounts[3] == event_args['owner']

    # Remove owner
    nonce += 1
    tx = multisig.functions.removeOwner(accounts[3]).buildTransaction({'from': multisig.address, 'gasPrice': 0})
    assert multisig.functions.isOwner(accounts[3]).call()
    execute_transaction(testerchain, multisig, [owners[0], accounts[3]], tx)
    assert not multisig.functions.isOwner(accounts[3]).call()

    # Check that all events are emitted
    events = execution_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert owners[0] == event_args['sender']
    assert multisig.address == event_args['destination']
    assert 0 == event_args['value']
    assert 1 == event_args['nonce']

    events = owner_removal_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert accounts[3] == event_args['owner']

    # Change requirement
    nonce += 1
    tx = multisig.functions.changeRequirement(1).buildTransaction({'from': multisig.address, 'gasPrice': 0})
    assert 2 == multisig.functions.required().call()
    execute_transaction(testerchain, multisig, [owners[1], owners[2]], tx)
    assert 1 == multisig.functions.required().call()

    # Check that all events are emitted
    events = execution_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert owners[1] == event_args['sender']
    assert multisig.address == event_args['destination']
    assert 0 == event_args['value']
    assert 2 == event_args['nonce']

    events = requirement_changes_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert 1 == event_args['required']

    # Change requirement back
    nonce += 1
    tx = multisig.functions.changeRequirement(2).buildTransaction({'from': multisig.address, 'gasPrice': 0})
    execute_transaction(testerchain, multisig, [owners[0]], tx)

    # Can't add the same owner again
    with pytest.raises((TransactionFailed, ValueError)):
        multisig.functions.addOwner(owners[0]).buildTransaction({'from': multisig.address, 'gasPrice': 0})
    # Can't add the address 0x0 as an owner
    with pytest.raises((TransactionFailed, ValueError)):
        multisig.functions.addOwner(NULL_ADDRESS).buildTransaction({'from': multisig.address, 'gasPrice': 0})

    # Can't remove nonexistent owner
    with pytest.raises((TransactionFailed, ValueError)):
        multisig.functions.removeOwner(accounts[3]).buildTransaction({'from': multisig.address, 'gasPrice': 0})
    # Remove one owner
    nonce += 1
    tx = multisig.functions.removeOwner(owners[2]).buildTransaction({'from': multisig.address, 'gasPrice': 0})
    execute_transaction(testerchain, multisig, [owners[0], owners[1]], tx)
    # The next owner can not be deleted because the number of owners can not be less than the requirement value
    with pytest.raises((TransactionFailed, ValueError)):
        multisig.functions.removeOwner(accounts[3]).buildTransaction({'from': multisig.address, 'gasPrice': 0})

    # Can't change requirement to 0 because this means that no signs are required
    with pytest.raises((TransactionFailed, ValueError)):
        multisig.functions.changeRequirement(0).buildTransaction({'from': multisig.address, 'gasPrice': 0})
    # Requirement can't be more than number of owners
    # In this case  there are always not enough owners who can sign the transaction
    with pytest.raises((TransactionFailed, ValueError)):
        multisig.functions.changeRequirement(3).buildTransaction({'from': multisig.address, 'gasPrice': 0})

    assert 5 == len(execution_log.get_all_entries())
    assert 1 == len(owner_addition_log.get_all_entries())
    assert 2 == len(owner_removal_log.get_all_entries())
    assert 2 == len(requirement_changes_log.get_all_entries())
