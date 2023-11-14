from pathlib import Path

import click
import maya
from tabulate import tabulate
from web3 import Web3

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    CoordinatorAgent,
    TACoApplicationAgent,
)
from nucypher.blockchain.eth.constants import (
    AVERAGE_BLOCK_TIME_IN_SECONDS,
    TACO_CONTRACT_NAMES,
)
from nucypher.blockchain.eth.utils import truncate_checksum_address
from nucypher.cli.config import group_general_config
from nucypher.cli.options import (
    group_options,
    option_contract_name,
    option_event_name,
    option_light,
    option_poa,
    option_registry_filepath,
)
from nucypher.cli.painting.status import paint_application_contract_status
from nucypher.cli.utils import (
    get_registry,
    parse_event_filters_into_argument_filters,
    retrieve_events,
    setup_emitter,
)
from nucypher.utilities.events import generate_events_csv_filepath

option_blockchain_endpoint = click.option(
    "--blockchain-endpoint",
    "blockchain_endpoint",
    help="Blockchain provider's URI i.e. 'file:///path/to/geth.ipc'",
    type=click.STRING,
    required=True,
)

option_domain = click.option(
    "--domain",
    help="TACo Domain",
    type=click.STRING,
    default=click.Choice(domains.SUPPORTED_DOMAINS),
    required=True,
)


class RegistryOptions:
    __option_name__ = "registry_options"

    def __init__(self, blockchain_endpoint, poa, registry_filepath, light, domain):
        self.blockchain_endpoint = blockchain_endpoint
        self.poa = poa
        self.registry_filepath = registry_filepath
        self.light = light
        self.domain = domains.get_domain(str(domain))

    def setup(self, general_config) -> tuple:
        emitter = setup_emitter(general_config)
        registry = get_registry(
            domain=self.domain, registry_filepath=self.registry_filepath
        )
        return emitter, registry, self.blockchain_endpoint


group_registry_options = group_options(
    RegistryOptions,
    poa=option_poa,
    light=option_light,
    registry_filepath=option_registry_filepath,
    domain=option_domain,
    blockchain_endpoint=option_blockchain_endpoint,
)

option_csv = click.option(
    "--csv",
    help="Write event data to a CSV file using a default filename in the current directory",
    default=False,
    is_flag=True,
)
option_csv_file = click.option(
    "--csv-file",
    help="Write event data to the CSV file at specified filepath",
    type=click.Path(dir_okay=False, path_type=Path),
)
option_event_filters = click.option(
    "--event-filter",
    "-f",
    "event_filters",
    help="Event filter of the form <name>=<value>",
    multiple=True,
    type=click.STRING,
    default=[],
)

option_from_block = click.option(
    "--from-block",
    help="Collect events from this block number; defaults to the block number from ~24 hours ago",
    type=click.INT,
)
option_to_block = click.option(
    "--to-block",
    help="Collect events until this block number; defaults to 'latest' block number",
    type=click.INT,
)

option_ritual_ids = click.option(
    "--ritual-id",
    "-r",
    "ritual_ids",
    help="ID of a ritual",
    multiple=True,
    type=click.INT,
    default=[],
)


@click.group()
def taco():
    """Provide snapshot information about the TACo Application on Threshold Network."""


@taco.command()
@group_registry_options
@group_general_config
def application_info(general_config, registry_options):
    """Overall information about the TACo Application."""
    emitter, registry, blockchain_endpoint = registry_options.setup(
        general_config=general_config
    )
    paint_application_contract_status(
        emitter=emitter, registry=registry, eth_endpoint=blockchain_endpoint
    )


@taco.command()
@group_registry_options
@group_general_config
def active_providers(general_config, registry_options):
    """List of active stakers for the TACo Domain."""
    emitter, registry, blockchain_endpoint = registry_options.setup(
        general_config=general_config
    )
    application_agent = ContractAgency.get_agent(
        TACoApplicationAgent, registry=registry, blockchain_endpoint=blockchain_endpoint
    )
    (
        total_staked,
        staking_providers,
    ) = application_agent.get_all_active_staking_providers()
    emitter.echo(
        f"Total Active Stakes ............... {Web3.from_wei(total_staked, 'ether'):,}"
    )
    emitter.echo(f"Active Staking Providers .......... {len(staking_providers)}")
    for provider, staked in staking_providers.items():
        emitter.echo(f"\t{provider} ..... {Web3.from_wei(staked, 'ether'):,}")


