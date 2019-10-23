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
import functools

import click
from web3 import Web3

from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import IndividualAllocationRegistry
from nucypher.blockchain.eth.token import NU, StakeList
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.blockchain.eth.actors import StakeHolder
from nucypher.cli import painting, actions
from nucypher.cli.actions import (
    confirm_staged_stake,
    get_client_password,
    select_stake,
    handle_client_account_for_staking,
    confirm_enable_restaking_lock,
    confirm_enable_restaking
)
from nucypher.cli.common_options import (
    group_options,
    option_config_file,
    option_config_root,
    option_force,
    option_hw_wallet,
    option_light,
    option_poa,
    option_provider_uri,
    option_registry_filepath,
    option_staking_address,
    )
from nucypher.cli.config import group_general_config
from nucypher.cli.painting import paint_receipt_summary
from nucypher.cli.types import (
    EIP55_CHECKSUM_ADDRESS,
    EXISTING_READABLE_FILE
)
from nucypher.config.characters import StakeHolderConfiguration


option_value = click.option('--value', help="Token value of stake", type=click.INT)
option_lock_periods = click.option('--lock-periods', help="Duration of stake in periods.", type=click.INT)


group_admin = group_options(
    'admin',
    poa=option_poa,
    light=option_light,
    registry_filepath=option_registry_filepath,
    )


group_api = group_options(
    'api',
    admin=group_admin,
    config_file=option_config_file,
    provider_uri=option_provider_uri(),
    staking_address=option_staking_address,
    )


group_stake = group_options(
    'stake_',
    api=group_api,
    hw_wallet=option_hw_wallet,
    beneficiary_address=click.option('--beneficiary-address', help="Address of a pre-allocation beneficiary", type=EIP55_CHECKSUM_ADDRESS),
    allocation_filepath=click.option('--allocation-filepath', help="Path to individual allocation file", type=EXISTING_READABLE_FILE),
    )


group_worker = group_options(
    'worker',
    stake_=group_stake,
    worker_address=click.option('--worker-address', help="Address to assign as an Ursula-Worker", type=EIP55_CHECKSUM_ADDRESS),
    )


@click.group()
def stake():
    """
    Manage stakes and other staker-related operations.
    """
    pass


@stake.command(name='init-stakeholder')
@option_provider_uri(required=True)
@option_config_root
@option_force
@group_admin
@group_general_config
def init_stakeholder(general_config,

                     # Other (required)
                     provider_uri,

                     # Other
                     config_root, force,

                     # Admin Options
                     admin
                     ):
    """
    Create a new stakeholder configuration.
    """

    emitter = _setup_emitter(general_config)
    new_stakeholder = StakeHolderConfiguration.generate(config_root=config_root,
                                                        provider_uri=provider_uri,
                                                        poa=admin.poa,
                                                        light=admin.light,
                                                        sync=False,
                                                        registry_filepath=admin.registry_filepath)

    filepath = new_stakeholder.to_configuration_file(override=force)
    emitter.echo(f"Wrote new stakeholder configuration to {filepath}", color='green')


@stake.command()
@group_api
@click.option('--all', help="List all stakes, including inactive", is_flag=True)
@group_general_config
def list(general_config,

         # API Options
         api,

         all
         ):
    """
    List active stakes for current stakeholder.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    STAKEHOLDER, blockchain = _create_stakeholder(
        api.config_file, api.provider_uri, api.admin.poa, api.admin.light, api.admin.registry_filepath, api.staking_address,
        beneficiary_address=None, allocation_filepath=None)
    #############

    painting.paint_stakes(emitter=emitter, stakes=STAKEHOLDER.all_stakes, paint_inactive=all)


@stake.command()
@group_api
@group_general_config
def accounts(general_config,

             # API Options
             api
             ):
    """
    Show ETH and NU balances for stakeholder's accounts.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    STAKEHOLDER, blockchain = _create_stakeholder(
        api.config_file, api.provider_uri, api.admin.poa, api.admin.light, api.admin.registry_filepath, api.staking_address,
        beneficiary_address=None, allocation_filepath=None)
    #############

    painting.paint_accounts(emitter=emitter, balances=STAKEHOLDER.wallet.balances)


