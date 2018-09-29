import pytest
from web3.contract import Contract


secret = (123456).to_bytes(32, byteorder='big')


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
def proxy(testerchain, token, escrow, policy_manager):
    # Creator deploys the user escrow proxy
    contract, _ = testerchain.interface.deploy_contract(
        'UserEscrowProxy', token.address, escrow.address, policy_manager.address)
    return contract


@pytest.fixture()
def linker(testerchain, proxy):
    secret_hash = testerchain.interface.w3.sha3(secret)
    linker, _ = testerchain.interface.deploy_contract('UserEscrowLibraryLinker', proxy.address, secret_hash)
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
