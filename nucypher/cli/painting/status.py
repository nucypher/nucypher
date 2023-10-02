from nucypher.blockchain.eth.agents import (
    ContractAgency,
    TACoApplicationAgent,
)


def paint_application_contract_status(emitter, registry, provider_uri):
    application_agent = ContractAgency.get_agent(
        TACoApplicationAgent, registry=registry, blockchain_endpoint=provider_uri
    )
    blockchain = application_agent.blockchain

    contracts = f"""
Contract Deployment
===================
Blockchain ........................ {blockchain.client.chain_name}
TACoApplication Contract........... {application_agent.contract_address}
    """

    staking = f"""
TACoApplication
================
Staking Provider Population ....... {application_agent.get_staking_providers_population()}
    """

    emitter.echo(contracts)
    emitter.echo(staking)
