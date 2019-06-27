import json
import os

import pytest

from nucypher.blockchain.eth.actors import StakeHolder, Worker
from nucypher.blockchain.eth.agents import Agency, StakingEscrowAgent
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD


@pytest.fixture(scope='session')
def stakeholder_config_file_location():
    path = os.path.join('/', 'tmp', 'nucypher-test-stakeholder.json')
    return path


@pytest.fixture(scope='module')
def staking_software_stakeholder(testerchain,
                                 agency,
                                 blockchain_ursulas,
                                 stakeholder_config_file_location):

    # Setup
    path = stakeholder_config_file_location
    if os.path.exists(path):
        os.remove(path)

    # Create stakeholder from on-chain values given accounts over a web3 provider
    stakeholder = StakeHolder(blockchain=testerchain,
                              funding_account=testerchain.etherbase_account,
                              trezor=False)

    # Teardown
    yield stakeholder
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture(scope='module')
def manual_worker(testerchain):
    worker_private_key = '4115115f4159db59a06327aa29544c417c52ddb80a4a26517367ff4514e0f694'
    address = testerchain.provider.ethereum_tester.add_account(worker_private_key, password=INSECURE_DEVELOPMENT_PASSWORD)
    yield address


def test_software_stakeholder_configuration(testerchain,
                                            staking_software_stakeholder,
                                            stakeholder_config_file_location):

    stakeholder = staking_software_stakeholder
    path = stakeholder_config_file_location

    # Check attributes can be successfully read
    assert stakeholder.total_stake
    assert stakeholder.trezor is False
    assert stakeholder.stakes
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
    the_same_stakeholder = StakeHolder.from_configuration_file(filepath=path, blockchain=testerchain)

    # Save the JSON config again
    the_same_stakeholder.to_configuration_file(filepath=path, override=True)
    with open(the_same_stakeholder.filepath, 'r') as file:
        contents = file.read()
        second_config_contents = json.loads(contents)

    # Ensure the stakeholder was accurately restored from JSON config
    assert first_config_contents == second_config_contents


def test_initialize_stake_with_existing_staking_account(staking_software_stakeholder, stake_value, token_economics):

    stake = staking_software_stakeholder.stakes[0]

    # Stake, deriving a new account, using tokens and ethers from the funding account
    stake = staking_software_stakeholder.initialize_stake(checksum_address=stake.owner_address,
                                                          amount=stake_value,
                                                          duration=token_economics.minimum_locked_periods)

    assert stake.blockchain == staking_software_stakeholder.blockchain
    assert stake.value == stake_value
    assert stake.duration == token_economics.minimum_locked_periods
    assert stake.owner_address != staking_software_stakeholder.funding_account

    staking_software_stakeholder.blockchain.time_travel(periods=1)  # Wait for stake to begin
    staking_agent = Agency.get_agent(StakingEscrowAgent)
    stakes = list(staking_agent.get_all_stakes(staker_address=stake.owner_address))
    assert len(stakes) == 2


def test_initialize_stake_with_new_account(staking_software_stakeholder, stake_value, token_economics):

    # Stake, deriving a new account, using tokens and ethers from the funding account
    stake = staking_software_stakeholder.initialize_stake(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                          amount=stake_value,
                                                          duration=token_economics.minimum_locked_periods)

    assert stake.blockchain == staking_software_stakeholder.blockchain
    assert stake.value == stake_value
    assert stake.duration == token_economics.minimum_locked_periods
    assert stake.owner_address != staking_software_stakeholder.funding_account

    staking_agent = Agency.get_agent(StakingEscrowAgent)
    stakes = list(staking_agent.get_all_stakes(staker_address=stake.owner_address))
    assert len(stakes) == 1


def test_divide_stake(staking_software_stakeholder, token_economics):
    stake = staking_software_stakeholder.stakes[1]

    original_stake, new_stake = staking_software_stakeholder.divide_stake(address=stake.owner_address,
                                                                          password=INSECURE_DEVELOPMENT_PASSWORD,
                                                                          index=0,
                                                                          duration=10,
                                                                          value=token_economics.minimum_allowed_locked * 2)

    staking_agent = Agency.get_agent(StakingEscrowAgent)
    stakes = list(staking_agent.get_all_stakes(staker_address=stake.owner_address))
    assert len(stakes) == 2


def test_set_worker(staking_software_stakeholder, manual_worker):
    stake = staking_software_stakeholder.stakes[0]
    staker = staking_software_stakeholder.get_active_staker(stake.owner_address)
    staking_agent = Agency.get_agent(StakingEscrowAgent)

    staking_software_stakeholder.set_worker(staker_address=staker.checksum_address,
                                            worker_address=manual_worker)
    assert staking_agent.get_worker_from_staker(staker_address=staker.checksum_address) == manual_worker


def test_collect_inflation_rewards(staking_software_stakeholder, manual_worker):

    stake = staking_software_stakeholder.stakes[0]
    worker_config = staking_software_stakeholder.create_worker_configuration(staking_address=stake.owner_address,
                                                                             worker_address=manual_worker,
                                                                             password=INSECURE_DEVELOPMENT_PASSWORD)

    worker = worker_config.produce(password=INSECURE_DEVELOPMENT_PASSWORD)
    for period in range(stake.periods_remaining):
        worker.confirm_activity()
        staking_software_stakeholder.blockchain.time_travel(periods=1)

    result = staking_software_stakeholder.collect_rewards(staker_address=stake.owner_address,
                                                          password=INSECURE_DEVELOPMENT_PASSWORD)
    assert False
