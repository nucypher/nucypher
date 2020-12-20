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


from decimal import Decimal

import click
from web3 import Web3

from nucypher.blockchain.eth.actors import StakeHolder
from nucypher.blockchain.eth.constants import MAX_UINT16
from nucypher.blockchain.eth.events import EventRecord
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory, BlockchainInterface
from nucypher.blockchain.eth.registry import IndividualAllocationRegistry
from nucypher.blockchain.eth.signers import TrezorSigner
from nucypher.blockchain.eth.signers.software import ClefSigner
from nucypher.blockchain.eth.token import NU, Stake
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.cli.actions.auth import get_client_password
from nucypher.cli.actions.configure import get_or_update_configuration, handle_missing_configuration_file
from nucypher.cli.actions.confirm import (
    confirm_enable_restaking,
    confirm_enable_restaking_lock,
    confirm_enable_winding_down,
    confirm_large_stake,
    confirm_staged_stake,
    confirm_disable_snapshots
)
from nucypher.cli.actions.select import select_client_account_for_staking, select_stake
from nucypher.cli.config import group_general_config, GroupGeneralConfig
from nucypher.cli.literature import (
    BONDING_DETAILS,
    BONDING_RELEASE_INFO,
    COLLECTING_ETH_FEE,
    COLLECTING_PREALLOCATION_REWARD,
    COLLECTING_TOKEN_REWARD,
    CONFIRM_BROADCAST_CREATE_STAKE,
    CONFIRM_BROADCAST_STAKE_DIVIDE,
    CONFIRM_DISABLE_RESTAKING, CONFIRM_DISABLE_WIND_DOWN,
    CONFIRM_NEW_MIN_POLICY_RATE,
    CONFIRM_PROLONG,
    CONFIRM_WORKER_AND_STAKER_ADDRESSES_ARE_EQUAL,
    DETACH_DETAILS,
    PERIOD_ADVANCED_WARNING,
    PROMPT_PROLONG_VALUE,
    PROMPT_STAKER_MIN_POLICY_RATE,
    PROMPT_STAKE_DIVIDE_VALUE,
    PROMPT_STAKE_EXTEND_VALUE,
    PROMPT_WORKER_ADDRESS,
    SUCCESSFUL_DETACH_WORKER,
    SUCCESSFUL_DISABLE_RESTAKING, SUCCESSFUL_DISABLE_WIND_DOWN,
    SUCCESSFUL_ENABLE_RESTAKE_LOCK,
    SUCCESSFUL_ENABLE_RESTAKING,
    SUCCESSFUL_ENABLE_WIND_DOWN,
    SUCCESSFUL_NEW_STAKEHOLDER_CONFIG,
    SUCCESSFUL_SET_MIN_POLICY_RATE,
    SUCCESSFUL_STAKE_DIVIDE,
    SUCCESSFUL_STAKE_PROLONG,
    SUCCESSFUL_WORKER_BONDING,
    NO_MINTABLE_PERIODS,
    STILL_LOCKED_TOKENS,
    CONFIRM_MINTING,
    SUCCESSFUL_MINTING,
    CONFIRM_COLLECTING_WITHOUT_MINTING,
    NO_TOKENS_TO_WITHDRAW,
    NO_FEE_TO_WITHDRAW,
    CONFIRM_INCREASING_STAKE,
    PROMPT_STAKE_INCREASE_VALUE,
    SUCCESSFUL_STAKE_INCREASE,
    INSUFFICIENT_BALANCE_TO_INCREASE,
    MAXIMUM_STAKE_REACHED,
    INSUFFICIENT_BALANCE_TO_CREATE,
    PROMPT_STAKE_CREATE_VALUE,
    PROMPT_STAKE_CREATE_LOCK_PERIODS,
    ONLY_DISPLAYING_MERGEABLE_STAKES_NOTE,
    CONFIRM_MERGE,
    SUCCESSFUL_STAKES_MERGE,
    SUCCESSFUL_ENABLE_SNAPSHOTS,
    SUCCESSFUL_DISABLE_SNAPSHOTS,
    CONFIRM_ENABLE_SNAPSHOTS,
    CONFIRM_STAKE_USE_UNLOCKED,
    CONFIRM_REMOVE_SUBSTAKE,
    SUCCESSFUL_STAKE_REMOVAL
)
from nucypher.cli.options import (
    group_options,
    option_config_file,
    option_config_root,
    option_event_name,
    option_force,
    option_hw_wallet,
    option_light,
    option_network,
    option_poa,
    option_provider_uri,
    option_registry_filepath,
    option_signer_uri,
    option_staking_address,
    option_gas_price)
from nucypher.cli.painting.staking import (
    paint_min_rate, paint_staged_stake,
    paint_staged_stake_division,
    paint_stakes,
    paint_staking_accounts,
    paint_staking_confirmation, paint_all_stakes
)
from nucypher.cli.painting.status import paint_preallocation_status
from nucypher.cli.painting.transactions import paint_receipt_summary
from nucypher.cli.types import (
    EIP55_CHECKSUM_ADDRESS,
    EXISTING_READABLE_FILE,
    GWEI,
    DecimalRange
)
from nucypher.cli.utils import setup_emitter
from nucypher.config.characters import StakeHolderConfiguration
from nucypher.utilities.gas_strategies import construct_fixed_price_gas_strategy

option_value = click.option('--value', help="Token value of stake", type=DecimalRange(min=0))
option_lock_periods = click.option('--lock-periods', help="Duration of stake in periods.", type=click.INT)
option_worker_address = click.option('--worker-address', help="Address to bond as an Ursula-Worker", type=EIP55_CHECKSUM_ADDRESS)
option_index = click.option('--index', help="The staker-specific stake index to edit", type=click.INT)
option_from_unlocked = click.option('--from-unlocked',
                                    help="Only use uncollected staking rewards and unlocked sub-stakes; not tokens from staker address",
                                    default=False,
                                    is_flag=True)


