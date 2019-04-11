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


import os

import datetime
import maya
import pytest

from umbral.kfrags import KFrag

from nucypher.characters.lawful import Bob
from nucypher.config.characters import AliceConfiguration
from nucypher.crypto.api import keccak_digest
from nucypher.crypto.powers import SigningPower, DecryptingPower
from nucypher.policy.models import Revocation
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD
from nucypher.utilities.sandbox.middleware import MockRestMiddleware
from nucypher.utilities.sandbox.policy import MockPolicyCreation


@pytest.mark.skip(reason="to be implemented")  # TODO
@pytest.mark.usefixtures('blockchain_ursulas')
def test_mocked_decentralized_grant(blockchain_alice, blockchain_bob, three_agents):

    # Monkey patch Policy Creation
    _token_agent, _miner_agent, policy_agent = three_agents
    policy_agent.blockchain.wait_for_receipt = MockPolicyCreation.wait_for_receipt
    policy_agent.contract.functions.createPolicy = MockPolicyCreation

    # Setup the policy details
    n = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    # Create the Policy, Granting access to Bob
    policy = blockchain_alice.grant(blockchain_bob, label, m=2, n=n, expiration=policy_end_datetime)

    # Check the policy ID
    policy_id = keccak_digest(policy.label + bytes(policy.bob.stamp))
    assert policy_id == policy.id

    # The number of accepted arrangements at least the number of Ursulas we're using (n)
    assert len(policy._accepted_arrangements) >= n

    # The number of actually enacted arrangements is exactly equal to n.
    assert len(policy._enacted_arrangements) == n

    # Let's look at the enacted arrangements.
    for kfrag in policy.kfrags:
        arrangement = policy._enacted_arrangements[kfrag]

        # Get the Arrangement from Ursula's datastore, looking up by the Arrangement ID.
        retrieved_policy = arrangement.ursula.datastore.get_policy_arrangement(arrangement.id.hex().encode())
        retrieved_kfrag = KFrag.from_bytes(retrieved_policy.kfrag)

        assert kfrag == retrieved_kfrag


@pytest.mark.usefixtures('federated_ursulas')
def test_federated_grant(federated_alice, federated_bob):

    # Setup the policy details
    m, n = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    # Create the Policy, granting access to Bob
    policy = federated_alice.grant(federated_bob, label, m=m, n=n, expiration=policy_end_datetime)

    # Check the policy ID
    policy_id = keccak_digest(policy.label + bytes(policy.bob.stamp))
    assert policy_id == policy.id

    # Check Alice's active policies
    assert policy_id in federated_alice.active_policies
    assert federated_alice.active_policies[policy_id] == policy

    # The number of accepted arrangements at least the number of Ursulas we're using (n)
    assert len(policy._accepted_arrangements) >= n

    # The number of actually enacted arrangements is exactly equal to n.
    assert len(policy._enacted_arrangements) == n

    # Let's look at the enacted arrangements.
    for kfrag in policy.kfrags:
        arrangement = policy._enacted_arrangements[kfrag]

        # Get the Arrangement from Ursula's datastore, looking up by the Arrangement ID.
        retrieved_policy = arrangement.ursula.datastore.get_policy_arrangement(arrangement.id.hex().encode())
        retrieved_kfrag = KFrag.from_bytes(retrieved_policy.kfrag)

        assert kfrag == retrieved_kfrag


@pytest.mark.usefixtures('federated_ursulas')
def test_revocation(federated_alice, federated_bob):
    m, n = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"revocation test"

    policy = federated_alice.grant(federated_bob, label, m=m, n=n, expiration=policy_end_datetime)

    # Test that all arrangements are included in the RevocationKit
    for node_id, arrangement_id in policy.treasure_map:
        assert policy.revocation_kit[node_id].arrangement_id == arrangement_id

    # Test revocation kit's signatures
    for revocation in policy.revocation_kit:
        assert revocation.verify_signature(federated_alice.stamp.as_umbral_pubkey())

    # Test Revocation deserialization
    revocation = policy.revocation_kit[node_id]
    revocation_bytes = bytes(revocation)
    deserialized_revocation = Revocation.from_bytes(revocation_bytes)
    assert deserialized_revocation == revocation

    # Attempt to revoke the new policy
    failed_revocations = federated_alice.revoke(policy)
    assert len(failed_revocations) == 0

    # Try to revoke the already revoked policy
    already_revoked = federated_alice.revoke(policy)
    assert len(already_revoked) == 3


def test_alices_powers_are_persistent(federated_ursulas, tmpdir):

    # Create a non-learning AliceConfiguration
    alice_config = AliceConfiguration(
        config_root=os.path.join(tmpdir, 'nucypher-custom-alice-config'),
        network_middleware=MockRestMiddleware(),
        known_nodes=federated_ursulas,
        start_learning_now=False,
        federated_only=True,
        save_metadata=False,
        reload_metadata=False)

    # Generate keys and write them the disk
    alice_config.initialize(password=INSECURE_DEVELOPMENT_PASSWORD)

    # Unlock Alice's keyring
    alice_config.keyring.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)

    # Produce an Alice
    alice = alice_config()  # or alice_config.produce()

    # Save Alice's node configuration file to disk for later use
    alice_config_file = alice_config.to_configuration_file()

    # Let's save Alice's public keys too to check they are correctly restored later
    alices_verifying_key = alice.public_keys(SigningPower)
    alices_receiving_key = alice.public_keys(DecryptingPower)

    # Next, let's fix a label for all the policies we will create later.
    label = b"this_is_the_path_to_which_access_is_being_granted"

    # Even before creating the policies, we can know what will be its public key.
    # This can be used by Enrico (i.e., a Data Source) to encrypt messages
    # before Alice grants access to Bobs.
    policy_pubkey = alice.get_policy_pubkey_from_label(label)

    # Now, let's create a policy for some Bob.
    m, n = 3, 4
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)

    bob = Bob(federated_only=True,
              start_learning_now=False,
              network_middleware=MockRestMiddleware())

    bob_policy = alice.grant(bob, label, m=m, n=n, expiration=policy_end_datetime)

    assert policy_pubkey == bob_policy.public_key

    # ... and Alice and her configuration disappear.
    del alice
    del alice_config

    ###################################
    #        Some time passes.        #
    #               ...               #
    # (jmyles plays the Song of Time) #
    #               ...               #
    #       Alice appears again.      #
    ###################################

    # A new Alice is restored from the configuration file
    new_alice_config = AliceConfiguration.from_configuration_file(
        filepath=alice_config_file,
        network_middleware=MockRestMiddleware(),
        known_nodes=federated_ursulas,
        start_learning_now=False,
    )

    # Alice unlocks her restored keyring from disk
    new_alice_config.keyring.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
    new_alice = new_alice_config()

    # First, we check that her public keys are correctly restored
    assert alices_verifying_key == new_alice.public_keys(SigningPower)
    assert alices_receiving_key == new_alice.public_keys(DecryptingPower)

    # Bob's eldest brother, Roberto, appears too
    roberto = Bob(federated_only=True,
                  start_learning_now=False,
                  network_middleware=MockRestMiddleware())

    # Alice creates a new policy for Roberto. Note how all the parameters
    # except for the label (i.e., recipient, m, n, policy_end) are different
    # from previous policy
    m, n = 2, 5
    policy_end_datetime = maya.now() + datetime.timedelta(days=3)
    roberto_policy = new_alice.grant(roberto, label, m=m, n=n, expiration=policy_end_datetime)

    # Both policies must share the same public key (i.e., the policy public key)
    assert policy_pubkey == roberto_policy.public_key
