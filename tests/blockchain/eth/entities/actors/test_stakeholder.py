import json
import os

import pytest
from constant_sorrow.constants import NO_STAKES
from web3 import Web3

from nucypher.blockchain.eth.actors import Worker
from nucypher.characters.lawful import StakeHolder
from nucypher.blockchain.eth.agents import StakingEscrowAgent, NucypherTokenAgent
from nucypher.blockchain.eth.token import NU
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD


def test_software_stakeholder_configuration(testerchain,
                                            software_stakeholder,
                                            stakeholder_config_file_location):

    stakeholder = software_stakeholder
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
                                                               registry=test_registry)

    # Save the JSON config again
    the_same_stakeholder.to_configuration_file(filepath=path, override=True)
    with open(the_same_stakeholder.filepath, 'r') as file:
        contents = file.read()
        second_config_contents = json.loads(contents)

    # Ensure the stakeholder was accurately restored from JSON config
    assert first_config_contents == second_config_contents


def test_initialize_stake_with_existing_account(software_stakeholder, stake_value, token_economics):

    # There are no stakes.
    assert len(software_stakeholder.stakers) == 0
    assert len(software_stakeholder.stakes) == 0

    # No Stakes
    with pytest.raises(IndexError):
        stake = software_stakeholder.stakes[0]

    # Really... there are no stakes.
    stakes = list(staking_agent.get_all_stakes(staker_address=software_stakeholder.accounts[0]))
    assert len(stakes) == 0

    # Stake, deriving a new account with a password,
    # sending tokens and ethers from the funding account
    # to the staker's account, then initializing a new stake.
    stake = software_stakeholder.initialize_stake(checksum_address=software_stakeholder.accounts[0],
                                                  amount=stake_value,
                                                  duration=token_economics.minimum_locked_periods)

    # Wait for stake to begin
    software_stakeholder.blockchain.time_travel(periods=1)

    # Ensure the stakeholder is tracking the new staker and stake.
    assert len(software_stakeholder.stakers) == 1
    assert len(software_stakeholder.stakes) == 1

    # Ensure common stake perspective between stakeholder and stake
    assert stake.blockchain == software_stakeholder.blockchain
    assert stake.value == stake_value
    assert stake.duration == token_economics.minimum_locked_periods

    stakes = list(staking_agent.get_all_stakes(staker_address=stake.owner_address))
    assert len(stakes) == 1


def test_divide_stake(software_stakeholder, token_economics):
    stake = software_stakeholder.stakes[0]

    target_value = token_economics.minimum_allowed_locked
    pre_divide_stake_value = stake.value

    original_stake, new_stake = software_stakeholder.divide_stake(address=stake.owner_address,
                                                                  password=INSECURE_DEVELOPMENT_PASSWORD,
                                                                  index=0,
                                                                  duration=10,
                                                                  value=target_value)

    stakes = list(staking_agent.get_all_stakes(staker_address=stake.owner_address))
    assert len(stakes) == 2
    assert new_stake.value == target_value
    assert original_stake.value == (pre_divide_stake_value - target_value)


def test_set_worker(software_stakeholder, manual_worker):
    stake = software_stakeholder.stakes[1]

    staker = software_stakeholder.get_active_staker(stake.owner_address)

    software_stakeholder.set_worker(staker_address=staker.checksum_address,
                                    worker_address=manual_worker)
    assert staking_agent.get_worker_from_staker(staker_address=staker.checksum_address) == manual_worker


def test_collect_inflation_rewards(software_stakeholder, manual_worker, testerchain):

    # Get stake
    stake = software_stakeholder.stakes[1]

    # Make assigned Worker
    worker = Worker(is_me=True,
                    worker_address=manual_worker,
                    checksum_address=stake.owner_address,
                    start_working_loop=False,
                    blockchain=testerchain)

    # Mock TransactingPower consumption (Worker-Ursula)
    worker.blockchain.transacting_power = TransactingPower(account=manual_worker, blockchain=testerchain)
    worker.blockchain.transacting_power.activate()

    # Wait out stake lock_periods, manually confirming activity once per period.
    periods_remaining = stake.end_period - worker.staking_agent.get_current_period()

    for period in range(periods_remaining):
        worker.confirm_activity()
        testerchain.time_travel(periods=1)

    # Mock TransactingPower consumption (Staker-Ursula)
    worker.blockchain.transacting_power = TransactingPower(account=stake.owner_address, blockchain=testerchain)
    worker.blockchain.transacting_power.activate()

    # Collect the staking reward in NU.
    result = software_stakeholder.collect_rewards(staker_address=stake.owner_address,
                                                  staking=True,  # collect only inflation reward.
                                                  policy=False,
                                                  password=INSECURE_DEVELOPMENT_PASSWORD)

    # TODO: Make Assertions reasonable for this layer.
    #       Consider recycling logic from test_collect_reward_integration CLI test.
    assert result