class StakeHolderConfigOptions:

    __option_name__ = 'config_options'

    def __init__(self, provider_uri, poa, light, registry_filepath, network, signer_uri):
        self.provider_uri = provider_uri
        self.signer_uri = signer_uri
        self.poa = poa
        self.light = light
        self.registry_filepath = registry_filepath
        self.network = network

    def retrieve_config(self, emitter, config_file):
        try:
            return StakeHolderConfiguration.from_configuration_file(
                emitter=emitter,
                filepath=config_file,
                provider_uri=self.provider_uri,
                signer_uri=self.signer_uri,
                poa=self.poa,
                light=self.light,
                domain=self.network,
                registry_filepath=self.registry_filepath)

        except FileNotFoundError:
            return handle_missing_configuration_file(
                character_config_class=StakeHolderConfiguration,
                init_command_hint=f"{stake.name} {init_stakeholder.name}",
                config_file=config_file)

    def generate_config(self, config_root):

        if self.provider_uri is None:
            raise click.BadOptionUsage(
                option_name="--provider",
                message="--provider must be specified to create a new stakeholder")

        if self.network is None:
            raise click.BadOptionUsage(
                option_name="--network",
                message="--network must be specified to create a new stakeholder")

        return StakeHolderConfiguration.generate(
            config_root=config_root,
            provider_uri=self.provider_uri,
            signer_uri=self.signer_uri,
            poa=self.poa,
            light=self.light,
            registry_filepath=self.registry_filepath,
            domain=self.network
        )

    def get_updates(self) -> dict:
        payload = dict(provider_uri=self.provider_uri,
                       signer_uri=self.signer_uri,
                       poa=self.poa,
                       light=self.light,
                       registry_filepath=self.registry_filepath,
                       domain=self.network)
        # Depends on defaults being set on Configuration classes, filtrates None values
        updates = {k: v for k, v in payload.items() if v is not None}
        return updates


group_config_options = group_options(
    StakeHolderConfigOptions,
    provider_uri=option_provider_uri(),
    poa=option_poa,
    light=option_light,
    registry_filepath=option_registry_filepath,
    network=option_network(),
    signer_uri=option_signer_uri
)


class StakerOptions:

    __option_name__ = 'staker_options'

    def __init__(self, config_options: StakeHolderConfigOptions, staking_address: str):
        self.config_options = config_options
        self.staking_address = staking_address

    def create_character(self, emitter, config_file, initial_address=None, *args, **kwargs):
        stakeholder_config = self.config_options.retrieve_config(emitter, config_file)
        if initial_address is None:
            initial_address = self.staking_address
        return stakeholder_config.produce(initial_address=initial_address, *args, **kwargs)

    def get_blockchain(self):
        return BlockchainInterfaceFactory.get_interface(provider_uri=self.config_options.provider_uri)  # Eager connection


group_staker_options = group_options(
    StakerOptions,
    config_options=group_config_options,
    staking_address=option_staking_address,
)


class TransactingStakerOptions:

    __option_name__ = 'transacting_staker_options'

    def __init__(self, staker_options: StakerOptions, hw_wallet, beneficiary_address, allocation_filepath, gas_price):
        self.staker_options = staker_options
        self.hw_wallet = hw_wallet
        self.beneficiary_address = beneficiary_address
        self.allocation_filepath = allocation_filepath
        self.gas_price = gas_price

    def create_character(self, emitter, config_file):

        opts = self.staker_options
        stakeholder_config = opts.config_options.retrieve_config(emitter, config_file)

        # Now let's check whether we're dealing here with a regular staker or a preallocation staker
        is_preallocation_staker = (self.beneficiary_address and opts.staking_address) or self.allocation_filepath

        if is_preallocation_staker:
            network = opts.config_options.network or stakeholder_config.domain
            if self.allocation_filepath:
                if self.beneficiary_address or opts.staking_address:
                    message = "--allocation-filepath is incompatible with --beneficiary-address and --staking-address."
                    raise click.BadOptionUsage(option_name="--allocation-filepath", message=message)

                # This assumes the user has an individual allocation file in disk
                individual_allocation = IndividualAllocationRegistry.from_allocation_file(self.allocation_filepath,
                                                                                          network=network)
                initial_address = individual_allocation.beneficiary_address
            elif self.beneficiary_address and opts.staking_address:
                individual_allocation = IndividualAllocationRegistry(beneficiary_address=self.beneficiary_address,
                                                                     contract_address=opts.staking_address,
                                                                     network=network)
                initial_address = self.beneficiary_address
            else:
                option = "--beneficiary_address" if self.beneficiary_address else "--staking-address"
                raise click.BadOptionUsage(option_name=option,
                                           message=f"You must specify both --beneficiary-address and --staking-address. "
                                                   f"Only {option} was provided. As an alternative, you can simply "
                                                   f"provide an individual allocation with --allocation-file <PATH>")
        else:
            individual_allocation = None
            initial_address = None

        return opts.create_character(
            emitter,
            config_file,
            individual_allocation=individual_allocation,
            initial_address=initial_address,
        )

    def get_blockchain(self):
        blockchain = self.staker_options.get_blockchain()
        if self.gas_price:  # TODO: Consider performing this step in the init of EthereumClient
            fixed_price_strategy = construct_fixed_price_gas_strategy(gas_price=self.gas_price, denomination="gwei")
            blockchain.configure_gas_strategy(fixed_price_strategy)
        return blockchain


group_transacting_staker_options = group_options(
    TransactingStakerOptions,
    staker_options=group_staker_options,
    hw_wallet=option_hw_wallet,
    beneficiary_address=click.option('--beneficiary-address', help="Address of a pre-allocation beneficiary", type=EIP55_CHECKSUM_ADDRESS),
    allocation_filepath=click.option('--allocation-filepath', help="Path to individual allocation file", type=EXISTING_READABLE_FILE),
    gas_price=option_gas_price,
)


def get_password(stakeholder: StakeHolder,
                 blockchain: BlockchainInterface,
                 client_account: str,
                 hw_wallet: bool = False):
    signer_handles_passwords = isinstance(stakeholder.wallet.signer, (ClefSigner, TrezorSigner))
    eth_password_needed = not hw_wallet and not blockchain.client.is_local and not signer_handles_passwords
    password = None
    if eth_password_needed:
        password = get_client_password(checksum_address=client_account)
    return password


@click.group()
def stake():
    """Manage stakes and other staker-related operations."""


