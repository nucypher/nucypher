

import pytest
from web3.contract import Contract

from nucypher.blockchain.economics import Economics
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.token import NU

TOTAL_SUPPLY = NU(1_000_000_000, 'NU').to_units()


@pytest.fixture()
def token(deploy_contract):
    # Create an ERC20 token
    token, _ = deploy_contract('NuCypherToken', _totalSupplyOfTokens=TOTAL_SUPPLY)
    return token


@pytest.fixture()
def worklock(deploy_contract, token):
    worklock, _ = deploy_contract('WorkLockForStakingEscrowMock', token.address)
    return worklock


@pytest.fixture()
def threshold_staking(deploy_contract):
    threshold_staking, _ = deploy_contract('ThresholdStakingForStakingEscrowMock')
    return threshold_staking


@pytest.fixture(params=[False, True])
def escrow(testerchain, token, worklock, threshold_staking, request, deploy_contract):
    contract, _ = deploy_contract(
        'EnhancedStakingEscrow',
        token.address,
        worklock.address,
        threshold_staking.address
    )

    if request.param:
        dispatcher, _ = deploy_contract('Dispatcher', contract.address)
        contract = testerchain.client.get_contract(
            abi=contract.abi,
            address=dispatcher.address,
            ContractFactoryClass=Contract)

    tx = worklock.functions.setStakingEscrow(contract.address).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakingEscrow(contract.address).transact()
    testerchain.wait_for_receipt(tx)

    assert contract.functions.token().call() == token.address
    assert contract.functions.workLock().call() == worklock.address

    return contract
