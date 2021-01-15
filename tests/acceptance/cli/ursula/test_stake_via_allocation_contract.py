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
import random

import maya
import os
import pytest
import tempfile
from web3 import Web3

from nucypher.blockchain.eth.actors import Staker
from nucypher.blockchain.eth.agents import (ContractAgency, NucypherTokenAgent, PreallocationEscrowAgent,
                                            StakingEscrowAgent)
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.deployers import PreallocationEscrowDeployer
from nucypher.blockchain.eth.registry import InMemoryAllocationRegistry, IndividualAllocationRegistry
from nucypher.blockchain.eth.token import NU, Stake, StakeList
from nucypher.characters.lawful import Enrico, Ursula
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.utilities.logging import Logger
from tests.constants import (FAKE_PASSWORD_CONFIRMED, INSECURE_DEVELOPMENT_PASSWORD,
                             MOCK_INDIVIDUAL_ALLOCATION_FILEPATH, MOCK_IP_ADDRESS,
                             ONE_YEAR_IN_SECONDS,
                             TEST_PROVIDER_URI)
from tests.utils.middleware import MockRestMiddleware
from tests.utils.ursula import MOCK_KNOWN_URSULAS_CACHE, MOCK_URSULA_STARTING_PORT, select_test_port


#
# This test module is intended to mirror tests/cli/ursula/test_stakeholder_and_ursula.py,
# but using a staking contract (namely, PreallocationEscrow)
#


@pytest.fixture(scope='module')
def mock_allocation_registry(testerchain, agency_local_registry, token_economics):
    # Deploy the PreallocationEscrow contract
    allocation_registry = InMemoryAllocationRegistry()
    deployer = PreallocationEscrowDeployer(deployer_address=testerchain.etherbase_account,
                                           registry=agency_local_registry,
                                           allocation_registry=allocation_registry)

    deployer.deploy()
    deployer.assign_beneficiary(checksum_address=testerchain.unassigned_accounts[0])
    deployer.initial_deposit(value=2 * token_economics.minimum_allowed_locked,
                             duration_seconds=ONE_YEAR_IN_SECONDS)
    deployer.enroll_principal_contract()
    return allocation_registry


@pytest.fixture(scope='module')
def beneficiary(testerchain, mock_allocation_registry):
    # First, let's give the beneficiary some cash for TXs
    beneficiary = testerchain.unassigned_accounts[0]
    tx = {'to': beneficiary,
          'from': testerchain.etherbase_account,
          'value': Web3.toWei('1', 'ether')}

    txhash = testerchain.client.w3.eth.sendTransaction(tx)
    _receipt = testerchain.wait_for_receipt(txhash)

    # .. and create a mock individual allocation file
    contract_data = mock_allocation_registry.search(beneficiary_address=beneficiary)
    contract_address = contract_data[0]
    individual_allocation_file_data = {
        'beneficiary_address': beneficiary,
        'contract_address': contract_address
    }
    with open(MOCK_INDIVIDUAL_ALLOCATION_FILEPATH, 'w') as outfile:
        json.dump(individual_allocation_file_data, outfile)

    yield beneficiary

    if os.path.isfile(MOCK_INDIVIDUAL_ALLOCATION_FILEPATH):
        os.remove(MOCK_INDIVIDUAL_ALLOCATION_FILEPATH)


@pytest.fixture(scope='module')
def individual_allocation(beneficiary):
    return IndividualAllocationRegistry.from_allocation_file(MOCK_INDIVIDUAL_ALLOCATION_FILEPATH,
                                                             network=TEMPORARY_DOMAIN)


@pytest.fixture(scope='module')
def preallocation_escrow_agent(beneficiary,
                               agency_local_registry,
                               mock_allocation_registry,
                               test_registry_source_manager,
                               individual_allocation):
    preallocation_escrow_agent = PreallocationEscrowAgent(beneficiary=beneficiary,
                                                          registry=agency_local_registry,
                                                          allocation_registry=individual_allocation)
    return preallocation_escrow_agent


