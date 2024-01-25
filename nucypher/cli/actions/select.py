from typing import Optional

import click
from tabulate import tabulate

from nucypher.blockchain.eth import domains
from nucypher.cli.literature import (
    SELECT_DOMAIN,
)
from nucypher.utilities.emitters import StdoutEmitter


def select_domain(emitter: StdoutEmitter, message: Optional[str] = None) -> str:
    """Interactively select a domain from TACo domain inventory list"""
    emitter.message(message=message or str(), color="yellow")
    domain_list = list(domains.SUPPORTED_DOMAINS)
    rows = [[n] for n in domain_list]
    emitter.echo(tabulate(rows, showindex="always"))
    choice = click.prompt(
        SELECT_DOMAIN,
        default=0,
        type=click.IntRange(0, len(rows) - 1),
    )
    domain = domain_list[choice]
    return domain
