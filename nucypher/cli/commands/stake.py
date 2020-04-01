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
import click
from web3 import Web3

from nucypher.blockchain.eth.actors import StakeHolder
from nucypher.blockchain.eth.constants import MAX_UINT16
from nucypher.blockchain.eth.events import EventRecord
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import IndividualAllocationRegistry
from nucypher.blockchain.eth.token import NU, StakeList
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.cli import painting, actions
from nucypher.cli.actions import (
    confirm_staged_stake,
    get_client_password,
    select_stake,
    handle_client_account_for_staking,
    confirm_enable_restaking_lock,
    confirm_enable_restaking,
    confirm_enable_winding_down,
    get_or_update_configuration, issue_stake_suggestions)
from nucypher.cli.config import group_general_config
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
    option_staking_address,
    option_signer_uri)
from nucypher.cli.painting import paint_receipt_summary
from nucypher.cli.types import (
    EIP55_CHECKSUM_ADDRESS,
    EXISTING_READABLE_FILE,
    WEI
)
from nucypher.config.characters import StakeHolderConfiguration

option_value = click.option('--value', help="Token value of stake", type=click.INT)
option_lock_periods = click.option('--lock-periods', help="Duration of stake in periods.", type=click.INT)
option_worker_address = click.option('--worker-address', help="Address to assign as an Ursula-Worker", type=EIP55_CHECKSUM_ADDRESS)


def _setup_emitter(general_config):
    # Banner
    emitter = general_config.emitter
    emitter.banner(StakeHolder.banner)

    return emitter


class StakeHolderConfigOptions:

    __option_name__ = 'config_options'

    def __init__(self, provider_uri, poa, light, registry_filepath, network, signer_uri):
        self.provider_uri = provider_uri
        self.signer_uri = signer_uri
        self.poa = poa
        self.light = light
        self.registry_filepath = registry_filepath
        self.network = network

    def create_config(self, emitter, config_file):
        try:
            return StakeHolderConfiguration.from_configuration_file(
                emitter=emitter,
                filepath=config_file,
                provider_uri=self.provider_uri,
                signer_uri=self.signer_uri,
                poa=self.poa,
                light=self.light,
                sync=False,
                domains={self.network} if self.network else None,  # TODO: #1580
                registry_filepath=self.registry_filepath)

        except FileNotFoundError:
            return actions.handle_missing_configuration_file(
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
            sync=False,
            registry_filepath=self.registry_filepath,
            domains={self.network}  # TODO: #1580
        )

    def get_updates(self) -> dict:
        payload = dict(provider_uri=self.provider_uri,
                       signer_uri=self.signer_uri,
                       poa=self.poa,
                       light=self.light,
                       registry_filepath=self.registry_filepath,
                       domains={self.network} if self.network else None)  # TODO: #1580
        # Depends on defaults being set on Configuration classes, filtrates None values
        updates = {k: v for k, v in payload.items() if v is not None}
        return updates


group_config_options = group_options(
    StakeHolderConfigOptions,
    provider_uri=option_provider_uri(),
    poa=option_poa,
    light=option_light,
    registry_filepath=option_registry_filepath,
    network=option_network,
    signer_uri=option_signer_uri
)


class StakerOptions:

    __option_name__ = 'staker_options'

    def __init__(self, config_options, staking_address):
        self.config_options = config_options
        self.staking_address = staking_address

    def create_character(self, emitter, config_file, initial_address=None, *args, **kwargs):
        stakeholder_config = self.config_options.create_config(emitter, config_file)

        if initial_address is None:
            initial_address = self.staking_address

        return stakeholder_config.produce(
            initial_address=initial_address,
            *args, **kwargs
        )

    def get_blockchain(self):
        return BlockchainInterfaceFactory.get_interface(provider_uri=self.config_options.provider_uri)  # Eager connection


group_staker_options = group_options(
    StakerOptions,
    config_options=group_config_options,
    staking_address=option_staking_address,
)


class TransactingStakerOptions:

    __option_name__ = 'transacting_staker_options'

    def __init__(self, staker_options, hw_wallet, beneficiary_address, allocation_filepath):
        self.staker_options = staker_options
        self.hw_wallet = hw_wallet
        self.beneficiary_address = beneficiary_address
        self.allocation_filepath = allocation_filepath

    def create_character(self, emitter, config_file):

        opts = self.staker_options
        stakeholder_config = opts.config_options.create_config(emitter, config_file)

        # Now let's check whether we're dealing here with a regular staker or a preallocation staker
        is_preallocation_staker = (self.beneficiary_address and opts.staking_address) or self.allocation_filepath

        if is_preallocation_staker:
            network = opts.config_options.network or list(stakeholder_config.domains)[0]  # TODO: 1580 - ugly network/domains mapping
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
        return self.staker_options.get_blockchain()

    def get_password(self, blockchain, client_account):
        password = None
        if not self.hw_wallet and not blockchain.client.is_local:
            password = get_client_password(checksum_address=client_account)
        return password


