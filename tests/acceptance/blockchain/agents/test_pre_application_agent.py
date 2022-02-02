
import pytest
from eth_tester.exceptions import TransactionFailed

from nucypher.blockchain.eth.agents import NucypherTokenAgent, PREApplicationAgent, ContractAgency
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer, PREApplicationDeployer
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower


def test_get_min_authorization(agency, test_registry, application_economics):
    pre_application = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)
    result = pre_application.get_min_authorization()
    assert result == application_economics.min_authorization


def test_get_min_seconds(agency, test_registry, application_economics):
    pre_application = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)
    result = pre_application.get_min_operator_seconds()
    assert result == application_economics.min_operator_seconds
