

from nucypher.blockchain.eth.agents import ContractAgency, PREApplicationAgent


def test_get_agent_with_different_registries(application_economics, test_registry, agency_local_registry):
    # Get agents using same registry instance
    application_agent_1 = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)
    application_agent_2 = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)
    assert application_agent_2.registry == application_agent_1.registry == test_registry
    assert application_agent_2 is application_agent_1

    # Same content but different classes of registries
    application_agent_2 = ContractAgency.get_agent(PREApplicationAgent, registry=agency_local_registry)
    assert application_agent_2.registry == test_registry
    assert application_agent_2 is application_agent_1