@stake.command(name='init-stakeholder')
@option_config_root
@option_force
@group_config_options
@group_general_config
def init_stakeholder(general_config, config_root, force, config_options):
    """Create a new stakeholder configuration."""
    emitter = setup_emitter(general_config)
    new_stakeholder = config_options.generate_config(config_root)
    filepath = new_stakeholder.to_configuration_file(override=force)
    emitter.echo(SUCCESSFUL_NEW_STAKEHOLDER_CONFIG.format(filepath=filepath), color='green')


@stake.command()
@option_config_file
@group_general_config
@group_config_options
def config(general_config, config_file, config_options):
    """View and optionally update existing StakeHolder's configuration."""
    emitter = setup_emitter(general_config)
    configuration_file_location = config_file or StakeHolderConfiguration.default_filepath()
    updates = config_options.get_updates()
    get_or_update_configuration(emitter=emitter,
                                config_class=StakeHolderConfiguration,
                                filepath=configuration_file_location,
                                updates=updates)


@stake.command('list')
@group_staker_options
@option_config_file
@click.option('--all', 'show_all', help="List all stakes, including unlocked and inactive", is_flag=True)
@group_general_config
def list_stakes(general_config, staker_options, config_file, show_all):
    """List active stakes for current stakeholder."""
    emitter = setup_emitter(general_config)
    STAKEHOLDER = staker_options.create_character(emitter, config_file)
    paint_all_stakes(emitter=emitter, stakeholder=STAKEHOLDER, paint_unlocked=show_all)


@stake.command()
@group_staker_options
@option_config_file
@group_general_config
def accounts(general_config, staker_options, config_file):
    """Show ETH and NU balances for stakeholder's accounts."""
    emitter = setup_emitter(general_config)
    STAKEHOLDER = staker_options.create_character(emitter, config_file)
    paint_staking_accounts(emitter=emitter, wallet=STAKEHOLDER.wallet, registry=STAKEHOLDER.registry)


@stake.command('bond-worker')
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
@option_worker_address
def bond_worker(general_config: GroupGeneralConfig,
                transacting_staker_options: TransactingStakerOptions,
                config_file, force, worker_address):
    """Bond a worker to a staker."""

    emitter = setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()
    economics = STAKEHOLDER.economics

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    if not worker_address:
        worker_address = click.prompt(PROMPT_WORKER_ADDRESS, type=EIP55_CHECKSUM_ADDRESS)

    if (worker_address == staking_address) and not force:
        click.confirm(CONFIRM_WORKER_AND_STAKER_ADDRESSES_ARE_EQUAL.format(address=worker_address), abort=True)

    # TODO: Check preconditions (e.g., minWorkerPeriods, already in use, etc)

    # TODO: Double-check dates
    # Calculate release datetime
    current_period = STAKEHOLDER.staking_agent.get_current_period()
    bonded_date = datetime_at_period(period=current_period, seconds_per_period=economics.seconds_per_period)
    min_worker_periods = STAKEHOLDER.economics.minimum_worker_periods

    release_period = current_period + min_worker_periods
    release_date = datetime_at_period(period=release_period,
                                      seconds_per_period=economics.seconds_per_period,
                                      start_of_period=True)

    if not force:
        click.confirm(f"Commit to bonding "
                      f"worker {worker_address} to staker {staking_address} "
                      f"for a minimum of {STAKEHOLDER.economics.minimum_worker_periods} periods?", abort=True)

    password = get_password(stakeholder=STAKEHOLDER,
                            blockchain=blockchain,
                            client_account=client_account,
                            hw_wallet=transacting_staker_options.hw_wallet)
    STAKEHOLDER.assimilate(password=password)
    receipt = STAKEHOLDER.bond_worker(worker_address=worker_address)

    # Report Success
    message = SUCCESSFUL_WORKER_BONDING.format(worker_address=worker_address, staking_address=staking_address)
    emitter.echo(message, color='green')
    paint_receipt_summary(emitter=emitter,
                          receipt=receipt,
                          chain_name=blockchain.client.chain_name,
                          transaction_type='bond_worker')
    emitter.echo(BONDING_DETAILS.format(current_period=current_period, bonded_date=bonded_date), color='green')
    emitter.echo(BONDING_RELEASE_INFO.format(release_period=release_period, release_date=release_date), color='green')


@stake.command('unbond-worker')
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
def unbond_worker(general_config: GroupGeneralConfig,
                  transacting_staker_options: TransactingStakerOptions,
                  config_file, force):
    """
    Unbond worker currently bonded to a staker.
    """
    emitter = setup_emitter(general_config)

    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    economics = STAKEHOLDER.economics

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    # TODO: Check preconditions (e.g., minWorkerPeriods)
    worker_address = STAKEHOLDER.staking_agent.get_worker_from_staker(staking_address)

    password = get_password(stakeholder=STAKEHOLDER,
                            blockchain=blockchain,
                            client_account=client_account,
                            hw_wallet=transacting_staker_options.hw_wallet)

    if not force:
        click.confirm("Are you sure you want to unbond your worker?", abort=True)

    STAKEHOLDER.assimilate(password=password)
    receipt = STAKEHOLDER.unbond_worker()

    # TODO: Double-check dates
    current_period = STAKEHOLDER.staking_agent.get_current_period()
    bonded_date = datetime_at_period(period=current_period, seconds_per_period=economics.seconds_per_period)

    message = SUCCESSFUL_DETACH_WORKER.format(worker_address=worker_address, staking_address=staking_address)
    emitter.echo(message, color='green')
    paint_receipt_summary(emitter=emitter,
                          receipt=receipt,
                          chain_name=blockchain.client.chain_name,
                          transaction_type='unbond_worker')
    emitter.echo(DETACH_DETAILS.format(current_period=current_period, bonded_date=bonded_date), color='green')


