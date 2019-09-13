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

from nucypher.blockchain.eth.deployers import (
    UserEscrowDeployer,
    UserEscrowProxyDeployer,
    LibraryLinkerDeployer,
    NucypherTokenDeployer,
    StakingEscrowDeployer,
    PolicyManagerDeployer,
    AdjudicatorDeployer
)
from nucypher.crypto.api import keccak_digest
from nucypher.utilities.sandbox.constants import (
    USER_ESCROW_PROXY_DEPLOYMENT_SECRET,
    INSECURE_DEPLOYMENT_SECRET_PLAINTEXT,
    INSECURE_DEPLOYMENT_SECRET_HASH
)

user_escrow_contracts = list()
NUMBER_OF_PREALLOCATIONS = 50


@pytest.mark.slow()
def test_user_escrow_proxy_deployer(testerchain, deployment_progress, test_registry, test_economics):

    #
    # Setup
    #

    origin = testerchain.etherbase_account

    token_deployer = NucypherTokenDeployer(deployer_address=origin,
                                           registry=test_registry,
                                           economics=test_economics)
    token_deployer.deploy()

    staking_escrow_deployer = StakingEscrowDeployer(deployer_address=origin,
                                                    registry=test_registry,
                                                    economics=test_economics)
    staking_escrow_deployer.deploy(secret_hash=INSECURE_DEPLOYMENT_SECRET_HASH)

    policy_manager_deployer = PolicyManagerDeployer(deployer_address=origin,
                                                    registry=test_registry,
                                                    economics=test_economics)
    policy_manager_deployer.deploy(secret_hash=INSECURE_DEPLOYMENT_SECRET_HASH)

    adjudicator_deployer = AdjudicatorDeployer(deployer_address=origin,
                                               registry=test_registry,
                                               economics=test_economics)
    adjudicator_deployer.deploy(secret_hash=INSECURE_DEPLOYMENT_SECRET_HASH)

    #
    # Test
    #

    user_escrow_proxy_deployer = UserEscrowProxyDeployer(deployer_address=origin, registry=test_registry)
    user_escrow_proxy_receipts = user_escrow_proxy_deployer.deploy(secret_hash=INSECURE_DEPLOYMENT_SECRET_HASH,
                                                                   progress=deployment_progress)

    # deployment steps must match expected number of steps
    assert deployment_progress.num_steps == len(user_escrow_proxy_deployer.deployment_steps) == 2
    assert len(user_escrow_proxy_receipts) == 2

    for step in user_escrow_proxy_deployer.deployment_steps:
        assert user_escrow_proxy_receipts[step]['status'] == 1


@pytest.mark.slow()
def test_deploy_multiple_preallocations(testerchain, test_registry, test_economics):
    testerchain = testerchain
    deployer_account = testerchain.etherbase_account

    linker = testerchain.get_contract_by_name(registry=test_registry, name=LibraryLinkerDeployer.contract_name)
    linker_address = linker.address
    for index in range(NUMBER_OF_PREALLOCATIONS):
        deployer = UserEscrowDeployer(deployer_address=deployer_account,
                                      registry=test_registry,
                                      economics=test_economics)

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
def test_upgrade_user_escrow_proxy(testerchain, test_registry):

    old_secret = INSECURE_DEPLOYMENT_SECRET_PLAINTEXT
    new_secret = 'new' + USER_ESCROW_PROXY_DEPLOYMENT_SECRET
    new_secret_hash = keccak_digest(new_secret.encode())
    linker = testerchain.get_contract_by_name(registry=test_registry, name=LibraryLinkerDeployer.contract_name)

    contract = testerchain.get_contract_by_name(registry=test_registry,
                                                name=UserEscrowProxyDeployer.contract_name,
                                                proxy_name=LibraryLinkerDeployer.contract_name,
                                                use_proxy_address=False)

    target = linker.functions.target().call()
    assert target == contract.address

    user_escrow_proxy_deployer = UserEscrowProxyDeployer(deployer_address=testerchain.etherbase_account,
                                                         registry=test_registry)

    receipts = user_escrow_proxy_deployer.upgrade(existing_secret_plaintext=old_secret,
                                                  new_secret_hash=new_secret_hash)

    assert len(receipts) == 2

    for title, receipt in receipts.items():
        assert receipt['status'] == 1

    for user_escrow_contract in user_escrow_contracts:
        linker_address = user_escrow_contract.functions.linker().call()
        assert linker.address == linker_address

    new_target = linker.functions.target().call()
    contract = testerchain.get_contract_by_name(registry=test_registry,
                                                name=UserEscrowProxyDeployer.contract_name,
                                                proxy_name=LibraryLinkerDeployer.contract_name,
                                                use_proxy_address=False)
    assert new_target == contract.address
    assert new_target != target
