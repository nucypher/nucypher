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
from mock import Mock

import pytest
from cryptography.hazmat.backends.openssl import backend
from cryptography.hazmat.primitives import hashes
from eth_tester.exceptions import TransactionFailed
from eth_utils import to_canonical_address
from web3.contract import Contract

from umbral.keys import UmbralPrivateKey
from umbral.signing import Signer

from nucypher.blockchain.eth.token import NU
from nucypher.crypto.signing import SignatureStamp
from nucypher.crypto.utils import get_coordinates_as_bytes


RE_STAKE_FIELD = 3

DISABLED_FIELD = 5

SECRET_LENGTH = 32
escrow_secret = os.urandom(SECRET_LENGTH)
policy_manager_secret = os.urandom(SECRET_LENGTH)
user_escrow_secret = os.urandom(SECRET_LENGTH)
adjudicator_secret = os.urandom(SECRET_LENGTH)


@pytest.fixture()
def token(testerchain):
    # Create an ERC20 token
    contract, _ = testerchain.deploy_contract('NuCypherToken', _totalSupply=int(NU(2 * 10 ** 9, 'NuNit')))
    return contract


@pytest.fixture()
def escrow(testerchain, token):
    # Creator deploys the escrow
    contract, _ = testerchain.deploy_contract(
        contract_name='StakingEscrow',
        _token=token.address,
        _hoursPerPeriod=1,
        _miningCoefficient=8*10**7,
        _lockedPeriodsCoefficient=4,
        _rewardedPeriods=4,
        _minLockedPeriods=2,
        _minAllowableLockedTokens=100,
        _maxAllowableLockedTokens=2000,
        _minWorkerPeriods=2
    )

    secret_hash = testerchain.w3.keccak(escrow_secret)
    dispatcher, _ = testerchain.deploy_contract('Dispatcher', contract.address, secret_hash)

    # Wrap dispatcher contract
    contract = testerchain.w3.eth.contract(
        abi=contract.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    return contract, dispatcher


@pytest.fixture()
def policy_manager(testerchain, escrow):
    escrow, _ = escrow
    creator = testerchain.w3.eth.accounts[0]

    secret_hash = testerchain.w3.keccak(policy_manager_secret)

    # Creator deploys the policy manager
    contract, _ = testerchain.deploy_contract('PolicyManager', escrow.address)
    dispatcher, _ = testerchain.deploy_contract('Dispatcher', contract.address, secret_hash)

    # Wrap dispatcher contract
    contract = testerchain.w3.eth.contract(
        abi=contract.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    tx = escrow.functions.setPolicyManager(contract.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    return contract, dispatcher


@pytest.fixture()
def adjudicator(testerchain, escrow, slashing_economics):
    escrow, _ = escrow
    creator = testerchain.w3.eth.accounts[0]

    secret_hash = testerchain.w3.keccak(adjudicator_secret)

    deployment_parameters = list(slashing_economics.deployment_parameters)
    # TODO: For some reason this test used non-stadard slashing parameters (#354)
    deployment_parameters[1] = 300
    deployment_parameters[3] = 2

    # Creator deploys the contract
    contract, _ = testerchain.deploy_contract(
        'Adjudicator',
        escrow.address,
        *deployment_parameters)

    dispatcher, _ = testerchain.deploy_contract('Dispatcher', contract.address, secret_hash)

    # Wrap dispatcher contract
    contract = testerchain.w3.eth.contract(
        abi=contract.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    tx = escrow.functions.setAdjudicator(contract.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    return contract, dispatcher


def mock_ursula_with_stamp():
    ursula_privkey = UmbralPrivateKey.gen_key()
    ursula_stamp = SignatureStamp(verifying_key=ursula_privkey.pubkey,
                                  signer=Signer(ursula_privkey))
    ursula = Mock(stamp=ursula_stamp)
    return ursula


def sha256_hash(data):
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(data)
    digest = hash_ctx.finalize()
    return digest


# TODO organize support functions
def generate_args_for_slashing(testerchain, mock_ursula_reencrypts, ursula, account):
    evidence = mock_ursula_reencrypts(ursula, corrupt_cfrag=True)

    # Sign Umbral public key using eth-key
    staker_umbral_public_key_hash = sha256_hash(get_coordinates_as_bytes(ursula.stamp))
    provider = testerchain.provider
    address = to_canonical_address(account)
    sig_key = provider.ethereum_tester.backend._key_lookup[address]
    signed_staker_umbral_public_key = bytes(sig_key.sign_msg_hash(staker_umbral_public_key_hash))

    args = list(evidence.evaluation_arguments())
    args[-2] = signed_staker_umbral_public_key  # FIXME  #962

    data_hash = sha256_hash(bytes(evidence.task.capsule) + bytes(evidence.task.cfrag))
    return data_hash, args


@pytest.fixture()
def user_escrow_proxy(testerchain, token, escrow, policy_manager):
    escrow, _ = escrow
    policy_manager, _ = policy_manager
    secret_hash = testerchain.w3.keccak(user_escrow_secret)
    # Creator deploys the user escrow proxy
    user_escrow_proxy, _ = testerchain.deploy_contract(
        'UserEscrowProxy', token.address, escrow.address, policy_manager.address)
    linker, _ = testerchain.deploy_contract(
        'UserEscrowLibraryLinker', user_escrow_proxy.address, secret_hash)
    return user_escrow_proxy, linker


@pytest.fixture()
def multisig(testerchain, escrow, policy_manager, adjudicator, user_escrow_proxy):
    escrow, escrow_dispatcher = escrow
    policy_manager, policy_manager_dispatcher = policy_manager
    adjudicator, adjudicator_dispatcher = adjudicator
    user_escrow_proxy, user_escrow_linker = user_escrow_proxy
    creator, ursula1, ursula2, ursula3, ursula4, alice1, alice2, *contract_owners =\
        testerchain.w3.eth.accounts
    contract_owners = sorted(contract_owners)
    contract, _ = testerchain.deploy_contract('MultiSig', 2, contract_owners)
    tx = escrow.functions.transferOwnership(contract.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = policy_manager.functions.transferOwnership(contract.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = adjudicator.functions.transferOwnership(contract.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = user_escrow_linker.functions.transferOwnership(contract.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    return contract


def execute_multisig_transaction(testerchain, multisig, accounts, tx):

    def to_32byte_hex(w3, value):
        return w3.toHex(w3.toBytes(value).rjust(32, b'\0'))

    def sign_hash(testerchain, account: str, data_hash: bytes) -> dict:
        provider = testerchain.provider
        address = to_canonical_address(account)
        key = provider.ethereum_tester.backend._key_lookup[address]._raw_key
        signed_data = testerchain.w3.eth.account.signHash(data_hash, key)
        return signed_data

    nonce = multisig.functions.nonce().call()
    tx_hash = multisig.functions.getUnsignedTransactionHash(accounts[0], tx['to'], 0, tx['data'], nonce).call()
    signatures = [sign_hash(testerchain, account, tx_hash) for account in accounts]
    w3 = testerchain.w3
    tx = multisig.functions.execute(
        [signature.v for signature in signatures],
        [to_32byte_hex(w3, signature.r) for signature in signatures],
        [to_32byte_hex(w3, signature.s) for signature in signatures],
        tx['to'],
        0,
        tx['data']
    ).transact({'from': accounts[0]})
    testerchain.wait_for_receipt(tx)


@pytest.mark.slow
def test_all(testerchain,
             token,
             escrow,
             policy_manager,
             adjudicator,
             user_escrow_proxy,
             multisig,
             slashing_economics,
             mock_ursula_reencrypts):

    # Travel to the start of the next period to prevent problems with unexpected overflow first period
    testerchain.time_travel(hours=1)

    escrow, escrow_dispatcher = escrow
    policy_manager, policy_manager_dispatcher = policy_manager
    adjudicator, adjudicator_dispatcher = adjudicator
    user_escrow_proxy, user_escrow_linker = user_escrow_proxy
    creator, ursula1, ursula2, ursula3, ursula4, alice1, alice2, *contracts_owners =\
        testerchain.w3.eth.accounts
    contracts_owners = sorted(contracts_owners)

    # We'll need this later for slashing these Ursulas
    ursula1_with_stamp = mock_ursula_with_stamp()
    ursula2_with_stamp = mock_ursula_with_stamp()
    ursula3_with_stamp = mock_ursula_with_stamp()

    # Give clients some ether
    tx = testerchain.w3.eth.sendTransaction(
        {'from': testerchain.w3.eth.coinbase, 'to': alice1, 'value': 10 ** 10})
    testerchain.wait_for_receipt(tx)
    tx = testerchain.w3.eth.sendTransaction(
        {'from': testerchain.w3.eth.coinbase, 'to': alice2, 'value': 10 ** 10})
    testerchain.wait_for_receipt(tx)

    # Give Ursula and Alice some coins
    tx = token.functions.transfer(ursula1, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.transfer(alice1, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.transfer(alice2, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 10000 == token.functions.balanceOf(ursula1).call()
    assert 10000 == token.functions.balanceOf(alice1).call()
    assert 10000 == token.functions.balanceOf(alice2).call()

    # Ursula give Escrow rights to transfer
    tx = token.functions.approve(escrow.address, 10000).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.approve(escrow.address, 10000).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)

    # Ursula can't deposit tokens before Escrow initialization
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(1, 1).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Initialize escrow
    reward = 10 ** 9
    tx = token.functions.transfer(escrow.address, reward).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.initialize().buildTransaction({'from': multisig.address, 'gasPrice': 0})
    execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], contracts_owners[1]], tx)

    # Create the first user escrow, set and lock re-stake parameter
    user_escrow_1, _ = testerchain.deploy_contract(
        'UserEscrow', user_escrow_linker.address, token.address)
    user_escrow_proxy_1 = testerchain.w3.eth.contract(
        abi=user_escrow_proxy.abi,
        address=user_escrow_1.address,
        ContractFactoryClass=Contract)
    tx = user_escrow_1.functions.transferOwnership(ursula3).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert not escrow.functions.stakerInfo(user_escrow_1.address).call()[RE_STAKE_FIELD]
    tx = user_escrow_proxy_1.functions.setReStake(True).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    current_period = escrow.functions.getCurrentPeriod().call()
    tx = user_escrow_proxy_1.functions.lockReStake(current_period + 22).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.stakerInfo(user_escrow_1.address).call()[RE_STAKE_FIELD]
    # Can't unlock re-stake parameter now
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_proxy_1.functions.setReStake(False).transact({'from': ursula3})
        testerchain.wait_for_receipt(tx)

    # Deposit some tokens to the user escrow and lock them
    tx = token.functions.approve(user_escrow_1.address, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = user_escrow_1.functions.initialDeposit(10000, 20 * 60 * 60).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    user_escrow_2, _ = testerchain.deploy_contract(
        'UserEscrow', user_escrow_linker.address, token.address)
    tx = user_escrow_2.functions.transferOwnership(ursula4).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.approve(user_escrow_2.address, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = user_escrow_2.functions.initialDeposit(10000, 20 * 60 * 60).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 10000 == token.functions.balanceOf(user_escrow_1.address).call()
    assert ursula3 == user_escrow_1.functions.owner().call()
    assert 10000 >= user_escrow_1.functions.getLockedTokens().call()
    assert 9500 <= user_escrow_1.functions.getLockedTokens().call()
    assert 10000 == token.functions.balanceOf(user_escrow_2.address).call()
    assert ursula4 == user_escrow_2.functions.owner().call()
    assert 10000 >= user_escrow_2.functions.getLockedTokens().call()
    assert 9500 <= user_escrow_2.functions.getLockedTokens().call()

    # Ursula's withdrawal attempt won't succeed because nothing to withdraw
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(100).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # And can't lock because nothing to lock
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.lock(500, 2).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Check that nothing is locked
    assert 0 == escrow.functions.getLockedTokens(ursula1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula3).call()
    assert 0 == escrow.functions.getLockedTokens(ursula4).call()
    assert 0 == escrow.functions.getLockedTokens(user_escrow_1.address).call()
    assert 0 == escrow.functions.getLockedTokens(user_escrow_2.address).call()
    assert 0 == escrow.functions.getLockedTokens(contracts_owners[0]).call()

    # Ursula can't deposit and lock too low value
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(1, 1).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # And can't deposit and lock too high value
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(2001, 1).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Grant access to transfer tokens
    tx = token.functions.approve(escrow.address, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Deposit tokens for 1 owner
    tx = escrow.functions.preDeposit([ursula2], [1000], [9]).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWorker(ursula2).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert reward + 1000 == token.functions.balanceOf(escrow.address).call()
    assert 1000 == escrow.functions.getAllTokens(ursula2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula2, 9).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 10).call()

    # Can't pre-deposit tokens again for the same owner
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([ursula2], [1000], [9]).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Can't pre-deposit tokens with too low or too high value
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([ursula3], [1], [10]).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([ursula3], [10 ** 6], [10]).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.preDeposit([ursula3], [500], [1]).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Ursula transfer some tokens to the escrow and lock them
    tx = escrow.functions.deposit(1000, 10).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWorker(ursula1).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert reward + 2000 == token.functions.balanceOf(escrow.address).call()
    assert 9000 == token.functions.balanceOf(ursula1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1, 10).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 11).call()

    # Wait 1 period and deposit from one more Ursula
    testerchain.time_travel(hours=1)
    tx = user_escrow_proxy_1.functions.depositAsStaker(1000, 10).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    tx = user_escrow_proxy_1.functions.setWorker(ursula3).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    assert 1000 == escrow.functions.getAllTokens(user_escrow_1.address).call()
    assert 0 == escrow.functions.getLockedTokens(user_escrow_1.address).call()
    assert 1000 == escrow.functions.getLockedTokens(user_escrow_1.address, 1).call()
    assert 1000 == escrow.functions.getLockedTokens(user_escrow_1.address, 10).call()
    assert 0 == escrow.functions.getLockedTokens(user_escrow_1.address, 11).call()
    assert reward + 3000 == token.functions.balanceOf(escrow.address).call()
    assert 9000 == token.functions.balanceOf(user_escrow_1.address).call()

    # Only user can deposit tokens to the staking escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_proxy_1.functions.depositAsStaker(1000, 5).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    # Can't deposit more than amount in the user escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_proxy_1.functions.depositAsStaker(10000, 5).transact({'from': ursula3})
        testerchain.wait_for_receipt(tx)

    # Divide stakes
    tx = escrow.functions.divideStake(0, 500, 6).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.divideStake(0, 500, 9).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = user_escrow_proxy_1.functions.divideStake(0, 500, 6).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Confirm activity
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Turn on re-stake for Ursula1
    assert not escrow.functions.stakerInfo(ursula1).call()[RE_STAKE_FIELD]
    tx = escrow.functions.setReStake(True).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.stakerInfo(ursula1).call()[RE_STAKE_FIELD]

    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Create policies
    policy_id_1 = os.urandom(16)
    tx = policy_manager.functions.createPolicy(policy_id_1, 5, 44, [ursula1, ursula2]) \
        .transact({'from': alice1, 'value': 2 * 1000 + 2 * 44, 'gas_price': 0})

    testerchain.wait_for_receipt(tx)
    policy_id_2 = os.urandom(16)
    tx = policy_manager.functions.createPolicy(policy_id_2, 5, 44, [ursula2, user_escrow_1.address]) \
        .transact({'from': alice1, 'value': 2 * 1000 + 2 * 44, 'gas_price': 0})

    testerchain.wait_for_receipt(tx)
    policy_id_3 = os.urandom(16)
    tx = policy_manager.functions.createPolicy(policy_id_3, 5, 44, [ursula1, user_escrow_1.address]) \
        .transact({'from': alice2, 'value': 2 * 1000 + 2 * 44, 'gas_price': 0})

    testerchain.wait_for_receipt(tx)
    policy_id_4 = os.urandom(16)
    tx = policy_manager.functions.createPolicy(policy_id_4, 5, 44, [ursula2, user_escrow_1.address]) \
        .transact({'from': alice2, 'value': 2 * 1000 + 2 * 44, 'gas_price': 0})

    testerchain.wait_for_receipt(tx)
    policy_id_5 = os.urandom(16)
    tx = policy_manager.functions.createPolicy(policy_id_5, 5, 44, [ursula1, ursula2]) \
        .transact({'from': alice2, 'value': 2 * 1000 + 2 * 44, 'gas_price': 0})

    testerchain.wait_for_receipt(tx)

    # Only Alice can revoke policy
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id_5).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    alice2_balance = testerchain.w3.eth.getBalance(alice2)
    tx = policy_manager.functions.revokePolicy(policy_id_5).transact({'from': alice2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 8440 == testerchain.w3.eth.getBalance(policy_manager.address)
    assert alice2_balance + 2000 == testerchain.w3.eth.getBalance(alice2)
    assert policy_manager.functions.policies(policy_id_5).call()[DISABLED_FIELD]

    # Can't revoke again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id_5).transact({'from': alice2})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_5, ursula1).transact({'from': alice2})
        testerchain.wait_for_receipt(tx)

    alice1_balance = testerchain.w3.eth.getBalance(alice1)
    tx = policy_manager.functions.revokeArrangement(policy_id_2, ursula2).transact({'from': alice1, 'gas_price': 0})

    testerchain.wait_for_receipt(tx)
    assert 7440 == testerchain.w3.eth.getBalance(policy_manager.address)
    assert alice1_balance + 1000 == testerchain.w3.eth.getBalance(alice1)
    assert not policy_manager.functions.policies(policy_id_2).call()[DISABLED_FIELD]

    # Can't revoke again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, ursula2).transact({'from': alice1})
        testerchain.wait_for_receipt(tx)

    # Wait, confirm activity, mint
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(hours=1)
    tx = policy_manager.functions.revokeArrangement(policy_id_3, user_escrow_1.address) \
        .transact({'from': alice2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Turn off re-stake for Ursula1
    assert escrow.functions.stakerInfo(ursula1).call()[RE_STAKE_FIELD]
    tx = escrow.functions.setReStake(False).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert not escrow.functions.stakerInfo(ursula1).call()[RE_STAKE_FIELD]

    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    # Withdraw reward and refund
    testerchain.time_travel(hours=3)
    ursula1_balance = testerchain.w3.eth.getBalance(ursula1)
    tx = policy_manager.functions.withdraw().transact({'from': ursula1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert ursula1_balance < testerchain.w3.eth.getBalance(ursula1)
    ursula2_balance = testerchain.w3.eth.getBalance(ursula2)
    tx = policy_manager.functions.withdraw().transact({'from': ursula2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert ursula2_balance < testerchain.w3.eth.getBalance(ursula2)
    ursula3_balance = testerchain.w3.eth.getBalance(ursula3)
    tx = user_escrow_proxy_1.functions.withdrawPolicyReward().transact({'from': ursula3, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert ursula3_balance < testerchain.w3.eth.getBalance(ursula3)

    alice1_balance = testerchain.w3.eth.getBalance(alice1)
    tx = policy_manager.functions.refund(policy_id_1).transact({'from': alice1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert alice1_balance < testerchain.w3.eth.getBalance(alice1)
    alice1_balance = testerchain.w3.eth.getBalance(alice1)
    tx = policy_manager.functions.refund(policy_id_2).transact({'from': alice1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert alice1_balance < testerchain.w3.eth.getBalance(alice1)
    alice2_balance = testerchain.w3.eth.getBalance(alice2)
    tx = policy_manager.functions.refund(policy_id_3).transact({'from': alice2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert alice2_balance == testerchain.w3.eth.getBalance(alice2)
    tx = policy_manager.functions.refund(policy_id_4).transact({'from': alice2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert alice2_balance < testerchain.w3.eth.getBalance(alice2)

    # Upgrade main contracts
    escrow_secret2 = os.urandom(SECRET_LENGTH)
    policy_manager_secret2 = os.urandom(SECRET_LENGTH)
    escrow_secret2_hash = testerchain.w3.keccak(escrow_secret2)
    policy_manager_secret2_hash = testerchain.w3.keccak(policy_manager_secret2)
    escrow_v1 = escrow.functions.target().call()
    policy_manager_v1 = policy_manager.functions.target().call()
    # Creator deploys the contracts as the second versions
    escrow_v2, _ = testerchain.deploy_contract(
        contract_name='StakingEscrow',
        _token=token.address,
        _hoursPerPeriod=1,
        _miningCoefficient=8 * 10 ** 7,
        _lockedPeriodsCoefficient=4,
        _rewardedPeriods=4,
        _minLockedPeriods=2,
        _minAllowableLockedTokens=100,
        _maxAllowableLockedTokens=2000,
        _minWorkerPeriods=2
    )
    policy_manager_v2, _ = testerchain.deploy_contract('PolicyManager', escrow.address)
    # Ursula and Alice can't upgrade contracts, only owner can
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow_dispatcher.functions.upgrade(escrow_v2.address, escrow_secret, escrow_secret2_hash) \
            .transact({'from': alice1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow_dispatcher.functions.upgrade(escrow_v2.address, escrow_secret, escrow_secret2_hash) \
            .transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager_dispatcher.functions \
            .upgrade(policy_manager_v2.address, policy_manager_secret, policy_manager_secret2_hash) \
            .transact({'from': alice1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager_dispatcher.functions \
            .upgrade(policy_manager_v2.address, policy_manager_secret, policy_manager_secret2_hash) \
            .transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Prepare transactions to upgrade contracts
    tx1 = escrow_dispatcher.functions.upgrade(escrow_v2.address, escrow_secret, escrow_secret2_hash)\
        .buildTransaction({'from': multisig.address, 'gasPrice': 0})
    tx2 = policy_manager_dispatcher.functions\
        .upgrade(policy_manager_v2.address, policy_manager_secret, policy_manager_secret2_hash)\
        .buildTransaction({'from': multisig.address, 'gasPrice': 0})
    # Ursula and Alice can't sign this transactions
    with pytest.raises((TransactionFailed, ValueError)):
        execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], ursula1], tx1)
    with pytest.raises((TransactionFailed, ValueError)):
        execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], alice1], tx1)
    with pytest.raises((TransactionFailed, ValueError)):
        execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], ursula1], tx2)
    with pytest.raises((TransactionFailed, ValueError)):
        execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], alice1], tx2)

    # Execute transactions
    execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], contracts_owners[1]], tx1)
    execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], contracts_owners[1]], tx2)
    assert escrow_v2.address == escrow.functions.target().call()
    assert policy_manager_v2.address == policy_manager.functions.target().call()

    # Ursula and Alice can't rollback contracts, only owner can
    escrow_secret3 = os.urandom(SECRET_LENGTH)
    policy_manager_secret3 = os.urandom(SECRET_LENGTH)
    escrow_secret3_hash = testerchain.w3.keccak(escrow_secret3)
    policy_manager_secret3_hash = testerchain.w3.keccak(policy_manager_secret3)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow_dispatcher.functions.rollback(escrow_secret2, escrow_secret3_hash).transact({'from': alice1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow_dispatcher.functions.rollback(escrow_secret2, escrow_secret3_hash).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager_dispatcher.functions.rollback(policy_manager_secret2, policy_manager_secret3_hash) \
            .transact({'from': alice1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager_dispatcher.functions.rollback(policy_manager_secret2, policy_manager_secret3_hash) \
            .transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Prepare transactions to rollback contracts
    tx1 = escrow_dispatcher.functions.rollback(escrow_secret2, escrow_secret3_hash) \
        .buildTransaction({'from': multisig.address, 'gasPrice': 0})
    tx2 = policy_manager_dispatcher.functions.rollback(policy_manager_secret2, policy_manager_secret3_hash) \
        .buildTransaction({'from': multisig.address, 'gasPrice': 0})
    # Ursula and Alice can't sign this transactions
    with pytest.raises((TransactionFailed, ValueError)):
        execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], ursula1], tx1)
    with pytest.raises((TransactionFailed, ValueError)):
        execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], alice1], tx1)
    with pytest.raises((TransactionFailed, ValueError)):
        execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], ursula1], tx2)
    with pytest.raises((TransactionFailed, ValueError)):
        execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], alice1], tx2)

    # Execute transactions
    execute_multisig_transaction(testerchain, multisig, [contracts_owners[1], contracts_owners[2]], tx1)
    execute_multisig_transaction(testerchain, multisig, [contracts_owners[1], contracts_owners[2]], tx2)
    assert escrow_v1 == escrow.functions.target().call()
    assert policy_manager_v1 == policy_manager.functions.target().call()

    # Upgrade the user escrow library
    # Deploy the same contract as the second version
    user_escrow_proxy_v2, _ = testerchain.deploy_contract(
        'UserEscrowProxy', token.address, escrow.address, policy_manager.address)
    user_escrow_secret2 = os.urandom(SECRET_LENGTH)
    user_escrow_secret2_hash = testerchain.w3.keccak(user_escrow_secret2)
    # Ursula and Alice can't upgrade library, only owner can
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_linker.functions \
            .upgrade(user_escrow_proxy_v2.address, user_escrow_secret, user_escrow_secret2_hash) \
            .transact({'from': alice1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_linker.functions \
            .upgrade(user_escrow_proxy_v2.address, user_escrow_secret, user_escrow_secret2_hash) \
            .transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Prepare transactions to upgrade library
    tx = user_escrow_linker.functions \
        .upgrade(user_escrow_proxy_v2.address, user_escrow_secret, user_escrow_secret2_hash)\
        .buildTransaction({'from': multisig.address, 'gasPrice': 0})
    # Ursula and Alice can't sign this transactions
    with pytest.raises((TransactionFailed, ValueError)):
        execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], ursula1], tx)
    with pytest.raises((TransactionFailed, ValueError)):
        execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], alice1], tx)

    # Execute transactions
    execute_multisig_transaction(testerchain, multisig, [contracts_owners[1], contracts_owners[2]], tx)
    assert user_escrow_proxy_v2.address == user_escrow_linker.functions.target().call()

    # Slash stakers
    # Confirm activity for two periods
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)

    # Can't slash directly using the escrow contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.slashStaker(ursula1, 100, alice1, 10).transact()
        testerchain.wait_for_receipt(tx)

    # Slash part of the free amount of tokens
    current_period = escrow.functions.getCurrentPeriod().call()
    tokens_amount = escrow.functions.getAllTokens(ursula1).call()
    previous_lock = escrow.functions.getLockedTokensInPast(ursula1, 1).call()
    lock = escrow.functions.getLockedTokens(ursula1).call()
    next_lock = escrow.functions.getLockedTokens(ursula1, 1).call()
    total_previous_lock = escrow.functions.lockedPerPeriod(current_period - 1).call()
    total_lock = escrow.functions.lockedPerPeriod(current_period).call()
    alice1_balance = token.functions.balanceOf(alice1).call()

    deployment_parameters = list(slashing_economics.deployment_parameters)
    # TODO: For some reason this test used non-stadard slashing parameters (#354)
    deployment_parameters[1] = 300
    deployment_parameters[3] = 2

    algorithm_sha256, base_penalty, *coefficients = deployment_parameters
    penalty_history_coefficient, percentage_penalty_coefficient, reward_coefficient = coefficients

    data_hash, slashing_args = generate_args_for_slashing(testerchain, mock_ursula_reencrypts, ursula1_with_stamp, ursula1)
    assert not adjudicator.functions.evaluatedCFrags(data_hash).call()
    tx = adjudicator.functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)
    assert adjudicator.functions.evaluatedCFrags(data_hash).call()
    assert tokens_amount - base_penalty == escrow.functions.getAllTokens(ursula1).call()
    assert previous_lock == escrow.functions.getLockedTokensInPast(ursula1, 1).call()
    assert lock == escrow.functions.getLockedTokens(ursula1).call()
    assert next_lock == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert total_previous_lock == escrow.functions.lockedPerPeriod(current_period - 1).call()
    assert total_lock == escrow.functions.lockedPerPeriod(current_period).call()
    assert 0 == escrow.functions.lockedPerPeriod(current_period + 1).call()
    assert alice1_balance + base_penalty / reward_coefficient == token.functions.balanceOf(alice1).call()

    # Slash part of the one sub stake
    tokens_amount = escrow.functions.getAllTokens(ursula2).call()
    unlocked_amount = tokens_amount - escrow.functions.getLockedTokens(ursula2).call()
    tx = escrow.functions.withdraw(unlocked_amount).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    previous_lock = escrow.functions.getLockedTokensInPast(ursula2, 1).call()
    lock = escrow.functions.getLockedTokens(ursula2).call()
    next_lock = escrow.functions.getLockedTokens(ursula2, 1).call()
    data_hash, slashing_args = generate_args_for_slashing(testerchain, mock_ursula_reencrypts, ursula2_with_stamp, ursula2)
    assert not adjudicator.functions.evaluatedCFrags(data_hash).call()
    tx = adjudicator.functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)
    assert adjudicator.functions.evaluatedCFrags(data_hash).call()
    assert lock - base_penalty == escrow.functions.getAllTokens(ursula2).call()
    assert previous_lock == escrow.functions.getLockedTokensInPast(ursula2, 1).call()
    assert lock - base_penalty == escrow.functions.getLockedTokens(ursula2).call()
    assert next_lock - base_penalty == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert total_previous_lock == escrow.functions.lockedPerPeriod(current_period - 1).call()
    assert total_lock - base_penalty == escrow.functions.lockedPerPeriod(current_period).call()
    assert 0 == escrow.functions.lockedPerPeriod(current_period + 1).call()
    assert alice1_balance + base_penalty == token.functions.balanceOf(alice1).call()

    # Slash user escrow
    tokens_amount = escrow.functions.getAllTokens(user_escrow_1.address).call()
    previous_lock = escrow.functions.getLockedTokensInPast(user_escrow_1.address, 1).call()
    lock = escrow.functions.getLockedTokens(user_escrow_1.address).call()
    next_lock = escrow.functions.getLockedTokens(user_escrow_1.address, 1).call()
    total_previous_lock = escrow.functions.lockedPerPeriod(current_period - 1).call()
    total_lock = escrow.functions.lockedPerPeriod(current_period).call()
    alice1_balance = token.functions.balanceOf(alice1).call()

    data_hash, slashing_args = generate_args_for_slashing(testerchain, mock_ursula_reencrypts, ursula3_with_stamp, ursula3)
    assert not adjudicator.functions.evaluatedCFrags(data_hash).call()
    tx = adjudicator.functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)
    assert adjudicator.functions.evaluatedCFrags(data_hash).call()
    assert tokens_amount - base_penalty == escrow.functions.getAllTokens(user_escrow_1.address).call()
    assert previous_lock == escrow.functions.getLockedTokensInPast(user_escrow_1.address, 1).call()
    assert lock - base_penalty == escrow.functions.getLockedTokens(user_escrow_1.address).call()
    assert next_lock - base_penalty == escrow.functions.getLockedTokens(user_escrow_1.address, 1).call()
    assert total_previous_lock == escrow.functions.lockedPerPeriod(current_period - 1).call()
    assert total_lock - base_penalty == escrow.functions.lockedPerPeriod(current_period).call()
    assert 0 == escrow.functions.lockedPerPeriod(current_period + 1).call()
    assert alice1_balance + base_penalty / reward_coefficient == token.functions.balanceOf(alice1).call()

    # Upgrade the adjudicator
    # Deploy the same contract as the second version
    adjudicator_v1 = adjudicator.functions.target().call()
    adjudicator_v2, _ = testerchain.deploy_contract(
        'Adjudicator',
        escrow.address,
        *slashing_economics.deployment_parameters)
    adjudicator_secret2 = os.urandom(SECRET_LENGTH)
    adjudicator_secret2_hash = testerchain.w3.keccak(adjudicator_secret2)
    # Ursula and Alice can't upgrade library, only owner can
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_dispatcher.functions \
            .upgrade(adjudicator_v2.address, adjudicator_secret, adjudicator_secret2_hash) \
            .transact({'from': alice1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_dispatcher.functions \
            .upgrade(adjudicator_v2.address, adjudicator_secret, adjudicator_secret2_hash) \
            .transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Prepare transactions to upgrade contracts
    tx = adjudicator_dispatcher.functions\
        .upgrade(adjudicator_v2.address, adjudicator_secret, adjudicator_secret2_hash) \
        .buildTransaction({'from': multisig.address, 'gasPrice': 0})
    # Ursula and Alice can't sign this transactions
    with pytest.raises((TransactionFailed, ValueError)):
        execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], ursula1], tx)
    with pytest.raises((TransactionFailed, ValueError)):
        execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], alice1], tx)

    # Execute transactions
    execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], contracts_owners[1]], tx)
    assert adjudicator_v2.address == adjudicator.functions.target().call()

    # Ursula and Alice can't rollback contract, only owner can
    adjudicator_secret3 = os.urandom(SECRET_LENGTH)
    adjudicator_secret3_hash = testerchain.w3.keccak(adjudicator_secret3)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_dispatcher.functions.rollback(adjudicator_secret2, adjudicator_secret3_hash)\
            .transact({'from': alice1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_dispatcher.functions.rollback(adjudicator_secret2, adjudicator_secret3_hash)\
            .transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Prepare transactions to rollback contracts
    tx = adjudicator_dispatcher.functions.rollback(adjudicator_secret2, adjudicator_secret3_hash) \
        .buildTransaction({'from': multisig.address, 'gasPrice': 0})
    # Ursula and Alice can't sign this transactions
    with pytest.raises((TransactionFailed, ValueError)):
        execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], ursula1], tx)
    with pytest.raises((TransactionFailed, ValueError)):
        execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], alice1], tx)

    # Execute transactions
    execute_multisig_transaction(testerchain, multisig, [contracts_owners[1], contracts_owners[2]], tx)
    assert adjudicator_v1 == adjudicator.functions.target().call()

    # Slash two sub stakes
    tokens_amount = escrow.functions.getAllTokens(ursula1).call()
    unlocked_amount = tokens_amount - escrow.functions.getLockedTokens(ursula1).call()
    tx = escrow.functions.withdraw(unlocked_amount).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    previous_lock = escrow.functions.getLockedTokensInPast(ursula1, 1).call()
    lock = escrow.functions.getLockedTokens(ursula1).call()
    next_lock = escrow.functions.getLockedTokens(ursula1, 1).call()
    total_lock = escrow.functions.lockedPerPeriod(current_period).call()
    alice2_balance = token.functions.balanceOf(alice2).call()
    data_hash, slashing_args = generate_args_for_slashing(testerchain, mock_ursula_reencrypts, ursula1_with_stamp, ursula1)
    assert not adjudicator.functions.evaluatedCFrags(data_hash).call()
    tx = adjudicator.functions.evaluateCFrag(*slashing_args).transact({'from': alice2})
    testerchain.wait_for_receipt(tx)
    assert adjudicator.functions.evaluatedCFrags(data_hash).call()
    data_hash, slashing_args = generate_args_for_slashing(testerchain, mock_ursula_reencrypts, ursula1_with_stamp, ursula1)
    assert not adjudicator.functions.evaluatedCFrags(data_hash).call()
    tx = adjudicator.functions.evaluateCFrag(*slashing_args).transact({'from': alice2})
    testerchain.wait_for_receipt(tx)
    assert adjudicator.functions.evaluatedCFrags(data_hash).call()
    penalty = (2 * base_penalty + 3 * penalty_history_coefficient)
    assert lock - penalty == escrow.functions.getAllTokens(ursula1).call()
    assert previous_lock == escrow.functions.getLockedTokensInPast(ursula1, 1).call()
    assert lock - penalty == escrow.functions.getLockedTokens(ursula1).call()
    assert next_lock - (penalty - (lock - next_lock)) == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert total_previous_lock == escrow.functions.lockedPerPeriod(current_period - 1).call()
    assert total_lock - penalty == escrow.functions.lockedPerPeriod(current_period).call()
    assert 0 == escrow.functions.lockedPerPeriod(current_period + 1).call()
    assert alice2_balance + penalty / reward_coefficient == token.functions.balanceOf(alice2).call()

    # Unlock and withdraw all tokens in StakingEscrow
    for index in range(9):
        tx = escrow.functions.confirmActivity().transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
        tx = escrow.functions.confirmActivity().transact({'from': ursula2})
        testerchain.wait_for_receipt(tx)
        tx = escrow.functions.confirmActivity().transact({'from': ursula3})
        testerchain.wait_for_receipt(tx)
        testerchain.time_travel(hours=1)

    # Can't unlock re-stake parameter yet
    with pytest.raises((TransactionFailed, ValueError)):
        tx = user_escrow_proxy_1.functions.setReStake(False).transact({'from': ursula3})
        testerchain.wait_for_receipt(tx)

    testerchain.time_travel(hours=1)
    # Now can turn off re-stake
    tx = user_escrow_proxy_1.functions.setReStake(False).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    assert not escrow.functions.stakerInfo(user_escrow_1.address).call()[RE_STAKE_FIELD]

    tx = escrow.functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = user_escrow_proxy_1.functions.mint().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    assert 0 == escrow.functions.getLockedTokens(ursula1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula3).call()
    assert 0 == escrow.functions.getLockedTokens(ursula4).call()
    assert 0 == escrow.functions.getLockedTokens(user_escrow_1.address).call()
    assert 0 == escrow.functions.getLockedTokens(user_escrow_2.address).call()

    ursula1_balance = token.functions.balanceOf(ursula1).call()
    ursula2_balance = token.functions.balanceOf(ursula2).call()
    user_escrow_1_balance = token.functions.balanceOf(user_escrow_1.address).call()
    tokens_amount = escrow.functions.getAllTokens(ursula1).call()
    tx = escrow.functions.withdraw(tokens_amount).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tokens_amount = escrow.functions.getAllTokens(ursula2).call()
    tx = escrow.functions.withdraw(tokens_amount).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tokens_amount = escrow.functions.getAllTokens(user_escrow_1.address).call()
    tx = user_escrow_proxy_1.functions.withdrawAsStaker(tokens_amount).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    assert ursula1_balance < token.functions.balanceOf(ursula1).call()
    assert ursula2_balance < token.functions.balanceOf(ursula2).call()
    assert user_escrow_1_balance < token.functions.balanceOf(user_escrow_1.address).call()

    # Unlock and withdraw all tokens in UserEscrow
    testerchain.time_travel(hours=1)
    assert 0 == user_escrow_1.functions.getLockedTokens().call()
    assert 0 == user_escrow_2.functions.getLockedTokens().call()
    ursula3_balance = token.functions.balanceOf(ursula3).call()
    ursula4_balance = token.functions.balanceOf(ursula4).call()
    tokens_amount = token.functions.balanceOf(user_escrow_1.address).call()
    tx = user_escrow_1.functions.withdrawTokens(tokens_amount).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    tokens_amount = token.functions.balanceOf(user_escrow_2.address).call()
    tx = user_escrow_2.functions.withdrawTokens(tokens_amount).transact({'from': ursula4})
    testerchain.wait_for_receipt(tx)
    assert ursula3_balance < token.functions.balanceOf(ursula3).call()
    assert ursula4_balance < token.functions.balanceOf(ursula4).call()
