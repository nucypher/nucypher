
import click
from constant_sorrow.constants import NO_STAKING_DEVICE
from web3 import Web3

from nucypher.blockchain.eth.actors import StakeHolder
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.characters.banners import NU_BANNER
from nucypher.cli import painting
from nucypher.cli.actions import confirm_staged_stake, get_password, select_stake
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import (
    EIP55_CHECKSUM_ADDRESS,
    STAKE_VALUE,
    STAKE_DURATION,
    STAKE_EXTENSION,
    EXISTING_READABLE_FILE)
from nucypher.utilities.sandbox.hardware import MockTrezor


@click.command()
@click.argument('action')
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@click.option('--quiet', '-Q', help="Disable logging", is_flag=True)
@click.option('--trezor', help="Use the NuCypher Trezor Staking CLI", is_flag=True, default=None)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--poa', help="Inject POA middleware", is_flag=True, default=None)
@click.option('--offline', help="Operate in offline mode", is_flag=True, default=None)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--funding-address', help="Address to stake NU ERC20 tokens", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--pre-funded', help="Do not fund new stake's accounts", is_flag=True, default=False)
@click.option('--staking-address', help="Address to stake NU ERC20 tokens", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--worker-address', help="Address to assign as an Ursula-Worker", type=EIP55_CHECKSUM_ADDRESS)
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
          quiet,
          offline,
          trezor,

          # Blockchain
          poa,
          registry_filepath,
          provider_uri,

          # Stake
          funding_address,
          staking_address,
          worker_address,
          withdraw_address,
          value,
          duration,
          index,
          pre_funded

          ) -> None:

    # Banner
    if not quiet:
        click.clear()
        click.secho(NU_BANNER)

    device = NO_STAKING_DEVICE

    if action == 'new-stakeholder':

        registry = None
        if registry_filepath:
            registry = EthereumContractRegistry(registry_filepath=registry_filepath)

        blockchain = BlockchainInterface(provider_uri=provider_uri,
                                         registry=registry,
                                         poa=poa)

        new_stakeholder = StakeHolder(config_root=config_root,
                                      funding_account=funding_address,
                                      offline_mode=offline,
                                      device=device,
                                      blockchain=blockchain)

        filepath = new_stakeholder.to_configuration_file()
        click.secho(f"Wrote new stakeholder configuration to {filepath}", fg='green')
        return  # Exit

    #
    # Make Staker
    #

    STAKEHOLDER = StakeHolder.from_configuration_file(filepath=config_file,
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

        staker_password = get_password(confirm=False)
        STAKEHOLDER.set_worker(staker_address=staking_address,
                               password=staker_password,
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
            enumerated_accounts = dict(enumerate(STAKEHOLDER.accounts))
            click.secho(f"c | CREATE NEW ACCOUNT ")
            for index, account in enumerated_accounts.items():
                click.secho(f"{index} | {account}")

            choice = click.prompt("Select staking account, or enter 'c' to derive a new one", default='c')
            if choice == 'c':
                click.confirm("Create new ethereum account for staking?", abort=True)
                password = click.prompt("Enter new account password", hide_input=True, confirmation_prompt=True)
                staking_address = None  # signals to create an account later
            else:
                try:
                    staking_address = enumerated_accounts[int(choice)]
                except KeyError:
                    raise click.BadParameter(f"'{choice}' is not a valid command.")

        if not password:
            password = click.prompt(f"Enter password to unlock {staking_address}",
                                    hide_input=True,
                                    confirmation_prompt=False)

        if not pre_funded:
            fund_now = click.confirm("Fund staking account with funding account?", abort=False, default=True)
        else:
            # TODO: Validate the balance of self-manged funders.
            fund_now = False

        # Validate balance
        if STAKEHOLDER.funding_tokens == 0 and fund_now:
            click.secho(f"{STAKEHOLDER.funding_account} has 0 NU.")
            raise click.Abort
        if not quiet:
            click.echo(f"Funding account balance | {STAKEHOLDER.funding_tokens} | {STAKEHOLDER.funding_eth} ETH")


        #
        # Stage Stake
        #

        if not value:
            min_locked = STAKEHOLDER.economics.minimum_allowed_locked
            value = click.prompt(f"Enter stake value in NuNits", type=STAKE_VALUE, default=min_locked)
        value = NU.from_nunits(int(value))

        if not duration:
            prompt = f"Enter stake duration ({STAKEHOLDER.economics.minimum_locked_periods} period min)"
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
        target = staking_address or "derived account"
        message = f"Transfer {value.to_nunits()} NuNits and {STAKEHOLDER.eth_funding} wei to {target}?"
        if not force:
            if fund_now:
                click.confirm(message, abort=True)
            click.confirm("Publish staged stake to the blockchain?", abort=True)

        # Execute
        new_stake = STAKEHOLDER.initialize_stake(amount=value,
                                                 duration=duration,
                                                 checksum_address=staking_address,
                                                 password=password,
                                                 fund_now=fund_now)

        painting.paint_staking_confirmation(ursula=STAKEHOLDER, transactions=new_stake.transactions)
        return  # Exit

    elif action == 'divide':
        """Divide an existing stake by specifying the new target value and end period"""

        current_stake = select_stake(stakeholder=STAKEHOLDER)

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
                                                 original_stake=current_stake,
                                                 target_value=value,
                                                 extension=extension)
            click.confirm("Is this correct?", abort=True)

        # Execute
        password = get_password(confirm=False)
        modified_stake, new_stake = STAKEHOLDER.divide_stake(address=current_stake.owner_address,
                                                             index=current_stake.index,
                                                             value=value,
                                                             duration=extension,
                                                             password=password)
        if not quiet:
            click.secho('Successfully divided stake', fg='green')
            click.secho(f'Receipt ........... {new_stake.receipt}')

        # Show the resulting stake list
        painting.paint_stakes(stakes=STAKEHOLDER.stakes)
        return  # Exit
    
    elif action == 'collect-reward':
        """Withdraw staking reward to the specified wallet address"""
        if not force:
            click.confirm(f"Send {STAKEHOLDER.calculate_reward()} to {STAKEHOLDER.funding_account}?")

        password = get_password(confirm=False)
        STAKEHOLDER.collect_rewards(staker_address=staking_address, password=password)

    return  # Exit
