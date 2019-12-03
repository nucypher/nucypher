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


import datetime
import os
import shutil

import maya
import pytest
from umbral.kfrags import KFrag

from nucypher.characters.lawful import Bob, Enrico
from nucypher.config.characters import AliceConfiguration
from nucypher.crypto.api import keccak_digest
from nucypher.crypto.kits import RevocationKit
from nucypher.crypto.powers import SigningPower, DecryptingPower
from nucypher.crypto.utils import construct_policy_id
from nucypher.keystore.keystore import KeyStore, NotFound
from nucypher.policy.collections import Revocation, PolicyCredential
from nucypher.policy.policies import BlockchainPolicy, Policy
from nucypher.storage.policy import LocalFilePolicyCredentialStorage
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD
from nucypher.utilities.sandbox.middleware import MockRestMiddleware


@pytest.mark.usefixtures('blockchain_ursulas')
def test_decentralized_grant(blockchain_alice, blockchain_bob, agency):

    # Setup the policy details
    n = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    # Create the Policy, Granting access to Bob
    policy = blockchain_alice.grant(bob=blockchain_bob,
                                    label=label,
                                    m=2,
                                    n=n,
                                    rate=int(1e18),  # one ether
                                    expiration=policy_end_datetime)

    # Check the policy ID
    policy_id = construct_policy_id(label=label,
                                    stamp=bytes(policy.bob.stamp),
                                    truncate=BlockchainPolicy.ID_LENGTH)
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


def test_read_cached_policies(blockchain_alice):
    assert len(blockchain_alice.active_policies) == 1
    policy_id, cached_policy = list(blockchain_alice.active_policies.items())[0]
    assert len(policy_id) == BlockchainPolicy.ID_LENGTH
    assert cached_policy.n == 3


def test_read_policy_credential_storage(blockchain_alice):
    cached_policy = list(blockchain_alice.active_policies.values())[0]
    loaded_credential = blockchain_alice.credential_storage.load(policy_id=cached_policy.id)
    assert loaded_credential.id == cached_policy.id

    all_credentials = list(blockchain_alice.credential_storage.all())
    assert len(all_credentials) == 1


def test_manual_policy_credential_creation(blockchain_alice):

    policy = list(blockchain_alice.active_policies.values())[0]

    def assert_content_is_valid(c):
        assert c.label == policy.label
        assert c.alice_stamp == policy.alice.stamp
        assert bytes(c.alice_stamp) == bytes(policy.alice.stamp)
        assert c.bob_stamp == policy.bob.stamp
        assert bytes(c.bob_stamp) == bytes(policy.bob.stamp)
        assert c.policy_encrypting_key == policy.public_key
        assert bytes(c.policy_encrypting_key) == bytes(policy.public_key)
        return True

    # Test PolicyCredential w/o TreasureMap
    credential = policy.credential(with_treasure_map=False)

    assert assert_content_is_valid(c=credential)
    assert credential.treasure_map is None

    cred_json = credential.to_json()
    deserialized_cred = PolicyCredential.from_json(cred_json)
    assert credential == deserialized_cred

    # Test PolicyCredential w/ TreasureMap
    credential = policy.credential()
    assert assert_content_is_valid(c=credential)
    assert credential.treasure_map == policy.treasure_map

    cred_json = credential.to_json()
    deserialized_cred = PolicyCredential.from_json(cred_json)
    assert credential == deserialized_cred
    assert credential.alice_stamp == deserialized_cred.alice_stamp


def test_restore_policy_from_credential_storage(blockchain_alice, temp_dir_path):
    test_credentials_dir = temp_dir_path
    if os.path.exists(test_credentials_dir):
        shutil.rmtree(test_credentials_dir, ignore_errors=True)
    file_storage = LocalFilePolicyCredentialStorage(credential_dir=test_credentials_dir)

    policy = list(blockchain_alice.active_policies.values())[0]
    credential = policy.credential()

    original_credential_storage = blockchain_alice.credential_storage
    try:
        blockchain_alice.credential_storage = file_storage
        expected_filename = f"{credential.id.hex()}.{LocalFilePolicyCredentialStorage.extension}"
        expected_filepath = os.path.join(test_credentials_dir, expected_filename)

        assert not os.path.exists(expected_filepath)
        filepath = file_storage.save(credential=credential)
        assert filepath == expected_filepath
        assert os.path.exists(filepath)

        restored_credential = file_storage.load(policy_id=credential.id)
        assert restored_credential == credential

        blockchain_alice._Alice__active_policies = {}
        assert len(blockchain_alice.active_policies) == 0
        blockchain_alice.restore_policies()
        assert len(blockchain_alice.active_policies) == 1

        restored_policy = list(blockchain_alice.active_policies.values())[0]
        assert restored_policy.id == policy.id

    finally:
        blockchain_alice.credential_storage = original_credential_storage


