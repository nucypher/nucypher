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

import csv
import webbrowser
from collections import Counter
from datetime import timedelta
from typing import List

import click
import maya
import tabulate
import time
from constant_sorrow.constants import NO_KNOWN_NODES
from web3 import Web3

from nucypher.blockchain.eth.agents import (
    ContractAgency,
    NucypherTokenAgent,
    AdjudicatorAgent,
    PolicyManagerAgent,
    StakingEscrowAgent,
    PreallocationEscrowAgent,
    WorkLockAgent)
from nucypher.blockchain.eth.constants import NUCYPHER_TOKEN_CONTRACT_NAME, STAKING_ESCROW_CONTRACT_NAME
from nucypher.blockchain.eth.deployers import DispatcherDeployer, StakingInterfaceRouterDeployer, PolicyManagerDeployer
from nucypher.blockchain.eth.interfaces import BlockchainInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.blockchain.eth.sol import SOLIDITY_COMPILER_VERSION
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.utils import datetime_at_period, etherscan_url, prettify_eth_amount
from nucypher.characters.banners import NUCYPHER_BANNER, NU_BANNER
from nucypher.config.constants import SEEDNODES
from nucypher.network.nicknames import nickname_from_seed


def echo_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.secho(NUCYPHER_BANNER, bold=True)
    ctx.exit()


def paint_new_installation_help(emitter, new_configuration):
    character_config_class = new_configuration.__class__
    character_name = character_config_class._NAME.lower()

    emitter.message("Generated keyring {}".format(new_configuration.keyring_root), color='green')
    emitter.message("Saved configuration file {}".format(new_configuration.config_file_location), color='green')

    # Felix
    if character_name == 'felix':
        suggested_db_command = 'nucypher felix createdb'
        how_to_proceed_message = f'\nTo initialize a new faucet database run:'
        emitter.echo(how_to_proceed_message, color='green')
        emitter.echo(f'\n\'{suggested_db_command}\'', color='green')

    # Ursula
    elif character_name == 'ursula' and not new_configuration.federated_only:
        how_to_stake_message = f"\nIf you haven't done it already, initialize a NU stake with 'nucypher stake' or"
        emitter.echo(how_to_stake_message, color='green')

    # Everyone: Give the use a suggestion as to what to do next
    vowels = ('a', 'e', 'i', 'o', 'u')
    character_name_starts_with_vowel = character_name[0].lower() in vowels
    adjective = 'an' if character_name_starts_with_vowel else 'a'
    suggested_command = f'nucypher {character_name} run'
    how_to_run_message = f"\nTo run {adjective} {character_name.capitalize()} node from the default configuration filepath run: \n\n'{suggested_command}'\n"

    emitter.echo(how_to_run_message.format(suggested_command), color='green')


def build_fleet_state_status(ursula) -> str:
    # Build FleetState status line
    if ursula.known_nodes.checksum is not NO_KNOWN_NODES:
        fleet_state_checksum = ursula.known_nodes.checksum[:7]
        fleet_state_nickname = ursula.known_nodes.nickname
        fleet_state_icon = ursula.known_nodes.icon
        fleet_state = '{checksum} ⇀{nickname}↽ {icon}'.format(icon=fleet_state_icon,
                                                              nickname=fleet_state_nickname,
                                                              checksum=fleet_state_checksum)
    elif ursula.known_nodes.checksum is NO_KNOWN_NODES:
        fleet_state = 'No Known Nodes'
    else:
        fleet_state = 'Unknown'

    return fleet_state


def paint_node_status(emitter, ursula, start_time):
    ursula.mature()  # Just to be sure

    # Build Learning status line
    learning_status = "Unknown"
    if ursula._learning_task.running:
        learning_status = "Learning at {}s Intervals".format(ursula._learning_task.interval)
    elif not ursula._learning_task.running:
        learning_status = "Not Learning"

    teacher = 'Current Teacher ..... No Teacher Connection'
    if ursula._current_teacher_node:
        teacher = 'Current Teacher ..... {}'.format(ursula._current_teacher_node)

    # Build FleetState status line
    fleet_state = build_fleet_state_status(ursula=ursula)

    stats = ['⇀URSULA {}↽'.format(ursula.nickname_icon),
             '{}'.format(ursula),
             'Uptime .............. {}'.format(maya.now() - start_time),
             'Start Time .......... {}'.format(start_time.slang_time()),
             'Fleet State.......... {}'.format(fleet_state),
             'Learning Status ..... {}'.format(learning_status),
             'Learning Round ...... Round #{}'.format(ursula._learning_round),
             'Operating Mode ...... {}'.format('Federated' if ursula.federated_only else 'Decentralized'),
             'Rest Interface ...... {}'.format(ursula.rest_url()),
             'Node Storage Type ... {}'.format(ursula.node_storage._name.capitalize()),
             'Known Nodes ......... {}'.format(len(ursula.known_nodes)),
             'Work Orders ......... {}'.format(len(ursula.work_orders())),
             teacher]

    if not ursula.federated_only:
        worker_address = 'Worker Address ...... {}'.format(ursula.worker_address)
        current_period = f'Current Period ...... {ursula.staking_agent.get_current_period()}'
        stats.extend([current_period, worker_address])

    if ursula._availability_tracker:
        if ursula._availability_tracker.running:
            score = 'Availability Score .. {} ({} responders)'.format(ursula._availability_tracker.score, len(ursula._availability_tracker.responders))
        else:
            score = 'Availability Score .. Disabled'

        stats.append(score)

    emitter.echo('\n' + '\n'.join(stats) + '\n')


