"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import datetime
import maya
import os
import pytest
from umbral.fragments import KFrag

from nucypher.characters.lawful import Alice, Bob
from nucypher.config.characters import AliceConfiguration
from nucypher.config.storages import LocalFileBasedNodeStorage
from nucypher.crypto.api import keccak_digest
from nucypher.utilities.sandbox.constants import TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD
from nucypher.utilities.sandbox.middleware import MockRestMiddleware
from nucypher.utilities.sandbox.policy import MockPolicyCreation


@pytest.mark.skip(reason="to be implemented")
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

    # Create the Policy, Grating access to Bob
    policy = blockchain_alice.grant(blockchain_bob, label, m=2, n=n, expiration=policy_end_datetime)

    # The number of accepted arrangements at least the number of Ursulas we're using (n)
    assert len(policy._accepted_arrangements) >= n

    # The number of actually enacted arrangements is exactly equal to n.
    assert len(policy._enacted_arrangements) == n

    # Let's look at the enacted arrangements.
    for kfrag in policy.kfrags:
        arrangement = policy._enacted_arrangements[kfrag]

        # Get the Arrangement from Ursula's datastore, looking up by hrac.
        # This will be changed in 180, when we use the Arrangement ID.
        proper_hrac = keccak_digest(bytes(blockchain_alice.stamp) + bytes(blockchain_bob.stamp) + label)
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

    # The number of accepted arrangements at least the number of Ursulas we're using (n)
    assert len(policy._accepted_arrangements) >= n

    # The number of actually enacted arrangements is exactly equal to n.
    assert len(policy._enacted_arrangements) == n

    # Let's look at the enacted arrangements.
    for kfrag in policy.kfrags:
        arrangement = policy._enacted_arrangements[kfrag]

        # Get the Arrangement from Ursula's datastore, looking up by hrac.
        # This will be changed in 180, when we use the Arrangement ID.
        proper_hrac = keccak_digest(bytes(federated_alice.stamp) + bytes(federated_bob.stamp) + label)
        retrieved_policy = arrangement.ursula.datastore.get_policy_arrangement(arrangement.id.hex().encode())
        retrieved_kfrag = KFrag.from_bytes(retrieved_policy.kfrag)

        assert kfrag == retrieved_kfrag


def test_alice_delegation_power_is_persistent(federated_ursulas, tmpdir):

    passphrase = TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD

    # Let's create an Alice from a Configuration.
    # This requires creating a local storage for her first.
    node_storage = LocalFileBasedNodeStorage(
        federated_only=True,
        character_class=Alice,
        known_metadata_dir=os.path.join(tmpdir, "known_metadata"),
    )

    alice_config = AliceConfiguration(
        config_root=os.path.join(tmpdir, "config_root"),
        node_storage=node_storage,
        auto_initialize=True,
        auto_generate_keys=True,
        passphrase=passphrase,
        is_me=True,
        network_middleware=MockRestMiddleware(),
        known_nodes=federated_ursulas,
        start_learning_now=False,
        federated_only=True,
        # abort_on_learning_error=True,
        save_metadata=False,
        load_metadata=False
    )
    alice = alice_config(passphrase=passphrase)

    # We will save Alice's config to a file for later use
    alice_config_file = alice_config.to_configuration_file()

    # Now, let's create a policy for some Bob
    m, n = 3, 4
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    bob = Bob(federated_only=True,
              start_learning_now=False,
              network_middleware=MockRestMiddleware(),
              )

    bob_policy = alice.grant(bob, label, m=m, n=n, expiration=policy_end_datetime)

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

    new_alice_config = AliceConfiguration.from_configuration_file(
        filepath=alice_config_file,
        network_middleware=MockRestMiddleware(),
        known_nodes=federated_ursulas,
        start_learning_now=False,
    )

    new_alice = new_alice_config(passphrase=passphrase)

    # Bob's eldest brother, Roberto, appears too
    roberto = Bob(federated_only=True,
                  start_learning_now=False,
                  network_middleware=MockRestMiddleware(),
                  )

    # Alice creates a new policy for Roberto. Note how all the parameters
    # except for the label (i.e., recipient, m, n, policy_end) are different
    # from previous policy
    m, n = 2, 5
    policy_end_datetime = maya.now() + datetime.timedelta(days=3)
    roberto_policy = new_alice.grant(roberto, label, m=m, n=n, expiration=policy_end_datetime)

    # Both policies must share the same delegation public key
    assert bob_policy.public_key == roberto_policy.public_key

