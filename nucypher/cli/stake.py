
import click
from constant_sorrow.constants import NO_STAKING_DEVICE

from nucypher.blockchain.eth.actors import StakeHolder
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.blockchain.eth.token import NU
from nucypher.characters.banners import NU_BANNER
from nucypher.cli import painting
from nucypher.cli.actions import confirm_staged_stake
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import (
    EIP55_CHECKSUM_ADDRESS,
    STAKE_VALUE,
    STAKE_DURATION,
    STAKE_EXTENSION
)
from nucypher.utilities.sandbox.hardware import MockTrezor


@click.command()
@click.argument('action')
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@click.option('--quiet', '-Q', help="Disable logging", is_flag=True)
@click.option('--trezor', help="Use the NuCypher Trezor Staking CLI", is_flag=True, default=None)
@click.option('--poa', help="Inject POA middleware", is_flag=True, default=None)
@click.option('--offline', help="Operate in offline mode", is_flag=True, default=None)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--funding-address', help="Address to stake NU ERC20 tokens", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--staking-address', help="Address to stake NU ERC20 tokens", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--worker-address', help="Address to assign as an Ursula-Worker", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--withdraw-address', help="Send reward collection to an alternate address", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--value', help="Token value of stake", type=click.INT)
@click.option('--duration', help="Period duration of stake", type=click.INT)
@click.option('--index', help="A specific stake index to resume", type=click.INT)
@nucypher_click_config
def stake(click_config,
          action,

          # Mode
          force,
          quiet,
          offline,
          trezor,

          # Blockchain
          poa,
          provider_uri,

          # Stake
          funding_address,
          staking_address,
          worker_address,
          withdraw_address,
          value,
          duration,
          index

          ) -> None:

    # Banner
    if not quiet:
        click.clear()
        click.secho(NU_BANNER)

    device = NO_STAKING_DEVICE
    if trezor:
        # TODO: Unmock device API
        device = MockTrezor()

    blockchain = None
    if not offline:
        blockchain = Blockchain.connect(provider_uri=provider_uri, poa=poa)

    if action == 'new-stakeholder':
        new_stakeholder = StakeHolder(funding_account=funding_address,
                                      offline_mode=offline,
                                      device=device,
                                      blockchain=blockchain)
        filepath = new_stakeholder.to_configuration_file()
        click.secho(f"Wrote new stakeholder configuration to {filepath}", fg='green')
        return  # Exit

    #
    # Make Staker
    #

    STAKEHOLDER = StakeHolder.from_configuration_file(blockchain=blockchain,
                                                      offline=offline)
    #
    # Eager Actions
    #

    if action == 'list':
        if not STAKEHOLDER.stakes:
            click.echo(f"There are no active stakes for {STAKEHOLDER.funding_account}")
        else:
            painting.paint_stakes(stakes=STAKEHOLDER.stakes)
        return

    #
    # Authenticate
    #

    # if trezor:
    #     # TODO: Implement TrezorClient and Staker
    #     raise NotImplementedError
    #
    # else:
    #     node_password = click.prompt("Enter Client Keyring Password", hide_input=True)
    #     blockchain.interface.client.unlock_account(address=STAKEHOLDER.funding_account,
    #                                                password=node_password)

    #
    # Authenticated Actions
    #

    if action == 'set-worker':
        STAKEHOLDER.set_worker(staker_address=staking_address, worker_address=worker_address)
        return  # Exit

    elif action == 'init':
        """Initialize a new stake"""

        # Confirm new stake init
        if not force:
            click.confirm("Stage a new stake?", abort=True)

        # Validate balance
        balance = STAKEHOLDER.funding_tokens
        if balance == 0:
            click.secho(f"{STAKEHOLDER.funding_account} has 0 NU.")
            raise click.Abort

        if not quiet:
            click.echo(f"Current balance: {balance}")

        #
        # Stage Stake
        #

        # Stake Value
        if not value:
            min_locked = NU(STAKEHOLDER.economics.minimum_allowed_locked, 'NuNit')
            value = click.prompt(f"Enter stake value", type=STAKE_VALUE, default=min_locked)
        else:
            value = NU(int(value), 'NU')

        # Stake Duration
        if not quiet:
            message = f"Minimum duration: {STAKEHOLDER.economics.minimum_locked_periods}"
            click.echo(message)

        if not duration:
            duration = click.prompt("Enter stake duration in periods (1 Period = 24 Hours)", type=STAKE_DURATION)

        start_period = STAKEHOLDER.staking_agent.get_current_period()
        end_period = start_period + duration

        #
        # Review
        #

        if not force:
            painting.paint_staged_stake(ursula=STAKEHOLDER,
                                        stake_value=value,
                                        duration=duration,
                                        start_period=start_period,
                                        end_period=end_period)

            confirm_staged_stake(stakeholder=STAKEHOLDER, value=value, duration=duration)

        # Last chance to bail
        if not force:
            click.confirm("Publish staged stake to the blockchain?", abort=True)

        # Execute
        new_password = click.prompt("New Stake Keyring Password", hide_input=True, confirmation_prompt=True)
        new_stake = STAKEHOLDER.initialize_stake(amount=value, duration=duration, password=new_password)
        painting.paint_staking_confirmation(ursula=STAKEHOLDER, transactions=new_stake.transactions)
        return  # Exit

    elif action == 'divide':
        """Divide an existing stake by specifying the new target value and end period"""

        # Validate
        if not STAKEHOLDER.stakes:
            click.echo(f"There are no active stakes for {STAKEHOLDER.funding_account}")
            return

        # Stake Selection
        if index is None:
            painting.paint_stakes(stakes=STAKEHOLDER.stakes)
            index = click.prompt("Select a stake to divide", type=click.IntRange(min=0, max=len(STAKEHOLDER.stakes)-1))
        current_stake = STAKEHOLDER.stakes[index]

        #
        # Stage Stake
        #

        # Value
        if not value:
            value = click.prompt(f"Enter target value (must be less than {str(current_stake.value)})", type=STAKE_VALUE)
        value = NU(value, 'NU')

        # Duration
        if not duration:
            extension = click.prompt("Enter number of periods to extend", type=STAKE_EXTENSION)
        else:
            extension = duration

        if not force:
            painting.paint_staged_stake_division(ursula=STAKEHOLDER,
                                                 original_index=index,
                                                 original_stake=current_stake,
                                                 target_value=value,
                                                 extension=extension)

            click.confirm("Is this correct?", abort=True)

        # Execute
        modified_stake, new_stake = STAKEHOLDER.divide_stake(address=staking_address,
                                                             index=index,
                                                             value=value,
                                                             duration=extension)
        if not quiet:
            click.secho('Successfully divided stake', fg='green')
            click.secho(f'Transaction Hash ........... {new_stake.receipt}')

        # Show the resulting stake list
        painting.paint_stakes(stakes=STAKEHOLDER.stakes)
        return  # Exit
    
    elif action == 'collect-reward':
        """Withdraw staking reward to the specified wallet address"""
        if not force:
            click.confirm(f"Send {STAKEHOLDER.calculate_reward()} to {STAKEHOLDER.funding_account}?")
        STAKEHOLDER.collect_rewards(staker_address=staking_address)

    return  # Exit
