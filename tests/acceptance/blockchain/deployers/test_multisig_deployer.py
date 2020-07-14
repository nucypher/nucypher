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

from nucypher.blockchain.eth.agents import MultiSigAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.deployers import MultiSigDeployer


def test_multisig_deployer_and_agent(testerchain,
                                     deployment_progress,
                                     test_registry):
    origin = testerchain.etherbase_account
    multisig_deployer = MultiSigDeployer(deployer_address=origin, registry=test_registry)

    # Can't have a threshold of 0
    with pytest.raises(ValueError):
        owners = testerchain.unassigned_accounts[0:3]
        _ = multisig_deployer.deploy(threshold=0, owners=owners)

    # Can't have no owners
    with pytest.raises(ValueError):
        _ = multisig_deployer.deploy(threshold=1, owners=[])

    # Can't have the zero address as an owner
    with pytest.raises(ValueError):
        owners = testerchain.unassigned_accounts[0:3] + [NULL_ADDRESS]
        _ = multisig_deployer.deploy(threshold=1, owners=owners)

    # Can't have repeated owners
    with pytest.raises(ValueError):
        owners = testerchain.unassigned_accounts[0] * 3
        _ = multisig_deployer.deploy(threshold=1, owners=owners)

    # At last, sane initialization arguments for the MultiSig
    threshold = 2
    owners = testerchain.unassigned_accounts[0:3]
    receipts = multisig_deployer.deploy(threshold=threshold, owners=owners)
    for step in multisig_deployer.deployment_steps:
        assert receipts[step]['status'] == 1

    multisig_agent = multisig_deployer.make_agent()  # type: MultiSigAgent

    assert multisig_agent.nonce == 0
    assert multisig_agent.threshold == threshold
    assert multisig_agent.number_of_owners == len(owners)
    for i, owner in enumerate(owners):
        assert multisig_agent.get_owner(i) == owner
        assert multisig_agent.is_owner(owner)
    assert multisig_agent.owners == tuple(owners)