group_transacting_staker_options = group_options(
    TransactingStakerOptions,
    staker_options=group_staker_options,
    hw_wallet=option_hw_wallet,
    beneficiary_address=click.option('--beneficiary-address', help="Address of a pre-allocation beneficiary", type=EIP55_CHECKSUM_ADDRESS),
    allocation_filepath=click.option('--allocation-filepath', help="Path to individual allocation file", type=EXISTING_READABLE_FILE),
)


@click.group()
def stake():
    """
    Manage stakes and other staker-related operations.
    """
    pass


@stake.command(name='init-stakeholder')
@option_config_root
@option_force
@group_config_options
@group_general_config
@option_network
def init_stakeholder(general_config, config_root, force, config_options):
    """
    Create a new stakeholder configuration.
    """
    emitter = _setup_emitter(general_config)
    new_stakeholder = config_options.generate_config(config_root)
    filepath = new_stakeholder.to_configuration_file(override=force)
    emitter.echo(f"Wrote new stakeholder configuration to {filepath}", color='green')


@stake.command()
@option_config_file
@group_general_config
@group_config_options
def config(general_config, config_file, config_options):
    """
    View and optionally update existing StakeHolder's configuration.
    """
    emitter = _setup_emitter(general_config)
    configuration_file_location = config_file or StakeHolderConfiguration.default_filepath()
    emitter.echo(f"StakeHolder Configuration {configuration_file_location} \n {'='*55}")
    return get_or_update_configuration(emitter=emitter,
                                       config_class=StakeHolderConfiguration,
                                       filepath=configuration_file_location,
                                       config_options=config_options)


@stake.command('list')
@group_staker_options
@option_config_file
@click.option('--all', help="List all stakes, including inactive", is_flag=True)
@group_general_config
def list_stakes(general_config, staker_options, config_file, all):
    """
    List active stakes for current stakeholder.
    """
    emitter = _setup_emitter(general_config)
    STAKEHOLDER = staker_options.create_character(emitter, config_file)
    painting.paint_stakes(emitter=emitter, stakeholder=STAKEHOLDER, paint_inactive=all)


@stake.command()
@group_staker_options
@option_config_file
@group_general_config
def accounts(general_config, staker_options, config_file):
    """
    Show ETH and NU balances for stakeholder's accounts.
    """
    emitter = _setup_emitter(general_config)
    STAKEHOLDER = staker_options.create_character(emitter, config_file)
    painting.paint_accounts(emitter=emitter, balances=STAKEHOLDER.wallet.balances, registry=STAKEHOLDER.registry)


@stake.command('set-worker')
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
@option_worker_address
def set_worker(general_config, transacting_staker_options, config_file, force, worker_address):
    """
    Bond a worker to a staker.
    """
    emitter = _setup_emitter(general_config)

    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    economics = STAKEHOLDER.economics

    client_account, staking_address = handle_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    if not worker_address:
        worker_address = click.prompt("Enter worker address", type=EIP55_CHECKSUM_ADDRESS)

    if (worker_address == staking_address) and not force:
        click.confirm("The worker address provided is the same as the staking account.  "
                      "It is *highly recommended* to use a different accounts for staker and worker roles.\n"
                      "Continue?", abort=True)

    # TODO: Check preconditions (e.g., minWorkerPeriods, already in use, etc)

    password = transacting_staker_options.get_password(blockchain, client_account)

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

    STAKEHOLDER.assimilate(checksum_address=client_account, password=password)
    receipt = STAKEHOLDER.set_worker(worker_address=worker_address)

    # Report Success
    emitter.echo(f"\nWorker {worker_address} successfully bonded to staker {staking_address}", color='green')
    paint_receipt_summary(emitter=emitter,
                          receipt=receipt,
                          chain_name=blockchain.client.chain_name,
                          transaction_type='set_worker')
    emitter.echo(f"Bonded at period #{current_period} ({bonded_date})", color='green')
    emitter.echo(f"This worker can be replaced or detached after period "
                 f"#{release_period} ({release_date})", color='green')