@stake.command()
@group_transacting_staker_options
@option_config_file
@option_force
@option_value
@option_lock_periods
@group_general_config
@option_from_unlocked
def create(general_config: GroupGeneralConfig,
           transacting_staker_options: TransactingStakerOptions,
           config_file, force, value, lock_periods, from_unlocked):
    """Initialize a new stake."""

    # Setup
    emitter = setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()
    economics = STAKEHOLDER.economics

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    # Dynamic click types (Economics)
    min_locked = economics.minimum_allowed_locked
    stake_value_range = DecimalRange(min=NU.from_nunits(min_locked).to_tokens(), clamp=False)
    stake_duration_range = click.IntRange(min=economics.minimum_locked_periods, clamp=False)

    #
    # Stage Stake
    #

    if not value:
        if from_unlocked:
            click.confirm(CONFIRM_STAKE_USE_UNLOCKED, abort=True)

        token_balance = STAKEHOLDER.calculate_staking_reward() if from_unlocked else STAKEHOLDER.token_balance
        lower_limit = NU.from_nunits(STAKEHOLDER.economics.minimum_allowed_locked)
        locked_tokens = STAKEHOLDER.locked_tokens(periods=1).to_nunits()
        upper_limit = min(token_balance, NU.from_nunits(STAKEHOLDER.economics.maximum_allowed_locked - locked_tokens))

        if token_balance < lower_limit:
            emitter.echo(INSUFFICIENT_BALANCE_TO_CREATE, color='red')
            raise click.Abort
        if upper_limit < lower_limit:
            emitter.echo(MAXIMUM_STAKE_REACHED, color='red')
            raise click.Abort

        value = click.prompt(PROMPT_STAKE_CREATE_VALUE.format(lower_limit=lower_limit, upper_limit=upper_limit),
                             type=stake_value_range,
                             default=upper_limit.to_tokens())
    value = NU.from_tokens(value)

    if not lock_periods:
        min_locktime = STAKEHOLDER.economics.minimum_locked_periods
        default_locktime = STAKEHOLDER.economics.maximum_rewarded_periods
        max_locktime = MAX_UINT16 - STAKEHOLDER.staking_agent.get_current_period()
        lock_periods = click.prompt(PROMPT_STAKE_CREATE_LOCK_PERIODS.format(min_locktime=min_locktime,
                                                                            max_locktime=max_locktime),
                                    type=stake_duration_range,
                                    default=default_locktime)

    start_period = STAKEHOLDER.staking_agent.get_current_period() + 1
    unlock_period = start_period + lock_periods

    #
    # Review and Publish
    #

    if not force:
        confirm_large_stake(value=value, lock_periods=lock_periods)
        paint_staged_stake(emitter=emitter,
                           blockchain=blockchain,
                           stakeholder=STAKEHOLDER,
                           staking_address=staking_address,
                           stake_value=value,
                           lock_periods=lock_periods,
                           start_period=start_period,
                           unlock_period=unlock_period)

        confirm_staged_stake(staker_address=staking_address, value=value, lock_periods=lock_periods)

    # Last chance to bail
    click.confirm(CONFIRM_BROADCAST_CREATE_STAKE, abort=True)

    # Authenticate
    password = get_password(stakeholder=STAKEHOLDER,
                            blockchain=blockchain,
                            client_account=client_account,
                            hw_wallet=transacting_staker_options.hw_wallet)
    STAKEHOLDER.assimilate(password=password)

    # Consistency check to prevent the above agreement from going stale.
    last_second_current_period = STAKEHOLDER.staking_agent.get_current_period()
    if start_period != last_second_current_period + 1:
        emitter.echo(PERIOD_ADVANCED_WARNING, color='red')
        raise click.Abort

    # Execute
    receipt = STAKEHOLDER.initialize_stake(amount=value, lock_periods=lock_periods, from_unlocked=from_unlocked)
    paint_staking_confirmation(emitter=emitter, staker=STAKEHOLDER, receipt=receipt)


@stake.command()
@group_transacting_staker_options
@option_config_file
@option_force
@option_value
@option_index
@group_general_config
@option_from_unlocked
def increase(general_config: GroupGeneralConfig,
             transacting_staker_options: TransactingStakerOptions,
             config_file, force, value, index, from_unlocked):
    """Increase an existing stake."""

    # Setup
    emitter = setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    # Handle stake update and selection
    if index is not None:  # 0 is valid.
        current_stake = STAKEHOLDER.stakes[index]
    else:
        current_stake = select_stake(staker=STAKEHOLDER, emitter=emitter)

    #
    # Stage Stake
    #

    if not value:
        if from_unlocked:
            click.confirm(CONFIRM_STAKE_USE_UNLOCKED, abort=True)

        token_balance = STAKEHOLDER.calculate_staking_reward() if from_unlocked else STAKEHOLDER.token_balance
        locked_tokens = STAKEHOLDER.locked_tokens(periods=1).to_nunits()
        upper_limit = min(token_balance, NU.from_nunits(STAKEHOLDER.economics.maximum_allowed_locked - locked_tokens))

        if token_balance == 0:
            emitter.echo(INSUFFICIENT_BALANCE_TO_INCREASE, color='red')
            raise click.Abort
        if upper_limit == 0:
            emitter.echo(MAXIMUM_STAKE_REACHED, color='red')
            raise click.Abort

        stake_value_range = DecimalRange(min=0, max=upper_limit.to_tokens(), clamp=False)
        value = click.prompt(PROMPT_STAKE_INCREASE_VALUE.format(upper_limit=upper_limit),
                             type=stake_value_range)
    value = NU.from_tokens(value)

    #
    # Review and Publish
    #

    if not force:
        lock_periods = current_stake.periods_remaining - 1
        current_period = STAKEHOLDER.staking_agent.get_current_period()
        unlock_period = current_stake.final_locked_period + 1

        confirm_large_stake(value=value, lock_periods=lock_periods)
        paint_staged_stake(emitter=emitter,
                           blockchain=blockchain,
                           stakeholder=STAKEHOLDER,
                           staking_address=staking_address,
                           stake_value=value,
                           lock_periods=lock_periods,
                           start_period=current_period + 1,
                           unlock_period=unlock_period)
        click.confirm(CONFIRM_INCREASING_STAKE.format(stake_index=current_stake.index, value=value), abort=True)

    # Authenticate
    password = get_password(stakeholder=STAKEHOLDER,
                            blockchain=blockchain,
                            client_account=client_account,
                            hw_wallet=transacting_staker_options.hw_wallet)
    STAKEHOLDER.assimilate(password=password)

    # Execute
    receipt = STAKEHOLDER.increase_stake(stake=current_stake, amount=value, from_unlocked=from_unlocked)

    # Report
    emitter.echo(SUCCESSFUL_STAKE_INCREASE, color='green', verbosity=1)
    paint_receipt_summary(emitter=emitter, receipt=receipt, chain_name=blockchain.client.chain_name)
    paint_stakes(emitter=emitter, staker=STAKEHOLDER)


