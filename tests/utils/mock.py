from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.agents import ContractAgency
from tests.mock.agents import MockContractAgency

# def _mock_contract_agency(mocker, application_economics):
#     mocker.patch.object(EconomicsFactory, 'get_economics', return_value=application_economics)
#     ContractAgency.get_agent = MockContractAgency.get_agent
#     ContractAgency.get_agent_by_contract_name = MockContractAgency.get_agent_by_contract_name
#     yield MockContractAgency()
