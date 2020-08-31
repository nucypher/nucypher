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
from unittest.mock import patch

from nucypher.blockchain.eth.actors import Trustee
from nucypher.blockchain.eth.agents import MultiSigAgent
from nucypher.blockchain.eth.deployers import MultiSigDeployer


def test_trustee_proposes_multisig_management_operations(testerchain, test_registry):
    origin = testerchain.etherbase_account
    multisig_deployer = MultiSigDeployer(deployer_address=origin, registry=test_registry)

    threshold = 2
    owners = testerchain.unassigned_accounts[0:3]
    receipts = multisig_deployer.deploy(threshold=threshold, owners=owners)
    for step in multisig_deployer.deployment_steps:
        assert receipts[step]['status'] == 1

    multisig_agent = multisig_deployer.make_agent()  # type: MultiSigAgent

    trustee_address = testerchain.unassigned_accounts[-1]
    trustee = Trustee(checksum_address=trustee_address, registry=test_registry)

    # Propose changing threshold
    free_payload = {'nonce': 0, 'from': multisig_agent.contract_address, 'gasPrice': 0}
    with patch.object(testerchain, 'build_payload', return_value=free_payload):
        proposal = trustee.propose_changing_threshold(new_threshold=1)

    assert proposal.trustee_address == trustee_address
    assert proposal.target_address == multisig_agent.contract_address
    assert proposal.nonce == multisig_agent.nonce
    assert proposal.value == 0

    contract_function, params = proposal.decode_transaction_data(registry=test_registry)
    assert list(params.values()) == [1]  # The new threshold is the only parameter in the call

    # Propose adding new owner

    new_owner = testerchain.unassigned_accounts[4]
    with patch.object(testerchain, 'build_payload', return_value=free_payload):
        proposal = trustee.propose_adding_owner(new_owner_address=new_owner, evidence=None)

    assert proposal.trustee_address == trustee_address
    assert proposal.target_address == multisig_agent.contract_address
    assert proposal.nonce == multisig_agent.nonce
    assert proposal.value == 0

    contract_function, params = proposal.decode_transaction_data(registry=test_registry)
    assert list(params.values()) == [new_owner]  # The new owner is the only parameter in the call

    # Propose removing owner

    evicted_owner = testerchain.unassigned_accounts[1]
    with patch.object(testerchain, 'build_payload', return_value=free_payload):
        proposal = trustee.propose_removing_owner(evicted_owner)

    assert proposal.trustee_address == trustee_address
    assert proposal.target_address == multisig_agent.contract_address
    assert proposal.nonce == multisig_agent.nonce
    assert proposal.value == 0

    contract_function, params = proposal.decode_transaction_data(registry=test_registry)
    assert list(params.values()) == [evicted_owner]  # The owner to remove is the only parameter in the call
