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
import maya

from nucypher.characters.lawful import Bob
from nucypher.config.characters import AliceConfiguration
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import DecryptingPower, SigningPower
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD
from tests.utils.middleware import MockRestMiddleware


def test_alices_powers_are_persistent(federated_ursulas, temp_dir_path):
    # Create a non-learning AliceConfiguration
    config_root = temp_dir_path / 'nucypher-custom-alice-config'
    alice_config = AliceConfiguration(
        config_root=config_root,
        network_middleware=MockRestMiddleware(),
        domain=TEMPORARY_DOMAIN,
        start_learning_now=False,
        federated_only=True,
        save_metadata=False,
        reload_metadata=False
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
    m, n = 3, 4
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)

    bob = Bob(federated_only=True,
              start_learning_now=False,
              network_middleware=MockRestMiddleware())

    bob_policy = alice.grant(bob, label, m=m, n=n, expiration=policy_end_datetime)

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
        network_middleware=MockRestMiddleware(),
        known_nodes=federated_ursulas,
        start_learning_now=False,
        config_root=config_root
    )

    # Alice unlocks her restored keystore from disk
    new_alice_config.keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
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
    new_alice.disenchant()
