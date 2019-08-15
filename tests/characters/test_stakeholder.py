import json

import pytest

from nucypher.blockchain.eth.actors import Worker
from nucypher.blockchain.eth.agents import StakingEscrowAgent, ContractAgency
from nucypher.config.characters import StakeHolderConfiguration
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD


def test_software_stakeholder_configuration(testerchain,
                                            test_registry,
                                            stakeholder_configuration,
                                            stakeholder_config_file_location):

    path = stakeholder_config_file_location

    # Save the stakeholder JSON config
    stakeholder_configuration.to_configuration_file(filepath=path)
    with open(path, 'r') as file:

        # Ensure file contents are serializable
        contents = file.read()
        first_config_contents = json.loads(contents)

    # Destroy this stake holder, leaving only the configuration file behind
    del stakeholder_configuration

    # Restore StakeHolder instance from JSON config
    stakeholder_config = StakeHolderConfiguration.from_configuration_file(filepath=path)
    the_same_stakeholder = stakeholder_config.produce()

    # Save the JSON config again
    stakeholder_config.to_configuration_file(filepath=path, override=True)
    with open(stakeholder_config.filepath, 'r') as file:
        contents = file.read()
        second_config_contents = json.loads(contents)

    # Ensure the stakeholder was accurately restored from JSON config
    assert first_config_contents == second_config_contents


def test_initialize_stake_with_existing_account(testerchain,
                                                software_stakeholder,
                                                stake_value,
                                                token_economics,
                                                test_registry):

    assert len(software_stakeholder.all_stakes) == 0

    # No Stakes
    with pytest.raises(IndexError):
        _stake = software_stakeholder.stakes[0]

    # Really... there are no stakes.
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    assert staking_agent.get_staker_population() == 0

    # Stake, deriving a new account with a password,
    # sending tokens and ethers from the funding account
    # to the staker's account, then initializing a new stake.
    stake = software_stakeholder.initialize_stake(amount=stake_value,
                                                  lock_periods=token_economics.minimum_locked_periods)

    # Wait for stake to begin
    testerchain.time_travel(periods=1)

    # Ensure the stakeholder is tracking the new staker and stake.
    assert len(software_stakeholder.all_stakes) == 1

    # Ensure common stake perspective between stakeholder and stake
    assert stake.value == stake_value
    assert stake.duration == token_economics.minimum_locked_periods

    stakes = list(staking_agent.get_all_stakes(staker_address=stake.staker_address))
    assert len(stakes) == 1


def test_divide_stake(software_stakeholder, token_economics, test_registry):
    stake = software_stakeholder.stakes[0]

    target_value = token_economics.minimum_allowed_locked
    pre_divide_stake_value = stake.value

    original_stake, new_stake = software_stakeholder.divide_stake(stake_index=0,
                                                                  additional_periods=10,
                                                                  target_value=target_value)

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    stakes = list(staking_agent.get_all_stakes(staker_address=stake.staker_address))
    assert len(stakes) == 2
    assert new_stake.value == target_value
    assert original_stake.value == (pre_divide_stake_value - target_value)


def test_set_worker(software_stakeholder, manual_worker, test_registry):
    software_stakeholder.set_worker(worker_address=manual_worker)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    assert staking_agent.get_worker_from_staker(staker_address=software_stakeholder.checksum_address) == manual_worker


def test_collect_inflation_rewards(software_stakeholder, manual_worker, testerchain, test_registry):

    # Get stake
    stake = software_stakeholder.stakes[1]

    # Make assigned Worker
    worker = Worker(is_me=True,
                    worker_address=manual_worker,
                    checksum_address=stake.staker_address,
                    start_working_loop=False,
                    registry=test_registry)

    # Mock TransactingPower consumption (Worker-Ursula)
    testerchain.transacting_power = TransactingPower(account=manual_worker)
    testerchain.transacting_power.activate()

    # Wait out stake lock_periods, manually confirming activity once per period.
    for period in range(stake.periods_remaining-1):
        worker.confirm_activity()
        testerchain.time_travel(periods=1)

    # Mock TransactingPower consumption (Staker-Ursula)
    testerchain.transacting_power = TransactingPower(account=stake.staker_address)
    testerchain.transacting_power.activate()

    # Collect the staking reward in NU.
    result = software_stakeholder.collect_staking_reward()

    # TODO: Make Assertions reasonable for this layer.
    #       Consider recycling logic from test_collect_reward_integration CLI test.
    assert result