def test_stake_via_contract(click_runner,
                            custom_filepath,
                            agency_local_registry,
                            mock_allocation_registry,
                            testerchain,
                            stakeholder_configuration_file_location,
                            stake_value,
                            token_economics,
                            agency,
                            beneficiary,
                            preallocation_escrow_agent
                            ):

    #
    # Inital setup and checks: beneficiary and pre-allocation contract
    #

    # First, let's be sure the beneficiary is in the allocation registry...
    assert mock_allocation_registry.is_beneficiary_enrolled(beneficiary)

    # ... and that the pre-allocation contract has enough tokens
    preallocation_contract_address = preallocation_escrow_agent.principal_contract.address
    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=agency_local_registry)
    assert token_agent.get_balance(preallocation_contract_address) >= token_economics.minimum_allowed_locked

    # Let's not forget to create a stakeholder
    init_args = ('stake', 'init-stakeholder',
                 '--config-root', custom_filepath,
                 '--provider', TEST_PROVIDER_URI,
                 '--network', TEMPORARY_DOMAIN,
                 '--registry-filepath', agency_local_registry.filepath)

    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False)
    assert result.exit_code == 0

    with open(stakeholder_configuration_file_location) as f:
        print(f.read())

    #
    # The good stuff: Using `nucypher stake create --escrow`
    #

    # Staking contract has no stakes yet
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=agency_local_registry)
    stakes = list(staking_agent.get_all_stakes(staker_address=preallocation_contract_address))
    assert not stakes

    stake_args = ('stake', 'create',
                  '--config-file', stakeholder_configuration_file_location,
                  '--allocation-filepath', MOCK_INDIVIDUAL_ALLOCATION_FILEPATH,
                  '--value', str(stake_value.to_tokens()),
                  '--lock-periods', token_economics.minimum_locked_periods,
                  '--force')

    # TODO: This test is writing to the default system directory and ignoring updates to the passed filepath
    user_input = '0\n' + 'Y\n' + f'{INSECURE_DEVELOPMENT_PASSWORD}\n' + 'Y\n'
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # Test integration with BaseConfiguration
    with open(stakeholder_configuration_file_location, 'r') as config_file:
        _config_data = json.loads(config_file.read())

    # Verify the stake is on-chain
    # Test integration with Agency
    stakes = list(staking_agent.get_all_stakes(staker_address=preallocation_contract_address))
    assert len(stakes) == 1

    # Test integration with NU
    start_period, end_period, value = stakes[0]
    assert NU(int(value), 'NuNit') == stake_value
    assert (end_period - start_period) == token_economics.minimum_locked_periods - 1

    # Test integration with Stake
    stake = Stake.from_stake_info(index=0,
                                  checksum_address=preallocation_contract_address,
                                  stake_info=stakes[0],
                                  staking_agent=staking_agent,
                                  economics=token_economics)
    assert stake.value == stake_value
    assert stake.duration == token_economics.minimum_locked_periods


def test_stake_bond_worker(click_runner,
                           beneficiary,
                           mock_allocation_registry,
                           agency_local_registry,
                           manual_worker,
                           individual_allocation,
                           stakeholder_configuration_file_location):

    init_args = ('stake', 'bond-worker',
                 '--config-file', stakeholder_configuration_file_location,
                 '--allocation-filepath', MOCK_INDIVIDUAL_ALLOCATION_FILEPATH,
                 '--worker-address', manual_worker,
                 '--force')

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    staker = Staker(is_me=True,
                    checksum_address=beneficiary,
                    individual_allocation=individual_allocation,
                    registry=agency_local_registry)

    assert staker.worker_address == manual_worker