@stake.command()
@group_transacting_staker_options
@option_config_file
@click.option('--enable/--disable', help="Used to enable and disable re-staking", is_flag=True, default=True)
@click.option('--lock-until', help="Period to release re-staking lock", type=click.IntRange(min=0))
@option_force
@group_general_config
def restake(general_config: GroupGeneralConfig,
            transacting_staker_options: TransactingStakerOptions,
            config_file, enable, lock_until, force):
    """Manage re-staking with --enable or --disable."""

    # Setup
    emitter = setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    # Inner Exclusive Switch
    if lock_until:
        if not force:
            confirm_enable_restaking_lock(emitter, staking_address=staking_address, release_period=lock_until)

        # Authenticate and Execute
        password = get_password(stakeholder=STAKEHOLDER,
                                blockchain=blockchain,
                                client_account=client_account,
                                hw_wallet=transacting_staker_options.hw_wallet)
        STAKEHOLDER.assimilate(password=password)

        receipt = STAKEHOLDER.enable_restaking_lock(release_period=lock_until)
        emitter.echo(SUCCESSFUL_ENABLE_RESTAKE_LOCK.format(staking_address=staking_address, lock_until=lock_until),
                     color='green', verbosity=1)
    elif enable:
        if not force:
            confirm_enable_restaking(emitter, staking_address=staking_address)

        # Authenticate and Execute
        password = get_password(stakeholder=STAKEHOLDER,
                                blockchain=blockchain,
                                client_account=client_account,
                                hw_wallet=transacting_staker_options.hw_wallet)
        STAKEHOLDER.assimilate(password=password)

        receipt = STAKEHOLDER.enable_restaking()
        emitter.echo(SUCCESSFUL_ENABLE_RESTAKING.format(staking_address=staking_address), color='green', verbosity=1)
    else:
        if not force:
            click.confirm(CONFIRM_DISABLE_RESTAKING.format(staking_address=staking_address), abort=True)

        # Authenticate and Execute
        password = get_password(stakeholder=STAKEHOLDER,
                                blockchain=blockchain,
                                client_account=client_account,
                                hw_wallet=transacting_staker_options.hw_wallet)
        STAKEHOLDER.assimilate(password=password)

        receipt = STAKEHOLDER.disable_restaking()
        emitter.echo(SUCCESSFUL_DISABLE_RESTAKING.format(staking_address=staking_address), color='green', verbosity=1)

    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=blockchain.client.chain_name)


@stake.command()
@group_transacting_staker_options
@option_config_file
@click.option('--enable/--disable', help="Used to enable and disable winding down", is_flag=True, default=True)
@option_force
@group_general_config
def winddown(general_config: GroupGeneralConfig,
             transacting_staker_options: TransactingStakerOptions,
             config_file, enable, force):
    """Manage winding down with --enable or --disable."""

    # Setup
    emitter = setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    # Inner Exclusive Switch
    if enable:
        if not force:
            confirm_enable_winding_down(emitter, staking_address=staking_address)

        # Authenticate and Execute
        password = get_password(stakeholder=STAKEHOLDER,
                                blockchain=blockchain,
                                client_account=client_account,
                                hw_wallet=transacting_staker_options.hw_wallet)
        STAKEHOLDER.assimilate(password=password)

        receipt = STAKEHOLDER.enable_winding_down()
        emitter.echo(SUCCESSFUL_ENABLE_WIND_DOWN.format(staking_address=staking_address), color='green', verbosity=1)
    else:
        if not force:
            click.confirm(CONFIRM_DISABLE_WIND_DOWN.format(staking_address=staking_address), abort=True)

        # Authenticate and Execute
        password = get_password(stakeholder=STAKEHOLDER,
                                blockchain=blockchain,
                                client_account=client_account,
                                hw_wallet=transacting_staker_options.hw_wallet)
        STAKEHOLDER.assimilate(password=password)

        receipt = STAKEHOLDER.disable_winding_down()
        emitter.echo(SUCCESSFUL_DISABLE_WIND_DOWN.format(staking_address=staking_address), color='green', verbosity=1)

    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=blockchain.client.chain_name)


@stake.command()
@group_transacting_staker_options
@option_config_file
@click.option('--enable/--disable', help="Used to enable and disable taking snapshots", is_flag=True, default=True)
@option_force
@group_general_config
def snapshots(general_config: GroupGeneralConfig,
              transacting_staker_options: TransactingStakerOptions,
              config_file, enable, force):
    """Manage snapshots with --enable or --disable."""

    # Setup
    emitter = setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    # Inner Exclusive Switch
    if enable:
        if not force:
            click.confirm(CONFIRM_ENABLE_SNAPSHOTS.format(staking_address=staking_address), abort=True)

        # Authenticate and Execute
        password = get_password(stakeholder=STAKEHOLDER,
                                blockchain=blockchain,
                                client_account=client_account,
                                hw_wallet=transacting_staker_options.hw_wallet)
        STAKEHOLDER.assimilate(password=password)

        receipt = STAKEHOLDER.enable_snapshots()
        emitter.echo(SUCCESSFUL_ENABLE_SNAPSHOTS.format(staking_address=staking_address), color='green', verbosity=1)
    else:
        if not force:
            confirm_disable_snapshots(emitter, staking_address=staking_address)

        # Authenticate and Execute
        password = get_password(stakeholder=STAKEHOLDER,
                                blockchain=blockchain,
                                client_account=client_account,
                                hw_wallet=transacting_staker_options.hw_wallet)
        STAKEHOLDER.assimilate(password=password)

        receipt = STAKEHOLDER.disable_snapshots()
        emitter.echo(SUCCESSFUL_DISABLE_SNAPSHOTS.format(staking_address=staking_address), color='green', verbosity=1)

    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=blockchain.client.chain_name)


