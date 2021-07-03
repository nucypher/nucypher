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


import json
import os
import random
import tempfile
from unittest import mock

import maya
from web3 import Web3

from nucypher.blockchain.eth.actors import Staker
from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.blockchain.eth.token import NU, Stake
from nucypher.blockchain.eth.utils import prettify_eth_amount
from nucypher.characters.lawful import Enrico, Ursula
from nucypher.cli.literature import SUCCESSFUL_MINTING
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import StakeHolderConfiguration, UrsulaConfiguration
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.utilities.logging import Logger
from nucypher.utilities.networking import LOOPBACK_ADDRESS
from tests.constants import (
    FAKE_PASSWORD_CONFIRMED,
    FEE_RATE_RANGE,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_IP_ADDRESS,
    TEST_PROVIDER_URI,
    YES_ENTER
)
from tests.utils.middleware import MockRestMiddleware
from tests.utils.ursula import MOCK_KNOWN_URSULAS_CACHE, select_test_port


@mock.patch('nucypher.config.characters.StakeHolderConfiguration.default_filepath', return_value='/non/existent/file')
def test_missing_configuration_file(default_filepath_mock, click_runner):
    cmd_args = ('stake', 'list')
    result = click_runner.invoke(nucypher_cli, cmd_args, catch_exceptions=False)
    assert result.exit_code != 0
    assert default_filepath_mock.called
    assert "nucypher stake init-stakeholder" in result.output


def test_new_stakeholder(click_runner,
                         custom_filepath,
                         agency_local_registry,
                         testerchain):

    init_args = ('stake', 'init-stakeholder',
                 '--config-root', custom_filepath,
                 '--provider', TEST_PROVIDER_URI,
                 '--network', TEMPORARY_DOMAIN,
                 '--registry-filepath', agency_local_registry.filepath)

    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False)
    assert result.exit_code == 0

    # Files and Directories
    assert os.path.isdir(custom_filepath), 'Configuration file does not exist'

    custom_config_filepath = os.path.join(custom_filepath, StakeHolderConfiguration.generate_filename())
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    with open(custom_config_filepath, 'r') as config_file:
        raw_config_data = config_file.read()
        config_data = json.loads(raw_config_data)
        assert config_data['provider_uri'] == TEST_PROVIDER_URI


def test_stake_init(click_runner,
                    stakeholder_configuration_file_location,
                    stake_value,
                    token_economics,
                    testerchain,
                    agency_local_registry,
                    manual_staker):

    # Staker address has not stakes
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=agency_local_registry)
    stakes = list(staking_agent.get_all_stakes(staker_address=manual_staker))
    assert not stakes

    stake_args = ('stake', 'create',
                  '--config-file', stakeholder_configuration_file_location,
                  '--staking-address', manual_staker,
                  '--value', stake_value.to_tokens(),
                  '--lock-periods', token_economics.minimum_locked_periods,
                  '--force')

    # TODO: This test is writing to the default system directory and ignoring updates to the passed filepath
    user_input = f'0\n' + f'{INSECURE_DEVELOPMENT_PASSWORD}\n' + YES_ENTER
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # Test integration with BaseConfiguration
    with open(stakeholder_configuration_file_location, 'r') as config_file:
        _config_data = json.loads(config_file.read())

    # Verify the stake is on-chain
    # Test integration with Agency
    stakes = list(staking_agent.get_all_stakes(staker_address=manual_staker))
    assert len(stakes) == 1

    # Test integration with NU
    start_period, end_period, value = stakes[0]
    assert NU(int(value), 'NuNit') == stake_value
    assert (end_period - start_period) == token_economics.minimum_locked_periods - 1

    # Test integration with Stake
    stake = Stake.from_stake_info(index=0,
                                  checksum_address=manual_staker,
                                  stake_info=stakes[0],
                                  staking_agent=staking_agent,
                                  economics=token_economics)
    assert stake.value == stake_value
    assert stake.duration == token_economics.minimum_locked_periods


