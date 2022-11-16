

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
Gas Price ................ {Web3.from_wei(blockchain.client.gas_price, 'gwei')} Gwei
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