@stake.command('detach-worker')
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
def detach_worker(general_config, transacting_staker_options, config_file, force):
    """
    Detach worker currently bonded to a staker.
    """
    emitter = _setup_emitter(general_config)

    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    economics = STAKEHOLDER.economics

    client_account, staking_address = handle_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    # TODO: Check preconditions (e.g., minWorkerPeriods)

    worker_address = STAKEHOLDER.staking_agent.get_worker_from_staker(staking_address)

    password = transacting_staker_options.get_password(blockchain, client_account)

    STAKEHOLDER.assimilate(checksum_address=client_account, password=password)
    receipt = STAKEHOLDER.detach_worker()

    # TODO: Double-check dates
    current_period = STAKEHOLDER.staking_agent.get_current_period()
    bonded_date = datetime_at_period(period=current_period, seconds_per_period=economics.seconds_per_period)

    emitter.echo(f"Successfully detached worker {worker_address} from staker {staking_address}", color='green')
    paint_receipt_summary(emitter=emitter,
                          receipt=receipt,
                          chain_name=blockchain.client.chain_name,
                          transaction_type='detach_worker')
    emitter.echo(f"Detached at period #{current_period} ({bonded_date})", color='green')


@stake.command()
@group_transacting_staker_options
@option_config_file
@option_force
@option_value
@option_lock_periods
@group_general_config
def create(general_config, transacting_staker_options, config_file, force, value, lock_periods):
    """
    Initialize a new stake.
    """
    emitter = _setup_emitter(general_config)

    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    economics = STAKEHOLDER.economics

    client_account, staking_address = handle_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    # Dynamic click types (Economics)
    min_locked = economics.minimum_allowed_locked
    stake_value_range = click.FloatRange(min=NU.from_nunits(min_locked).to_tokens(), clamp=False)
    stake_duration_range = click.IntRange(min=economics.minimum_locked_periods, clamp=False)

    #
    # Stage Stake
    #

    if not value:
        token_balance = NU.from_nunits(STAKEHOLDER.token_agent.get_balance(staking_address))
        lower_limit = NU.from_nunits(STAKEHOLDER.economics.minimum_allowed_locked)
        upper_limit = min(token_balance, NU.from_nunits(STAKEHOLDER.economics.maximum_allowed_locked))
        value = click.prompt(f"Enter stake value in NU "
                             f"({lower_limit} - {upper_limit})",
                             type=stake_value_range,
                             default=upper_limit.to_tokens())
    value = NU.from_tokens(value)

    if not lock_periods:
        min_locktime = STAKEHOLDER.economics.minimum_locked_periods
        default_locktime = STAKEHOLDER.economics.maximum_rewarded_periods
        max_locktime = MAX_UINT16 - STAKEHOLDER.staking_agent.get_current_period()
        prompt = f"Enter stake duration ({min_locktime} - {max_locktime})"
        lock_periods = click.prompt(prompt, type=stake_duration_range, default=default_locktime)

    start_period = STAKEHOLDER.staking_agent.get_current_period() + 1
    unlock_period = start_period + lock_periods

    #
    # Review and Publish
    #

    if not force:
        issue_stake_suggestions(value=value, lock_periods=lock_periods)
        painting.paint_staged_stake(emitter=emitter,
                                    stakeholder=STAKEHOLDER,
                                    staking_address=staking_address,
                                    stake_value=value,
                                    lock_periods=lock_periods,
                                    start_period=start_period,
                                    unlock_period=unlock_period)

        confirm_staged_stake(staker_address=staking_address, value=value, lock_periods=lock_periods)

    # Last chance to bail
    click.confirm("Publish staged stake to the blockchain?", abort=True)

    # Authenticate
    password = transacting_staker_options.get_password(blockchain, client_account)

    # Consistency check to prevent the above agreement from going stale.
    last_second_current_period = STAKEHOLDER.staking_agent.get_current_period()
    if start_period != last_second_current_period + 1:
        emitter.echo("Current period advanced before stake was broadcasted. Please try again.",
                     color='red')
        raise click.Abort

    # Authenticate and Execute
    STAKEHOLDER.assimilate(checksum_address=client_account, password=password)

    new_stake = STAKEHOLDER.initialize_stake(amount=value, lock_periods=lock_periods)

    painting.paint_staking_confirmation(emitter=emitter, staker=STAKEHOLDER, new_stake=new_stake)