def test_stake_unbond_worker(click_runner,
                             testerchain,
                             token_economics,
                             beneficiary,
                             preallocation_escrow_agent,
                             mock_allocation_registry,
                             manual_worker,
                             agency_local_registry,
                             individual_allocation,
                             stakeholder_configuration_file_location):

    staker_address = preallocation_escrow_agent.principal_contract.address

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=agency_local_registry)
    assert manual_worker == staking_agent.get_worker_from_staker(staker_address=staker_address)

    testerchain.time_travel(periods=token_economics.minimum_worker_periods)

    init_args = ('stake', 'unbond-worker',
                 '--config-file', stakeholder_configuration_file_location,
                 '--allocation-filepath', MOCK_INDIVIDUAL_ALLOCATION_FILEPATH,
                 '--force')

    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    staker = Staker(is_me=True,
                    checksum_address=beneficiary,
                    individual_allocation=individual_allocation,
                    registry=agency_local_registry)

    assert staker.worker_address == NULL_ADDRESS

    # Ok ok, let's bond the worker again.

    init_args = ('stake', 'bond-worker',
                 '--config-file', stakeholder_configuration_file_location,
                 '--allocation-filepath', MOCK_INDIVIDUAL_ALLOCATION_FILEPATH,
                 '--worker-address', manual_worker,
                 '--force')

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    staker = Staker(is_me=True,
                    checksum_address=beneficiary,
                    individual_allocation=individual_allocation,
                    registry=agency_local_registry)

    assert staker.worker_address == manual_worker