@stake.command('set-worker')
@group_worker
@option_force
@group_general_config
def set_worker(general_config,

               # Worker Options
               worker,

               force
               ):
    """
    Bond a worker to a staker.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    api = worker.stake_.api
    STAKEHOLDER, blockchain = _create_stakeholder(
        api.config_file, api.provider_uri, api.admin.poa, api.admin.light, api.admin.registry_filepath, api.staking_address,
        beneficiary_address=worker.stake_.beneficiary_address,
        allocation_filepath=worker.stake_.allocation_filepath)

    #############

    economics = STAKEHOLDER.economics

    client_account, staking_address = handle_client_account_for_staking(emitter=emitter,
                                                                        stakeholder=STAKEHOLDER,
                                                                        staking_address=api.staking_address,
                                                                        individual_allocation=STAKEHOLDER.individual_allocation,
                                                                        force=force)

    worker_address = worker.worker_address
    if not worker_address:
        worker_address = click.prompt("Enter worker address", type=EIP55_CHECKSUM_ADDRESS)

    # TODO: Check preconditions (e.g., minWorkerPeriods, already in use, etc)

    password = None
    if not worker.stake_.hw_wallet and not blockchain.client.is_local:
        password = get_client_password(checksum_address=client_account)

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
@group_worker
@option_force
@group_general_config
def detach_worker(general_config,

                  # Worker Options
                  worker,

                  force
                  ):
    """
    Detach worker currently bonded to a staker.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    api = worker.stake_.api
    STAKEHOLDER, blockchain = _create_stakeholder(
        api.config_file, api.provider_uri, api.admin.poa, api.admin.light, api.admin.registry_filepath, api.staking_address,
        beneficiary_address=worker.stake_.beneficiary_address,
        allocation_filepath=worker.stake_.allocation_filepath)
    #############

    economics = STAKEHOLDER.economics

    client_account, staking_address = handle_client_account_for_staking(emitter=emitter,
                                                                        stakeholder=STAKEHOLDER,
                                                                        staking_address=api.staking_address,
                                                                        individual_allocation=STAKEHOLDER.individual_allocation,
                                                                        force=force)

    # TODO: then why even have it in the option list?
    if worker.worker_address:
        raise click.BadOptionUsage(message="detach-worker cannot be used together with --worker-address",
                                   option_name='--worker-address')

    # TODO: Check preconditions (e.g., minWorkerPeriods)

    worker_address = STAKEHOLDER.staking_agent.get_worker_from_staker(staking_address)

    password = None
    if not worker.stake_.hw_wallet and not blockchain.client.is_local:
        password = get_client_password(checksum_address=client_account)

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
@group_stake
@option_force
@option_value
@option_lock_periods
@group_general_config
def create(general_config,

           # Stake Options
           stake_,

           # Other
           force, value, lock_periods):
    """
    Initialize a new stake.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    api = stake_.api
    STAKEHOLDER, blockchain = _create_stakeholder(
        api.config_file, api.provider_uri, api.admin.poa, api.admin.light, api.admin.registry_filepath, api.staking_address,
        beneficiary_address=stake_.beneficiary_address,
        allocation_filepath=stake_.allocation_filepath)
    #############

    economics = STAKEHOLDER.economics

    client_account, staking_address = handle_client_account_for_staking(emitter=emitter,
                                                                        stakeholder=STAKEHOLDER,
                                                                        staking_address=api.staking_address,
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
        max_locktime = STAKEHOLDER.economics.maximum_rewarded_periods
        prompt = f"Enter stake duration ({min_locktime} - {max_locktime})"
        lock_periods = click.prompt(prompt, type=stake_duration_range, default=max_locktime)

    start_period = STAKEHOLDER.staking_agent.get_current_period() + 1
    unlock_period = start_period + lock_periods

    #
    # ReviewPub
    #

    if not force:
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
    password = None
    if not stake_.hw_wallet and not blockchain.client.is_local:
        password = get_client_password(checksum_address=client_account)

    # Consistency check to prevent the above agreement from going stale.
    last_second_current_period = STAKEHOLDER.staking_agent.get_current_period()
    if start_period != last_second_current_period + 1:
        emitter.echo("Current period advanced before stake was broadcasted. Please try again.",
                     color='red')
        raise click.Abort

    # Authenticate and Execute
    STAKEHOLDER.assimilate(checksum_address=client_account, password=password)

    emitter.echo("Broadcasting stake...", color='yellow')
    new_stake = STAKEHOLDER.initialize_stake(amount=value, lock_periods=lock_periods)

    painting.paint_staking_confirmation(emitter=emitter, staker=STAKEHOLDER, new_stake=new_stake)


@stake.command()
@group_stake
@click.option('--enable/--disable', help="Used to enable and disable re-staking", is_flag=True, default=True)
@click.option('--lock-until', help="Period to release re-staking lock", type=click.IntRange(min=0))
@option_force
@group_general_config
def restake(general_config,

            # Stake Options
            stake_,

            # Other
            enable, lock_until, force):
    """
    Manage re-staking with --enable or --disable.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    api = stake_.api
    STAKEHOLDER, blockchain = _create_stakeholder(
        api.config_file, api.provider_uri, api.admin.poa, api.admin.light, api.admin.registry_filepath, api.staking_address,
        beneficiary_address=stake_.beneficiary_address,
        allocation_filepath=stake_.allocation_filepath)

    #############

    client_account, staking_address = handle_client_account_for_staking(emitter=emitter,
                                                                        stakeholder=STAKEHOLDER,
                                                                        staking_address=api.staking_address,
                                                                        individual_allocation=STAKEHOLDER.individual_allocation,
                                                                        force=force)

    # Authenticate
    password = None
    if not stake_.hw_wallet and not blockchain.client.is_local:
        password = get_client_password(checksum_address=client_account)
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
@group_stake
@option_force
@option_value
@option_lock_periods
@click.option('--index', help="A specific stake index to resume", type=click.INT)
@group_general_config
def divide(general_config,

           # Stake Options
           stake_,

           # Other
           force, value, lock_periods, index):
    """
    Create a new stake from part of an existing one.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    api = stake_.api
    STAKEHOLDER, blockchain = _create_stakeholder(
        api.config_file, api.provider_uri, api.admin.poa, api.admin.light, api.admin.registry_filepath, api.staking_address,
        beneficiary_address=stake_.beneficiary_address,
        allocation_filepath=stake_.allocation_filepath)
    #############

    client_account, staking_address = handle_client_account_for_staking(emitter=emitter,
                                                                        stakeholder=STAKEHOLDER,
                                                                        staking_address=api.staking_address,
                                                                        individual_allocation=STAKEHOLDER.individual_allocation,
                                                                        force=force)

    economics = STAKEHOLDER.economics

    # Dynamic click types (Economics)
    min_locked = economics.minimum_allowed_locked
    stake_value_range = click.FloatRange(min=NU.from_nunits(min_locked).to_tokens(), clamp=False)
    stake_extension_range = click.IntRange(min=1, max=economics.maximum_allowed_locked, clamp=False)

    if api.staking_address and index is not None:  # 0 is valid.
        STAKEHOLDER.stakes = StakeList(registry=STAKEHOLDER.registry, checksum_address=api.staking_address)
        STAKEHOLDER.stakes.refresh()
        current_stake = STAKEHOLDER.stakes[index]
    else:
        current_stake = select_stake(stakeholder=STAKEHOLDER, emitter=emitter, divisible=True)

    #
    # Stage Stake
    #

    # Value
    if not value:
        min_allowed_locked = NU.from_nunits(STAKEHOLDER.economics.minimum_allowed_locked)
        max_divide_value = max(min_allowed_locked, current_stake.value - min_allowed_locked)
        value = click.prompt(f"Enter target value ({min_allowed_locked} - {str(max_divide_value)})",
                             type=stake_value_range)
    value = NU(value, 'NU')

    action_period = STAKEHOLDER.staking_agent.get_current_period()

    # Duration
    if not lock_periods:
        extension = click.prompt("Enter number of periods to extend", type=stake_extension_range)
    else:
        extension = lock_periods

    if not force:
        painting.paint_staged_stake_division(emitter=emitter,
                                             stakeholder=STAKEHOLDER,
                                             original_stake=current_stake,
                                             target_value=value,
                                             extension=extension)
        click.confirm("Publish stake division to the blockchain?", abort=True)

    # Authenticate
    password = None
    if not stake_.hw_wallet and not blockchain.client.is_local:
        password = get_client_password(checksum_address=current_stake.staker_address)

    # Consistency check to prevent the above agreement from going stale.
    last_second_current_period = STAKEHOLDER.staking_agent.get_current_period()
    if action_period != last_second_current_period:
        emitter.echo("Current period advanced before stake division was broadcasted. Please try again.",
                     red='red')
        raise click.Abort

    # Execute
    STAKEHOLDER.assimilate(checksum_address=current_stake.staker_address, password=password)
    emitter.echo("Broadcasting Stake Division...", color='yellow')
    modified_stake, new_stake = STAKEHOLDER.divide_stake(stake_index=current_stake.index,
                                                         target_value=value,
                                                         additional_periods=extension)
    emitter.echo('Successfully divided stake', color='green', verbosity=1)
    paint_receipt_summary(emitter=emitter,
                          receipt=new_stake.receipt,
                          chain_name=blockchain.client.chain_name)

    # Show the resulting stake list
    painting.paint_stakes(emitter=emitter, stakes=STAKEHOLDER.stakes)


@stake.command('collect-reward')
@group_stake
@click.option('--staking-reward/--no-staking-reward', is_flag=True, default=False)
@click.option('--policy-reward/--no-policy-reward', is_flag=True, default=False)
@click.option('--withdraw-address', help="Send reward collection to an alternate address", type=EIP55_CHECKSUM_ADDRESS)
@option_force
@group_general_config
def collect_reward(general_config,

                   # Stake Options
                   stake_,

                   # Other
                   staking_reward, policy_reward, withdraw_address, force):
    """
    Withdraw staking reward.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    api = stake_.api
    STAKEHOLDER, blockchain = _create_stakeholder(
        api.config_file, api.provider_uri, api.admin.poa, api.admin.light, api.admin.registry_filepath, api.staking_address,
        beneficiary_address=stake_.beneficiary_address,
        allocation_filepath=stake_.allocation_filepath)
    #############

    client_account, staking_address = handle_client_account_for_staking(emitter=emitter,
                                                                        stakeholder=STAKEHOLDER,
                                                                        staking_address=api.staking_address,
                                                                        individual_allocation=STAKEHOLDER.individual_allocation,
                                                                        force=force)

    password = None
    if not stake_.hw_wallet and not blockchain.client.is_local:
        password = get_client_password(checksum_address=client_account)

    if not staking_reward and not policy_reward:
        raise click.BadArgumentUsage(f"Either --staking-reward or --policy-reward must be True to collect rewards.")

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