@stake.command()
@group_transacting_staker_options
@option_config_file
@click.option('--enable/--disable', help="Used to enable and disable re-staking", is_flag=True, default=True)
@click.option('--lock-until', help="Period to release re-staking lock", type=click.IntRange(min=0))
@option_force
@group_general_config
def restake(general_config, transacting_staker_options, config_file, enable, lock_until, force):
    """
    Manage re-staking with --enable or --disable.
    """
    emitter = _setup_emitter(general_config)

    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    client_account, staking_address = handle_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    # Authenticate
    password = transacting_staker_options.get_password(blockchain, client_account)

    STAKEHOLDER.assimilate(checksum_address=client_account, password=password)

    # Inner Exclusive Switch
    if lock_until:
        if not force:
            confirm_enable_restaking_lock(emitter, staking_address=staking_address, release_period=lock_until)
        receipt = STAKEHOLDER.enable_restaking_lock(release_period=lock_until)
        emitter.echo(f'Successfully enabled re-staking lock for {staking_address} until {lock_until}',
                     color='green', verbosity=1)
    elif enable:
        if not force:
            confirm_enable_restaking(emitter, staking_address=staking_address)
        receipt = STAKEHOLDER.enable_restaking()
        emitter.echo(f'Successfully enabled re-staking for {staking_address}', color='green', verbosity=1)
    else:
        if not force:
            click.confirm(f"Confirm disable re-staking for staker {staking_address}?", abort=True)
        receipt = STAKEHOLDER.disable_restaking()
        emitter.echo(f'Successfully disabled re-staking for {staking_address}', color='green', verbosity=1)

    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=blockchain.client.chain_name)


@stake.command()
@group_transacting_staker_options
@option_config_file
@click.option('--enable/--disable', help="Used to enable and disable winding down", is_flag=True, default=True)
@click.option('--lock-until', help="Period to release re-staking lock", type=click.IntRange(min=0))
@option_force
@group_general_config
def winddown(general_config, transacting_staker_options, config_file, enable, lock_until, force):
    """
    Manage winding down with --enable or --disable.
    """

    emitter = _setup_emitter(general_config)

    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    client_account, staking_address = handle_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    # Authenticate
    password = transacting_staker_options.get_password(blockchain, client_account)

    STAKEHOLDER.assimilate(checksum_address=client_account, password=password)

    # Inner Exclusive Switch
    if enable:
        if not force:
            confirm_enable_winding_down(emitter, staking_address=staking_address)
        receipt = STAKEHOLDER.enable_winding_down()
        emitter.echo(f'Successfully enabled winding down for {staking_address}', color='green', verbosity=1)
    else:
        if not force:
            click.confirm(f"Confirm disable winding down for staker {staking_address}?", abort=True)
        receipt = STAKEHOLDER.disable_winding_down()
        emitter.echo(f'Successfully disabled winding down for {staking_address}', color='green', verbosity=1)

    paint_receipt_summary(receipt=receipt, emitter=emitter, chain_name=blockchain.client.chain_name)