def paint_known_nodes(emitter, ursula) -> None:
    # Gather Data
    known_nodes = ursula.known_nodes
    number_of_known_nodes = len(ursula.node_storage.all(federated_only=ursula.federated_only))
    seen_nodes = len(ursula.node_storage.all(federated_only=ursula.federated_only, certificates_only=True))

    # Operating Mode
    federated_only = ursula.federated_only
    if federated_only:
        emitter.echo("Configured in Federated Only mode", color='green')

    # Heading
    label = "Known Nodes (connected {} / seen {})".format(number_of_known_nodes, seen_nodes)
    heading = '\n' + label + " " * (45 - len(label))
    emitter.echo(heading, bold=True)

    # Build FleetState status line
    fleet_state = build_fleet_state_status(ursula=ursula)
    fleet_status_line = 'Fleet State {}'.format(fleet_state)
    emitter.echo(fleet_status_line, color='blue', bold=True)

    # Legend
    color_index = {
        'self': 'yellow',
        'known': 'white',
        'seednode': 'blue'
    }

    # Legend
    # for node_type, color in color_index.items():
    #     emitter.echo('{0:<6} | '.format(node_type), color=color, nl=False)
    # emitter.echo('\n')

    seednode_addresses = list(bn.checksum_address for bn in SEEDNODES)

    for node in known_nodes:
        node.mature()  # TODO: Use BSS "peek" or leave this here?
        row_template = "{} | {}"
        node_type = 'known'
        if node.checksum_address == ursula.checksum_address:
            node_type = 'self'
            row_template += ' ({})'.format(node_type)
        elif node.checksum_address in seednode_addresses:
            node_type = 'seednode'
            row_template += ' ({})'.format(node_type)
        emitter.echo(row_template.format(node.rest_url().ljust(20), node), color=color_index[node_type])


def paint_contract_status(registry, emitter):
    blockchain = BlockchainInterfaceFactory.get_interface()

    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=registry)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=registry)
    adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=registry)

    contracts = f"""
| Contract Deployments |
{token_agent.contract_name} ............ {token_agent.contract_address}
{staking_agent.contract_name} ............ {staking_agent.contract_address}
{policy_agent.contract_name} ............ {policy_agent.contract_address}
{adjudicator_agent.contract_name} .............. {adjudicator_agent.contract_address} 
    """

    blockchain = f"""    
| '{blockchain.client.chain_name}' Blockchain Network |
Gas Price ................ {Web3.fromWei(blockchain.client.gas_price, 'gwei')} Gwei
Provider URI ............. {blockchain.provider_uri}
Registry ................. {registry.filepath}
    """

    confirmed, pending, inactive = staking_agent.partition_stakers_by_activity()

    staking = f"""
| Staking |
Current Period ........... {staking_agent.get_current_period()}
Actively Staked Tokens ... {NU.from_nunits(staking_agent.get_global_locked_tokens())}
Stakers population ....... {staking_agent.get_staker_population()}
   Confirmed ............. {len(confirmed)}
   Pending confirmation .. {len(pending)}
   Inactive .............. {len(inactive)}

    """

    sep = '-' * 45
    emitter.echo(sep)
    emitter.echo(contracts)
    emitter.echo(sep)
    emitter.echo(blockchain)
    emitter.echo(sep)
    emitter.echo(staking)
    emitter.echo(sep)


