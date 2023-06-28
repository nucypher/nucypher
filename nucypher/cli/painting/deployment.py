

import webbrowser

import maya
from web3.main import Web3

from nucypher.blockchain.eth.agents import (
    ContractAgency,
    NucypherTokenAgent,
)
from nucypher.blockchain.eth.constants import NUCYPHER_TOKEN_CONTRACT_NAME
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.utils import etherscan_url
from nucypher.characters.banners import NU_BANNER
from nucypher.cli.painting.transactions import paint_receipt_summary


def paint_staged_deployment(emitter, deployer_interface, administrator) -> None:
    emitter.clear()
    emitter.banner(NU_BANNER)
    emitter.echo(f"Current Time ........ {maya.now().iso8601()}")
    emitter.echo(f"ETH Provider URI .... {deployer_interface.eth_provider_uri}")
    emitter.echo(f"Block ............... {deployer_interface.client.block_number}")
    emitter.echo(f"Gas Price ........... {deployer_interface.client.gas_price}")
    emitter.echo(f"Deployer Address .... {administrator.checksum_address}")
    emitter.echo(f"ETH ................. {administrator.eth_balance}")
    emitter.echo(f"Chain ID ............ {deployer_interface.client.chain_id}")
    emitter.echo(f"Chain Name .......... {deployer_interface.client.chain_name}")

    # Ask - Last chance to gracefully abort. This step cannot be forced.
    emitter.echo("\nDeployment successfully staged.", color='green')


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


def paint_deployer_contract_inspection(emitter, registry, deployer_address) -> None:

    blockchain = BlockchainInterfaceFactory.get_interface()

    sep = '-' * 45
    emitter.echo(sep)

    provider_info = f"""

* Web3 Provider
====================================================================

ETH Provider URI ......... {blockchain.eth_provider_uri}
Registry  ................ {registry.filepath}

* Standard Deployments
=====================================================================
"""
    emitter.echo(provider_info)

    try:
        token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=registry)
        token_contract_info = f"""

{token_agent.contract_name} ........... {token_agent.contract_address}
    ~ Ethers ............ {Web3.from_wei(blockchain.client.get_balance(token_agent.contract_address), 'ether')} ETH
    ~ Tokens ............ {NU.from_units(token_agent.get_balance(token_agent.contract_address))}"""
    except BaseContractRegistry.UnknownContract:
        message = f"\n{NucypherTokenAgent.contract_name} is not enrolled in {registry.filepath}"
        emitter.echo(message, color='yellow')
        emitter.echo(sep, nl=False)
    else:
        emitter.echo(token_contract_info)
