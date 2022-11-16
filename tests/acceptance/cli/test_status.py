


import csv
import re

import pytest

from nucypher.blockchain.eth.agents import (
    AdjudicatorAgent,
    ContractAgency,
    NucypherTokenAgent,
)
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.cli.commands.status import status
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import TransactingPower


@pytest.mark.skip()
def test_nucypher_status_network(click_runner, testerchain, agency_local_registry):

    network_command = ('network',
                       '--registry-filepath', str(agency_local_registry.filepath.absolute()),
                       '--eth-provider', TEST_ETH_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN)

    result = click_runner.invoke(status, network_command, catch_exceptions=False)
    assert result.exit_code == 0

    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=agency_local_registry)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=agency_local_registry)
    adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=agency_local_registry)

    agents = (token_agent, staking_agent, adjudicator_agent)
    for agent in agents:
        contract_regex = f"^{agent.contract_name} \\.+ {agent.contract_address}"
        assert re.search(contract_regex, result.output, re.MULTILINE)

    assert re.search(f"^Provider URI \\.+ {TEST_ETH_PROVIDER_URI}", result.output, re.MULTILINE)
    assert re.search(f"^Current Period \\.+ {staking_agent.get_current_period()}", result.output, re.MULTILINE)


@pytest.mark.skip()
def test_nucypher_status_events(click_runner, testerchain, agency_local_registry, staking_providers, temp_dir_path):
    # All workers make a commitment
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=agency_local_registry)
    starting_block_number = testerchain.get_block_number()
    for ursula in testerchain.ursulas_accounts:
        tpower = TransactingPower(signer=Web3Signer(client=testerchain.client), account=ursula)
        staking_agent.commit_to_next_period(transacting_power=tpower, fire_and_forget=False)
    committed_period = staking_agent.get_current_period() + 1

    testerchain.time_travel(periods=1)

    # Check CommitmentMade events

    #
    # CLI output
    #
    status_command = ('events',
                      '--eth-provider', TEST_ETH_PROVIDER_URI,
                      '--network', TEMPORARY_DOMAIN,
                      '--event-name', 'CommitmentMade',
                      '--contract-name', 'StakingEscrow',
                      '--from-block', starting_block_number)
    result = click_runner.invoke(status, status_command, catch_exceptions=False)
    for staker in staking_providers:
        assert re.search(f'staker: {staker.checksum_address}, period: {committed_period}', result.output, re.MULTILINE)

    # event filter output
    first_staker = staking_providers[0]
    filter_status_command = ('events',
                             '--eth-provider', TEST_ETH_PROVIDER_URI,
                             '--network', TEMPORARY_DOMAIN,
                             '--event-name', 'CommitmentMade',
                             '--contract-name', 'StakingEscrow',
                             '--from-block', starting_block_number,
                             '--event-filter', f'staker={first_staker.checksum_address}')
    result = click_runner.invoke(status, filter_status_command, catch_exceptions=False)
    assert re.search(f'staker: {first_staker.checksum_address}, period: {committed_period}', result.output, re.MULTILINE)
    for staker in staking_providers:
        if staker != first_staker:
            assert not re.search(f'staker: {staker.checksum_address}', result.output, re.MULTILINE), result.output

    #
    # CSV output
    #
    csv_file = temp_dir_path / 'status_events_output.csv'
    csv_status_command = ('events',
                          '--eth-provider', TEST_ETH_PROVIDER_URI,
                          '--network', TEMPORARY_DOMAIN,
                          '--event-name', 'CommitmentMade',
                          '--contract-name', 'StakingEscrow',
                          '--from-block', starting_block_number,
                          '--event-filter', f'staker={first_staker.checksum_address}',
                          '--csv-file', str(csv_file.absolute()))
    result = click_runner.invoke(status, csv_status_command, catch_exceptions=False)
    assert re.search(f'StakingEscrow::CommitmentMade events written to {csv_file}', result.output, re.MULTILINE), result.output
    assert csv_file.exists(), 'events output to csv file'
    with open(csv_file, mode='r') as f:
        csv_reader = csv.reader(f, delimiter=',')
        line_count = 0
        for row in csv_reader:
            if line_count == 0:
                assert ",".join(row) == 'event_name,block_number,unix_timestamp,date,staker,period,value'  # specific to CommitmentMade
            else:
                row_data = f'{row}'
                assert row[0] == 'CommitmentMade', row_data
                # skip block_number, unix_timestamp, date
                assert row[4] == first_staker.checksum_address, row_data
                assert row[5] == f'{committed_period}', row_data
                # skip value
            line_count += 1
        assert line_count == 2, 'column names and single event row in csv file'
