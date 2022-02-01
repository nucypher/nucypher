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


from unittest.mock import patch

import pytest

from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import TransactingPower
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.blockchain.eth.actors import Trustee
from nucypher.blockchain.eth.deployers import MultiSigDeployer


@pytest.mark.skip()
def test_trustee_proposes_multisig_management_operations(testerchain, test_registry):
    origin = testerchain.etherbase_account
    tpower = TransactingPower(account=origin, signer=Web3Signer(testerchain.client))
    multisig_deployer = MultiSigDeployer(registry=test_registry)

    threshold = 2
    owners = testerchain.unassigned_accounts[0:3]
    receipts = multisig_deployer.deploy(threshold=threshold, owners=owners, transacting_power=tpower)
    for step in multisig_deployer.deployment_steps:
        assert receipts[step]['status'] == 1

    multisig_agent = multisig_deployer.make_agent()

    trustee_address = testerchain.unassigned_accounts[-1]
    trustee = Trustee(checksum_address=trustee_address,
                      domain=TEMPORARY_DOMAIN,
                      signer=Web3Signer(testerchain.client),
                      registry=test_registry,
                      is_transacting=True)

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
