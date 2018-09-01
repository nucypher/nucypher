import pytest
from web3.contract import Contract


VALUE_FIELD = 0
DECIMALS_FIELD = 1
CONFIRMED_PERIOD_1_FIELD = 2
CONFIRMED_PERIOD_2_FIELD = 3
LAST_ACTIVE_PERIOD_FIELD = 4


@pytest.fixture()
def token(testerchain):
    # Create an ERC20 token
    token, _ = testerchain.interface.deploy_contract('NuCypherToken', 2 * 10 ** 9)
    return token


@pytest.fixture(params=[False, True])
def escrow_contract(testerchain, token, request):
    def make_escrow(max_allowed_locked_tokens):
        # Creator deploys the escrow
        contract, _ = testerchain.interface.deploy_contract(
            'MinersEscrow', token.address, 1, 4 * 2 * 10 ** 7, 4, 4, 2, 100, max_allowed_locked_tokens)

        if request.param:
            dispatcher, _ = testerchain.interface.deploy_contract('Dispatcher', contract.address)
            contract = testerchain.interface.w3.eth.contract(
                abi=contract.abi,
                address=dispatcher.address,
                ContractFactoryClass=Contract)

        policy_manager, _ = testerchain.interface.deploy_contract(
            'PolicyManagerForMinersEscrowMock', token.address, contract.address
        )
        tx = contract.functions.setPolicyManager(policy_manager.address).transact()
        testerchain.wait_for_receipt(tx)
        assert policy_manager.address == contract.functions.policyManager().call()
        return contract

    return make_escrow