def paint_deployer_contract_inspection(emitter, registry, deployer_address) -> None:

    blockchain = BlockchainInterfaceFactory.get_interface()

    sep = '-' * 45
    emitter.echo(sep)

    provider_info = f"""

* Web3 Provider
====================================================================

Provider URI ............. {blockchain.provider_uri}
Registry  ................ {registry.filepath}

* Standard Deployments
=====================================================================
"""
    emitter.echo(provider_info)

    try:
        token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=registry)
        token_contract_info = f"""

{token_agent.contract_name} ........... {token_agent.contract_address}
    ~ Ethers ............ {Web3.fromWei(blockchain.client.get_balance(token_agent.contract_address), 'ether')} ETH
    ~ Tokens ............ {NU.from_nunits(token_agent.get_balance(token_agent.contract_address))}"""
    except BaseContractRegistry.UnknownContract:
        message = f"\n{NucypherTokenAgent.contract_name} is not enrolled in {registry.filepath}"
        emitter.echo(message, color='yellow')
        emitter.echo(sep, nl=False)
    else:
        emitter.echo(token_contract_info)

    banner = """
* Proxy-Contract Deployments
====================================================================="""
    emitter.echo(banner)

    from nucypher.blockchain.eth.actors import ContractAdministrator
    for contract_deployer_class in ContractAdministrator.dispatched_upgradeable_deployer_classes:
        try:
            bare_contract = blockchain.get_contract_by_name(contract_name=contract_deployer_class.contract_name,
                                                            proxy_name=DispatcherDeployer.contract_name,
                                                            registry=registry,
                                                            use_proxy_address=False)

            dispatcher_deployer = DispatcherDeployer(registry=registry,
                                                     target_contract=bare_contract,
                                                     deployer_address=deployer_address,
                                                     bare=True)  # acquire agency for the dispatcher itself.

            agent = contract_deployer_class.agency(registry=registry, contract=bare_contract)

            proxy_payload = f"""
{agent.contract_name} .... {bare_contract.address}
    ~ Owner .............. {bare_contract.functions.owner().call()}
    ~ Ethers ............. {Web3.fromWei(blockchain.client.get_balance(bare_contract.address), 'ether')} ETH
    ~ Tokens ............. {NU.from_nunits(token_agent.get_balance(bare_contract.address))}
    ~ Dispatcher ......... {dispatcher_deployer.contract_address}
        ~ Owner .......... {dispatcher_deployer.contract.functions.owner().call()}
        ~ Target ......... {dispatcher_deployer.contract.functions.target().call()}
        ~ Ethers ......... {Web3.fromWei(blockchain.client.get_balance(dispatcher_deployer.contract_address), 'ether')} ETH
        ~ Tokens ......... {NU.from_nunits(token_agent.get_balance(dispatcher_deployer.contract_address))}"""
            emitter.echo(proxy_payload)
            emitter.echo(sep, nl=False)

        except BaseContractRegistry.UnknownContract:
            message = f"\n{contract_deployer_class.contract_name} is not enrolled in {registry.filepath}"
            emitter.echo(message, color='yellow')
            emitter.echo(sep, nl=False)

    try:

        #
        # StakingInterface
        #

        staking_interface_agent = PreallocationEscrowAgent.StakingInterfaceAgent(registry=registry)
        bare_contract = blockchain.get_contract_by_name(contract_name=staking_interface_agent.contract_name,
                                                        proxy_name=StakingInterfaceRouterDeployer.contract_name,
                                                        use_proxy_address=False,
                                                        registry=registry)

        router_deployer = StakingInterfaceRouterDeployer(registry=registry,
                                                         target_contract=bare_contract,
                                                         deployer_address=deployer_address,
                                                         bare=True)  # acquire agency for the dispatcher itself.

        preallocation_escrow_payload = f"""
{staking_interface_agent.contract_name} ......... {bare_contract.address}
  ~ Ethers ............... {Web3.fromWei(blockchain.client.get_balance(bare_contract.address), 'ether')} ETH
  ~ Tokens ............... {NU.from_nunits(token_agent.get_balance(bare_contract.address))}
  ~ StakingInterfaceRouter {router_deployer.contract.address}
        ~ Owner .......... {router_deployer.contract.functions.owner().call()}
        ~ Target ......... {router_deployer.contract.functions.target().call()}
        ~ Ethers ......... {Web3.fromWei(blockchain.client.get_balance(router_deployer.contract_address), 'ether')} ETH
        ~ Tokens ......... {NU.from_nunits(token_agent.get_balance(router_deployer.contract_address))}"""
        emitter.echo(preallocation_escrow_payload)
        emitter.echo(sep)

    except BaseContractRegistry.UnknownContract:
        message = f"\nStakingInterface is not enrolled in {registry.filepath}"
        emitter.echo(message, color='yellow')

    try:

        policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=registry)
        paint_min_reward_range(emitter, policy_agent)
        emitter.echo(sep, nl=False)

    except BaseContractRegistry.UnknownContract:
        message = f"\n{PolicyManagerDeployer.contract_name} is not enrolled in {registry.filepath}"
        emitter.echo(message, color='yellow')
        emitter.echo(sep, nl=False)


def paint_min_reward_range(emitter, policy_agent):
    minimum, default, maximum = policy_agent.get_min_reward_rate_range()

    range_payload = f"""
Range of the minimum reward rate:
    ~ Minimum ............ {prettify_eth_amount(minimum)}
    ~ Default ............ {prettify_eth_amount(default)}
    ~ Maximum ............ {prettify_eth_amount(maximum)}"""
    emitter.echo(range_payload)


def paint_min_rate(emitter, registry, policy_agent, staker_address):
    paint_min_reward_range(emitter, policy_agent)
    minimum = policy_agent.min_reward_rate(staker_address)
    raw_minimum = policy_agent.raw_min_reward_rate(staker_address)

    rate_payload = f"""
Minimum reward rate:
    ~ Previously set ....... {prettify_eth_amount(raw_minimum)}
    ~ Effective ............ {prettify_eth_amount(minimum)}"""
    emitter.echo(rate_payload)