@taco.command()
@option_ritual_ids
@click.option(
    "--show-inactive",
    "-i",
    "show_inactive",
    help="Include failed/expired rituals",
    is_flag=True,
)
@group_registry_options
@group_general_config
def rituals(ritual_ids, show_inactive, registry_options, general_config):
    """Information about rituals on the TACo domain."""
    if not show_inactive and ritual_ids:
        # provided ritual ids may/may not be active
        show_inactive = True

    emitter, registry, blockchain_endpoint = registry_options.setup(
        general_config=general_config
    )
    coordinator_agent = ContractAgency.get_agent(
        CoordinatorAgent, registry=registry, blockchain_endpoint=blockchain_endpoint
    )

    headers = [
        "ID",
        "Authority",
        "AccessController",
        "Threshold",
        "Participants",
        "Expiry",
        "State",
        "Active",
    ]

    rows = list()
    ritual_id_list = (
        ritual_ids if ritual_ids else range(coordinator_agent.number_of_rituals())
    )
    for ritual_id in ritual_id_list:
        ritual = coordinator_agent.get_ritual(ritual_id)

        ritual_status = coordinator_agent.get_ritual_status(ritual_id=ritual_id)
        ritual_expiry = maya.MayaDT(epoch=ritual.end_timestamp)
        is_ritual_active = coordinator_agent.is_ritual_active(ritual_id=ritual_id)
        if not show_inactive and not is_ritual_active:
            continue

        row = [
            ritual_id,
            truncate_checksum_address(ritual.authority),
            truncate_checksum_address(ritual.access_controller),
            f"{ritual.threshold}/{ritual.dkg_size}",
            "\n".join(
                [truncate_checksum_address(p.provider) for p in ritual.participants]
            ),
            ritual_expiry.rfc3339(),
            ritual_status,
            "✓" if is_ritual_active else "x",
        ]

        rows.append(row)

    emitter.echo(
        tabulate(rows, headers=headers, showindex=False, tablefmt="fancy_grid")
    )


@taco.command()
@group_registry_options
@group_general_config
@option_contract_name(required=True, valid_options=TACO_CONTRACT_NAMES)
@option_event_name
@option_from_block
@option_to_block
@option_csv
@option_csv_file
@option_event_filters
def events(
    general_config,
    registry_options,
    contract_name,
    from_block,
    to_block,
    event_name,
    csv,
    csv_file,
    event_filters,
):
    """Show events associated with TACo Application contracts."""

    if csv or csv_file:
        if csv and csv_file:
            raise click.BadOptionUsage(
                option_name="--event-filter",
                message=click.style(
                    "Pass either --csv or --csv-file, not both.", fg="red"
                ),
            )

        # ensure that event name is specified - different events would have different columns in the csv file
        if csv_file and not all((event_name, contract_name)):
            # TODO consider a single csv that just gets appended to for each event
            #  - each appended event adds their column names first
            #  - single report-type functionality, see #2561
            raise click.BadOptionUsage(
                option_name="--csv-file, --event-name, --contract_name",
                message=click.style(
                    "--event-name and --contract-name must be specified when outputting to "
                    "specific file using --csv-file; alternatively use --csv",
                    fg="red",
                ),
            )

    emitter, registry, blockchain_endpoint = registry_options.setup(
        general_config=general_config
    )

    contract_agent = ContractAgency.get_agent_by_contract_name(
        contract_name=contract_name,
        registry=registry,
        blockchain_endpoint=blockchain_endpoint,
    )

    if from_block is None:
        # by default, this command only shows events of the last 24 hours
        blocks_since_yesterday_kinda = (60 * 60 * 24) // AVERAGE_BLOCK_TIME_IN_SECONDS
        from_block = (
            contract_agent.blockchain.client.block_number - blocks_since_yesterday_kinda
        )
    if to_block is None:
        to_block = "latest"
    else:
        # validate block range
        if from_block > to_block:
            raise click.BadOptionUsage(
                option_name="--to-block, --from-block",
                message=click.style(
                    f"Invalid block range provided, "
                    f"from-block ({from_block}) > to-block ({to_block})",
                    fg="red",
                ),
            )

    # event argument filters
    argument_filters = None
    if event_filters:
        try:
            argument_filters = parse_event_filters_into_argument_filters(event_filters)
        except ValueError as e:
            raise click.BadOptionUsage(
                option_name="--event-filter",
                message=click.style(
                    f"Event filter must be specified as name-value pairs of "
                    f"the form `<name>=<value>` - {str(e)}",
                    fg="red",
                ),
            )

    emitter.echo(f"Retrieving events from block {from_block} to {to_block}")

    if event_name and event_name not in contract_agent.events.names:
        raise click.BadOptionUsage(
            option_name="--event-name, --contract_name",
            message=click.style(
                f"{contract_name} contract does not have an event named {event_name}",
                fg="red",
            ),
        )

    title = f" {contract_agent.contract_name} Events ".center(40, "-")
    emitter.echo(f"\n{title}\n", bold=True, color="green")
    names = contract_agent.events.names if not event_name else [event_name]
    for name in names:
        # csv output file - one per (contract_name, event_name) pair
        csv_output_file = csv_file
        if csv or csv_output_file:
            if not csv_output_file:
                csv_output_file = generate_events_csv_filepath(
                    contract_name=contract_name, event_name=name
                )

        retrieve_events(
            emitter=emitter,
            agent=contract_agent,
            event_name=name,  # None is fine - just means all events
            from_block=from_block,
            to_block=to_block,
            argument_filters=argument_filters,
            csv_output_file=csv_output_file,
        )
