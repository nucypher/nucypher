from web3.main import Web3

from nucypher.blockchain.eth.agents import (
    ContractAgency,
    TACoApplicationAgent,
)


def paint_application_contract_status(emitter, registry, provider_uri):
    application_agent = ContractAgency.get_agent(
        TACoApplicationAgent, registry=registry, provider_uri=provider_uri
    )
    blockchain = application_agent.blockchain

    contracts = f"""
| Contract Deployment |
{application_agent.contract_name} .............. {application_agent.contract_address}
    """

    blockchain = f"""
| '{blockchain.client.chain_name}' Blockchain Network |
Gas Price ................ {Web3.from_wei(blockchain.client.gas_price, 'gwei')} Gwei
ETH Provider URI ......... {blockchain.eth_provider_uri}
Registry ................. {registry.filepath}
    """

    staking = f"""
| TACoApplication |
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
