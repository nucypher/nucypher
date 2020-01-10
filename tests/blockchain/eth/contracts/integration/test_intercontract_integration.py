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
from eth_utils import to_canonical_address, to_wei
from web3.contract import Contract

from nucypher.blockchain.economics import TokenEconomics
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from umbral.keys import UmbralPrivateKey
from umbral.signing import Signer

from nucypher.crypto.api import sha256_digest
from nucypher.crypto.signing import SignatureStamp


DISABLE_RE_STAKE_FIELD = 3

DISABLED_FIELD = 5

SECRET_LENGTH = 32
escrow_secret = os.urandom(SECRET_LENGTH)
policy_manager_secret = os.urandom(SECRET_LENGTH)
router_secret = os.urandom(SECRET_LENGTH)
adjudicator_secret = os.urandom(SECRET_LENGTH)


@pytest.fixture()
def token_economics():
    economics = TokenEconomics(initial_supply=10 ** 9,
                               total_supply=2 * 10 ** 9,
                               staking_coefficient=8 * 10 ** 7,
                               locked_periods_coefficient=4,
                               maximum_rewarded_periods=4,
                               hours_per_period=1,
                               minimum_locked_periods=6,
                               minimum_allowed_locked=100,
                               maximum_allowed_locked=2000,
                               minimum_worker_periods=2,
                               base_penalty=300,
                               percentage_penalty_coefficient=2)
    return economics


@pytest.fixture()
def token(token_economics, deploy_contract):
    # Create an ERC20 token
    contract, _ = deploy_contract('NuCypherToken', _totalSupply=token_economics.erc20_total_supply)
    return contract


