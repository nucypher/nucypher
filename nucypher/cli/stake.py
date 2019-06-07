
import click

from nucypher.blockchain.eth.actors import Staker
from nucypher.blockchain.eth.chains import Blockchain
from nucypher.blockchain.eth.token import NU
from nucypher.characters.banners import NU_BANNER
from nucypher.cli import painting
from nucypher.cli.actions import confirm_staged_stake
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import (
    EIP55_CHECKSUM_ADDRESS,
    STAKE_VALUE, STAKE_DURATION, STAKE_EXTENSION)


@click.command()
@click.argument('action')
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@click.option('--quiet', '-Q', help="Disable logging", is_flag=True)
@click.option('--trezor', help="Use the NuCypher Trezor Staking CLI", is_flag=True, default=None)
@click.option('--poa', help="Inject POA middleware", is_flag=True, default=None)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
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
          trezor,

          # Blockchain
          poa,
          provider_uri,

          # Stake
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

    #
    # Make Staker
    #

    blockchain = Blockchain.connect(provider_uri=provider_uri, poa=poa)

    STAKER = Staker(is_me=True,
                    checksum_address=staking_address,
                    blockchain=blockchain)

    #
    # Eager Actions
    #

    if action == 'list':
        if not STAKER.stakes:
            click.echo(f"There are no active stakes for {STAKER.checksum_public_address}")
        else:
            painting.paint_stakes(stakes=STAKER.stakes)
        return

    #
    # Authenticate
    #

    if trezor:
        # TODO: Implement TrezorClient and Staker
        raise NotImplementedError

    else:
        blockchain.interface.client.unlock_account(address=staking_address,
                                                   password=click_config.get_password())

    #
    # Authenticated Actions
    #

    if action == 'set-worker':
        STAKER.set_worker(worker_address=worker_address)
        return  # Exit

    elif action == 'init':
        """Initialize a new stake"""

        # Confirm new stake init
        if not force:
            click.confirm("Stage a new stake?", abort=True)

        # Validate balance
        balance = STAKER.token_balance
        if balance == 0:
            click.secho(f"{STAKER.checksum_public_address} has 0 NU.")
            raise click.Abort

        if not quiet:
            click.echo(f"Current balance: {balance}")

        #
        # Stage Stake
        #

        # Stake Value
        if not value:
            min_locked = NU(STAKER.economics.minimum_allowed_locked, 'NuNit')
            value = click.prompt(f"Enter stake value", type=STAKE_VALUE, default=min_locked)
        else:
            value = NU(int(value), 'NU')

        # Stake Duration
        if not quiet:
            message = f"Minimum duration: {STAKER.economics.minimum_allowed_locked} | " \
                      f"Maximum Duration: {STAKER.economics.maximum_allowed_locked}"
            click.echo(message)
        
        if not duration:
            duration = click.prompt("Enter stake duration in periods (1 Period = 24 Hours)", type=STAKE_DURATION)
        
        start_period = STAKER.staking_agent.get_current_period()
        end_period = start_period + duration

        #
        # Review
        #

        if not force:
            painting.paint_staged_stake(ursula=STAKER,
                                        stake_value=value,
                                        duration=duration,
                                        start_period=start_period,
                                        end_period=end_period)

            confirm_staged_stake(ursula=STAKER, value=value, duration=duration)

        # Last chance to bail
        if not force:
            click.confirm("Publish staged stake to the blockchain?", abort=True)

        # Execute
        new_stake = STAKER.initialize_stake(amount=int(value), lock_periods=duration)
        painting.paint_staking_confirmation(ursula=STAKER, transactions=new_stake.transactions)
        return  # Exit
    
    elif action == 'divide':
        """Divide an existing stake by specifying the new target value and end period"""

        # Validate
        if not STAKER.stakes:
            click.echo(f"There are no active stakes for {STAKER.checksum_public_address}")
            return

        # Stake Selection
        if index is None:
            painting.paint_stakes(stakes=STAKER.stakes)
            index = click.prompt("Select a stake to divide", type=click.IntRange(min=0, max=len(STAKER.stakes)-1))
        current_stake = STAKER.stakes[index]

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
            painting.paint_staged_stake_division(ursula=STAKER,
                                                 original_index=index,
                                                 original_stake=current_stake,
                                                 target_value=value,
                                                 extension=extension)

            click.confirm("Is this correct?", abort=True)

        # Execute
        modified_stake, new_stake = STAKER.divide_stake(stake_index=index,
                                                        target_value=value,
                                                        additional_periods=extension)

        if not quiet:
            click.secho('Successfully divided stake', fg='green')
            click.secho(f'Transaction Hash ........... {new_stake.receipt}')

        # Show the resulting stake list
        painting.paint_stakes(stakes=STAKER.stakes)

        return  # Exit
    
    elif action == 'collect-reward':
        """Withdraw staking reward to the specified wallet address"""

        if not force:
            click.confirm(f"Send {STAKER.calculate_reward()} to {STAKER.checksum_public_address}?")
        
        STAKER.collect_policy_reward(collector_address=withdraw_address)
        STAKER.collect_staking_reward()

    return  # Exit