def test_stake_list(click_runner,
                    stakeholder_configuration_file_location,
                    stake_value,
                    agency_local_registry,
                    testerchain):

    stake_args = ('stake', 'list',
                  '--config-file', stakeholder_configuration_file_location)

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert str(stake_value) in result.output
    _minimum, default, _maximum = FEE_RATE_RANGE
    assert f"{default} wei" in result.output


def test_staker_divide_stakes(click_runner,
                              stakeholder_configuration_file_location,
                              token_economics,
                              manual_staker,
                              testerchain,
                              agency_local_registry):

    divide_args = ('stake', 'divide',
                   '--config-file', stakeholder_configuration_file_location,
                   '--force',
                   '--staking-address', manual_staker,
                   '--index', 0,
                   '--value', NU(token_economics.minimum_allowed_locked, 'NuNit').to_tokens(),
                   '--lock-periods', 10)

    result = click_runner.invoke(nucypher_cli,
                                 divide_args,
                                 catch_exceptions=False,
                                 env=dict(NUCYPHER_KEYSTORE_PASSWORD=INSECURE_DEVELOPMENT_PASSWORD))
    assert result.exit_code == 0

    stake_args = ('stake', 'list', '--config-file', stakeholder_configuration_file_location)

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert str(NU(token_economics.minimum_allowed_locked, 'NuNit').to_tokens()) in result.output


def test_stake_prolong(click_runner,
                       testerchain,
                       agency_local_registry,
                       manual_staker,
                       manual_worker,
                       stakeholder_configuration_file_location):

    prolong_args = ('stake', 'prolong',
                    '--config-file', stakeholder_configuration_file_location,
                    '--index', 0,
                    '--lock-periods', 1,
                    '--staking-address', manual_staker,
                    '--force')

    staker = Staker(domain=TEMPORARY_DOMAIN,
                    checksum_address=manual_staker,
                    registry=agency_local_registry)
    staker.refresh_stakes()
    stake = staker.stakes[0]
    old_termination = stake.final_locked_period

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(nucypher_cli,
                                 prolong_args,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # Ensure Integration with Stakes
    stake.sync()
    new_termination = stake.final_locked_period
    assert new_termination == old_termination + 1


def test_stake_increase(click_runner,
                        stakeholder_configuration_file_location,
                        token_economics,
                        testerchain,
                        agency_local_registry,
                        manual_staker):
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=agency_local_registry)
    stakes = list(staking_agent.get_all_stakes(staker_address=manual_staker))
    stakes_length = len(stakes)
    assert stakes_length > 0

    selection = 0
    new_value = NU.from_nunits(token_economics.minimum_allowed_locked // 10)
    origin_stake = stakes[selection]

    stake_args = ('stake', 'increase',
                  '--config-file', stakeholder_configuration_file_location,
                  '--staking-address', manual_staker,
                  '--value', new_value.to_tokens(),
                  '--index', selection,
                  '--force')

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n'
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # Verify the stake is on-chain
    # Test integration with Agency
    stakes = list(staking_agent.get_all_stakes(staker_address=manual_staker))
    assert len(stakes) == stakes_length

    # Test integration with NU
    _start_period, end_period, value = stakes[selection]
    assert NU(int(value), 'NuNit') == origin_stake.locked_value + new_value
    assert end_period == origin_stake.last_period


def test_merge_stakes(click_runner,
                      stakeholder_configuration_file_location,
                      token_economics,
                      testerchain,
                      agency_local_registry,
                      manual_staker,
                      stake_value):
    # Prepare new stake
    stake_args = ('stake', 'create',
                  '--config-file', stakeholder_configuration_file_location,
                  '--staking-address', manual_staker,
                  '--value', stake_value.to_tokens(),
                  '--lock-periods', token_economics.minimum_locked_periods + 1,
                  '--force')
    user_input = f'0\n' + f'{INSECURE_DEVELOPMENT_PASSWORD}\n' + YES_ENTER
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=agency_local_registry)
    stakes = list(staking_agent.get_all_stakes(staker_address=manual_staker))
    stakes_length = len(stakes)
    assert stakes_length > 0

    selection_1 = 0
    selection_2 = 2
    origin_stake_1 = stakes[selection_1]
    origin_stake_2 = stakes[selection_2]
    assert origin_stake_1.last_period == origin_stake_2.last_period

    stake_args = ('stake', 'merge',
                  '--config-file', stakeholder_configuration_file_location,
                  '--staking-address', manual_staker,
                  '--index-1', selection_1,
                  '--index-2', selection_2,
                  '--force')

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n'
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # Verify the tx is on-chain
    stakes = list(staking_agent.get_all_stakes(staker_address=manual_staker))
    assert len(stakes) == stakes_length
    assert stakes[selection_1].locked_value == origin_stake_1.locked_value + origin_stake_2.locked_value
    assert stakes[selection_2].last_period == 1