@pytest.fixture()
def escrow(testerchain, token, token_economics, deploy_contract):
    # Creator deploys the escrow
    contract, _ = deploy_contract(
        'StakingEscrow', token.address, *token_economics.staking_deployment_parameters, True
    )

    secret_hash = testerchain.w3.keccak(escrow_secret)
    dispatcher, _ = deploy_contract('Dispatcher', contract.address, secret_hash)

    # Wrap dispatcher contract
    contract = testerchain.client.get_contract(
        abi=contract.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    return contract, dispatcher


@pytest.fixture()
def policy_manager(testerchain, escrow, deploy_contract):
    escrow, _ = escrow
    creator = testerchain.client.accounts[0]

    secret_hash = testerchain.w3.keccak(policy_manager_secret)

    # Creator deploys the policy manager
    contract, _ = deploy_contract('PolicyManager', escrow.address)
    dispatcher, _ = deploy_contract('Dispatcher', contract.address, secret_hash)

    # Wrap dispatcher contract
    contract = testerchain.client.get_contract(
        abi=contract.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    tx = escrow.functions.setPolicyManager(contract.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    return contract, dispatcher


@pytest.fixture()
def adjudicator(testerchain, escrow, token_economics, deploy_contract):
    escrow, _ = escrow
    creator = testerchain.client.accounts[0]

    secret_hash = testerchain.w3.keccak(adjudicator_secret)

    # Creator deploys the contract
    contract, _ = deploy_contract(
        'Adjudicator',
        escrow.address,
        *token_economics.slashing_deployment_parameters)

    dispatcher, _ = deploy_contract('Dispatcher', contract.address, secret_hash)

    # Wrap dispatcher contract
    contract = testerchain.client.get_contract(
        abi=contract.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    tx = escrow.functions.setAdjudicator(contract.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    return contract, dispatcher


def mock_ursula(testerchain, account, mocker):
    ursula_privkey = UmbralPrivateKey.gen_key()
    ursula_stamp = SignatureStamp(verifying_key=ursula_privkey.pubkey,
                                  signer=Signer(ursula_privkey))

    signed_stamp = testerchain.client.sign_message(account=account,
                                                   message=bytes(ursula_stamp))

    ursula = mocker.Mock(stamp=ursula_stamp, decentralized_identity_evidence=signed_stamp)
    return ursula


# TODO organize support functions
def generate_args_for_slashing(mock_ursula_reencrypts, ursula):
    evidence = mock_ursula_reencrypts(ursula, corrupt_cfrag=True)
    args = list(evidence.evaluation_arguments())
    data_hash = sha256_digest(evidence.task.capsule, evidence.task.cfrag)
    return data_hash, args


@pytest.fixture()
def staking_interface(testerchain, token, escrow, policy_manager, deploy_contract):
    escrow, _ = escrow
    policy_manager, _ = policy_manager
    secret_hash = testerchain.w3.keccak(router_secret)
    # Creator deploys the staking interface
    staking_interface, _ = deploy_contract(
        'StakingInterface', token.address, escrow.address, policy_manager.address)
    router, _ = deploy_contract(
        'StakingInterfaceRouter', staking_interface.address, secret_hash)
    return staking_interface, router


@pytest.fixture()
def worklock(testerchain, token, escrow, staking_interface, deploy_contract):
    escrow, _ = escrow
    creator = testerchain.w3.eth.accounts[0]
    _, router = staking_interface

    # Creator deploys the worklock using test values
    now = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    start_bid_date = ((now + 3600) // 3600 + 1) * 3600  # beginning of the next hour plus 1 hour
    end_bid_date = start_bid_date + 3600
    boosting_refund = 100
    locking_duration = 20 * 60 * 60
    contract, _ = deploy_contract(
        contract_name='WorkLock',
        _token=token.address,
        _escrow=escrow.address,
        _router=router.address,
        _startBidDate=start_bid_date,
        _endBidDate=end_bid_date,
        _boostingRefund=boosting_refund,
        _lockingDuration=locking_duration
    )

    tx = escrow.functions.setWorkLock(contract.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    return contract


@pytest.fixture()
def multisig(testerchain, escrow, policy_manager, adjudicator, staking_interface, deploy_contract):
    escrow, escrow_dispatcher = escrow
    policy_manager, policy_manager_dispatcher = policy_manager
    adjudicator, adjudicator_dispatcher = adjudicator
    staking_interface, staking_interface_router = staking_interface
    creator, ursula1, ursula2, ursula3, ursula4, alice1, alice2, *contract_owners =\
        testerchain.client.accounts
    contract_owners = sorted(contract_owners)
    contract, _ = deploy_contract('MultiSig', 2, contract_owners)
    tx = escrow.functions.transferOwnership(contract.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = policy_manager.functions.transferOwnership(contract.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = adjudicator.functions.transferOwnership(contract.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = staking_interface_router.functions.transferOwnership(contract.address).transact({'from': creator})
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
             token_economics,
             token,
             escrow,
             policy_manager,
             adjudicator,
             worklock,
             staking_interface,
             multisig,
             mock_ursula_reencrypts,
             deploy_contract,
             mocker):

    # Travel to the start of the next period to prevent problems with unexpected overflow first period
    testerchain.time_travel(hours=1)

    escrow, escrow_dispatcher = escrow
    policy_manager, policy_manager_dispatcher = policy_manager
    adjudicator, adjudicator_dispatcher = adjudicator
    staking_interface, staking_interface_router = staking_interface
    creator, ursula1, ursula2, ursula3, ursula4, alice1, alice2, *contracts_owners =\
        testerchain.client.accounts
    contracts_owners = sorted(contracts_owners)

    # Create the first preallocation escrow
    preallocation_escrow_1, _ = deploy_contract(
        'PreallocationEscrow', staking_interface_router.address, token.address, escrow.address)
    preallocation_escrow_interface_1 = testerchain.client.get_contract(
        abi=staking_interface.abi,
        address=preallocation_escrow_1.address,
        ContractFactoryClass=Contract)

    # We'll need this later for slashing these Ursulas
    ursula1_with_stamp = mock_ursula(testerchain, ursula1, mocker=mocker)
    ursula2_with_stamp = mock_ursula(testerchain, ursula2, mocker=mocker)
    ursula3_with_stamp = mock_ursula(testerchain, ursula3, mocker=mocker)

    # Give clients some ether
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': alice1, 'value': 10 ** 10})
    testerchain.wait_for_receipt(tx)
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': alice2, 'value': 10 ** 10})
    testerchain.wait_for_receipt(tx)
    tx = testerchain.w3.eth.sendTransaction(
        {'from': testerchain.w3.eth.coinbase, 'to': ursula2, 'value': 10 ** 10})
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
    tx = token.functions.transfer(multisig.address, token_economics.erc20_reward_supply).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.approve(escrow.address, token_economics.erc20_reward_supply)\
        .buildTransaction({'from': multisig.address, 'gasPrice': 0})
    execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], contracts_owners[1]], tx)
    tx = escrow.functions.initialize(token_economics.erc20_reward_supply)\
        .buildTransaction({'from': multisig.address, 'gasPrice': 0})
    execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], contracts_owners[1]], tx)

    # Initialize worklock
    worklock_supply = 1980
    tx = token.functions.approve(worklock.address, worklock_supply).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.tokenDeposit(worklock_supply).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Can't do anything before start date
    deposited_eth_1 = to_wei(18, 'ether')
    deposited_eth_2 = to_wei(1, 'ether')
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact({'from': ursula2, 'value': deposited_eth_1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Wait for the start of the bidding
    testerchain.time_travel(hours=1)

    # Ursula does bid
    assert worklock.functions.workInfo(ursula2).call()[0] == 0
    assert testerchain.w3.eth.getBalance(worklock.address) == 0
    tx = worklock.functions.bid().transact({'from': ursula2, 'value': deposited_eth_1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(ursula2).call()[0] == deposited_eth_1
    assert testerchain.w3.eth.getBalance(worklock.address) == deposited_eth_1
    assert worklock.functions.ethToTokens(deposited_eth_1).call() == worklock_supply

    # Can't claim while bidding phase
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.claim().transact({'from': ursula2, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Other Ursula do bid
    assert worklock.functions.workInfo(ursula1).call()[0] == 0
    tx = worklock.functions.bid().transact({'from': ursula1, 'value': deposited_eth_2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(ursula1).call()[0] == deposited_eth_2
    assert testerchain.w3.eth.getBalance(worklock.address) == deposited_eth_1 + deposited_eth_2
    assert worklock.functions.ethToTokens(deposited_eth_2).call() == worklock_supply // 19

    assert worklock.functions.workInfo(ursula4).call()[0] == 0
    tx = worklock.functions.bid().transact({'from': ursula4, 'value': deposited_eth_2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(ursula4).call()[0] == deposited_eth_2
    assert testerchain.w3.eth.getBalance(worklock.address) == deposited_eth_1 + 2 * deposited_eth_2
    assert worklock.functions.ethToTokens(deposited_eth_2).call() == worklock_supply // 20

    # Wait for the end of the bidding
    testerchain.time_travel(hours=1)

    # Can't bid after the enf of bidding
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact({'from': ursula2, 'value': 1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # One of Ursulas cancels bid
    tx = worklock.functions.cancelBid().transact({'from': ursula1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(ursula1).call()[0] == 0
    assert testerchain.w3.eth.getBalance(worklock.address) == deposited_eth_1 + deposited_eth_2
    assert worklock.functions.ethToTokens(deposited_eth_2).call() == worklock_supply // 20
    assert worklock.functions.unclaimedTokens().call() == worklock_supply // 20

    # Ursula claims tokens
    tx = worklock.functions.claim().transact({'from': ursula2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    preallocation_escrow_2 = testerchain.client.get_contract(
        abi=preallocation_escrow_1.abi,
        address=worklock.functions.workInfo(ursula2).call()[2],
        ContractFactoryClass=Contract)

    ursula2_tokens = worklock_supply * 9 // 10
    assert token.functions.balanceOf(ursula2).call() == 0
    assert token.functions.balanceOf(preallocation_escrow_2.address).call() == ursula2_tokens
    assert preallocation_escrow_2.functions.owner().call() == ursula2
    assert preallocation_escrow_2.functions.getLockedTokens().call() == ursula2_tokens
    ursula2_remaining_work = ursula2_tokens
    assert worklock.functions.ethToWork(deposited_eth_1).call() == ursula2_remaining_work
    assert worklock.functions.workToETH(ursula2_remaining_work).call() == deposited_eth_1
    assert worklock.functions.getRemainingWork(preallocation_escrow_2.address).call() == ursula2_remaining_work
    assert token.functions.balanceOf(worklock.address).call() == worklock_supply - ursula2_tokens

    preallocation_escrow_interface_2 = testerchain.client.get_contract(
        abi=staking_interface.abi,
        address=preallocation_escrow_2.address,
        ContractFactoryClass=Contract)
    tx = preallocation_escrow_interface_2.functions.depositAsStaker(1000, 6).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow_interface_2.functions.setWorker(ursula2).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    escrow_balance = token_economics.erc20_reward_supply + 1000
    assert 1000 == escrow.functions.getAllTokens(preallocation_escrow_2.address).call()
    assert 0 == escrow.functions.getLockedTokens(preallocation_escrow_2.address, 0).call()
    assert 1000 == escrow.functions.getLockedTokens(preallocation_escrow_2.address, 1).call()
    assert 1000 == escrow.functions.getLockedTokens(preallocation_escrow_2.address, 6).call()
    assert 0 == escrow.functions.getLockedTokens(preallocation_escrow_2.address, 7).call()
    assert 0 == escrow.functions.getCompletedWork(preallocation_escrow_2.address).call()

    # Another Ursula claims tokens
    tx = worklock.functions.claim().transact({'from': ursula4, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    preallocation_escrow_3 = testerchain.client.get_contract(
        abi=preallocation_escrow_1.abi,
        address=worklock.functions.workInfo(ursula4).call()[2],
        ContractFactoryClass=Contract)

    ursula4_tokens = worklock_supply // 20
    assert token.functions.balanceOf(ursula4).call() == 0
    assert token.functions.balanceOf(preallocation_escrow_3.address).call() == ursula4_tokens
    assert preallocation_escrow_3.functions.owner().call() == ursula4
    assert preallocation_escrow_3.functions.getLockedTokens().call() == ursula4_tokens
    assert token.functions.balanceOf(worklock.address).call() == worklock_supply - ursula2_tokens - ursula4_tokens

    # Burn remaining tokens in WorkLock
    tx = worklock.functions.burnUnclaimed().transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    escrow_balance += worklock_supply // 20
    assert 0 == worklock.functions.unclaimedTokens().call()
    assert 0 == token.functions.balanceOf(worklock.address).call()
    assert escrow_balance == token.functions.balanceOf(escrow.address).call()
    assert token_economics.erc20_reward_supply + worklock_supply // 20 == escrow.functions.getReservedReward().call()

    # Ursula prolongs lock duration
    tx = preallocation_escrow_interface_2.functions.prolongStake(0, 3).transact({'from': ursula2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 0 == escrow.functions.getLockedTokens(preallocation_escrow_2.address, 0).call()
    assert 1000 == escrow.functions.getLockedTokens(preallocation_escrow_2.address, 1).call()
    assert 1000 == escrow.functions.getLockedTokens(preallocation_escrow_2.address, 9).call()
    assert 0 == escrow.functions.getLockedTokens(preallocation_escrow_2.address, 10).call()
    assert 0 == escrow.functions.getCompletedWork(preallocation_escrow_2.address).call()

    # Can't claim more than once
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.claim().transact({'from': ursula2, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    # Can't refund without work
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.refund(preallocation_escrow_2.address).transact({'from': ursula2, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Set and lock re-stake parameter in first preallocation escrow
    tx = preallocation_escrow_1.functions.transferOwnership(ursula3).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert not escrow.functions.stakerInfo(preallocation_escrow_1.address).call()[DISABLE_RE_STAKE_FIELD]
    current_period = escrow.functions.getCurrentPeriod().call()
    tx = preallocation_escrow_interface_1.functions.lockReStake(current_period + 22).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    assert not escrow.functions.stakerInfo(preallocation_escrow_1.address).call()[DISABLE_RE_STAKE_FIELD]
    # Can't unlock re-stake parameter now
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface_1.functions.setReStake(False).transact({'from': ursula3})
        testerchain.wait_for_receipt(tx)

    # Deposit some tokens to the preallocation escrow and lock them
    tx = token.functions.approve(preallocation_escrow_1.address, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow_1.functions.initialDeposit(10000, 20 * 60 * 60).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    assert 10000 == token.functions.balanceOf(preallocation_escrow_1.address).call()
    assert ursula3 == preallocation_escrow_1.functions.owner().call()
    assert 10000 >= preallocation_escrow_1.functions.getLockedTokens().call()
    assert 9500 <= preallocation_escrow_1.functions.getLockedTokens().call()

    # Ursula's withdrawal attempt won't succeed because nothing to withdraw
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(100).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # And can't lock because nothing to lock
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.lock(500, 2).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Check that nothing is locked
    assert 0 == escrow.functions.getLockedTokens(ursula1, 0).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 0).call()
    assert 0 == escrow.functions.getLockedTokens(ursula3, 0).call()
    assert 0 == escrow.functions.getLockedTokens(ursula4, 0).call()
    assert 0 == escrow.functions.getLockedTokens(preallocation_escrow_1.address, 0).call()
    assert 0 == escrow.functions.getLockedTokens(preallocation_escrow_2.address, 0).call()
    assert 0 == escrow.functions.getLockedTokens(preallocation_escrow_3.address, 0).call()
    assert 0 == escrow.functions.getLockedTokens(contracts_owners[0], 0).call()

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

    # Ursula transfer some tokens to the escrow and lock them
    tx = escrow.functions.deposit(1000, 10).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWorker(ursula1).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setReStake(False).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    escrow_balance += 1000
    assert escrow_balance == token.functions.balanceOf(escrow.address).call()
    assert 9000 == token.functions.balanceOf(ursula1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 0).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1, 10).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 11).call()

    # Wait 1 period and deposit from one more Ursula
    testerchain.time_travel(hours=1)
    tx = preallocation_escrow_interface_1.functions.depositAsStaker(1000, 10).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow_interface_1.functions.setWorker(ursula3).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    escrow_balance += 1000
    assert 1000 == escrow.functions.getAllTokens(preallocation_escrow_1.address).call()
    assert 0 == escrow.functions.getLockedTokens(preallocation_escrow_1.address, 0).call()
    assert 1000 == escrow.functions.getLockedTokens(preallocation_escrow_1.address, 1).call()
    assert 1000 == escrow.functions.getLockedTokens(preallocation_escrow_1.address, 10).call()
    assert 0 == escrow.functions.getLockedTokens(preallocation_escrow_1.address, 11).call()
    assert escrow_balance == token.functions.balanceOf(escrow.address).call()
    assert 9000 == token.functions.balanceOf(preallocation_escrow_1.address).call()

    # Only owner can deposit tokens to the staking escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface_1.functions.depositAsStaker(1000, 5).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    # Can't deposit more than amount in the preallocation escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface_1.functions.depositAsStaker(10000, 5).transact({'from': ursula3})
        testerchain.wait_for_receipt(tx)

    # Divide stakes
    tx = preallocation_escrow_interface_2.functions.divideStake(0, 500, 6).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.divideStake(0, 500, 9).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow_interface_1.functions.divideStake(0, 500, 6).transact({'from': ursula3})
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
    assert escrow.functions.stakerInfo(ursula1).call()[DISABLE_RE_STAKE_FIELD]
    tx = escrow.functions.setReStake(True).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert not escrow.functions.stakerInfo(ursula1).call()[DISABLE_RE_STAKE_FIELD]

    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Create policies
    policy_id_1 = os.urandom(16)
    number_of_periods = 5
    one_period = 60 * 60
    rate = 200
    one_node_value = number_of_periods * rate
    value = 2 * one_node_value
    current_timestamp = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    end_timestamp = current_timestamp + (number_of_periods - 1) * one_period
    tx = policy_manager.functions.createPolicy(policy_id_1, alice1, end_timestamp, [ursula1, preallocation_escrow_2.address]) \
        .transact({'from': alice1, 'value': value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    policy_id_2 = os.urandom(16)
    tx = policy_manager.functions.createPolicy(
        policy_id_2, alice2, end_timestamp, [preallocation_escrow_2.address, preallocation_escrow_1.address]) \
        .transact({'from': alice1, 'value': value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    policy_id_3 = os.urandom(16)
    tx = policy_manager.functions.createPolicy(
        policy_id_3, BlockchainInterface.NULL_ADDRESS, end_timestamp, [ursula1, preallocation_escrow_1.address]) \
        .transact({'from': alice2, 'value': value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    policy_id_4 = os.urandom(16)
    tx = policy_manager.functions.createPolicy(
        policy_id_4, alice1, end_timestamp, [preallocation_escrow_2.address, preallocation_escrow_1.address]) \
        .transact({'from': alice2, 'value': value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    policy_id_5 = os.urandom(16)
    tx = policy_manager.functions.createPolicy(
        policy_id_5, alice1, end_timestamp, [ursula1, preallocation_escrow_2.address]) \
        .transact({'from': alice2, 'value': value, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 5 * value == testerchain.client.get_balance(policy_manager.address)

    # Only Alice can revoke policy
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id_5).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    alice2_balance = testerchain.client.get_balance(alice2)
    tx = policy_manager.functions.revokePolicy(policy_id_5).transact({'from': alice1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    two_nodes_rate = 2 * rate
    assert 4 * value + two_nodes_rate == testerchain.client.get_balance(policy_manager.address)
    assert alice2_balance + (value - two_nodes_rate) == testerchain.client.get_balance(alice2)
    assert policy_manager.functions.policies(policy_id_5).call()[DISABLED_FIELD]

    # Can't revoke again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokePolicy(policy_id_5).transact({'from': alice2})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_5, ursula1).transact({'from': alice2})
        testerchain.wait_for_receipt(tx)

    alice1_balance = testerchain.client.get_balance(alice1)
    tx = policy_manager.functions.revokeArrangement(policy_id_2, preallocation_escrow_2.address).transact({'from': alice2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    remaining_value = 3 * value + two_nodes_rate + one_node_value + rate
    assert remaining_value == testerchain.client.get_balance(policy_manager.address)
    assert alice1_balance + one_node_value - rate == testerchain.client.get_balance(alice1)
    assert not policy_manager.functions.policies(policy_id_2).call()[DISABLED_FIELD]

    # Can't revoke again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = policy_manager.functions.revokeArrangement(policy_id_2, preallocation_escrow_2.address)\
            .transact({'from': alice1})
        testerchain.wait_for_receipt(tx)

    # Wait, confirm activity, mint
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Check work measurement
    completed_work = escrow.functions.getCompletedWork(preallocation_escrow_2.address).call()
    assert 0 < completed_work
    assert 0 == escrow.functions.getCompletedWork(preallocation_escrow_1.address).call()
    assert 0 == escrow.functions.getCompletedWork(ursula1).call()

    testerchain.time_travel(hours=1)
    tx = policy_manager.functions.revokeArrangement(policy_id_3, preallocation_escrow_1.address) \
        .transact({'from': alice2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Turn off re-stake for Ursula1
    assert not escrow.functions.stakerInfo(ursula1).call()[DISABLE_RE_STAKE_FIELD]
    tx = escrow.functions.setReStake(False).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.stakerInfo(ursula1).call()[DISABLE_RE_STAKE_FIELD]

    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    # Withdraw reward and refund
    testerchain.time_travel(hours=3)
    ursula1_balance = testerchain.client.get_balance(ursula1)
    tx = policy_manager.functions.withdraw().transact({'from': ursula1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert ursula1_balance < testerchain.client.get_balance(ursula1)
    ursula2_balance = testerchain.client.get_balance(ursula2)
    tx = preallocation_escrow_interface_2.functions.withdrawPolicyReward(ursula2).transact({'from': ursula2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert ursula2_balance < testerchain.client.get_balance(ursula2)
    ursula3_balance = testerchain.client.get_balance(ursula3)
    tx = preallocation_escrow_interface_1.functions.withdrawPolicyReward(ursula3).transact({'from': ursula3, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert ursula3_balance < testerchain.client.get_balance(ursula3)

    alice1_balance = testerchain.client.get_balance(alice1)
    tx = policy_manager.functions.refund(policy_id_1).transact({'from': alice1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert alice1_balance < testerchain.client.get_balance(alice1)
    alice1_balance = testerchain.client.get_balance(alice1)
    tx = policy_manager.functions.refund(policy_id_2).transact({'from': alice1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert alice1_balance < testerchain.client.get_balance(alice1)
    alice2_balance = testerchain.client.get_balance(alice2)
    tx = policy_manager.functions.refund(policy_id_3).transact({'from': alice2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert alice2_balance == testerchain.client.get_balance(alice2)
    tx = policy_manager.functions.refund(policy_id_4).transact({'from': alice1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert alice2_balance < testerchain.client.get_balance(alice2)

    # Upgrade main contracts
    escrow_secret2 = os.urandom(SECRET_LENGTH)
    policy_manager_secret2 = os.urandom(SECRET_LENGTH)
    escrow_secret2_hash = testerchain.w3.keccak(escrow_secret2)
    policy_manager_secret2_hash = testerchain.w3.keccak(policy_manager_secret2)
    escrow_v1 = escrow.functions.target().call()
    policy_manager_v1 = policy_manager.functions.target().call()
    # Creator deploys the contracts as the second versions
    escrow_v2, _ = deploy_contract(
        'StakingEscrow', token.address, *token_economics.staking_deployment_parameters, False
    )
    policy_manager_v2, _ = deploy_contract('PolicyManager', escrow.address)
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

    # Upgrade the preallocation escrow library
    # Deploy the same contract as the second version
    staking_interface_v2, _ = deploy_contract(
        'StakingInterface', token.address, escrow.address, policy_manager.address)
    router_secret2 = os.urandom(SECRET_LENGTH)
    router_secret2_hash = testerchain.w3.keccak(router_secret2)
    # Ursula and Alice can't upgrade library, only owner can
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface_router.functions \
            .upgrade(staking_interface_v2.address, router_secret, router_secret2_hash) \
            .transact({'from': alice1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface_router.functions \
            .upgrade(staking_interface_v2.address, router_secret, router_secret2_hash) \
            .transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Prepare transactions to upgrade library
    tx = staking_interface_router.functions \
        .upgrade(staking_interface_v2.address, router_secret, router_secret2_hash)\
        .buildTransaction({'from': multisig.address, 'gasPrice': 0})
    # Ursula and Alice can't sign this transactions
    with pytest.raises((TransactionFailed, ValueError)):
        execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], ursula1], tx)
    with pytest.raises((TransactionFailed, ValueError)):
        execute_multisig_transaction(testerchain, multisig, [contracts_owners[0], alice1], tx)

    # Execute transactions
    execute_multisig_transaction(testerchain, multisig, [contracts_owners[1], contracts_owners[2]], tx)
    assert staking_interface_v2.address == staking_interface_router.functions.target().call()

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
    lock = escrow.functions.getLockedTokens(ursula1, 0).call()
    next_lock = escrow.functions.getLockedTokens(ursula1, 1).call()
    total_previous_lock = escrow.functions.lockedPerPeriod(current_period - 1).call()
    total_lock = escrow.functions.lockedPerPeriod(current_period).call()
    alice1_balance = token.functions.balanceOf(alice1).call()

    algorithm_sha256, base_penalty, *coefficients = token_economics.slashing_deployment_parameters
    penalty_history_coefficient, percentage_penalty_coefficient, reward_coefficient = coefficients

    data_hash, slashing_args = generate_args_for_slashing(mock_ursula_reencrypts, ursula1_with_stamp)
    assert not adjudicator.functions.evaluatedCFrags(data_hash).call()
    tx = adjudicator.functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)
    assert adjudicator.functions.evaluatedCFrags(data_hash).call()
    assert tokens_amount - base_penalty == escrow.functions.getAllTokens(ursula1).call()
    assert previous_lock == escrow.functions.getLockedTokensInPast(ursula1, 1).call()
    assert lock == escrow.functions.getLockedTokens(ursula1, 0).call()
    assert next_lock == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert total_previous_lock == escrow.functions.lockedPerPeriod(current_period - 1).call()
    assert total_lock == escrow.functions.lockedPerPeriod(current_period).call()
    assert 0 == escrow.functions.lockedPerPeriod(current_period + 1).call()
    assert alice1_balance + base_penalty / reward_coefficient == token.functions.balanceOf(alice1).call()

    # Slash part of the one sub stake
    tokens_amount = escrow.functions.getAllTokens(preallocation_escrow_2.address).call()
    unlocked_amount = tokens_amount - escrow.functions.getLockedTokens(preallocation_escrow_2.address, 0).call()
    tx = preallocation_escrow_interface_2.functions.withdrawAsStaker(unlocked_amount).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    previous_lock = escrow.functions.getLockedTokensInPast(preallocation_escrow_2.address, 1).call()
    lock = escrow.functions.getLockedTokens(preallocation_escrow_2.address, 0).call()
    next_lock = escrow.functions.getLockedTokens(preallocation_escrow_2.address, 1).call()
    data_hash, slashing_args = generate_args_for_slashing(mock_ursula_reencrypts, ursula2_with_stamp)
    assert not adjudicator.functions.evaluatedCFrags(data_hash).call()
    tx = adjudicator.functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)
    assert adjudicator.functions.evaluatedCFrags(data_hash).call()
    assert lock - base_penalty == escrow.functions.getAllTokens(preallocation_escrow_2.address).call()
    assert previous_lock == escrow.functions.getLockedTokensInPast(preallocation_escrow_2.address, 1).call()
    assert lock - base_penalty == escrow.functions.getLockedTokens(preallocation_escrow_2.address, 0).call()
    assert next_lock - base_penalty == escrow.functions.getLockedTokens(preallocation_escrow_2.address, 1).call()
    assert total_previous_lock == escrow.functions.lockedPerPeriod(current_period - 1).call()
    assert total_lock - base_penalty == escrow.functions.lockedPerPeriod(current_period).call()
    assert 0 == escrow.functions.lockedPerPeriod(current_period + 1).call()
    assert alice1_balance + base_penalty == token.functions.balanceOf(alice1).call()

    # Slash preallocation escrow
    tokens_amount = escrow.functions.getAllTokens(preallocation_escrow_1.address).call()
    previous_lock = escrow.functions.getLockedTokensInPast(preallocation_escrow_1.address, 1).call()
    lock = escrow.functions.getLockedTokens(preallocation_escrow_1.address, 0).call()
    next_lock = escrow.functions.getLockedTokens(preallocation_escrow_1.address, 1).call()
    total_previous_lock = escrow.functions.lockedPerPeriod(current_period - 1).call()
    total_lock = escrow.functions.lockedPerPeriod(current_period).call()
    alice1_balance = token.functions.balanceOf(alice1).call()

    data_hash, slashing_args = generate_args_for_slashing(mock_ursula_reencrypts, ursula3_with_stamp)
    assert not adjudicator.functions.evaluatedCFrags(data_hash).call()
    tx = adjudicator.functions.evaluateCFrag(*slashing_args).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)
    assert adjudicator.functions.evaluatedCFrags(data_hash).call()
    assert tokens_amount - base_penalty == escrow.functions.getAllTokens(preallocation_escrow_1.address).call()
    assert previous_lock == escrow.functions.getLockedTokensInPast(preallocation_escrow_1.address, 1).call()
    assert lock - base_penalty == escrow.functions.getLockedTokens(preallocation_escrow_1.address, 0).call()
    assert next_lock - base_penalty == escrow.functions.getLockedTokens(preallocation_escrow_1.address, 1).call()
    assert total_previous_lock == escrow.functions.lockedPerPeriod(current_period - 1).call()
    assert total_lock - base_penalty == escrow.functions.lockedPerPeriod(current_period).call()
    assert 0 == escrow.functions.lockedPerPeriod(current_period + 1).call()
    assert alice1_balance + base_penalty / reward_coefficient == token.functions.balanceOf(alice1).call()

    # Upgrade the adjudicator
    # Deploy the same contract as the second version
    adjudicator_v1 = adjudicator.functions.target().call()
    adjudicator_v2, _ = deploy_contract(
        'Adjudicator',
        escrow.address,
        *token_economics.slashing_deployment_parameters)
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
    unlocked_amount = tokens_amount - escrow.functions.getLockedTokens(ursula1, 0).call()
    tx = escrow.functions.withdraw(unlocked_amount).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    previous_lock = escrow.functions.getLockedTokensInPast(ursula1, 1).call()
    lock = escrow.functions.getLockedTokens(ursula1, 0).call()
    next_lock = escrow.functions.getLockedTokens(ursula1, 1).call()
    total_lock = escrow.functions.lockedPerPeriod(current_period).call()
    alice2_balance = token.functions.balanceOf(alice2).call()
    data_hash, slashing_args = generate_args_for_slashing(mock_ursula_reencrypts, ursula1_with_stamp)
    assert not adjudicator.functions.evaluatedCFrags(data_hash).call()
    tx = adjudicator.functions.evaluateCFrag(*slashing_args).transact({'from': alice2})
    testerchain.wait_for_receipt(tx)
    assert adjudicator.functions.evaluatedCFrags(data_hash).call()
    data_hash, slashing_args = generate_args_for_slashing(mock_ursula_reencrypts, ursula1_with_stamp)
    assert not adjudicator.functions.evaluatedCFrags(data_hash).call()
    tx = adjudicator.functions.evaluateCFrag(*slashing_args).transact({'from': alice2})
    testerchain.wait_for_receipt(tx)
    assert adjudicator.functions.evaluatedCFrags(data_hash).call()
    penalty = (2 * base_penalty + 3 * penalty_history_coefficient)
    assert lock - penalty == escrow.functions.getAllTokens(ursula1).call()
    assert previous_lock == escrow.functions.getLockedTokensInPast(ursula1, 1).call()
    assert lock - penalty == escrow.functions.getLockedTokens(ursula1, 0).call()
    assert next_lock - (penalty - (lock - next_lock)) == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert total_previous_lock == escrow.functions.lockedPerPeriod(current_period - 1).call()
    assert total_lock - penalty == escrow.functions.lockedPerPeriod(current_period).call()
    assert 0 == escrow.functions.lockedPerPeriod(current_period + 1).call()
    assert alice2_balance + penalty / reward_coefficient == token.functions.balanceOf(alice2).call()

    # Can't prolong stake by too low duration
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface_2.functions.prolongStake(0, 1).transact({'from': ursula2, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Unlock and withdraw all tokens
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
        tx = preallocation_escrow_interface_1.functions.setReStake(False).transact({'from': ursula3})
        testerchain.wait_for_receipt(tx)

    testerchain.time_travel(hours=1)
    # Now can turn off re-stake
    tx = preallocation_escrow_interface_1.functions.setReStake(False).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.stakerInfo(preallocation_escrow_1.address).call()[DISABLE_RE_STAKE_FIELD]

    tx = escrow.functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow_interface_2.functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow_interface_1.functions.mint().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    assert 0 == escrow.functions.getLockedTokens(ursula1, 0).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 0).call()
    assert 0 == escrow.functions.getLockedTokens(ursula3, 0).call()
    assert 0 == escrow.functions.getLockedTokens(ursula4, 0).call()
    assert 0 == escrow.functions.getLockedTokens(preallocation_escrow_1.address, 0).call()
    assert 0 == escrow.functions.getLockedTokens(preallocation_escrow_2.address, 0).call()
    assert 0 == escrow.functions.getLockedTokens(preallocation_escrow_3.address, 0).call()

    ursula1_balance = token.functions.balanceOf(ursula1).call()
    ursula2_balance = token.functions.balanceOf(preallocation_escrow_2.address).call()
    preallocation_escrow_1_balance = token.functions.balanceOf(preallocation_escrow_1.address).call()
    tokens_amount = escrow.functions.getAllTokens(ursula1).call()
    tx = escrow.functions.withdraw(tokens_amount).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tokens_amount = escrow.functions.getAllTokens(preallocation_escrow_2.address).call()
    tx = preallocation_escrow_interface_2.functions.withdrawAsStaker(tokens_amount).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tokens_amount = escrow.functions.getAllTokens(preallocation_escrow_1.address).call()
    tx = preallocation_escrow_interface_1.functions.withdrawAsStaker(tokens_amount).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    assert ursula1_balance < token.functions.balanceOf(ursula1).call()
    assert ursula2_balance < token.functions.balanceOf(preallocation_escrow_2.address).call()
    assert preallocation_escrow_1_balance < token.functions.balanceOf(preallocation_escrow_1.address).call()

    # Unlock and withdraw all tokens in PreallocationEscrow
    testerchain.time_travel(hours=1)
    assert 0 == preallocation_escrow_1.functions.getLockedTokens().call()
    assert 0 == preallocation_escrow_3.functions.getLockedTokens().call()
    ursula3_balance = token.functions.balanceOf(ursula3).call()
    ursula4_balance = token.functions.balanceOf(ursula4).call()
    tokens_amount = token.functions.balanceOf(preallocation_escrow_1.address).call()
    tx = preallocation_escrow_1.functions.withdrawTokens(tokens_amount).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)
    tokens_amount = token.functions.balanceOf(preallocation_escrow_3.address).call()
    tx = preallocation_escrow_3.functions.withdrawTokens(tokens_amount).transact({'from': ursula4})
    testerchain.wait_for_receipt(tx)
    assert ursula3_balance < token.functions.balanceOf(ursula3).call()
    assert ursula4_balance < token.functions.balanceOf(ursula4).call()

    # Partial refund for Ursula
    new_completed_work = escrow.functions.getCompletedWork(preallocation_escrow_2.address).call()
    assert completed_work < new_completed_work
    remaining_work = worklock.functions.getRemainingWork(preallocation_escrow_2.address).call()
    assert 0 < remaining_work
    assert deposited_eth_1 == worklock.functions.workInfo(ursula2).call()[0]
    ursula2_balance = testerchain.w3.eth.getBalance(ursula2)
    tx = worklock.functions.refund(preallocation_escrow_2.address).transact({'from': ursula2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    refund = worklock.functions.workToETH(new_completed_work).call()
    assert deposited_eth_1 - refund == worklock.functions.workInfo(ursula2).call()[0]
    assert refund + ursula2_balance == testerchain.w3.eth.getBalance(ursula2)
    assert deposited_eth_1 + deposited_eth_2 - refund == testerchain.w3.eth.getBalance(worklock.address)
    assert 0 == escrow.functions.getCompletedWork(ursula1).call()
    assert 0 == escrow.functions.getCompletedWork(preallocation_escrow_1.address).call()