def paint_multisig_contract_info(emitter, multisig_agent, token_agent):

    sep = '-' * 45
    emitter.echo(sep)

    blockchain = multisig_agent.blockchain
    registry = multisig_agent.registry

    contract_payload = f"""

* Web3 Provider
====================================================================

Provider URI ............. {blockchain.provider_uri}
Registry  ................ {registry.filepath}

* MultiSig Contract Information
=====================================================================

{multisig_agent.contract_name} ................. {multisig_agent.contract_address}
    ~ Ethers ............. {Web3.fromWei(blockchain.client.get_balance(multisig_agent.contract_address), 'ether')} ETH
    ~ Tokens ............. {NU.from_nunits(token_agent.get_balance(multisig_agent.contract_address))}"""
    emitter.echo(contract_payload)

    emitter.echo(f"Nonce .................... {multisig_agent.nonce}")
    emitter.echo(f"Threshold: ............... {multisig_agent.threshold}")
    emitter.echo(f"Owners:")
    for i, owner in enumerate(multisig_agent.owners):
        emitter.echo(f"[{i}] {owner}")


def paint_multisig_proposed_transaction(emitter, data_for_multisig_executives, contract=None):
    executive_summary = data_for_multisig_executives['parameters']
    data_to_sign = data_for_multisig_executives['digest']
    raw_data = executive_summary['data']

    info = f"""
Trustee address: .... {executive_summary['trustee_address']}
Target address: ..... {executive_summary['target_address']}
Value: .............. {Web3.fromWei(executive_summary['value'], 'ether')} ETH
Nonce: .............. {executive_summary['nonce']}
Raw TX data: ........ {raw_data}
Unsigned TX hash: ... {data_to_sign}
"""
    emitter.echo(info)

    if contract:
        paint_decoded_transaction(emitter, raw_data, contract)


def paint_decoded_transaction(emitter, raw_transaction_data, contract):
    emitter.echo("Decoded transaction:\n")
    contract_function, params = contract.decode_function_input(raw_transaction_data)
    emitter.echo(str(contract_function))
    for param, value in params.items():
        emitter.echo(f"  {param}={value}")


def paint_staged_stake(emitter,
                       stakeholder,
                       staking_address,
                       stake_value,
                       lock_periods,
                       start_period,
                       unlock_period,
                       division_message: str = None):
    start_datetime = datetime_at_period(period=start_period,
                                        seconds_per_period=stakeholder.economics.seconds_per_period,
                                        start_of_period=True)

    unlock_datetime = datetime_at_period(period=unlock_period,
                                         seconds_per_period=stakeholder.economics.seconds_per_period,
                                         start_of_period=True)

    start_datetime_pretty = start_datetime.local_datetime().strftime("%b %d %H:%M %Z")
    unlock_datetime_pretty = unlock_datetime.local_datetime().strftime("%b %d %H:%M %Z")

    if division_message:
        emitter.echo(f"\n{'═' * 30} ORIGINAL STAKE {'═' * 28}", bold=True)
        emitter.echo(division_message)

    emitter.echo(f"\n{'═' * 30} STAGED STAKE {'═' * 30}", bold=True)

    emitter.echo(f"""
Staking address: {staking_address}
~ Chain      -> ID # {stakeholder.wallet.blockchain.client.chain_id} | {stakeholder.wallet.blockchain.client.chain_name}
~ Value      -> {stake_value} ({int(stake_value)} NuNits)
~ Duration   -> {lock_periods} Days ({lock_periods} Periods)
~ Enactment  -> {start_datetime_pretty} (period #{start_period})
~ Expiration -> {unlock_datetime_pretty} (period #{unlock_period})
    """)

    # TODO: periods != Days - Do we inform the user here?

    emitter.echo('═'*73, bold=True)


def paint_staking_confirmation(emitter, staker, new_stake):
    emitter.echo("\nStake initialization transaction was successful.", color='green')
    emitter.echo(f'\nTransaction details:')
    paint_receipt_summary(emitter=emitter, receipt=new_stake.receipt, transaction_type="deposit stake")
    emitter.echo(f'\n{STAKING_ESCROW_CONTRACT_NAME} address: {staker.staking_agent.contract_address}', color='blue')
    next_steps = f'''\nView your stakes by running 'nucypher stake list'
or set your Ursula worker node address by running 'nucypher stake set-worker'.

See https://docs.nucypher.com/en/latest/guides/staking_guide.html'''
    emitter.echo(next_steps, color='green')