def test_decentralized_revoke_with_treasure_map(testerchain, blockchain_alice):

    # Restore saved Policy Credential with Treasure Map
    blockchain_alice._Alice__active_policies = dict()
    blockchain_alice.restore_policies()
    policy = list(blockchain_alice.active_policies.values())[0]

    # Contract reports active policy
    assert not blockchain_alice.policy_agent.fetch_policy(policy.id)[-1]

    # Let's look at the published arrangements. Each ursula has an arrangement in it' datastore.
    for ursula_address, arrangement_id in policy.treasure_map.destinations.items():
        ursula = blockchain_alice.known_nodes[ursula_address]
        assert ursula.datastore.get_policy_arrangement(arrangement_id.hex().encode())

    receipt, failed_revocations = blockchain_alice.revoke(policy)

    # Successful requests to Ursulas for fragment deletion
    assert failed_revocations == {}  # No Failed Revocations  # TODO ... What if there *are* failed revocations?

    # Positive revocation receipt
    assert receipt['status'] == 1

    # Positive policy-local state update
    assert policy._is_revoked

    # Contract reports inactive policy
    assert blockchain_alice.policy_agent.fetch_policy(policy.id)[-1]

    # Let's look for the revoked arrangements.  The Ursulas no longer have the arrangement record.
    for ursula_address, arrangement_id in policy.treasure_map.destinations.items():
        ursula = blockchain_alice.known_nodes[ursula_address]
        with pytest.raises(NotFound):
            ursula.datastore.get_policy_arrangement(arrangement_id.hex().encode())


@pytest.mark.usefixtures('federated_ursulas')
def test_federated_grant(federated_alice, federated_bob):

    # Setup the policy details
    m, n = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    # Create the Policy, granting access to Bob
    policy = federated_alice.grant(federated_bob, label, m=m, n=n, expiration=policy_end_datetime)

    # Check the policy ID
    policy_id = keccak_digest(policy.label + bytes(policy.bob.stamp))[:Policy.ID_LENGTH]
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


def test_federated_alice_can_decrypt(federated_alice, federated_bob):
    """
    Test that alice can decrypt data encrypted by an enrico
    for her own derived policy pubkey.
    """

    # Setup the policy details
    m, n = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    policy = federated_alice.create_policy(
        bob=federated_bob,
        label=label,
        m=m,
        n=n,
        expiration=policy_end_datetime,
    )

    enrico = Enrico.from_alice(
        federated_alice,
        policy.label,
    )
    plaintext = b"this is the first thing i'm encrypting ever."

    # use the enrico to encrypt the message
    message_kit, signature = enrico.encrypt_message(plaintext)

    # decrypt the data
    decrypted_data = federated_alice.verify_from(
        enrico,
        message_kit,
        signature=signature,
        decrypt=True,
        label=policy.label
    )

    assert plaintext == decrypted_data


@pytest.mark.usefixtures('federated_ursulas')
def test_federated_revocation(federated_alice, federated_bob):
    m, n = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"revocation test"

    policy = federated_alice.grant(federated_bob, label, m=m, n=n, expiration=policy_end_datetime)

    # Test that all arrangements are included in the RevocationKit
    revocation_kit = RevocationKit.from_treasure_map(treasure_map=policy.treasure_map, signer=federated_alice.stamp)
    for node_id, arrangement_id in policy.treasure_map:
        assert revocation_kit[node_id].arrangement_id == arrangement_id

    # Test revocation kit's signatures
    for revocation in revocation_kit:
        assert revocation.verify_signature(federated_alice.stamp.as_umbral_pubkey())

    # Test Revocation deserialization
    revocation = revocation_kit[node_id]
    revocation_bytes = bytes(revocation)
    deserialized_revocation = Revocation.from_bytes(revocation_bytes)
    assert deserialized_revocation == revocation

    # Attempt to revoke the new policy
    receipt, failed_revocations = federated_alice.revoke(policy)
    assert len(failed_revocations) == 0

    # Try to revoke the already revoked policy
    receipt, already_revoked = federated_alice.revoke(policy)
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
        reload_metadata=False
    )

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
    policy_pubkey = alice.get_policy_encrypting_key_from_label(label)

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
    new_alice_config.attach_keyring()
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