@stake.command('preallocation')
@click.argument('action', type=click.Choice(['status', 'withdraw']))
@group_stake
@option_force
@group_general_config
def preallocation(general_config,

                  # Stake Options
                  stake_,

                  # Preallocation subcommands,
                  action,

                  # Other
                  force):
    """
    Claim token rewards collected by a preallocation contract.
    """

    ### Setup ###
    emitter = _setup_emitter(general_config)

    api = stake_.api
    STAKEHOLDER, blockchain = _create_stakeholder(
        api.config_file, api.provider_uri, api.admin.poa, api.admin.light, api.admin.registry_filepath, api.staking_address,
        beneficiary_address=stake_.beneficiary_address,
        allocation_filepath=stake_.allocation_filepath)

    #############
    # Unauthenticated actions: status

    if action == 'status':
        painting.paint_preallocation_status(emitter=emitter,
                                   token_agent=STAKEHOLDER.token_agent,
                                   preallocation_agent=STAKEHOLDER.preallocation_escrow_agent)
        return

    # Authenticated actions: withdraw-tokens

    client_account, staking_address = handle_client_account_for_staking(emitter=emitter,
                                                                        stakeholder=STAKEHOLDER,
                                                                        staking_address=api.staking_address,
                                                                        individual_allocation=STAKEHOLDER.individual_allocation,
                                                                        force=force)

    password = None
    if not stake_.hw_wallet and not blockchain.client.is_local:
        password = get_client_password(checksum_address=client_account)

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


