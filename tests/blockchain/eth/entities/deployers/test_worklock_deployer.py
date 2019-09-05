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
from eth_utils import is_checksum_address

from nucypher.blockchain.eth.agents import WorkLockAgent
from nucypher.blockchain.eth.deployers import WorklockDeployer
from nucypher.blockchain.eth.registry import BaseContractRegistry


def test_worklock_deployer(testerchain, test_registry, agency, token_economics):
    origin = testerchain.etherbase_account

    # Trying to get token from blockchain before it's been published fails
    with pytest.raises(BaseContractRegistry.UnknownContract):
        WorkLockAgent(registry=test_registry)

    # Generate WorkLock params
    # TODO: Move to "WorkLockEconomics" class #1126
    now = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    start_bid_date = now + (60 * 60)  # 1 Hour
    end_bid_date = start_bid_date + (60 * 60)
    deposit_rate = 100
    refund_rate = 200
    locked_periods = 2 * token_economics.minimum_locked_periods

    # Create WorkLock Deployer
    deployer = WorklockDeployer(blockchain=testerchain,
                                deployer_address=origin,
                                start_date=start_bid_date,
                                end_date=end_bid_date,
                                refund_rate=refund_rate,
                                deposit_rate=deposit_rate,
                                locked_periods=locked_periods)

    # Deploy WorkLock
    deployment_receipts = deployer.deploy()
    assert len(deployment_receipts) == 1

    # Create a token instance
    assert deployer.contract
    assert is_checksum_address(deployer.contract_address)
    assert deployer.contract.address == deployer.contract_address

    testerchain.registry.clear()
