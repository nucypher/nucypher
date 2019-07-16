import json
import os

import pytest
from constant_sorrow.constants import NO_STAKES
from web3 import Web3

from nucypher.blockchain.eth.actors import StakeHolder, Worker
from nucypher.blockchain.eth.agents import Agency, StakingEscrowAgent, NucypherTokenAgent
from nucypher.blockchain.eth.token import NU
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD


@pytest.fixture(scope='session')
def stakeholder_config_file_location():
    path = os.path.join('/', 'tmp', 'nucypher-test-stakeholder.json')
    if os.path.exists(path):
        os.remove(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture(scope='module')
def staking_software_stakeholder(testerchain, agency, stakeholder_config_file_location):

    # Setup
    path = stakeholder_config_file_location
    if os.path.exists(path):
        os.remove(path)

    #                          0xaAa482c790b4301bE18D75A0D1B11B2ACBEF798B
    stakeholder_private_key = '255f64a948eeb1595b8a2d1e76740f4683eca1c8f1433d13293db9b6e27676cc'
    address = testerchain.provider.ethereum_tester.add_account(stakeholder_private_key,
                                                               password=INSECURE_DEVELOPMENT_PASSWORD)

    testerchain.provider.ethereum_tester.unlock_account(address, password=INSECURE_DEVELOPMENT_PASSWORD)

    tx = {'to': address,
          'from': testerchain.etherbase_account,
          'value': Web3.toWei('1', 'ether')}

    txhash = testerchain.client.w3.eth.sendTransaction(tx)
    _receipt = testerchain.wait_for_receipt(txhash)

    # Mock TransactingPower consumption (Etherbase)
    transacting_power = TransactingPower(account=testerchain.etherbase_account,
                                         password=INSECURE_DEVELOPMENT_PASSWORD,
                                         blockchain=testerchain)
    transacting_power.activate()

    token_agent = Agency.get_agent(NucypherTokenAgent)
    token_agent.transfer(amount=NU(200_000, 'NU').to_nunits(),
                         sender_address=testerchain.etherbase_account,
                         target_address=address)

    # Create stakeholder from on-chain values given accounts over a web3 provider
    stakeholder = StakeHolder(blockchain=testerchain,
                              funding_account=address,
                              funding_password=INSECURE_DEVELOPMENT_PASSWORD,
                              trezor=False)

    assert stakeholder.funding_power.is_unlocked is True

    # Teardown
    yield stakeholder
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture(scope='module')
def manual_worker(testerchain):
    worker_private_key = '4115115f4159db59a06327aa29544c417c52ddb80a4a26517367ff4514e0f694'
    address = testerchain.provider.ethereum_tester.add_account(worker_private_key,
                                                               password=INSECURE_DEVELOPMENT_PASSWORD)

    tx = {'to': address,
          'from': testerchain.etherbase_account,
          'value': Web3.toWei('1', 'ether')}

    txhash = testerchain.client.w3.eth.sendTransaction(tx)
    _receipt = testerchain.wait_for_receipt(txhash)
    yield address


def test_software_stakeholder_configuration(testerchain,
                                            staking_software_stakeholder,
                                            stakeholder_config_file_location):

    stakeholder = staking_software_stakeholder
    path = stakeholder_config_file_location

    # Check attributes can be successfully read
    assert stakeholder.total_stake == 0
    assert not stakeholder.stakes
    assert stakeholder.accounts

    # Save the stakeholder JSON config
    stakeholder.to_configuration_file(filepath=path)
    with open(stakeholder.filepath, 'r') as file:

        # Ensure file contents are serializable
        contents = file.read()
        first_config_contents = json.loads(contents)

    # Destroy this stake holder, leaving only the configuration file behind
    del stakeholder

    # Restore StakeHolder instance from JSON config
    the_same_stakeholder = StakeHolder.from_configuration_file(filepath=path,
                                                               funding_password=INSECURE_DEVELOPMENT_PASSWORD,
                                                               blockchain=testerchain)

    # Save the JSON config again
    the_same_stakeholder.to_configuration_file(filepath=path, override=True)
    with open(the_same_stakeholder.filepath, 'r') as file:
        contents = file.read()
        second_config_contents = json.loads(contents)

    # Ensure the stakeholder was accurately restored from JSON config
    assert first_config_contents == second_config_contents


def test_initialize_stake_with_new_software_wallet_account(staking_software_stakeholder,
                                                           testerchain,
                                                           stake_value,
                                                           token_economics):

    # There are no stakers and not stakes
    assert len(staking_software_stakeholder.stakers) == 0
    with pytest.raises(IndexError):
        _stake = staking_software_stakeholder.stakes[0]

    # Record the number of accounts before staking.
    number_of_accounts = len(staking_software_stakeholder.accounts)

    # Stake, deriving a new account, using tokens and ethers from the funding account
    stake = staking_software_stakeholder.initialize_stake(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                          amount=stake_value,
                                                          duration=token_economics.minimum_locked_periods)

    # A new account was derived for the new staker.
    assert len(staking_software_stakeholder.accounts) == number_of_accounts + 1

    # Wait for the stake to begin (+1 Period from init)
    testerchain.time_travel(periods=1)

    # Ensure the stakeholder is tracking the new staker and stake.
    assert len(staking_software_stakeholder.stakers) == 1
    assert len(staking_software_stakeholder.stakes) == 1

    # Ensure the stakeholder and stakes agree on staking metadata
    assert stake.blockchain == staking_software_stakeholder.blockchain
    assert stake.owner_address != staking_software_stakeholder.funding_account
    assert stake.value == stake_value
    assert stake.duration == token_economics.minimum_locked_periods

    # Lookup the new staker by address
    staker = staking_software_stakeholder.get_active_staker(address=stake.owner_address)
    assert len(staker.stakes) == 1
    assert staker.stakes[0] == stake

    # Ensure stake is on-chain via agency
    staking_agent = Agency.get_agent(StakingEscrowAgent)
    stakes = list(staking_agent.get_all_stakes(staker_address=stake.owner_address))
    assert len(stakes) == 1


def test_initialize_stake_with_existing_staking_account(staking_software_stakeholder, stake_value, token_economics):

    # There is one staker and one stake.
    assert len(staking_software_stakeholder.stakers) == 1
    assert len(staking_software_stakeholder.stakes) == 1

    stake = staking_software_stakeholder.stakes[0]

    # Really... there is one stake.
    staking_agent = Agency.get_agent(StakingEscrowAgent)
    stakes = list(staking_agent.get_all_stakes(staker_address=stake.owner_address))
    assert len(stakes) == 1

    # Stake, deriving a new account with a password,
    # sending tokens and ethers from the funding account
    # to the staker's account, then initializing a new stake.
    stake = staking_software_stakeholder.initialize_stake(checksum_address=stake.owner_address,
                                                          amount=stake_value,
                                                          duration=token_economics.minimum_locked_periods)

    # Wait for stake to begin
    staking_software_stakeholder.blockchain.time_travel(periods=1)

    # Ensure the stakeholder is tracking the new staker and stake.
    assert len(staking_software_stakeholder.stakers) == 1
    assert len(staking_software_stakeholder.stakes) == 2

    # Ensure common stake perspective between stakeholder and stake
    assert stake.blockchain == staking_software_stakeholder.blockchain
    assert stake.value == stake_value
    assert stake.duration == token_economics.minimum_locked_periods
    assert stake.owner_address != staking_software_stakeholder.funding_account

    stakes = list(staking_agent.get_all_stakes(staker_address=stake.owner_address))
    assert len(stakes) == 2


def test_divide_stake(staking_software_stakeholder, token_economics):
    stake = staking_software_stakeholder.stakes[1]

    target_value = token_economics.minimum_allowed_locked
    pre_divide_stake_value = stake.value

    original_stake, new_stake = staking_software_stakeholder.divide_stake(address=stake.owner_address,
                                                                          password=INSECURE_DEVELOPMENT_PASSWORD,
                                                                          index=0,
                                                                          duration=10,
                                                                          value=target_value)

    staking_agent = Agency.get_agent(StakingEscrowAgent)
    stakes = list(staking_agent.get_all_stakes(staker_address=stake.owner_address))
    assert len(stakes) == 3
    assert new_stake.value == target_value
    assert original_stake.value == (pre_divide_stake_value - target_value)


def test_set_worker(staking_software_stakeholder, manual_worker):
    stake = staking_software_stakeholder.stakes[1]

    staker = staking_software_stakeholder.get_active_staker(stake.owner_address)
    staking_agent = Agency.get_agent(StakingEscrowAgent)

    staking_software_stakeholder.set_worker(staker_address=staker.checksum_address,
                                            worker_address=manual_worker)
    assert staking_agent.get_worker_from_staker(staker_address=staker.checksum_address) == manual_worker


def test_collect_inflation_rewards(staking_software_stakeholder, manual_worker, testerchain):

    # Get stake
    stake = staking_software_stakeholder.stakes[1]

    # Make assigned Worker
    worker = Worker(is_me=True,
                    worker_address=manual_worker,
                    checksum_address=stake.owner_address,
                    start_working_loop=False,
                    blockchain=testerchain)

    # Mock TransactingPower consumption (Worker-Ursula)
    worker.blockchain.transacting_power = TransactingPower(account=manual_worker, blockchain=testerchain)
    worker.blockchain.transacting_power.activate()

    # Wait out stake duration, manually confirming activity once per period.
    periods_remaining = stake.end_period - worker.staking_agent.get_current_period()

    for period in range(periods_remaining):
        worker.confirm_activity()
        testerchain.time_travel(periods=1)

    # Mock TransactingPower consumption (Staker-Ursula)
    worker.blockchain.transacting_power = TransactingPower(account=testerchain.etherbase_account, blockchain=testerchain)
    worker.blockchain.transacting_power.activate()

    # Collect the staking reward in NU.
    result = staking_software_stakeholder.collect_rewards(staker_address=stake.owner_address,
                                                          staking=True,  # collect only inflation reward.
                                                          policy=False,
                                                          password=INSECURE_DEVELOPMENT_PASSWORD)

    # TODO: Make Assertions reasonable for this layer.
    #       Consider recycling logic from test_collect_reward_integration CLI test.
    assert result