def paint_stakes(emitter, stakeholder, paint_inactive: bool = False, staker_address: str = None):
    headers = ('Idx', 'Value', 'Remaining', 'Enactment', 'Termination')
    staker_headers = ('Status', 'Restaking', 'Winding Down', 'Unclaimed Fees', 'Min reward rate')

    stakers = stakeholder.get_stakers()
    if not stakers:
        emitter.echo("No staking accounts found.")

    total_stakers = 0
    for staker in stakers:
        if not staker.stakes:
            # This staker has no active stakes.
            # TODO: Something with non-staking accounts?
            continue

        # Filter Target
        if staker_address and staker.checksum_address != staker_address:
            continue

        stakes = sorted(staker.stakes, key=lambda s: s.address_index_ordering_key)
        active_stakes = filter(lambda s: s.is_active, stakes)
        if not active_stakes:
            emitter.echo(f"There are no active stakes\n")

        fees = staker.policy_agent.get_reward_amount(staker.checksum_address)
        pretty_fees = prettify_eth_amount(fees)
        last_confirmed = staker.staking_agent.get_last_active_period(staker.checksum_address)
        missing = staker.missing_confirmations
        min_reward_rate = prettify_eth_amount(staker.min_reward_rate)

        if missing == -1:
            missing_info = "Never Confirmed (New Stake)"
        else:
            missing_info = f'Missing {missing} confirmation{"s" if missing > 1 else ""}' if missing else f'Confirmed #{last_confirmed}'

        staker_data = [missing_info,
                       f'{"Yes" if staker.is_restaking else "No"} ({"Locked" if staker.restaking_lock_enabled else "Unlocked"})',
                       "Yes" if bool(staker.is_winding_down) else "No",
                       pretty_fees,
                       min_reward_rate]

        emitter.echo(f"\nStaker {staker.checksum_address} ════", bold=True, color='red' if missing else 'green')
        emitter.echo(f"Worker {staker.worker_address} ════")
        emitter.echo(tabulate.tabulate(zip(staker_headers, staker_data), floatfmt="fancy_grid"))

        rows = list()
        for index, stake in enumerate(stakes):
            if not stake.is_active and not paint_inactive:
                # This stake is inactive.
                continue
            rows.append(list(stake.describe().values()))
        total_stakers += 1
        emitter.echo(tabulate.tabulate(rows, headers=headers, tablefmt="fancy_grid"))  # newline

    if not total_stakers:
        emitter.echo("No Stakes found", color='red')


def prettify_stake(stake, index: int = None) -> str:
    start_datetime = stake.start_datetime.local_datetime().strftime("%b %d %H:%M %Z")
    expiration_datetime = stake.unlock_datetime.local_datetime().strftime("%b %d %H:%M %Z")
    duration = stake.duration

    pretty_periods = f'{duration} periods {"." if len(str(duration)) == 2 else ""}'

    pretty = f'| {index if index is not None else "-"} ' \
             f'| {stake.staker_address[:6]} ' \
             f'| {stake.worker_address[:6]} ' \
             f'| {stake.index} ' \
             f'| {str(stake.value)} ' \
             f'| {pretty_periods} ' \
             f'| {start_datetime} - {expiration_datetime} ' \

    return pretty


def paint_staged_stake_division(emitter,
                                stakeholder,
                                original_stake,
                                target_value,
                                extension):
    new_end_period = original_stake.final_locked_period + extension
    new_duration_periods = new_end_period - original_stake.first_locked_period + 1
    staking_address = original_stake.staker_address

    division_message = f"""
Staking address: {staking_address}
~ Original Stake: {prettify_stake(stake=original_stake, index=None)}
"""

    paint_staged_stake(emitter=emitter,
                       stakeholder=stakeholder,
                       staking_address=staking_address,
                       stake_value=target_value,
                       lock_periods=new_duration_periods,
                       start_period=original_stake.first_locked_period,
                       unlock_period=new_end_period + 1,
                       division_message=division_message)


def paint_accounts(emitter, balances, registry):
    from nucypher.blockchain.eth.actors import Staker

    rows = list()
    max_eth_len, max_nu_len = 0, 0
    for address, balances in sorted(balances.items()):
        eth = str(Web3.fromWei(balances['ETH'], 'ether')) + " ETH"
        nu = str(NU.from_nunits(balances['NU']))

        max_eth_len = max(max_eth_len, len(eth))
        max_nu_len = max(max_nu_len, len(nu))

        staker = Staker(is_me=True, checksum_address=address, registry=registry)
        staker.stakes.refresh()
        is_staking = 'Yes' if bool(staker.stakes) else 'No'
        rows.append((is_staking, address, eth, nu))
    headers = ('Staking', 'Account', 'ETH', 'NU')
    emitter.echo(tabulate.tabulate(rows, showindex=True, headers=headers, tablefmt="fancy_grid"))


def paint_receipt_summary(emitter, receipt, chain_name: str = None, transaction_type=None, provider_uri: str = None):
    tx_hash = receipt['transactionHash'].hex()
    emitter.echo("OK", color='green', nl=False, bold=True)
    if transaction_type:
        emitter.echo(f" | {transaction_type} | {tx_hash}", color='yellow', nl=False)
    else:
        emitter.echo(f" | {tx_hash}", color='yellow', nl=False)
    emitter.echo(f" ({receipt['gasUsed']} gas)")
    emitter.echo(f"Block #{receipt['blockNumber']} | {receipt['blockHash'].hex()}")

    if not chain_name:
        blockchain = BlockchainInterfaceFactory.get_interface(provider_uri=provider_uri)
        chain_name = blockchain.client.chain_name
    try:
        url = etherscan_url(item=tx_hash, network=chain_name)
    except ValueError as e:
        emitter.log.info("Failed Etherscan URL construction: " + str(e))
    else:
        emitter.echo(f" See {url}\n")