def _setup_emitter(general_config):
    # Banner
    emitter = general_config.emitter
    emitter.clear()
    emitter.banner(StakeHolder.banner)

    return emitter


def _get_stakeholder_config(config_file, provider_uri, poa, light, registry_filepath):
    try:
        stakeholder_config = StakeHolderConfiguration.from_configuration_file(filepath=config_file,
                                                                              provider_uri=provider_uri,
                                                                              poa=poa,
                                                                              light=light,
                                                                              sync=False,
                                                                              registry_filepath=registry_filepath)

        return stakeholder_config
    except FileNotFoundError:
        return actions.handle_missing_configuration_file(character_config_class=StakeHolderConfiguration,
                                                         config_file=config_file)


def _create_stakeholder(config_file, provider_uri, poa, light, registry_filepath,
                        staking_address, beneficiary_address, allocation_filepath):
    stakeholder_config = _get_stakeholder_config(config_file, provider_uri, poa, light, registry_filepath)

    # Now let's check whether we're dealing here with a regular staker or a preallocation staker
    is_preallocation_staker = (beneficiary_address and staking_address) or allocation_filepath

    # Configure the individual allocation registry, if needed
    individual_allocation = None
    if is_preallocation_staker:
        if allocation_filepath:
            if beneficiary_address or staking_address:
                message = "--allocation-filepath is incompatible with --beneficiary-address and --staking-address."
                raise click.BadOptionUsage(option_name="--allocation-filepath", message=message)

            # This assumes the user has an individual allocation file in disk
            individual_allocation = IndividualAllocationRegistry.from_allocation_file(allocation_filepath)
        elif beneficiary_address and staking_address:
            individual_allocation = IndividualAllocationRegistry(beneficiary_address=beneficiary_address,
                                                                 contract_address=staking_address)

        else:
            option = "--beneficiary_address" if beneficiary_address else "--staking-address"
            raise click.BadOptionUsage(option_name=option,
                                       message=f"You must specify both --beneficiary-address and --staking-address. "
                                               f"Only {option} was provided. As an alternative, you can simply "
                                               f"provide an individual allocation with --allocation-file <PATH>")

    # Lazy initialization of StakeHolder
    stakeholder = stakeholder_config.produce(initial_address=None,
                                             individual_allocation=individual_allocation)
    blockchain = BlockchainInterfaceFactory.get_interface(provider_uri=provider_uri)  # Eager connection

    return stakeholder, blockchain
