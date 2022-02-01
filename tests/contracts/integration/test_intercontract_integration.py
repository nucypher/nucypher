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

from nucypher_core.umbral import SecretKey, Signer

from nucypher.blockchain.economics import Economics, Economics
from nucypher.blockchain.eth.constants import NULL_ADDRESS, POLICY_ID_LENGTH
from nucypher.blockchain.eth.token import NU
from nucypher.crypto.utils import sha256_digest
from nucypher.crypto.signing import SignatureStamp
from nucypher.utilities.ethereum import to_32byte_hex


def pytest_namespace():
    return {'escrow_supply': 0,
            'staker1_tokens': 0,
            'staker4_tokens': 0,
            'staker1_completed_work': 0,
            'staker2_completed_work': 0}


@pytest.fixture(scope='module')
def token_economics():
    economics = Economics(
        maximum_allowed_locked=Economics._default_minimum_allowed_locked * 10
    )
    return economics


@pytest.fixture(scope='module')
def token(application_economics, deploy_contract):
    # Create an ERC20 token
    contract, _ = deploy_contract('NuCypherToken', _totalSupplyOfTokens=application_economics.erc20_total_supply)
    return contract


@pytest.fixture(scope='module')
def escrow_dispatcher(testerchain, token, application_economics, deploy_contract):
    escrow_stub, _ = deploy_contract('StakingEscrowStub',
                                     token.address,
                                     application_economics.min_authorization,
                                     application_economics.maximum_allowed_locked)
    dispatcher, _ = deploy_contract('Dispatcher', escrow_stub.address)
    return dispatcher