def paint_contract_deployment(emitter,
                              contract_name: str,
                              contract_address: str,
                              receipts: dict,
                              chain_name: str = None,
                              open_in_browser: bool = False):
    # TODO: switch to using an explicit emitter

    is_token_contract = contract_name == NUCYPHER_TOKEN_CONTRACT_NAME

    # Paint heading
    heading = f'\r{" "*80}\n{contract_name} ({contract_address})'
    emitter.echo(heading, bold=True)
    emitter.echo('*' * (42 + 3 + len(contract_name)))
    try:
        url = etherscan_url(item=contract_address, network=chain_name, is_token=is_token_contract)
    except ValueError as e:
        emitter.log.info("Failed Etherscan URL construction: " + str(e))
    else:
        emitter.echo(f" See {url}\n")

    # Paint Transactions
    for tx_name, receipt in receipts.items():
        paint_receipt_summary(emitter=emitter,
                              receipt=receipt,
                              chain_name=chain_name,
                              transaction_type=tx_name)

    if open_in_browser:
        try:
            url = etherscan_url(item=contract_address,
                                network=chain_name,
                                is_token=is_token_contract)
        except ValueError as e:
            emitter.log.info("Failed Etherscan URL construction: " + str(e))
        else:
            webbrowser.open_new_tab(url)


def paint_staged_deployment(emitter, deployer_interface, administrator) -> None:
    emitter.clear()
    emitter.banner(NU_BANNER)
    emitter.echo(f"Current Time ........ {maya.now().iso8601()}")
    emitter.echo(f"Web3 Provider ....... {deployer_interface.provider_uri}")
    emitter.echo(f"Block ............... {deployer_interface.client.block_number}")
    emitter.echo(f"Gas Price ........... {deployer_interface.client.gas_price}")
    emitter.echo(f"Deployer Address .... {administrator.checksum_address}")
    emitter.echo(f"ETH ................. {administrator.eth_balance}")
    emitter.echo(f"Chain ID ............ {deployer_interface.client.chain_id}")
    emitter.echo(f"Chain Name .......... {deployer_interface.client.chain_name}")

    # Ask - Last chance to gracefully abort. This step cannot be forced.
    emitter.echo("\nDeployment successfully staged. Take a deep breath. \n", color='green')


def paint_deployment_delay(emitter, delay: int = 3) -> None:
    emitter.echo(f"Starting deployment in {delay} seconds...", color='red')
    for i in range(delay)[::-1]:
        emitter.echo(f"{i}...", color='yellow')
        time.sleep(1)


def paint_stakers(emitter, stakers: List[str], staking_agent, policy_agent) -> None:
    current_period = staking_agent.get_current_period()
    emitter.echo(f"\nCurrent period: {current_period}")
    emitter.echo("\n| Stakers |\n")
    emitter.echo(f"{'Checksum address':42}  Staker information")
    emitter.echo('=' * (42 + 2 + 53))

    for staker in stakers:
        nickname, pairs = nickname_from_seed(staker)
        symbols = f"{pairs[0][1]}  {pairs[1][1]}"
        emitter.echo(f"{staker}  {'Nickname:':10} {nickname} {symbols}")
        tab = " " * len(staker)

        owned_tokens = staking_agent.owned_tokens(staker)
        last_confirmed_period = staking_agent.get_last_active_period(staker)
        worker = staking_agent.get_worker_from_staker(staker)
        is_restaking = staking_agent.is_restaking(staker)
        is_winding_down = staking_agent.is_winding_down(staker)

        missing_confirmations = current_period - last_confirmed_period
        owned_in_nu = round(NU.from_nunits(owned_tokens), 2)
        locked_tokens = round(NU.from_nunits(staking_agent.get_locked_tokens(staker)), 2)

        emitter.echo(f"{tab}  {'Owned:':10} {owned_in_nu}  (Staked: {locked_tokens})")
        if is_restaking:
            if staking_agent.is_restaking_locked(staker):
                unlock_period = staking_agent.get_restake_unlock_period(staker)
                emitter.echo(f"{tab}  {'Re-staking:':10} Yes  (Locked until period: {unlock_period})")
            else:
                emitter.echo(f"{tab}  {'Re-staking:':10} Yes  (Unlocked)")
        else:
            emitter.echo(f"{tab}  {'Re-staking:':10} No")
        emitter.echo(f"{tab}  {'Winding down:':10} {'Yes' if is_winding_down else 'No'}")
        emitter.echo(f"{tab}  {'Activity:':10} ", nl=False)
        if missing_confirmations == -1:
            emitter.echo(f"Next period confirmed (#{last_confirmed_period})", color='green')
        elif missing_confirmations == 0:
            emitter.echo(f"Current period confirmed (#{last_confirmed_period}). "
                         f"Pending confirmation of next period.", color='yellow')
        elif missing_confirmations == current_period:
            emitter.echo(f"Never confirmed activity", color='red')
        else:
            emitter.echo(f"Missing {missing_confirmations} confirmations "
                         f"(last time for period #{last_confirmed_period})", color='red')

        emitter.echo(f"{tab}  {'Worker:':10} ", nl=False)
        if worker == BlockchainInterface.NULL_ADDRESS:
            emitter.echo(f"Worker not set", color='red')
        else:
            emitter.echo(f"{worker}")

        fees = prettify_eth_amount(policy_agent.get_reward_amount(staker))
        emitter.echo(f"{tab}  Unclaimed fees: {fees}")

        min_rate = prettify_eth_amount(policy_agent.get_min_reward_rate(staker))
        emitter.echo(f"{tab}  Min reward rate: {min_rate}")