@stake.command()
@group_transacting_staker_options
@option_config_file
@option_force
@option_value
@option_lock_periods
@click.option('--index', help="A specific stake index to resume", type=click.INT)
@group_general_config
def divide(general_config, transacting_staker_options, config_file, force, value, lock_periods, index):
    """
    Create a new stake from part of an existing one.
    """

    # Setup
    emitter = _setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()
    economics = STAKEHOLDER.economics
    action_period = STAKEHOLDER.staking_agent.get_current_period()

    client_account, staking_address = handle_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force
    )

    # Dynamic click types (Economics)
    min_locked = economics.minimum_allowed_locked
    stake_value_range = click.FloatRange(min=NU.from_nunits(min_locked).to_tokens(), clamp=False)

    if transacting_staker_options.staker_options.staking_address and index is not None:  # 0 is valid.
        STAKEHOLDER.stakes = StakeList(registry=STAKEHOLDER.registry,
                                       checksum_address=transacting_staker_options.staker_options.staking_address)
        STAKEHOLDER.stakes.refresh()
        current_stake = STAKEHOLDER.stakes[index]
    else:
        current_stake = select_stake(stakeholder=STAKEHOLDER,
                                     emitter=emitter,
                                     divisible=True,
                                     staker_address=client_account)

    #
    # Stage Stake
    #

    # Value
    if not value:
        min_allowed_locked = NU.from_nunits(STAKEHOLDER.economics.minimum_allowed_locked)
        max_divide_value = max(min_allowed_locked, current_stake.value - min_allowed_locked)
        value = click.prompt(f"Enter target value ({min_allowed_locked} - {str(max_divide_value)})", type=stake_value_range)
    value = NU(value, 'NU')

    # Duration
    if not lock_periods:
        max_extension = MAX_UINT16 - current_stake.final_locked_period
        divide_extension_range = click.IntRange(min=1, max=max_extension, clamp=False)
        extension = click.prompt(f"Enter number of periods to extend",
                                 type=divide_extension_range)
    else:
        extension = lock_periods

    if not force:
        issue_stake_suggestions(lock_periods=extension, value=value)
        painting.paint_staged_stake_division(emitter=emitter,
                                             stakeholder=STAKEHOLDER,
                                             original_stake=current_stake,
                                             target_value=value,
                                             extension=extension)
        click.confirm("Publish stake division to the blockchain?", abort=True)

    # Authenticate
    password = transacting_staker_options.get_password(blockchain, client_account)

    # Consistency check to prevent the above agreement from going stale.
    last_second_current_period = STAKEHOLDER.staking_agent.get_current_period()
    if action_period != last_second_current_period:
        emitter.echo("Current period advanced before stake division was broadcasted. Please try again.", red='red')
        raise click.Abort

    # Execute
    STAKEHOLDER.assimilate(checksum_address=current_stake.staker_address, password=password)
    modified_stake, new_stake = STAKEHOLDER.divide_stake(stake_index=current_stake.index,
                                                         target_value=value,
                                                         additional_periods=extension)
    emitter.echo('Successfully divided stake', color='green', verbosity=1)
    paint_receipt_summary(emitter=emitter,
                          receipt=new_stake.receipt,
                          chain_name=blockchain.client.chain_name)

    # Show the resulting stake list
    painting.paint_stakes(emitter=emitter, stakeholder=STAKEHOLDER)


@stake.command()
@group_transacting_staker_options
@option_config_file
@option_force
@option_lock_periods
@click.option('--index', help="The staker-specific stake index to prolong", type=click.INT)
@group_general_config
def prolong(general_config, transacting_staker_options, config_file, force, lock_periods, index):
    """Prolong an existing stake's duration."""

    # Setup
    emitter = _setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    action_period = STAKEHOLDER.staking_agent.get_current_period()
    blockchain = transacting_staker_options.get_blockchain()
    economics = STAKEHOLDER.economics

    # Handle account selection
    client_account, staking_address = handle_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    # Handle stake update and selection
    if transacting_staker_options.staker_options.staking_address and index is not None:  # 0 is valid.
        STAKEHOLDER.stakes = StakeList(registry=STAKEHOLDER.registry,
                                       checksum_address=transacting_staker_options.staker_options.staking_address)
        STAKEHOLDER.stakes.refresh()
        current_stake = STAKEHOLDER.stakes[index]
    else:
        current_stake = select_stake(stakeholder=STAKEHOLDER, emitter=emitter)

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
        lock_periods = click.prompt(f"Enter number of periods to extend ({min_extension}-{max_extension})",
                                    type=duration_extension_range)
    if not force:
        click.confirm(f"Publish stake extension of {lock_periods} period(s) to the blockchain?", abort=True)
    password = transacting_staker_options.get_password(blockchain, client_account)

    # Non-interactive: Consistency check to prevent the above agreement from going stale.
    last_second_current_period = STAKEHOLDER.staking_agent.get_current_period()
    if action_period != last_second_current_period:
        emitter.echo("Current period advanced before transaction was broadcasted. Please try again.", red='red')
        raise click.Abort

    # Authenticate and Execute
    STAKEHOLDER.assimilate(checksum_address=current_stake.staker_address, password=password)
    receipt = STAKEHOLDER.prolong_stake(stake_index=current_stake.index, additional_periods=lock_periods)

    # Report
    emitter.echo('Successfully Prolonged Stake', color='green', verbosity=1)
    paint_receipt_summary(emitter=emitter, receipt=receipt, chain_name=blockchain.client.chain_name)
    painting.paint_stakes(emitter=emitter, stakeholder=STAKEHOLDER)
    return  # Exit


