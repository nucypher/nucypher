
import click
from constant_sorrow.constants import NO_STAKING_DEVICE
from web3 import Web3

from nucypher.blockchain.eth.actors import StakeHolder
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.characters.banners import NU_BANNER
from nucypher.cli import painting
from nucypher.cli.actions import confirm_staged_stake, get_password, select_stake, select_client_account
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import (
    EIP55_CHECKSUM_ADDRESS,
    STAKE_VALUE,
    STAKE_DURATION,
    STAKE_EXTENSION,
    EXISTING_READABLE_FILE)


@click.command()
@click.argument('action')
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@click.option('--hw-wallet/--no-hw-wallet', default=False)  # TODO: Make True or deprecate.
@click.option('--sync/--no-sync', default=True)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--poa', help="Inject POA middleware", is_flag=True)
@click.option('--offline', help="Operate in offline mode", is_flag=True)
@click.option('--provider-uri', help="Blockchain provider's URI i.e. 'file:///path/to/geth.ipc'", type=click.STRING)
@click.option('--staking-address', help="Address to stake NU ERC20 tokens", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--worker-address', help="Address to assign as an Ursula-Worker", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--staking-reward/--no-staking-reward', is_flag=True, default=True)
@click.option('--policy-reward/--no-policy-reward', is_flag=True, default=True)
@click.option('--withdraw-address', help="Send reward collection to an alternate address", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--value', help="Token value of stake", type=click.INT)
@click.option('--duration', help="Period duration of stake", type=click.INT)
@click.option('--index', help="A specific stake index to resume", type=click.INT)
@nucypher_click_config
def stake(click_config,
          action,

          config_root,
          config_file,

          # Mode
          force,
          offline,
          hw_wallet,

          # Blockchain
          poa,
          registry_filepath,
          provider_uri,
          sync,

          # Stake
          staking_address,
          worker_address,
          withdraw_address,
          value,
          duration,
          index,
          policy_reward,
          staking_reward,

          ) -> None:

    # Banner
    if not click_config.quiet:
        click.clear()
        click.secho(NU_BANNER)

    if action == 'new-stakeholder':

        if not provider_uri:
            raise click.BadOptionUsage(option_name='--provider-uri',
                                       message="--provider-uri is required to create a new stakeholder.")

        registry = None
        if registry_filepath:
            registry = EthereumContractRegistry(registry_filepath=registry_filepath)

        blockchain = BlockchainInterface(provider_uri=provider_uri,
                                         registry=registry,
                                         poa=poa)
        blockchain.connect()  # TODO: Leave this here?

        new_stakeholder = StakeHolder(config_root=config_root,
                                      offline_mode=offline,
                                      blockchain=blockchain)

        filepath = new_stakeholder.to_configuration_file(override=force)
        click.secho(f"Wrote new stakeholder configuration to {filepath}", fg='green')
        return  # Exit

    #
    # Make Staker
    #

    STAKEHOLDER = StakeHolder.from_configuration_file(filepath=config_file,
                                                      provider_uri=provider_uri,
                                                      registry_filepath=registry_filepath,
                                                      offline=offline)
    #
    # Eager Actions
    #

    if action == 'list':
        if not STAKEHOLDER.stakes:
            click.echo(f"There are no active stakes")
        else:
            painting.paint_stakes(stakes=STAKEHOLDER.stakes)
        return

    elif action == 'accounts':
        for address, balances in STAKEHOLDER.account_balances.items():
            click.secho(f"{address} | {Web3.fromWei(balances['ETH'], 'ether')} ETH | {NU.from_nunits(balances['NU'])}")
        return  # Exit

    elif action == 'sync':
        click.secho("Reading on-chain stake data...")
        STAKEHOLDER.read_onchain_stakes()
        STAKEHOLDER.to_configuration_file(override=True)
        click.secho("OK!", fg='green')
        return  # Exit

    elif action == 'set-worker':

        if not staking_address:
            staking_address = select_stake(stakeholder=STAKEHOLDER).owner_address

        if not worker_address:
            worker_address = click.prompt("Enter worker address", type=EIP55_CHECKSUM_ADDRESS)

        password = None
        if not hw_wallet:
            password = get_password(confirm=False)
        STAKEHOLDER.set_worker(staker_address=staking_address,
                               password=password,
                               worker_address=worker_address)

        click.secho("OK!", fg='green')
        return  # Exit

    elif action == 'init':
        """Initialize a new stake"""

        #
        # Get Staking Account
        #

        password = None
        if not staking_address:
            staking_address = select_client_account(blockchain=STAKEHOLDER.blockchain, prompt="Select staking account")

        if not hw_wallet and not STAKEHOLDER.blockchain.client.is_local:  # TODO: encapsulate/recycle in function?
            password = click.prompt(f"Enter password to unlock {staking_address}",
                                    hide_input=True,
                                    confirmation_prompt=False)
        #
        # Stage Stake
        #

        if not value:
            min_locked = STAKEHOLDER.economics.minimum_allowed_locked
            value = click.prompt(f"Enter stake value in NU", type=STAKE_VALUE, default=NU.from_nunits(min_locked).to_tokens())
        value = NU.from_tokens(value)

        if not duration:
            prompt = f"Enter stake duration ({STAKEHOLDER.economics.minimum_locked_periods} periods minimum)"
            duration = click.prompt(prompt, type=STAKE_DURATION)

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
        click.confirm("Publish staged stake to the blockchain?", abort=True)

        # Execute
        new_stake = STAKEHOLDER.initialize_stake(amount=value,
                                                 duration=duration,
                                                 checksum_address=staking_address,
                                                 password=password)

        painting.paint_staking_confirmation(ursula=STAKEHOLDER, transactions=new_stake.transactions)
        return  # Exit

    elif action == 'divide':
        """Divide an existing stake by specifying the new target value and end period"""

        if staking_address and index is not None:
            staker = STAKEHOLDER.get_active_staker(address=staking_address)
            current_stake = staker.stakes[index]
        else:
            current_stake = select_stake(stakeholder=STAKEHOLDER)

        #
        # Stage Stake
        #

        # Value
        if not value:
            value = click.prompt(f"Enter target value (must be less than or equal to {str(current_stake.value)})",
                                 type=STAKE_VALUE)
        value = NU(value, 'NU')

        # Duration
        if not duration:
            extension = click.prompt("Enter number of periods to extend", type=STAKE_EXTENSION)
        else:
            extension = duration

        if not force:
            painting.paint_staged_stake_division(ursula=STAKEHOLDER,
                                                 original_stake=current_stake,
                                                 target_value=value,
                                                 extension=extension)
            click.confirm("Is this correct?", abort=True)

        # Execute
        password = None
        if not hw_wallet:
            password = get_password(confirm=False)
        modified_stake, new_stake = STAKEHOLDER.divide_stake(address=current_stake.owner_address,
                                                             index=current_stake.index,
                                                             value=value,
                                                             duration=extension,
                                                             password=password)
        if not click_config.quiet:
            click.secho('Successfully divided stake', fg='green')
            click.secho(f'Receipt ........... {new_stake.receipt}')

        # Show the resulting stake list
        painting.paint_stakes(stakes=STAKEHOLDER.stakes)
        return  # Exit

    elif action == 'collect-reward':
        """Withdraw staking reward to the specified wallet address"""
        password = None
        if not hw_wallet:
            password = get_password(confirm=False)
        STAKEHOLDER.collect_rewards(staker_address=staking_address,
                                    withdraw_address=withdraw_address,
                                    password=password,
                                    staking=staking_reward,
                                    policy=policy_reward)

    return  # Exit
