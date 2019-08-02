"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import pytest

from nucypher.blockchain.eth.deployers import (UserEscrowDeployer,
                                               UserEscrowProxyDeployer,
                                               LibraryLinkerDeployer)
from nucypher.crypto.api import keccak_digest
from nucypher.utilities.sandbox.constants import USER_ESCROW_PROXY_DEPLOYMENT_SECRET


user_escrow_contracts = list()
NUMBER_OF_PREALLOCATIONS = 50


@pytest.fixture(scope='module')
def user_escrow_proxy_deployer(session_testerchain, session_agency):
    print("ENTER USER ESCROW")
    testerchain = session_testerchain
    deployer = testerchain.etherbase_account
    user_escrow_proxy_deployer = UserEscrowProxyDeployer(deployer_address=deployer,
                                                         blockchain=testerchain)
    return user_escrow_proxy_deployer


@pytest.mark.slow()
def test_user_escrow_deployer(session_testerchain, session_agency, user_escrow_proxy_deployer, deployment_progress):
    testerchain = session_testerchain
    deployer_account = testerchain.etherbase_account
    secret_hash = keccak_digest(USER_ESCROW_PROXY_DEPLOYMENT_SECRET.encode())

    user_escrow_proxy_receipts = user_escrow_proxy_deployer.deploy(secret_hash=secret_hash,
                                                                   progress=deployment_progress)

    # deployment steps must match expected number of steps
    assert deployment_progress.num_steps == len(user_escrow_proxy_deployer.deployment_steps) == 2
    assert len(user_escrow_proxy_receipts) == 2

    for step in user_escrow_proxy_deployer.deployment_steps:
        assert user_escrow_proxy_receipts[step]['status'] == 1

    deployer = UserEscrowDeployer(deployer_address=deployer_account,
                                  blockchain=testerchain)

    receipt = deployer.deploy()
    assert receipt['status'] == 1


@pytest.mark.slow()
def test_deploy_multiple(session_testerchain, session_agency, user_escrow_proxy_deployer):
    testerchain = session_testerchain
    deployer_account = testerchain.etherbase_account

    linker_deployer = LibraryLinkerDeployer(blockchain=testerchain,
                                            deployer_address=deployer_account,
                                            target_contract=user_escrow_proxy_deployer.contract,
                                            bare=True)
    linker_address = linker_deployer.contract_address

    for index in range(NUMBER_OF_PREALLOCATIONS):
        deployer = UserEscrowDeployer(deployer_address=deployer_account, blockchain=testerchain)

        deployment_receipt = deployer.deploy()
        assert deployment_receipt['status'] == 1

        user_escrow_contract = deployer.contract
        linker = user_escrow_contract.functions.linker().call()
        assert linker == linker_address

        user_escrow_contracts.append(user_escrow_contract)

        # simulates passage of time / blocks
        if index % 5 == 0:
            testerchain.w3.eth.web3.testing.mine(1)
            testerchain.time_travel(seconds=5)

    assert len(user_escrow_contracts) == NUMBER_OF_PREALLOCATIONS


@pytest.mark.slow()
def test_upgrade_user_escrow_proxy(session_testerchain, session_agency, user_escrow_proxy_deployer):
    testerchain = session_testerchain
    agency = session_agency
    old_secret = USER_ESCROW_PROXY_DEPLOYMENT_SECRET.encode()
    new_secret = 'new' + USER_ESCROW_PROXY_DEPLOYMENT_SECRET
    new_secret_hash = keccak_digest(new_secret.encode())

    linker_deployer = LibraryLinkerDeployer(blockchain=testerchain,
                                            deployer_address=user_escrow_proxy_deployer.deployer_address,
                                            target_contract=user_escrow_proxy_deployer.contract,
                                            bare=True)
    linker_address = linker_deployer.contract_address

    target = linker_deployer.contract.functions.target().call()
    assert target == UserEscrowProxyDeployer.get_latest_version(blockchain=testerchain).address

    receipts = user_escrow_proxy_deployer.upgrade(existing_secret_plaintext=old_secret,
                                                  new_secret_hash=new_secret_hash)

    assert len(receipts) == 2

    for title, receipt in receipts.items():
        assert receipt['status'] == 1

    for user_escrow_contract in user_escrow_contracts:
        linker = user_escrow_contract.functions.linker().call()
        assert linker == linker_address

    new_target = linker_deployer.contract.functions.target().call()
    assert new_target == UserEscrowProxyDeployer.get_latest_version(blockchain=testerchain).address
    assert new_target != target