def test_stake_restake(click_runner,
                       beneficiary,
                       preallocation_escrow_agent,
                       mock_allocation_registry,
                       agency_local_registry,
                       manual_worker,
                       testerchain,
                       individual_allocation,
                       stakeholder_configuration_file_location):

    staker = Staker(is_me=True,
                    checksum_address=beneficiary,
                    registry=agency_local_registry,
                    individual_allocation=individual_allocation)
    assert staker.is_restaking

    restake_args = ('stake', 'restake',
                    '--disable',
                    '--config-file', stakeholder_configuration_file_location,
                    '--allocation-filepath', MOCK_INDIVIDUAL_ALLOCATION_FILEPATH,
                    '--force')

    result = click_runner.invoke(nucypher_cli,
                                 restake_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert not staker.is_restaking
    assert "Successfully disabled" in result.output

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=agency_local_registry)
    current_period = staking_agent.get_current_period()
    release_period = current_period + 1
    lock_args = ('stake', 'restake',
                 '--lock-until', release_period,
                 '--config-file', stakeholder_configuration_file_location,
                 '--allocation-filepath', MOCK_INDIVIDUAL_ALLOCATION_FILEPATH,
                 '--force')

    result = click_runner.invoke(nucypher_cli,
                                 lock_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # Still not staking and the lock is enabled
    assert not staker.is_restaking
    assert staker.restaking_lock_enabled

    # CLI Output includes success message
    assert "Successfully enabled" in result.output
    assert str(release_period) in result.output

    # Wait until release period
    testerchain.time_travel(periods=1)
    assert not staker.restaking_lock_enabled
    assert not staker.is_restaking

    disable_args = ('stake', 'restake',
                    '--enable',
                    '--config-file', stakeholder_configuration_file_location,
                    '--allocation-filepath', MOCK_INDIVIDUAL_ALLOCATION_FILEPATH,
                    '--force')

    result = click_runner.invoke(nucypher_cli,
                                 disable_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    allocation_contract_address = preallocation_escrow_agent.principal_contract.address
    assert staking_agent.is_restaking(allocation_contract_address)

    staker = Staker(is_me=True,
                    checksum_address=beneficiary,
                    registry=agency_local_registry,
                    individual_allocation=individual_allocation)
    assert staker.is_restaking
    assert "Successfully enabled" in result.output


def test_stake_winddown(click_runner,
                        beneficiary,
                        preallocation_escrow_agent,
                        mock_allocation_registry,
                        agency_local_registry,
                        manual_worker,
                        testerchain,
                        individual_allocation,
                        stakeholder_configuration_file_location):

    staker = Staker(is_me=True,
                    checksum_address=beneficiary,
                    registry=agency_local_registry,
                    individual_allocation=individual_allocation)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=agency_local_registry)
    assert not staker.is_winding_down
    allocation_contract_address = preallocation_escrow_agent.principal_contract.address
    assert not staking_agent.is_winding_down(allocation_contract_address)

    winddown_args = ('stake', 'winddown',
                     '--enable',
                     '--config-file', stakeholder_configuration_file_location,
                     '--allocation-filepath', MOCK_INDIVIDUAL_ALLOCATION_FILEPATH,
                     '--force')

    result = click_runner.invoke(nucypher_cli,
                                 winddown_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert staker.is_winding_down
    assert staking_agent.is_winding_down(allocation_contract_address)
    assert "Successfully enabled" in result.output

    disable_args = ('stake', 'winddown',
                    '--disable',
                    '--config-file', stakeholder_configuration_file_location,
                    '--allocation-filepath', MOCK_INDIVIDUAL_ALLOCATION_FILEPATH,
                    '--force')

    result = click_runner.invoke(nucypher_cli,
                                 disable_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert not staker.is_winding_down
    assert not staking_agent.is_winding_down(allocation_contract_address)
    assert "Successfully disabled" in result.output


def test_ursula_init(click_runner,
                     custom_filepath,
                     agency_local_registry,
                     preallocation_escrow_agent,
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
    assert os.path.isdir(os.path.join(custom_filepath, 'keyring')), 'Keyring does not exist'
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


def test_collect_rewards_integration(click_runner,
                                     testerchain,
                                     agency_local_registry,
                                     stakeholder_configuration_file_location,
                                     blockchain_alice,
                                     blockchain_bob,
                                     random_policy_label,
                                     beneficiary,
                                     preallocation_escrow_agent,
                                     mock_allocation_registry,
                                     manual_worker,
                                     token_economics,
                                     mock_transacting_power_activation,
                                     stake_value,
                                     policy_value,
                                     policy_rate):
    # Disable re-staking
    restake_args = ('stake', 'restake',
                    '--disable',
                    '--config-file', stakeholder_configuration_file_location,
                    '--allocation-filepath', MOCK_INDIVIDUAL_ALLOCATION_FILEPATH,
                    '--force')

    result = click_runner.invoke(nucypher_cli,
                                 restake_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    half_stake_time = token_economics.minimum_locked_periods // 2  # Test setup
    logger = Logger("Test-CLI")  # Enter the Teacher's Logger, and
    current_period = 0  # State the initial period for incrementing

    staker_address = preallocation_escrow_agent.principal_contract.address
    worker_address = manual_worker

    # The staker is staking.
    stakes = StakeList(registry=agency_local_registry, checksum_address=staker_address)
    stakes.refresh()
    assert stakes

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=agency_local_registry)
    assert worker_address == staking_agent.get_worker_from_staker(staker_address=staker_address)

    ursula_port = select_test_port()
    ursula = Ursula(is_me=True,
                    checksum_address=staker_address,
                    worker_address=worker_address,
                    registry=agency_local_registry,
                    rest_host='127.0.0.1',
                    rest_port=ursula_port,
                    commit_now=False,
                    network_middleware=MockRestMiddleware(),
                    db_filepath=tempfile.mkdtemp(),
                    domain=TEMPORARY_DOMAIN)

    MOCK_KNOWN_URSULAS_CACHE[ursula_port] = ursula
    assert ursula.worker_address == worker_address
    assert ursula.checksum_address == staker_address

    mock_transacting_power_activation(account=worker_address, password=INSECURE_DEVELOPMENT_PASSWORD)

    # Make a commitment for half the first stake duration
    for _ in range(half_stake_time):
        logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")
        ursula.commit_to_next_period()
        testerchain.time_travel(periods=1)
        current_period += 1

    # Alice creates a policy and grants Bob access
    blockchain_alice.selection_buffer = 1

    M, N = 1, 1
    days = 3
    now = testerchain.w3.eth.getBlock('latest').timestamp
    expiration = maya.MayaDT(now).add(days=days-1)
    blockchain_policy = blockchain_alice.grant(bob=blockchain_bob,
                                               label=random_policy_label,
                                               m=M, n=N,
                                               value=policy_value,
                                               expiration=expiration,
                                               handpicked_ursulas={ursula})

    # Ensure that the handpicked Ursula was selected for the policy
    assert ursula.checksum_address in blockchain_policy.treasure_map.destinations

    # Bob learns about the new staker and joins the policy
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
        message_kit, signature = enrico.encrypt_message(plaintext=random_data)

        # Decrypt
        cleartexts = blockchain_bob.retrieve(message_kit,
                                             enrico=enrico,
                                             alice_verifying_key=verifying_key,
                                             label=random_policy_label)
        assert random_data == cleartexts[0]

        # Ursula Staying online and the clock advancing
        testerchain.time_travel(periods=1)
        current_period += 1

    # Finish the passage of time
    for _ in range(5 - 1):  # minus 1 because the first period was already committed to in test_ursula_run
        logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")
        ursula.commit_to_next_period()
        current_period += 1
        testerchain.time_travel(periods=1)

    #
    # WHERES THE MONEY URSULA?? - Collecting Rewards
    #

    balance = testerchain.client.get_balance(beneficiary)

    # Rewards will be unlocked after the
    # final committed period has passed (+1).
    logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")
    testerchain.time_travel(periods=1)
    current_period += 1
    logger.debug(f">>>>>>>>>>> TEST PERIOD {current_period} <<<<<<<<<<<<<<<<")

    # Since we are mocking the blockchain connection, manually consume the transacting power of the Beneficiary.
    mock_transacting_power_activation(account=beneficiary, password=INSECURE_DEVELOPMENT_PASSWORD)

    # Collect Policy Fee
    collection_args = ('stake', 'collect-reward',
                       '--config-file', stakeholder_configuration_file_location,
                       '--policy-fee',
                       '--no-staking-reward',
                       '--withdraw-address', beneficiary,
                       '--allocation-filepath', MOCK_INDIVIDUAL_ALLOCATION_FILEPATH,
                       '--force')

    result = click_runner.invoke(nucypher_cli,
                                 collection_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # Policy Fee
    collected_policy_fee = testerchain.client.get_balance(beneficiary)
    assert collected_policy_fee > balance

    #
    # Collect Staking Reward
    #
    token_agent = ContractAgency.get_agent(agent_class=NucypherTokenAgent, registry=agency_local_registry)
    balance_before_collecting = token_agent.get_balance(address=staker_address)

    collection_args = ('stake', 'collect-reward',
                       '--config-file', stakeholder_configuration_file_location,
                       '--no-policy-fee',
                       '--staking-reward',
                       '--allocation-filepath', MOCK_INDIVIDUAL_ALLOCATION_FILEPATH,
                       '--force')

    result = click_runner.invoke(nucypher_cli,
                                 collection_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # The beneficiary has withdrawn her staking rewards, which are now in the staking contract
    assert token_agent.get_balance(address=staker_address) >= balance_before_collecting


def test_withdraw_from_preallocation(click_runner,
                                     testerchain,
                                     agency_local_registry,
                                     stakeholder_configuration_file_location,
                                     beneficiary,
                                     preallocation_escrow_agent,
                                     ):

    staker_address = preallocation_escrow_agent.principal_contract.address
    token_agent = ContractAgency.get_agent(agent_class=NucypherTokenAgent, registry=agency_local_registry)
    tokens_in_contract = NU.from_nunits(token_agent.get_balance(address=staker_address))
    locked_preallocation = NU.from_nunits(preallocation_escrow_agent.unvested_tokens)

    collection_args = ('stake', 'preallocation', 'status',
                       '--config-file', stakeholder_configuration_file_location,
                       '--allocation-filepath', MOCK_INDIVIDUAL_ALLOCATION_FILEPATH,)

    result = click_runner.invoke(nucypher_cli,
                                 collection_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=True)
    assert result.exit_code == 0
    assert f'NU balance: .......... {tokens_in_contract}' in result.output

    balance_before_collecting = token_agent.get_balance(address=beneficiary)

    collection_args = ('stake', 'preallocation', 'withdraw',
                       '--config-file', stakeholder_configuration_file_location,
                       '--allocation-filepath', MOCK_INDIVIDUAL_ALLOCATION_FILEPATH,
                       '--force')

    result = click_runner.invoke(nucypher_cli,
                                 collection_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=True)
    assert result.exit_code == 0
    assert token_agent.get_balance(address=staker_address) == locked_preallocation
    withdrawn_amount = tokens_in_contract - locked_preallocation
    balance_after_collecting = token_agent.get_balance(address=beneficiary)
    assert balance_after_collecting == balance_before_collecting + withdrawn_amount