@stake.command()
@group_transacting_staker_options
@option_config_file
@option_force
@option_value
@option_lock_periods
@option_index
@group_general_config
def divide(general_config: GroupGeneralConfig,
           transacting_staker_options: TransactingStakerOptions,
           config_file, force, value, lock_periods, index):
    """Create a new stake from part of an existing one."""

    # Setup
    emitter = setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()
    economics = STAKEHOLDER.economics
    action_period = STAKEHOLDER.staking_agent.get_current_period()

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force
    )

    # Dynamic click types (Economics)
    min_locked = economics.minimum_allowed_locked
    stake_value_range = DecimalRange(min=NU.from_nunits(min_locked).to_tokens(), clamp=False)

    if index is not None:  # 0 is valid.
        current_stake = STAKEHOLDER.stakes[index]
    else:
        current_stake = select_stake(staker=STAKEHOLDER, emitter=emitter, stakes_status=Stake.Status.DIVISIBLE)

    #
    # Stage Stake
    #

    # Value
    if not value:
        min_allowed_locked = NU.from_nunits(STAKEHOLDER.economics.minimum_allowed_locked)
        max_divide_value = max(min_allowed_locked, current_stake.value - min_allowed_locked)
        prompt = PROMPT_STAKE_DIVIDE_VALUE.format(minimum=min_allowed_locked, maximum=str(max_divide_value))
        value = click.prompt(prompt, type=stake_value_range)
    value = NU(value, 'NU')

    # Duration
    if not lock_periods:
        max_extension = MAX_UINT16 - current_stake.final_locked_period
        divide_extension_range = click.IntRange(min=1, max=max_extension, clamp=False)
        extension = click.prompt(PROMPT_STAKE_EXTEND_VALUE, type=divide_extension_range)
    else:
        extension = lock_periods

    if not force:
        confirm_large_stake(lock_periods=extension, value=value)
        paint_staged_stake_division(emitter=emitter,
                                    blockchain=blockchain,
                                    stakeholder=STAKEHOLDER,
                                    original_stake=current_stake,
                                    target_value=value,
                                    extension=extension)
        click.confirm(CONFIRM_BROADCAST_STAKE_DIVIDE, abort=True)

    # Authenticate
    password = get_password(stakeholder=STAKEHOLDER,
                            blockchain=blockchain,
                            client_account=client_account,
                            hw_wallet=transacting_staker_options.hw_wallet)
    STAKEHOLDER.assimilate(password=password)

    # Consistency check to prevent the above agreement from going stale.
    last_second_current_period = STAKEHOLDER.staking_agent.get_current_period()
    if action_period != last_second_current_period:
        emitter.echo(PERIOD_ADVANCED_WARNING, color='red')
        raise click.Abort

    # Execute
    receipt = STAKEHOLDER.divide_stake(stake=current_stake, target_value=value, additional_periods=extension)
    emitter.echo(SUCCESSFUL_STAKE_DIVIDE, color='green', verbosity=1)
    paint_receipt_summary(emitter=emitter,
                          receipt=receipt,
                          chain_name=blockchain.client.chain_name)

    # Show the resulting stake list
    paint_stakes(emitter=emitter, staker=STAKEHOLDER)


@stake.command()
@group_transacting_staker_options
@option_config_file
@option_force
@option_lock_periods
@option_index
@group_general_config
def prolong(general_config: GroupGeneralConfig,
            transacting_staker_options: TransactingStakerOptions,
            config_file, force, lock_periods, index):
    """Prolong an existing stake's duration."""

    # Setup
    emitter = setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    action_period = STAKEHOLDER.staking_agent.get_current_period()
    blockchain = transacting_staker_options.get_blockchain()
    economics = STAKEHOLDER.economics

    # Handle account selection
    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    # Handle stake update and selection
    if index is not None:  # 0 is valid.
        current_stake = STAKEHOLDER.stakes[index]
    else:
        current_stake = select_stake(staker=STAKEHOLDER, emitter=emitter)

    #
    # Prolong
    #

    # Interactive
    if not lock_periods:
        max_extension = MAX_UINT16 - current_stake.final_locked_period
        # +1 because current period excluded
        min_extension = economics.minimum_locked_periods - current_stake.periods_remaining + 1
        if min_extension < 1:
            min_extension = 1
        duration_extension_range = click.IntRange(min=min_extension, max=max_extension, clamp=False)
        lock_periods = click.prompt(PROMPT_PROLONG_VALUE.format(minimum=min_extension, maximum=max_extension),
                                    type=duration_extension_range)
    if not force:
        click.confirm(CONFIRM_PROLONG.format(lock_periods=lock_periods), abort=True)

    # Authenticate
    password = get_password(stakeholder=STAKEHOLDER,
                            blockchain=blockchain,
                            client_account=client_account,
                            hw_wallet=transacting_staker_options.hw_wallet)
    STAKEHOLDER.assimilate(password=password)

    # Non-interactive: Consistency check to prevent the above agreement from going stale.
    last_second_current_period = STAKEHOLDER.staking_agent.get_current_period()
    if action_period != last_second_current_period:
        emitter.echo(PERIOD_ADVANCED_WARNING, color='red')
        raise click.Abort

    # Execute
    receipt = STAKEHOLDER.prolong_stake(stake=current_stake, additional_periods=lock_periods)

    # Report
    emitter.echo(SUCCESSFUL_STAKE_PROLONG, color='green', verbosity=1)
    paint_receipt_summary(emitter=emitter, receipt=receipt, chain_name=blockchain.client.chain_name)
    paint_stakes(emitter=emitter, staker=STAKEHOLDER)


