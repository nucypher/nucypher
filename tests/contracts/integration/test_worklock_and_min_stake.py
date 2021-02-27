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
from umbral.keys import UmbralPrivateKey
from umbral.signing import Signer
from web3.contract import Contract

from nucypher.blockchain.economics import BaseEconomics, StandardTokenEconomics
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.crypto.api import sha256_digest
from nucypher.crypto.signing import SignatureStamp
from nucypher.utilities.ethereum import to_32byte_hex


@pytest.fixture(scope='module')
def token(token_economics, deploy_contract):
    # Create an ERC20 token
    contract, _ = deploy_contract('NuCypherToken', _totalSupplyOfTokens=token_economics.erc20_total_supply)
    return contract


@pytest.fixture(scope='module')
def escrow_dispatcher(testerchain, token, token_economics, deploy_contract):
    escrow_stub, _ = deploy_contract('StakingEscrowStub',
                                     token.address,
                                     token_economics.genesis_hours_per_period,
                                     token_economics.hours_per_period,
                                     token_economics.minimum_locked_periods,
                                     token_economics.minimum_allowed_locked,
                                     token_economics.maximum_allowed_locked)
    dispatcher, _ = deploy_contract('Dispatcher', escrow_stub.address)
    return dispatcher


@pytest.fixture(scope='module')
def policy_manager(deploy_contract, token_economics):
    policy_manager, _ = deploy_contract(
        'PolicyManagerForStakingEscrowMock', NULL_ADDRESS, token_economics.seconds_per_period)
    return policy_manager


@pytest.fixture(scope='module')
def adjudicator(deploy_contract, token_economics):
    adjudicator, _ = deploy_contract('AdjudicatorForStakingEscrowMock', token_economics.reward_coefficient)
    return adjudicator


@pytest.fixture(scope='module')
def worklock(testerchain, token, escrow_dispatcher, token_economics, deploy_contract):
    # Creator deploys the worklock using test values
    now = testerchain.w3.eth.getBlock('latest').timestamp
    end_bid_date = now + 2 * token_economics.seconds_per_period
    end_cancellation_date = end_bid_date
    contract, _ = deploy_contract(
        contract_name='WorkLock',
        _token=token.address,
        _escrow=escrow_dispatcher.address,
        _startBidDate=now,
        _endBidDate=end_bid_date,
        _endCancellationDate=end_cancellation_date,
        _boostingRefund=token_economics.worklock_boosting_refund_rate,
        _stakingPeriods=token_economics.worklock_commitment_duration,
        _minAllowedBid=token_economics.worklock_min_allowed_bid
    )

    return contract


@pytest.fixture(scope='module')
def escrow_bare(testerchain,
                token,
                policy_manager,
                adjudicator,
                worklock,
                token_economics,
                escrow_dispatcher,
                deploy_contract):
    # Creator deploys the escrow
    contract, _ = deploy_contract(
        'StakingEscrow',
        token.address,
        policy_manager.address,
        adjudicator.address,
        worklock.address,
        *token_economics.staking_deployment_parameters
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


def test_staking_before_changing_min_stake(testerchain, token_economics, token, escrow, worklock):
    creator, staker1, staker2, worklock_staker1, worklock_staker2, *everyone_else =\
        testerchain.client.accounts

    # Travel to the start of the next period to prevent problems with unexpected overflow first period
    testerchain.time_travel(periods=1, periods_base=token_economics.seconds_per_period)

    # Initialize worklock
    worklock_supply = 4 * token_economics.minimum_allowed_locked
    tx = token.functions.approve(worklock.address, worklock_supply).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.tokenDeposit(worklock_supply).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Give Escrow tokens for reward and initialize contract
    tx = token.functions.approve(escrow.address, token_economics.erc20_reward_supply).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.initialize(token_economics.erc20_reward_supply, creator).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Prepare stakers
    value = token_economics.maximum_allowed_locked
    for staker in (staker1, staker2):
        tx = token.functions.transfer(staker, value).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
        tx = token.functions.approve(escrow.address, value).transact({'from': staker})
        testerchain.wait_for_receipt(tx)

    # Prepare worklockers
    eth_value = token_economics.worklock_min_allowed_bid
    for worklock_staker in (worklock_staker1, worklock_staker2):
        tx = testerchain.w3.eth.sendTransaction(
            {'from': testerchain.w3.eth.coinbase, 'to': worklock_staker, 'value': eth_value})
        testerchain.wait_for_receipt(tx)
        tx = worklock.functions.bid().transact({'from': worklock_staker, 'value': eth_value, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    tx = testerchain.w3.eth.sendTransaction(
        {'from': testerchain.w3.eth.coinbase, 'to': everyone_else[0], 'value': eth_value + 1})
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.bid().transact({'from': everyone_else[0], 'value': eth_value + 1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(periods=3, periods_base=token_economics.seconds_per_period)

    # Prepare WorkLock
    assert worklock.functions.getBiddersLength().call() == 3
    assert worklock.functions.nextBidderToCheck().call() == 0
    tx = worklock.functions.verifyBiddingCorrectness(30000).transact()
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.nextBidderToCheck().call() == 3

    # Create min sub-stake directly and from WorkLock
    value = token_economics.minimum_allowed_locked
    duration = token_economics.minimum_locked_periods
    tx = escrow.functions.deposit(staker1, value, duration).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.claim().transact({'from': worklock_staker1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.getLockedTokens(staker1, 1).call() == value
    assert escrow.functions.getLockedTokens(worklock_staker1, 1).call() == value


def test_staking_after_changing_min_stake(testerchain,
                                          deploy_contract,
                                          token_economics,
                                          token,
                                          escrow,
                                          escrow_dispatcher,
                                          worklock,
                                          policy_manager,
                                          adjudicator):
    creator, staker1, staker2, worklock_staker1, worklock_staker2, *everyone_else =\
        testerchain.client.accounts

    # Upgrade to increase min stake size
    new_token_economics = StandardTokenEconomics(minimum_allowed_locked=2*token_economics.minimum_allowed_locked)
    escrow_v2, _ = deploy_contract(
        'StakingEscrow',
        token.address,
        policy_manager.address,
        adjudicator.address,
        worklock.address,
        *new_token_economics.staking_deployment_parameters
    )
    tx = escrow_dispatcher.functions.upgrade(escrow_v2.address).transact()
    testerchain.wait_for_receipt(tx)

    # Can't create sub-stake with old min size
    old_value = token_economics.minimum_allowed_locked
    duration = token_economics.minimum_locked_periods
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(staker2, old_value, duration).transact({'from': staker2})
        testerchain.wait_for_receipt(tx)

    # Create min sub-stake directly and from WorkLock
    new_value = new_token_economics.minimum_allowed_locked
    tx = escrow.functions.deposit(staker2, new_value, duration).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.claim().transact({'from': worklock_staker2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.getLockedTokens(staker2, 1).call() == new_value
    assert escrow.functions.getLockedTokens(worklock_staker2, 1).call() == old_value
