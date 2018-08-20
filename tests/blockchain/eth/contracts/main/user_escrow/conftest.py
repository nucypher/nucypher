import pytest
from web3.contract import Contract


@pytest.fixture()
def token(testerchain):
    # Create an ERC20 token
    token, _ = testerchain.interface.deploy_contract('NuCypherToken', int(2e9))
    return token


@pytest.fixture()
def escrow(testerchain, token):
    creator = testerchain.interface.w3.eth.accounts[0]
    # Creator deploys the escrow
    contract, _ = testerchain.interface.deploy_contract('MinersEscrowForUserEscrowMock', token.address)

    # Give some coins to the escrow
    tx = token.functions.transfer(contract.address, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    return contract


@pytest.fixture()
def policy_manager(testerchain):
    contract, _ = testerchain.interface.deploy_contract('PolicyManagerForUserEscrowMock')
    return contract


@pytest.fixture()
def government(testerchain):
    contract, _ = testerchain.interface.deploy_contract('GovernmentForUserEscrowMock')
    return contract


@pytest.fixture()
def proxy(testerchain, token, escrow, policy_manager, government):
    # Creator deploys the user escrow proxy
    contract, _ = testerchain.interface.deploy_contract(
        'UserEscrowProxy', token.address, escrow.address, policy_manager.address, government.address)
    return contract


@pytest.fixture()
def linker(testerchain, proxy):
    linker, _ = testerchain.interface.deploy_contract('UserEscrowLibraryLinker', proxy.address)
    return linker


@pytest.fixture()
def user_escrow(testerchain, token, linker):
    creator = testerchain.interface.w3.eth.accounts[0]
    user = testerchain.interface.w3.eth.accounts[1]

    contract, _ = testerchain.interface.deploy_contract('UserEscrow', linker.address, token.address)

    # Transfer ownership
    tx = contract.functions.transferOwnership(user).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    return contract


@pytest.fixture()
def user_escrow_proxy(testerchain, proxy, user_escrow):
    return testerchain.interface.w3.eth.contract(
        abi=proxy.abi,
        address=user_escrow.address,
        ContractFactoryClass=Contract)