def paint_preallocation_status(emitter, preallocation_agent, token_agent) -> None:
    blockchain = token_agent.blockchain

    staking_address = preallocation_agent.principal_contract.address

    token_balance = NU.from_nunits(token_agent.get_balance(staking_address))
    eth_balance = Web3.fromWei(blockchain.client.get_balance(staking_address), 'ether')
    initial_locked_amount = NU.from_nunits(preallocation_agent.initial_locked_amount)
    current_locked_amount = NU.from_nunits(preallocation_agent.unvested_tokens)
    available_amount = NU.from_nunits(preallocation_agent.available_balance)
    end_timestamp = preallocation_agent.end_timestamp

    width = 64
    output = f"""
{" Addresses ".center(width, "-")}
Staking contract: ... {staking_address}
Beneficiary: ........ {preallocation_agent.beneficiary}

{" Locked Tokens ".center(width, "-")}
Initial locked amount: {initial_locked_amount}
Current locked amount: {current_locked_amount}
Locked until: ........ {maya.MayaDT(epoch=end_timestamp)}

{" NU and ETH Balance ".center(width, "-")}
NU balance: .......... {token_balance}
    Available: ....... {available_amount} 
ETH balance: ......... {eth_balance} ETH
"""
    emitter.echo(output)


def paint_locked_tokens_status(emitter, agent, periods) -> None:

    MAX_ROWS = 30
    period_range = list(range(1, periods + 1))
    token_counter = Counter({day: agent.get_all_locked_tokens(day) for day in period_range})

    width = 60  # Adjust to desired width
    longest_key = max(len(str(key)) for key in token_counter)
    graph_width = width - longest_key - 2
    widest = token_counter.most_common(1)[0][1]
    scale = graph_width / float(widest)

    bucket_size = periods // MAX_ROWS if periods > MAX_ROWS else 1

    emitter.echo(f"\n| Locked Tokens for next {periods} periods |\n")

    buckets = [period_range[i:i + bucket_size] for i in range(0, len(period_range), bucket_size)]

    for bucket in buckets:
        bucket_start = bucket[0]
        bucket_end = bucket[-1]

        bucket_max = max([token_counter[period] for period in bucket])
        bucket_min = min([token_counter[period] for period in bucket])
        delta = bucket_max - bucket_min

        bucket_range = f"{bucket_start} - {bucket_end}"
        box_plot = f"{int(bucket_min * scale) * '■'}{int(delta * scale) * '□'}"
        emitter.echo(f"{bucket_range:>9}: {box_plot:60}"
                     f"Min: {NU.from_nunits(bucket_min)} - Max: {NU.from_nunits(bucket_max)}")


def paint_input_allocation_file(emitter, allocations) -> None:
    num_allocations = len(allocations)
    emitter.echo(f"Found {num_allocations} allocations:")
    emitter.echo(f"\n{'='*46} STAGED ALLOCATIONS {'='*45}", bold=True)
    emitter.echo(f"\n{'Beneficiary':42} | {'Name':20} | {'Duration':20} | {'Amount':20}", bold=True)
    emitter.echo("-"*(42+3+20+3+20+3+20), bold=True)
    for allocation in allocations:
        beneficiary = allocation['beneficiary_address']
        amount = str(NU.from_nunits(allocation['amount']))
        duration = (maya.now() + maya.timedelta(seconds=allocation['duration_seconds'])).slang_date()
        name = allocation.get('name', 'No name provided')
        emitter.echo(f"{beneficiary} | {name:20} | {duration:20} | {amount:20}")
    emitter.echo()


def paint_deployed_allocations(emitter, allocations, failed) -> None:
    emitter.echo(f"\n{'='*45} DEPLOYED ALLOCATIONS {'='*44}", bold=True)
    emitter.echo(f"\n{'Beneficiary':42} | {'Name':20} | {'PreallocationEscrow contract':42} ", bold=True)
    emitter.echo("-"*(42+3+20+3+42), bold=True)
    for allocation, contract_address in allocations:
        beneficiary = allocation['beneficiary_address']
        name = allocation.get('name', 'No name provided')
        emitter.echo(f"{beneficiary} | {name:20} | {contract_address}")
    for allocation in failed:
        beneficiary = allocation['beneficiary_address']
        name = allocation.get('name', 'No name provided')
        emitter.echo(f"{beneficiary} | {name:20} | FAILED", color='red')
    emitter.echo()


