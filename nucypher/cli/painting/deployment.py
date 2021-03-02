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


import maya
import tabulate
import webbrowser
from web3.main import Web3

from nucypher.blockchain.eth.agents import (
    ContractAgency,
    NucypherTokenAgent,
    PolicyManagerAgent,
)
from nucypher.blockchain.eth.constants import NUCYPHER_TOKEN_CONTRACT_NAME
from nucypher.blockchain.eth.deployers import DispatcherDeployer, PolicyManagerDeployer, StakingInterfaceRouterDeployer
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.utils import etherscan_url
from nucypher.characters.banners import NU_BANNER
from nucypher.cli.painting.staking import paint_fee_rate_range
from nucypher.cli.painting.transactions import paint_receipt_summary


def paint_staged_deployment(emitter, deployer_interface, administrator) -> None:
    emitter.clear()
    emitter.banner(NU_BANNER)
    emitter.echo(f"Current Time ........ {maya.now().iso8601()}")
    emitter.echo(f"Web3 Provider ....... {deployer_interface.provider_uri}")
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

Provider URI ............. {blockchain.provider_uri}
Registry  ................ {registry.filepath}

* Standard Deployments
=====================================================================
"""
    emitter.echo(provider_info)

    try:
        token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=registry)
        token_contract_info = f"""

{token_agent.contract_name} ........... {token_agent.contract_address}
    ~ Ethers ............ {Web3.fromWei(blockchain.client.get_balance(token_agent.contract_address), 'ether')} ETH
    ~ Tokens ............ {NU.from_nunits(token_agent.get_balance(token_agent.contract_address))}"""
    except BaseContractRegistry.UnknownContract:
        message = f"\n{NucypherTokenAgent.contract_name} is not enrolled in {registry.filepath}"
        emitter.echo(message, color='yellow')
        emitter.echo(sep, nl=False)
    else:
        emitter.echo(token_contract_info)

    banner = """
* Proxy-Contract Deployments
====================================================================="""
    emitter.echo(banner)

    from nucypher.blockchain.eth.actors import ContractAdministrator
    for contract_deployer_class in ContractAdministrator.dispatched_upgradeable_deployer_classes:
        try:
            bare_contract = blockchain.get_contract_by_name(contract_name=contract_deployer_class.contract_name,
                                                            proxy_name=DispatcherDeployer.contract_name,
                                                            registry=registry,
                                                            use_proxy_address=False)

            dispatcher_deployer = DispatcherDeployer(registry=registry,
                                                     target_contract=bare_contract,
                                                     bare=True)  # acquire agency for the dispatcher itself.

            agent = contract_deployer_class.agency(registry=registry, contract=bare_contract)

            proxy_payload = f"""
{agent.contract_name} .... {bare_contract.address}
    ~ Version ............ {bare_contract.version}
    ~ Owner .............. {bare_contract.functions.owner().call()}
    ~ Ethers ............. {Web3.fromWei(blockchain.client.get_balance(bare_contract.address), 'ether')} ETH
    ~ Tokens ............. {NU.from_nunits(token_agent.get_balance(bare_contract.address))}
    ~ Dispatcher ......... {dispatcher_deployer.contract_address}
        ~ Owner .......... {dispatcher_deployer.contract.functions.owner().call()}
        ~ Target ......... {dispatcher_deployer.contract.functions.target().call()}
        ~ Ethers ......... {Web3.fromWei(blockchain.client.get_balance(dispatcher_deployer.contract_address), 'ether')} ETH
        ~ Tokens ......... {NU.from_nunits(token_agent.get_balance(dispatcher_deployer.contract_address))}"""
            emitter.echo(proxy_payload)
            emitter.echo(sep, nl=False)

        except BaseContractRegistry.UnknownContract:
            message = f"\n{contract_deployer_class.contract_name} is not enrolled in {registry.filepath}"
            emitter.echo(message, color='yellow')
            emitter.echo(sep, nl=False)

    try:

        policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=registry)
        paint_fee_rate_range(emitter, policy_agent)
        emitter.echo(sep, nl=False)

    except BaseContractRegistry.UnknownContract:
        message = f"\n{PolicyManagerDeployer.contract_name} is not enrolled in {registry.filepath}"
        emitter.echo(message, color='yellow')
        emitter.echo(sep, nl=False)