def test_remove_inactive(click_runner,
                       stakeholder_configuration_file_location,
                       token_economics,
                       testerchain,
                       agency_local_registry,
                       manual_staker,
                       stake_value):

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=agency_local_registry)
    original_stakes = list(staking_agent.get_all_stakes(staker_address=manual_staker))

    selection = 2
    assert original_stakes[selection].last_period == 1

    stake_args = ('stake', 'remove-inactive',
                  '--config-file', stakeholder_configuration_file_location,
                  '--staking-address', manual_staker,
                  '--index', selection,
                  '--force')
    user_input = f'0\n' + f'{INSECURE_DEVELOPMENT_PASSWORD}\n' + YES_ENTER
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    stakes = list(staking_agent.get_all_stakes(staker_address=manual_staker))
    assert len(stakes) == len(original_stakes) - 1


def test_stake_bond_worker(click_runner,
                           testerchain,
                           agency_local_registry,
                           manual_staker,
                           manual_worker,
                           stakeholder_configuration_file_location):

    init_args = ('stake', 'bond-worker',
                 '--config-file', stakeholder_configuration_file_location,
                 '--staking-address', manual_staker,
                 '--worker-address', manual_worker,
                 '--force')

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    staker = Staker(domain=TEMPORARY_DOMAIN,
                    checksum_address=manual_staker,
                    registry=agency_local_registry)
    assert staker.worker_address == manual_worker


def test_ursula_init(click_runner,
                     custom_filepath,
                     agency_local_registry,
                     manual_staker,
                     manual_worker,
                     testerchain):

    deploy_port = select_test_port()

    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--worker-address', manual_worker,
                 '--config-root', custom_filepath,
                 '--provider', TEST_PROVIDER_URI,
                 '--registry-filepath', agency_local_registry.filepath,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--rest-port', deploy_port)

    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=FAKE_PASSWORD_CONFIRMED,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # Files and Directories
    assert os.path.isdir(custom_filepath), 'Configuration file does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'keystore')), 'KEYSTORE does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'known_nodes')), 'known_nodes directory does not exist'

    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.generate_filename())
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    with open(custom_config_filepath, 'r') as config_file:
        raw_config_data = config_file.read()
        config_data = json.loads(raw_config_data)
        assert config_data['provider_uri'] == TEST_PROVIDER_URI
        assert config_data['worker_address'] == manual_worker
        assert TEMPORARY_DOMAIN == config_data['domain']


def test_ursula_run(click_runner,
                    manual_worker,
                    manual_staker,
                    custom_filepath,
                    testerchain):

    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.generate_filename())

    # Now start running your Ursula!
    init_args = ('ursula', 'run',
                 '--dry-run',
                 '--config-file', custom_config_filepath)

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n' * 2
    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0