@stake.command('collect-reward')
@group_transacting_staker_options
@option_config_file
@click.option('--staking-reward/--no-staking-reward', is_flag=True, default=False)
@click.option('--policy-reward/--no-policy-reward', is_flag=True, default=False)
@click.option('--withdraw-address', help="Send reward collection to an alternate address", type=EIP55_CHECKSUM_ADDRESS)
@option_force
@group_general_config
def collect_reward(general_config, transacting_staker_options, config_file,
                   staking_reward, policy_reward, withdraw_address, force):
    """
    Withdraw staking reward.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    if not staking_reward and not policy_reward:
        raise click.BadArgumentUsage(f"Either --staking-reward or --policy-reward must be True to collect rewards.")

    client_account, staking_address = handle_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    password = transacting_staker_options.get_password(blockchain, client_account)

    STAKEHOLDER.assimilate(checksum_address=client_account, password=password)
    if staking_reward:
        # Note: Sending staking / inflation rewards to another account is not allowed.
        reward_amount = NU.from_nunits(STAKEHOLDER.calculate_staking_reward())
        emitter.echo(message=f'Collecting {reward_amount} from staking rewards...')
        staking_receipt = STAKEHOLDER.collect_staking_reward()
        paint_receipt_summary(receipt=staking_receipt,
                              chain_name=STAKEHOLDER.wallet.blockchain.client.chain_name,
                              emitter=emitter)

    if policy_reward:
        reward_amount = Web3.fromWei(STAKEHOLDER.calculate_policy_reward(), 'ether')
        emitter.echo(message=f'Collecting {reward_amount} ETH from policy rewards...')
        policy_receipt = STAKEHOLDER.collect_policy_reward(collector_address=withdraw_address)
        paint_receipt_summary(receipt=policy_receipt,
                              chain_name=STAKEHOLDER.wallet.blockchain.client.chain_name,
                              emitter=emitter)


@stake.command()
@click.argument('action', type=click.Choice(['status', 'withdraw']))
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
def preallocation(general_config, transacting_staker_options, config_file, action, force):
    """
    Claim token rewards collected by a preallocation contract.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    # Unauthenticated actions: status

    if action == 'status':
        painting.paint_preallocation_status(emitter=emitter,
                                   token_agent=STAKEHOLDER.token_agent,
                                   preallocation_agent=STAKEHOLDER.preallocation_escrow_agent)
        return

    # Authenticated actions: withdraw-tokens

    client_account, staking_address = handle_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    password = transacting_staker_options.get_password(blockchain, client_account)

    STAKEHOLDER.assimilate(checksum_address=client_account, password=password)
    if action == 'withdraw':
        token_balance = NU.from_nunits(STAKEHOLDER.token_agent.get_balance(staking_address))
        locked_tokens = NU.from_nunits(STAKEHOLDER.preallocation_escrow_agent.unvested_tokens)
        unlocked_tokens = token_balance - locked_tokens

        emitter.echo(message=f'Collecting {unlocked_tokens} from PreallocationEscrow contract {staking_address}...')
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
    """
    See blockchain events associated to a staker
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    STAKEHOLDER = staker_options.create_character(emitter, config_file)
    blockchain = staker_options.get_blockchain()

    _client_account, staking_address = handle_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=True)

    title = f" {STAKEHOLDER.staking_agent.registry_contract_name} Events ".center(40, "-")
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
        event_filter = event.createFilter(fromBlock=0, toBlock='latest', argument_filters={'staker': staking_address})
        entries = event_filter.get_all_entries()
        for event_record in entries:
            emitter.echo(f"  - {EventRecord(event_record)}")


@stake.command('set-min-rate')
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
@click.option('--min-rate', help="Minimum acceptable reward rate", type=WEI)
def set_min_rate(general_config, transacting_staker_options, config_file, force, min_rate):
    """
    Set minimum acceptable value for the reward rate.
    """
    emitter = _setup_emitter(general_config)

    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    client_account, staking_address = handle_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address,
        individual_allocation=STAKEHOLDER.individual_allocation,
        force=force)

    if not min_rate:
        painting.paint_min_rate(emitter, STAKEHOLDER.registry, STAKEHOLDER.policy_agent, staking_address)
        # TODO check range
        min_rate = click.prompt("Enter new value for min reward rate within range", type=WEI)

    password = transacting_staker_options.get_password(blockchain, client_account)

    if not force:
        click.confirm(f"Commit new value {min_rate} for "
                      f"minimum acceptable reward rate?", abort=True)

    STAKEHOLDER.assimilate(checksum_address=client_account, password=password)
    receipt = STAKEHOLDER.set_min_reward_rate(min_rate=min_rate)

    # Report Success
    emitter.echo(f"\nMinimum reward rate {min_rate} successfully set by staker {staking_address}", color='green')
    paint_receipt_summary(emitter=emitter,
                          receipt=receipt,
                          chain_name=blockchain.client.chain_name,
                          transaction_type='set_min_rate')