def write_deployed_allocations_to_csv(filepath: str, allocated: list, failed: list):
    fieldnames = ['Beneficiary', 'Name', 'Contract address']
    allocated += [(failed_allocation, "FAILED") for failed_allocation in failed]

    with open(filepath, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for allocation, contract_address in allocated:
            beneficiary = allocation['beneficiary_address']
            name = allocation.get('name', 'No name provided')
            row = (beneficiary, name, contract_address)
            writer.writerow(dict(zip(fieldnames, row)))


def echo_solidity_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.secho(f"Supported solidity version: {SOLIDITY_COMPILER_VERSION}", bold=True)
    ctx.exit()


def paint_worklock_status(emitter, registry: BaseContractRegistry):
    from maya import MayaDT
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=registry)  # type: WorkLockAgent
    blockchain = worklock_agent.blockchain

    # Time
    bidding_start = MayaDT(worklock_agent.contract.functions.startBidDate().call())
    bidding_end = MayaDT(worklock_agent.contract.functions.endBidDate().call())
    cancellation_end = MayaDT(worklock_agent.contract.functions.endCancellationDate().call())

    bidding_duration = bidding_end - bidding_start
    cancellation_duration = cancellation_end - bidding_start
    now = maya.now()
    bidding_remaining = bidding_end - now if bidding_end > now else timedelta()
    cancellation_remaining = cancellation_end - now if cancellation_end > now else timedelta()

    payload = f"""

Time
======================================================
Bidding Start Date ................... {bidding_start}
Bidding End Date ..................... {bidding_end}
Bidding Duration ..................... {bidding_duration}
Bidding Time Remaining ............... {bidding_remaining} 

Cancellation Window End Date ......... {cancellation_end}
Cancellation Window Duration ......... {cancellation_duration}
Cancellation Window Time Remaining ... {cancellation_remaining}
 
Claiming phase open .................. {'Yes' if worklock_agent.is_claiming_available() else 'No'} 

Economics
======================================================        
Min allowed bid ....... {prettify_eth_amount(worklock_agent.minimum_allowed_bid)}
ETH Pool .............. {prettify_eth_amount(blockchain.client.get_balance(worklock_agent.contract_address))}
ETH Supply ............ {prettify_eth_amount(worklock_agent.get_eth_supply())}
Bonus ETH Supply ...... {prettify_eth_amount(worklock_agent.get_bonus_eth_supply())}

Number of bidders...... {worklock_agent.get_bidders_population()}
Lot Size .............. {NU.from_nunits(worklock_agent.lot_value)} 
Bonus Lot Size ........ {NU.from_nunits(worklock_agent.get_bonus_lot_value())} 

Boosting Refund ....... {worklock_agent.contract.functions.boostingRefund().call()}
Slowing Refund ........ {worklock_agent.contract.functions.SLOWING_REFUND().call()}
Bonus Refund Rate ..... {worklock_agent.get_bonus_refund_rate()}
Bonus Deposit Rate .... {worklock_agent.get_bonus_deposit_rate()}
    """
    emitter.echo(payload)
    return


def paint_bidder_status(emitter, bidder):
    claim = NU.from_nunits(bidder.available_claim)
    if claim > bidder.economics.maximum_allowed_locked:
        claim = f"{claim} (Above the allowed max. The bid will be partially refunded)"

    message = f"""
WorkLock Participant {bidder.checksum_address}
=====================================================
Total Bid ............ {prettify_eth_amount(bidder.get_deposited_eth)}
Tokens Allocated ..... {claim}
Tokens Claimed? ...... {"Yes" if bidder._has_claimed else "No"}"""

    compensation = bidder.available_compensation
    if compensation:
        message += f"""
Unspent Bid Amount ... {prettify_eth_amount(compensation)}"""

    message += f"""\n
Completed Work ....... {bidder.completed_work}
Available Refund ..... {prettify_eth_amount(bidder.available_refund)}

Refunded Work ........ {bidder.refunded_work}
Remaining Work ....... {bidder.remaining_work}
"""

    emitter.echo(message)
    return


def paint_bidding_notice(emitter, bidder):

    obligation = f"""
* WorkLock Participant Notice *
-------------------------------

- By participating in NuCypher's WorkLock you are committing to operating a staking
  NuCypher node after the bidding window closes.

- WorkLock token rewards are claimed in the form of a stake and will be locked for
  the stake duration.

- WorkLock ETH deposits will be available for refund at a rate of {prettify_eth_amount(bidder.worklock_agent.get_bonus_refund_rate())} 
  per confirmed period. This rate may vary until {maya.MayaDT(bidder.economics.bidding_end_date).local_datetime()}.

- Once claiming WorkLock tokens, you are obligated to maintain a networked and available
  Ursula-Worker node bonded to the staker address {bidder.checksum_address}
  for the duration of the stake(s) ({bidder.economics.worklock_commitment_duration} periods).

- Allow NuCypher network users to carry out uninterrupted re-encryption work orders
  at-will without interference. Failure to keep your node online, or violation of
  re-encryption work orders will result in the loss of staked tokens as described
  in the NuCypher slashing protocol.

- Keeping your Ursula node online during the staking period and correctly servicing
  re-encryption work orders will result in rewards paid out in ethers retro-actively
  and on-demand.

Accept WorkLock terms and node operator obligation?"""  # TODO: Show a special message for first bidder, since there's no refund rate yet?

    emitter.echo(obligation)
    return


def paint_worklock_claim(emitter, bidder_address: str, network: str, provider_uri: str):
    message = f"""

Successfully claimed WorkLock tokens for {bidder_address}.

You can check that the stake was created correctly by running:

  nucypher status stakers --staking-address {bidder_address} --network {network} --provider {provider_uri} --poa

Next Steps for WorkLock Winners
===============================

Congratulations! You're officially a Staker in the NuCypher network.

See the official NuCypher documentation for a comprehensive guide on next steps!

As a first step, you need to bond a worker to your stake by running:

  nucypher stake set-worker --worker-address <WORKER ADDRESS>

"""
    emitter.echo(message, color='green')
