import pytest

from nucypher.blockchain.economics import EconomicsFactory


@pytest.mark.usefixtures('testerchain')
def test_retrieving_from_blockchain(application_economics, test_registry):
    economics = EconomicsFactory.get_economics(registry=test_registry)
    assert (
        economics.taco_application_deployment_parameters
        == application_economics.taco_application_deployment_parameters
    )
