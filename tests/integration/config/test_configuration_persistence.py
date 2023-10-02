import datetime

import maya

from nucypher.characters.lawful import Bob
from nucypher.config.characters import AliceConfiguration
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import DecryptingPower, SigningPower
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD, MOCK_ETH_PROVIDER_URI
from tests.utils.middleware import MockRestMiddleware


def test_alices_powers_are_persistent(ursulas, temp_dir_path, testerchain):
    # Create a non-learning AliceConfiguration
    config_root = temp_dir_path / 'nucypher-custom-alice-config'
    alice_config = AliceConfiguration(
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
        config_root=config_root,
        network_middleware=MockRestMiddleware(eth_provider_uri=MOCK_ETH_PROVIDER_URI),
        domain=TEMPORARY_DOMAIN,
        checksum_address=testerchain.alice_account,
        start_learning_now=False,
        save_metadata=False,
        reload_metadata=False,
        known_nodes=ursulas,
    )

    # Generate keys and write them the disk
    alice_config.initialize(password=INSECURE_DEVELOPMENT_PASSWORD)

    # Unlock Alice's keystore
    alice_config.keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)

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
    threshold, shares = 3, 4
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)

    bob = Bob(
        start_learning_now=False,
        domain=TEMPORARY_DOMAIN,
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
        network_middleware=MockRestMiddleware(eth_provider_uri=MOCK_ETH_PROVIDER_URI),
    )

    bob_policy = alice.grant(bob, label, threshold=threshold, shares=shares, expiration=policy_end_datetime)

    assert policy_pubkey == bob_policy.public_key

    # ... and Alice and her configuration disappear.
    alice.disenchant()
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
        network_middleware=MockRestMiddleware(eth_provider_uri=MOCK_ETH_PROVIDER_URI),
        start_learning_now=False,
        config_root=config_root,
        known_nodes=ursulas,
    )

    # Alice unlocks her restored keystore from disk
    new_alice_config.keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
    new_alice = new_alice_config()

    # First, we check that her public keys are correctly restored
    assert alices_verifying_key == new_alice.public_keys(SigningPower)
    assert alices_receiving_key == new_alice.public_keys(DecryptingPower)

    # Bob's eldest brother, Roberto, appears too
    roberto = Bob(
        domain=TEMPORARY_DOMAIN,
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
        start_learning_now=False,
        network_middleware=MockRestMiddleware(eth_provider_uri=MOCK_ETH_PROVIDER_URI),
    )

    # Alice creates a new policy for Roberto. Note how all the parameters
    # except for the label (i.e., recipient, m, n, policy_end) are different
    # from previous policy
    threshold, shares = 2, 5
    policy_end_datetime = maya.now() + datetime.timedelta(days=3)
    roberto_policy = new_alice.grant(roberto, label, threshold=threshold, shares=shares, expiration=policy_end_datetime)

    # Both policies must share the same public key (i.e., the policy public key)
    assert policy_pubkey == roberto_policy.public_key
    new_alice.disenchant()