@pytest.fixture(scope='module')
def worklock(testerchain, token, escrow_dispatcher, application_economics, deploy_contract):
    # Creator deploys the worklock using test values
    now = testerchain.w3.eth.getBlock('latest').timestamp
    start_bid_date = ((now + 3600) // 3600 + 1) * 3600  # beginning of the next hour plus 1 hour
    end_bid_date = start_bid_date + 3600
    end_cancellation_date = end_bid_date + 3600
    boosting_refund = 100
    staking_periods = application_economics.min_operator_seconds
    min_allowed_bid = to_wei(1, 'ether')
    contract, _ = deploy_contract(
        contract_name='WorkLock',
        _token=token.address,
        _escrow=escrow_dispatcher.address,
        _startBidDate=start_bid_date,
        _endBidDate=end_bid_date,
        _endCancellationDate=end_cancellation_date,
        _boostingRefund=boosting_refund,
        _stakingPeriods=staking_periods,
        _minAllowedBid=min_allowed_bid
    )

    return contract


@pytest.fixture(scope='module')
def threshold_staking(deploy_contract):
    threshold_staking, _ = deploy_contract('ThresholdStakingForStakingEscrowMock')
    return threshold_staking


@pytest.fixture(scope='module')
def escrow_bare(testerchain,
                token,
                worklock,
                threshold_staking,
                escrow_dispatcher,
                deploy_contract):
    # Creator deploys the escrow
    contract, _ = deploy_contract(
        'EnhancedStakingEscrow',
        token.address,
        worklock.address,
        threshold_staking.address
    )

    tx = escrow_dispatcher.functions.upgrade(contract.address).transact()
    testerchain.wait_for_receipt(tx)

    return contract


@pytest.fixture(scope='module')
def escrow(testerchain, escrow_bare, escrow_dispatcher):
    # Wrap dispatcher contract
    contract = testerchain.client.get_contract(
        abi=escrow_bare.abi,
        address=escrow_dispatcher.address,
        ContractFactoryClass=Contract)
    return contract


def mock_ursula(testerchain, account, mocker):
    ursula_privkey = SecretKey.random()
    ursula_stamp = SignatureStamp(verifying_key=ursula_privkey.public_key(),
                                  signer=Signer(ursula_privkey))

    signed_stamp = testerchain.client.sign_message(account=account,
                                                   message=bytes(ursula_stamp))

    ursula = mocker.Mock(stamp=ursula_stamp, decentralized_identity_evidence=signed_stamp)
    return ursula


@pytest.fixture(scope='module')
def staking_interface(testerchain, token, escrow, worklock, threshold_staking, deploy_contract):
    policy_manager, _ = deploy_contract('PolicyManagerForStakingContractMock')
    # Creator deploys the staking interface
    staking_interface, _ = deploy_contract(
        'StakingInterface',
        token.address,
        escrow.address,
        policy_manager.address,
        worklock.address,
        threshold_staking.address
    )
    return staking_interface


@pytest.fixture(scope='module')
def staking_interface_router(testerchain, staking_interface, deploy_contract):
    router, _ = deploy_contract('StakingInterfaceRouter', staking_interface.address)
    return router


@pytest.fixture(scope='module')
def simple_staking_contract(testerchain, staking_interface, staking_interface_router, deploy_contract):
    creator = testerchain.w3.eth.accounts[0]
    staker3 = testerchain.client.accounts[3]

    # Create the first preallocation escrow
    contract, _ = deploy_contract('SimpleStakingContract', staking_interface_router.address)
    tx = contract.functions.transferOwnership(staker3).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    return contract


@pytest.fixture(scope='module')
def simple_staking_contract_interface(testerchain, staking_interface, simple_staking_contract):
    contract = testerchain.client.get_contract(
        abi=staking_interface.abi,
        address=simple_staking_contract.address,
        ContractFactoryClass=Contract)

    return contract


def test_worklock_phases(testerchain,
                         application_economics,
                         token,
                         escrow,
                         simple_staking_contract,
                         simple_staking_contract_interface,
                         worklock):
    creator, staker1, staker2, staker3, staker4, alice1, alice2, *contracts_owners =\
        testerchain.client.accounts

    # Initialize worklock
    worklock_supply = 3 * application_economics.min_authorization + application_economics.maximum_allowed_locked
    tx = token.functions.approve(worklock.address, worklock_supply).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.tokenDeposit(worklock_supply).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Give staker some ether
    tx = testerchain.w3.eth.sendTransaction(
        {'from': testerchain.w3.eth.coinbase, 'to': staker2, 'value': 10 ** 10})
    testerchain.wait_for_receipt(tx)

    # Can't do anything before start date
    deposited_eth_1 = to_wei(18, 'ether')
    deposited_eth_2 = to_wei(1, 'ether')
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact({'from': staker2, 'value': deposited_eth_1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Wait for the start of the bidding
    testerchain.time_travel(hours=2)

    # Staker does bid
    min_stake = application_economics.min_authorization
    bonus_worklock_supply = worklock_supply - min_stake
    assert worklock.functions.workInfo(staker2).call()[0] == 0
    assert testerchain.w3.eth.getBalance(worklock.address) == 0
    tx = worklock.functions.bid().transact({'from': staker2, 'value': deposited_eth_1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker2).call()[0] == deposited_eth_1
    worklock_balance = deposited_eth_1
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert worklock.functions.ethToTokens(deposited_eth_1).call() == min_stake + bonus_worklock_supply

    # Can't claim while bidding phase
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.claim().transact({'from': staker2, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Other stakers do bid
    assert worklock.functions.workInfo(simple_staking_contract.address).call()[0] == 0
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': simple_staking_contract.address, 'value': deposited_eth_2})
    testerchain.wait_for_receipt(tx)
    assert testerchain.w3.eth.getBalance(simple_staking_contract.address) == deposited_eth_2
    tx = simple_staking_contract_interface.functions.bid(deposited_eth_2).transact({'from': staker3, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert testerchain.w3.eth.getBalance(simple_staking_contract.address) == 0
    assert worklock.functions.workInfo(simple_staking_contract.address).call()[0] == deposited_eth_2
    worklock_balance += deposited_eth_2
    bonus_worklock_supply -= min_stake
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert worklock.functions.ethToTokens(deposited_eth_2).call() == min_stake
    assert worklock.functions.ethToTokens(deposited_eth_1).call() == min_stake + bonus_worklock_supply

    assert worklock.functions.workInfo(staker1).call()[0] == 0
    tx = worklock.functions.bid().transact({'from': staker1, 'value': 2 * deposited_eth_2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker1).call()[0] == 2 * deposited_eth_2
    worklock_balance += 2 * deposited_eth_2
    bonus_worklock_supply -= min_stake
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert worklock.functions.ethToTokens(deposited_eth_2).call() == min_stake
    assert worklock.functions.ethToTokens(2 * deposited_eth_2).call() == min_stake + bonus_worklock_supply // 18

    # Wait for the end of the bidding
    testerchain.time_travel(hours=1)

    # Can't bid after the end of bidding
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact({'from': staker2, 'value': 1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # One of stakers cancels bid
    assert worklock.functions.getBiddersLength().call() == 3
    tx = simple_staking_contract_interface.functions.cancelBid().transact({'from': staker3, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(simple_staking_contract.address).call()[0] == 0
    worklock_balance -= deposited_eth_2
    bonus_worklock_supply += min_stake
    assert testerchain.w3.eth.getBalance(simple_staking_contract.address) == deposited_eth_2
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert worklock.functions.ethToTokens(deposited_eth_2).call() == min_stake
    assert worklock.functions.ethToTokens(2 * deposited_eth_2).call() == min_stake + bonus_worklock_supply // 18
    assert worklock.functions.getBiddersLength().call() == 2
    assert worklock.functions.bidders(1).call() == staker1
    assert worklock.functions.workInfo(staker1).call()[3] == 1

    # Wait for the end of the cancellation window
    testerchain.time_travel(hours=1)

    # Can't cancel after the end of cancellation window
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.cancelBid().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    # Can't claim before check
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.claim().transact({'from': staker2, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Do force refund to whale
    assert worklock.functions.ethToTokens(deposited_eth_1).call() > application_economics.maximum_allowed_locked
    staker2_balance = testerchain.w3.eth.getBalance(staker2)
    tx = worklock.functions.forceRefund([staker2]).transact()
    testerchain.wait_for_receipt(tx)
    staker2_bid = worklock.functions.workInfo(staker2).call()[0]
    refund = deposited_eth_1 - staker2_bid
    assert refund > 0
    staker2_tokens = worklock.functions.ethToTokens(staker2_bid).call()
    assert staker2_tokens <= application_economics.maximum_allowed_locked
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert testerchain.w3.eth.getBalance(staker2) == staker2_balance
    assert worklock.functions.compensation(staker2).call() == refund

    tx = worklock.functions.withdrawCompensation().transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    worklock_balance -= refund
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert testerchain.w3.eth.getBalance(staker2) == staker2_balance + refund
    assert worklock.functions.compensation(staker2).call() == 0

    # Check all bidders
    assert worklock.functions.getBiddersLength().call() == 2
    assert worklock.functions.nextBidderToCheck().call() == 0
    tx = worklock.functions.verifyBiddingCorrectness(30000).transact()
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.nextBidderToCheck().call() == 2

    # Stakers claim tokens
    assert not worklock.functions.workInfo(staker2).call()[2]
    tx = worklock.functions.claim().transact({'from': staker2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker2).call()[2]

    assert token.functions.balanceOf(staker2).call() == 0
    staker2_remaining_work = staker2_tokens
    assert worklock.functions.ethToWork(staker2_bid).call() == staker2_remaining_work
    assert worklock.functions.workToETH(staker2_remaining_work, staker2_bid).call() == staker2_bid
    assert worklock.functions.getRemainingWork(staker2).call() == 0
    assert token.functions.balanceOf(worklock.address).call() == worklock_supply - staker2_tokens
    pytest.escrow_supply = staker2_tokens
    assert escrow.functions.getAllTokens(staker2).call() == staker2_tokens
    assert escrow.functions.getCompletedWork(staker2).call() == application_economics.total_supply

    tx = worklock.functions.claim().transact({'from': staker1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker1).call()[2]
    staker1_claims = worklock.functions.ethToTokens(2 * deposited_eth_2).call()
    pytest.staker1_tokens = staker1_claims
    assert escrow.functions.getAllTokens(staker1).call() == pytest.staker1_tokens
    pytest.escrow_supply += staker1_claims

    # Can't claim more than once
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.claim().transact({'from': staker2, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)


def test_upgrading_and_rollback(testerchain,
                                token,
                                escrow,
                                escrow_dispatcher,
                                staking_interface_router,
                                worklock,
                                threshold_staking,
                                deploy_contract):
    creator, staker1, staker2, staker3, staker4, alice1, alice2, *others =\
        testerchain.client.accounts

    # Upgrade main contracts
    escrow_v1 = escrow.functions.target().call()
    # Creator deploys the contracts as the second versions
    escrow_v2, _ = deploy_contract(
        'StakingEscrow',
        token.address,
        worklock.address,
        threshold_staking.address
    )
    # Staker and Alice can't upgrade contracts, only owner can
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow_dispatcher.functions.upgrade(escrow_v2.address).transact({'from': alice1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow_dispatcher.functions.upgrade(escrow_v2.address).transact({'from': staker1})
        testerchain.wait_for_receipt(tx)

    # Prepare transactions to upgrade contracts
    tx = escrow_dispatcher.functions.upgrade(escrow_v2.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert escrow_v2.address == escrow.functions.target().call()

    # Staker and Alice can't rollback contracts, only owner can
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow_dispatcher.functions.rollback().transact({'from': alice1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow_dispatcher.functions.rollback().transact({'from': staker1})
        testerchain.wait_for_receipt(tx)

    # Prepare transactions to rollback contracts
    tx = escrow_dispatcher.functions.rollback().transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert escrow_v1 == escrow.functions.target().call()

    # Upgrade the staking interface
    # Deploy the same contract as the second version
    policy_manager, _ = deploy_contract('PolicyManagerForStakingContractMock')
    staking_interface_v2, _ = deploy_contract(
        'StakingInterface',
        token.address,
        escrow.address,
        policy_manager.address,
        worklock.address,
        threshold_staking.address
    )
    # Staker and Alice can't upgrade library, only owner can
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface_router.functions.upgrade(staking_interface_v2.address).transact({'from': alice1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface_router.functions.upgrade(staking_interface_v2.address).transact({'from': staker1})
        testerchain.wait_for_receipt(tx)

    # Prepare transactions to upgrade library
    tx = staking_interface_router.functions.upgrade(staking_interface_v2.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert staking_interface_v2.address == staking_interface_router.functions.target().call()


def test_refund(testerchain, escrow, worklock, application_economics):
    staker1, staker2, staker3, staker4 = testerchain.client.accounts[1:5]
    deposited_eth_2 = to_wei(1, 'ether')
    worklock_balance = testerchain.w3.eth.getBalance(worklock.address)

    # Full refund for staker
    assert escrow.functions.getCompletedWork(staker1).call() == application_economics.total_supply
    remaining_work = worklock.functions.getRemainingWork(staker1).call()
    assert remaining_work == 0
    assert worklock.functions.workInfo(staker1).call()[0] == 2 * deposited_eth_2
    staker1_balance = testerchain.w3.eth.getBalance(staker1)
    tx = worklock.functions.refund().transact({'from': staker1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker1).call()[0] == 0
    assert testerchain.w3.eth.getBalance(staker1) == staker1_balance + 2 * deposited_eth_2
    worklock_balance -= 2 * deposited_eth_2
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