@stake.command()
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
@click.option('--index-1', help="First index of stake to merge", type=click.INT)
@click.option('--index-2', help="Second index of stake to merge", type=click.INT)
def merge(general_config: GroupGeneralConfig,
          transacting_staker_options: TransactingStakerOptions,
          config_file, force, index_1, index_2):
    """Merge two stakes into one."""

    # Setup
    emitter = setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    action_period = STAKEHOLDER.staking_agent.get_current_period()
    blockchain = transacting_staker_options.get_blockchain()

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    # Handle stakes selection
    stake_1, stake_2 = None, None

    if index_1 is not None and index_2 is not None:
        stake_1 = STAKEHOLDER.stakes[index_1]
        stake_2 = STAKEHOLDER.stakes[index_2]
    elif index_1 is not None:  # 0 is valid.
        stake_1 = STAKEHOLDER.stakes[index_1]
    elif index_2 is not None:
        stake_1 = STAKEHOLDER.stakes[index_2]

    if stake_1 is None:
        stake_1 = select_stake(staker=STAKEHOLDER, emitter=emitter)
    if stake_2 is None:
        emitter.echo(ONLY_DISPLAYING_MERGEABLE_STAKES_NOTE.format(final_period=stake_1.final_locked_period),
                     color='yellow')
        stake_2 = select_stake(staker=STAKEHOLDER,
                               emitter=emitter,
                               filter_function=lambda s: s.index != stake_1.index and
                                                         s.final_locked_period == stake_1.final_locked_period)

    if not force:
        click.confirm(CONFIRM_MERGE.format(stake_index_1=stake_1.index, stake_index_2=stake_2.index), abort=True)

    # Authenticate
    password = get_password(stakeholder=STAKEHOLDER,
                            blockchain=blockchain,
                            client_account=client_account,
                            hw_wallet=transacting_staker_options.hw_wallet)
    STAKEHOLDER.assimilate(password=password)

    # Non-interactive: Consistency check to prevent the above agreement from going stale.
    last_second_current_period = STAKEHOLDER.staking_agent.get_current_period()
    if action_period != last_second_current_period:
        emitter.echo(PERIOD_ADVANCED_WARNING, color='red')
        raise click.Abort

    # Execute
    receipt = STAKEHOLDER.merge_stakes(stake_1=stake_1, stake_2=stake_2)

    # Report
    emitter.echo(SUCCESSFUL_STAKES_MERGE, color='green', verbosity=1)
    paint_receipt_summary(emitter=emitter, receipt=receipt, chain_name=blockchain.client.chain_name)
    paint_stakes(emitter=emitter, staker=STAKEHOLDER)


@stake.command()
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
@click.option('--index', help="Index of unused stake to remove", type=click.INT)
def remove_unused(general_config: GroupGeneralConfig,
                  transacting_staker_options: TransactingStakerOptions,
                  config_file, force, index):
    """Remove unused stake."""

    # Setup
    emitter = setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    action_period = STAKEHOLDER.staking_agent.get_current_period()
    blockchain = transacting_staker_options.get_blockchain()

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    # Handle stake update and selection
    if index is not None:  # 0 is valid.
        current_stake = STAKEHOLDER.stakes[index]
    else:
        current_stake = select_stake(staker=STAKEHOLDER, emitter=emitter, stakes_status=Stake.Status.INACTIVE)

    if not force:
        click.confirm(CONFIRM_REMOVE_SUBSTAKE.format(stake_index=current_stake.index), abort=True)

    # Authenticate
    password = get_password(stakeholder=STAKEHOLDER,
                            blockchain=blockchain,
                            client_account=client_account,
                            hw_wallet=transacting_staker_options.hw_wallet)
    STAKEHOLDER.assimilate(password=password)

    # Non-interactive: Consistency check to prevent the above agreement from going stale.
    last_second_current_period = STAKEHOLDER.staking_agent.get_current_period()
    if action_period != last_second_current_period:
        emitter.echo(PERIOD_ADVANCED_WARNING, color='red')
        raise click.Abort

    # Execute
    receipt = STAKEHOLDER.remove_unused_stake(stake=current_stake)

    # Report
    emitter.echo(SUCCESSFUL_STAKE_REMOVAL, color='green', verbosity=1)
    paint_receipt_summary(emitter=emitter, receipt=receipt, chain_name=blockchain.client.chain_name)
    paint_stakes(emitter=emitter, staker=STAKEHOLDER)


@stake.command('collect-reward')
@group_transacting_staker_options
@option_config_file
@click.option('--staking-reward/--no-staking-reward', is_flag=True, default=False)
@click.option('--policy-fee/--no-policy-fee', is_flag=True, default=False)
@click.option('--withdraw-address', help="Send fee collection to an alternate address", type=EIP55_CHECKSUM_ADDRESS)
@option_force
@group_general_config
def collect_reward(general_config: GroupGeneralConfig,
                   transacting_staker_options: TransactingStakerOptions,
                   config_file,
                   staking_reward,
                   policy_fee,
                   withdraw_address,
                   force):
    """Withdraw staking reward."""

    # Setup
    emitter = setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    if not staking_reward and not policy_fee:
        raise click.BadArgumentUsage(f"Either --staking-reward or --policy-fee must be True to collect rewards.")

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    password = None

    if staking_reward:
        # Note: Sending staking / inflation rewards to another account is not allowed.
        reward_amount = STAKEHOLDER.calculate_staking_reward()
        if reward_amount == 0:
            emitter.echo(NO_TOKENS_TO_WITHDRAW, color='red')
            raise click.Abort

        emitter.echo(message=COLLECTING_TOKEN_REWARD.format(reward_amount=reward_amount))

        withdrawing_last_portion = STAKEHOLDER.non_withdrawable_stake() == 0
        if not force and withdrawing_last_portion and STAKEHOLDER.mintable_periods() > 0:
            click.confirm(CONFIRM_COLLECTING_WITHOUT_MINTING, abort=True)

        # Authenticate and Execute
        password = get_password(stakeholder=STAKEHOLDER,
                                blockchain=blockchain,
                                client_account=client_account,
                                hw_wallet=transacting_staker_options.hw_wallet)
        STAKEHOLDER.assimilate(password=password)

        staking_receipt = STAKEHOLDER.collect_staking_reward()
        paint_receipt_summary(receipt=staking_receipt,
                              chain_name=STAKEHOLDER.wallet.blockchain.client.chain_name,
                              emitter=emitter)

    if policy_fee:
        fee_amount = Web3.fromWei(STAKEHOLDER.calculate_policy_fee(), 'ether')
        if fee_amount == 0:
            emitter.echo(NO_FEE_TO_WITHDRAW, color='red')
            raise click.Abort

        emitter.echo(message=COLLECTING_ETH_FEE.format(fee_amount=fee_amount))

        if password is None:
            # Authenticate and Execute
            password = get_password(stakeholder=STAKEHOLDER,
                                    blockchain=blockchain,
                                    client_account=client_account,
                                    hw_wallet=transacting_staker_options.hw_wallet)
            STAKEHOLDER.assimilate(password=password)

        policy_receipt = STAKEHOLDER.collect_policy_fee(collector_address=withdraw_address)
        paint_receipt_summary(receipt=policy_receipt,
                              chain_name=STAKEHOLDER.wallet.blockchain.client.chain_name,
                              emitter=emitter)


