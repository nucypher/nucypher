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

from web3.main import Web3

from nucypher.blockchain.eth.agents import (
    ContractAgency,
    NucypherTokenAgent,
    PREApplicationAgent,
)
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory


def paint_contract_status(registry, emitter):
    blockchain = BlockchainInterfaceFactory.get_interface()
    application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=registry)
    contracts = f"""
| Contract Deployments |
{application_agent.contract_name} .............. {application_agent.contract_address}
    """

    blockchain = f"""
| '{blockchain.client.chain_name}' Blockchain Network |
Gas Price ................ {Web3.fromWei(blockchain.client.gas_price, 'gwei')} Gwei
ETH Provider URI ......... {blockchain.eth_provider_uri}
Registry ................. {registry.filepath}
    """

    staking = f"""
| PREApplication |
Staking Provider Population ....... {application_agent.get_staking_providers_population()}
    """

    sep = '-' * 45
    emitter.echo(sep)
    emitter.echo(contracts)
    emitter.echo(sep)
    emitter.echo(blockchain)
    emitter.echo(sep)
    emitter.echo(staking)
    emitter.echo(sep)