def test_stake_restake(click_runner,
                       manual_staker,
                       custom_filepath,
                       testerchain,
                       agency_local_registry,
                       stakeholder_configuration_file_location):

    staker = Staker(domain=TEMPORARY_DOMAIN,
                    checksum_address=manual_staker,
                    registry=agency_local_registry)
    assert staker.is_restaking

    restake_args = ('stake', 'restake',
                    '--disable',
                    '--config-file', stakeholder_configuration_file_location,
                    '--staking-address', manual_staker,
                    '--force')

    result = click_runner.invoke(nucypher_cli,
                                 restake_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert not staker.is_restaking
    assert "Successfully disabled" in result.output

    disable_args = ('stake', 'restake',
                    '--enable',
                    '--config-file', stakeholder_configuration_file_location,
                    '--staking-address', manual_staker,
                    '--force')

    result = click_runner.invoke(nucypher_cli,
                                 disable_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert staker.is_restaking
    assert "Successfully enabled" in result.output

    # Disable again
    disable_args = ('stake', 'restake',
                    '--disable',
                    '--config-file', stakeholder_configuration_file_location,
                    '--staking-address', manual_staker,
                    '--force')

    result = click_runner.invoke(nucypher_cli,
                                 disable_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0


def test_stake_winddown(click_runner,
                        manual_staker,
                        custom_filepath,
                        testerchain,
                        agency_local_registry,
                        stakeholder_configuration_file_location):

    staker = Staker(domain=TEMPORARY_DOMAIN,
                    checksum_address=manual_staker,
                    registry=agency_local_registry)
    assert not staker.is_winding_down

    restake_args = ('stake', 'winddown',
                    '--enable',
                    '--config-file', stakeholder_configuration_file_location,
                    '--staking-address', manual_staker,
                    '--force')

    result = click_runner.invoke(nucypher_cli,
                                 restake_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert staker.is_winding_down
    assert "Successfully enabled" in result.output

    disable_args = ('stake', 'winddown',
                    '--disable',
                    '--config-file', stakeholder_configuration_file_location,
                    '--staking-address', manual_staker,
                    '--force')

    result = click_runner.invoke(nucypher_cli,
                                 disable_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert not staker.is_winding_down
    assert "Successfully disabled" in result.output


def test_stake_snapshots(click_runner,
                         manual_staker,
                         custom_filepath,
                         testerchain,
                         agency_local_registry,
                         stakeholder_configuration_file_location):

    staker = Staker(domain=TEMPORARY_DOMAIN,
                    checksum_address=manual_staker,
                    registry=agency_local_registry)
    assert staker.is_taking_snapshots

    restake_args = ('stake', 'snapshots',
                    '--disable',
                    '--config-file', stakeholder_configuration_file_location,
                    '--staking-address', manual_staker,
                    '--force')

    result = click_runner.invoke(nucypher_cli,
                                 restake_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert not staker.is_taking_snapshots
    assert "Successfully disabled" in result.output

    disable_args = ('stake', 'snapshots',
                    '--enable',
                    '--config-file', stakeholder_configuration_file_location,
                    '--staking-address', manual_staker,
                    '--force')

    result = click_runner.invoke(nucypher_cli,
                                 disable_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert staker.is_taking_snapshots
    assert "Successfully enabled" in result.output


def test_collect_rewards_integration(click_runner,
                                     testerchain,
                                     agency_local_registry,
                                     stakeholder_configuration_file_location,
                                     blockchain_alice,
                                     blockchain_bob,
                                     random_policy_label,
                                     manual_staker,
                                     manual_worker,
                                     token_economics,
                                     policy_value):

    half_stake_time = 2 * token_economics.minimum_locked_periods  # Test setup
    logger = Logger("Test-CLI")  # Enter the Teacher's Logger, and
    current_period = 0  # State the initial period for incrementing

    staker_address = manual_staker
    worker_address = manual_worker

    staker = Staker(domain=TEMPORARY_DOMAIN,
                    checksum_address=staker_address,
                    registry=agency_local_registry)
    staker.refresh_stakes()

    # The staker is staking.
    assert staker.is_staking
    assert staker.stakes
    assert staker.worker_address == worker_address

    ursula_port = select_test_port()
    ursula = Ursula(is_me=True,
                    checksum_address=staker_address,
                    signer=Web3Signer(testerchain.client),
                    worker_address=worker_address,
                    registry=agency_local_registry,
                    rest_host=LOOPBACK_ADDRESS,
                    rest_port=ursula_port,
                    provider_uri=TEST_PROVIDER_URI,
                    network_middleware=MockRestMiddleware(),
                    db_filepath=tempfile.mkdtemp(),
                    domain=TEMPORARY_DOMAIN)

    MOCK_KNOWN_URSULAS_CACHE[ursula_port] = ursula
    assert ursula.worker_address == worker_address
    assert ursula.checksum_address == staker_address

    # Make a commitment for half the first stake duration
    testerchain.time_travel(periods=1)
    for _ in range(half_stake_time):
        logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")
        ursula.commit_to_next_period()
        testerchain.time_travel(periods=1)
        current_period += 1

    # Alice creates a policy and grants Bob access
    blockchain_alice.selection_buffer = 1

    M, N = 1, 1
    duration_in_periods = 3
    days = (duration_in_periods - 1) * (token_economics.hours_per_period // 24)
    now = testerchain.w3.eth.getBlock('latest').timestamp
    expiration = maya.MayaDT(now).add(days=days)
    blockchain_policy = blockchain_alice.grant(bob=blockchain_bob,
                                               label=random_policy_label,
                                               m=M, n=N,
                                               value=policy_value,
                                               expiration=expiration,
                                               handpicked_ursulas={ursula})

    # Ensure that the handpicked Ursula was selected for the policy
    assert ursula.checksum_address in blockchain_policy.treasure_map.destinations

    # Bob learns about the new staker and joins the policy
    blockchain_bob.start_learning_loop()
    blockchain_bob.remember_node(node=ursula)
    blockchain_bob.join_policy(random_policy_label, bytes(blockchain_alice.stamp))

    # Enrico Encrypts (of course)
    enrico = Enrico(policy_encrypting_key=blockchain_policy.public_key,
                    network_middleware=MockRestMiddleware())

    verifying_key = blockchain_alice.stamp.as_umbral_pubkey()

    for index in range(half_stake_time - 5):
        logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")
        ursula.commit_to_next_period()

        # Encrypt
        random_data = os.urandom(random.randrange(20, 100))
        ciphertext, signature = enrico.encrypt_message(plaintext=random_data)

        # Decrypt
        cleartexts = blockchain_bob.retrieve(ciphertext,
                                             enrico=enrico,
                                             alice_verifying_key=verifying_key,
                                             label=random_policy_label)
        assert random_data == cleartexts[0]

        # Ursula Staying online and the clock advancing
        testerchain.time_travel(periods=1)
        current_period += 1

    # Finish the passage of time for the first Stake
    for _ in range(5):  # plus the extended periods from stake division
        logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")
        ursula.commit_to_next_period()
        testerchain.time_travel(periods=1)
        current_period += 1

    #
    # WHERES THE MONEY URSULA?? - Collecting Rewards
    #

    # The address the client wants Ursula to send rewards to
    burner_wallet = testerchain.w3.eth.account.create(INSECURE_DEVELOPMENT_PASSWORD)

    # The rewards wallet is initially empty, because it is freshly created
    assert testerchain.client.get_balance(burner_wallet.address) == 0

    # Rewards will be unlocked after the
    # final committed period has passed (+1).
    logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")
    testerchain.time_travel(periods=1)
    current_period += 1
    logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")

    # At least half of the tokens are unlocked (restaking was enabled for some prior periods)
    assert staker.locked_tokens() >= token_economics.minimum_allowed_locked

    # Collect Policy Fee
    collection_args = ('stake', 'rewards', 'withdraw',
                       '--config-file', stakeholder_configuration_file_location,
                       '--fees',
                       '--no-tokens',
                       '--staking-address', staker_address,
                       '--withdraw-address', burner_wallet.address)
    result = click_runner.invoke(nucypher_cli,
                                 collection_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # Policy Fee
    collected_policy_fee = testerchain.client.get_balance(burner_wallet.address)
    expected_collection = policy_value
    assert collected_policy_fee == expected_collection

    # Finish the passage of time... once and for all
    # Extended periods from stake division
    for _ in range(9):
        ursula.commit_to_next_period()
        current_period += 1
        logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")
        testerchain.time_travel(periods=1)

    #
    # Collect Staking Reward
    #

    balance_before_collecting = staker.token_agent.get_balance(address=staker_address)

    collection_args = ('stake', 'rewards', 'withdraw',
                       '--config-file', stakeholder_configuration_file_location,
                       '--no-fees',
                       '--tokens',
                       '--staking-address', staker_address,
                       '--force')

    result = click_runner.invoke(nucypher_cli,
                                 collection_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # The staker has withdrawn her staking rewards
    assert staker.token_agent.get_balance(address=staker_address) > balance_before_collecting


def test_stake_unbond_worker(click_runner,
                             testerchain,
                             manual_staker,
                             manual_worker,
                             agency_local_registry,
                             stakeholder_configuration_file_location):
    testerchain.time_travel(periods=1)

    staker = Staker(domain=TEMPORARY_DOMAIN,
                    checksum_address=manual_staker,
                    registry=agency_local_registry)

    assert staker.worker_address == manual_worker

    init_args = ('stake', 'unbond-worker',
                 '--config-file', stakeholder_configuration_file_location,
                 '--staking-address', manual_staker,
                 '--force'
                 )

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}'
    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    staker = Staker(domain=TEMPORARY_DOMAIN,
                    checksum_address=manual_staker,
                    registry=agency_local_registry)

    assert staker.worker_address == NULL_ADDRESS


def test_set_min_rate(click_runner,
                      manual_staker,
                      testerchain,
                      agency_local_registry,
                      stakeholder_configuration_file_location):

    _minimum, _default, maximum = FEE_RATE_RANGE
    min_rate = maximum - 1
    staker = Staker(domain=TEMPORARY_DOMAIN,
                    checksum_address=manual_staker,
                    registry=agency_local_registry)
    assert staker.raw_min_fee_rate == 0

    min_rate_in_gwei = Web3.fromWei(min_rate, 'gwei')

    restake_args = ('stake', 'set-min-rate',
                    '--min-rate', min_rate_in_gwei,
                    '--config-file', stakeholder_configuration_file_location,
                    '--staking-address', manual_staker,
                    '--force')

    result = click_runner.invoke(nucypher_cli,
                                 restake_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert staker.raw_min_fee_rate == min_rate
    assert "successfully set" in result.output

    stake_args = ('stake', 'list',
                  '--config-file', stakeholder_configuration_file_location)

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert f"{prettify_eth_amount(min_rate)}" in result.output


def test_mint(click_runner,
              manual_staker,
              testerchain,
              agency_local_registry,
              stakeholder_configuration_file_location):

    testerchain.time_travel(periods=2)
    staker = Staker(domain=TEMPORARY_DOMAIN,
                    checksum_address=manual_staker,
                    registry=agency_local_registry)
    assert staker.mintable_periods() > 0
    owned_tokens = staker.owned_tokens()

    mint_args = ('stake', 'mint',
                 '--config-file', stakeholder_configuration_file_location,
                 '--staking-address', manual_staker,
                 '--force')

    result = click_runner.invoke(nucypher_cli,
                                 mint_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert staker.owned_tokens() > owned_tokens
    assert staker.mintable_periods() == 0
    assert SUCCESSFUL_MINTING in result.output