@stake.command()
@click.argument('action', type=click.Choice(['status', 'withdraw']))
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
def preallocation(general_config: GroupGeneralConfig,
                  transacting_staker_options: TransactingStakerOptions,
                  config_file, action, force):
    """Claim token rewards collected by a preallocation contract."""

    # Setup
    emitter = setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    # Unauthenticated actions: status
    if action == 'status':
        return paint_preallocation_status(emitter=emitter,
                                          token_agent=STAKEHOLDER.token_agent,
                                          preallocation_agent=STAKEHOLDER.preallocation_escrow_agent)

    # Authenticated actions: withdraw-tokens
    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    # Authenticate
    password = get_password(stakeholder=STAKEHOLDER,
                            blockchain=blockchain,
                            client_account=client_account,
                            hw_wallet=transacting_staker_options.hw_wallet)
    STAKEHOLDER.assimilate(checksum_address=client_account, password=password)

    if action == 'withdraw':
        token_balance = NU.from_nunits(STAKEHOLDER.token_agent.get_balance(staking_address))
        locked_tokens = NU.from_nunits(STAKEHOLDER.preallocation_escrow_agent.unvested_tokens)
        unlocked_tokens = token_balance - locked_tokens

        emitter.echo(message=COLLECTING_PREALLOCATION_REWARD.format(unlocked_tokens=unlocked_tokens,
                                                                    staking_address=staking_address))
        receipt = STAKEHOLDER.withdraw_preallocation_tokens(unlocked_tokens)
        paint_receipt_summary(receipt=receipt,
                              chain_name=STAKEHOLDER.wallet.blockchain.client.chain_name,
                              emitter=emitter)


@stake.command()
@group_staker_options
@option_config_file
@option_event_name
@group_general_config
def events(general_config, staker_options, config_file, event_name):
    """See blockchain events associated to a staker"""

    # Setup
    emitter = setup_emitter(general_config)
    STAKEHOLDER = staker_options.create_character(emitter, config_file)

    _client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=True)

    title = f" {STAKEHOLDER.staking_agent.contract_name} Events ".center(40, "-")
    emitter.echo(f"\n{title}\n", bold=True, color='green')
    if event_name:
        events = [STAKEHOLDER.staking_agent.contract.events[event_name]]
    else:
        raise click.BadOptionUsage(message="You must specify an event name with --event-name")
        # TODO: Doesn't work for the moment
        # event_names = STAKEHOLDER.staking_agent.events.names
        # events = [STAKEHOLDER.staking_agent.contract.events[e] for e in event_names]
        # events = [e for e in events if 'staker' in e.argument_names]

    for event in events:
        emitter.echo(f"{event.event_name}:", bold=True, color='yellow')
        entries = event.getLogs(fromBlock=0, toBlock='latest', argument_filters={'staker': staking_address})
        for event_record in entries:
            emitter.echo(f"  - {EventRecord(event_record)}")


@stake.command('set-min-rate')
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
@click.option('--min-rate', help="Minimum acceptable fee rate (in GWEI), set by staker", type=GWEI)
def set_min_rate(general_config: GroupGeneralConfig,
                 transacting_staker_options: TransactingStakerOptions,
                 config_file, force, min_rate):
    """Staker sets the minimum acceptable fee rate for their associated worker."""

    # Setup
    emitter = setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    if not min_rate:
        paint_min_rate(emitter, STAKEHOLDER)
        minimum, _default, maximum = STAKEHOLDER.policy_agent.get_fee_rate_range()
        lower_bound_in_gwei = Web3.fromWei(minimum, 'gwei')
        upper_bound_in_gwei = Web3.fromWei(maximum, 'gwei')
        min_rate = click.prompt(PROMPT_STAKER_MIN_POLICY_RATE, type=DecimalRange(min=lower_bound_in_gwei,
                                                                                 max=upper_bound_in_gwei))

    min_rate = int(Web3.toWei(Decimal(min_rate), 'gwei'))

    if not force:
        min_rate_in_gwei = Web3.fromWei(min_rate, 'gwei')
        click.confirm(CONFIRM_NEW_MIN_POLICY_RATE.format(min_rate=min_rate_in_gwei), abort=True)

    password = get_password(stakeholder=STAKEHOLDER,
                            blockchain=blockchain,
                            client_account=client_account,
                            hw_wallet=transacting_staker_options.hw_wallet)
    STAKEHOLDER.assimilate(password=password)
    receipt = STAKEHOLDER.set_min_fee_rate(min_rate=min_rate)

    # Report Success
    message = SUCCESSFUL_SET_MIN_POLICY_RATE.format(min_rate=min_rate, staking_address=staking_address)
    emitter.echo(message, color='green')
    paint_receipt_summary(emitter=emitter,
                          receipt=receipt,
                          chain_name=blockchain.client.chain_name,
                          transaction_type='set_min_rate')


@stake.command()
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
def mint(general_config: GroupGeneralConfig,
         transacting_staker_options: TransactingStakerOptions,
         config_file, force):
    """Mint last portion of reward"""

    # Setup
    emitter = setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    # Nothing to mint
    mintable_periods = STAKEHOLDER.mintable_periods()
    if mintable_periods == 0:
        emitter.echo(NO_MINTABLE_PERIODS, color='red')
        raise click.Abort

    # Still locked token
    if STAKEHOLDER.non_withdrawable_stake() > 0:
        emitter.echo(STILL_LOCKED_TOKENS, color='yellow')

    if not force:
        click.confirm(CONFIRM_MINTING.format(mintable_periods=mintable_periods), abort=True)

    # Authenticate
    password = get_password(stakeholder=STAKEHOLDER,
                            blockchain=blockchain,
                            client_account=client_account,
                            hw_wallet=transacting_staker_options.hw_wallet)
    STAKEHOLDER.assimilate(password=password)
    receipt = STAKEHOLDER.mint()
    emitter.echo(SUCCESSFUL_MINTING, color='green', verbosity=1)

    paint_receipt_summary(receipt=receipt,
                          emitter=emitter,
                          chain_name=blockchain.client.chain_name,
                          transaction_type='mint')
