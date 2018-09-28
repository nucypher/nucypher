import datetime
import maya
import pytest
from umbral.fragments import KFrag

from nucypher.crypto.api import keccak_digest
from nucypher.utilities.sandbox.policy import MockPolicyCreation


@pytest.mark.skip(reason="to be implemented")
@pytest.mark.usefixtures('blockchain_ursulas')
def test_mocked_decentralized_grant(blockchain_alice, blockchain_bob, three_agents):

    # Monkey patch KFrag repr for better debugging.
    KFrag.__repr__ = lambda kfrag: "KFrag: {}".format(bytes(kfrag)[:10].hex())

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
        retrieved_kfrag = KFrag.from_bytes(retrieved_policy.k_frag)

        assert kfrag == retrieved_kfrag


@pytest.mark.usefixtures('federated_ursulas')
def test_federated_grant(federated_alice, federated_bob):

    # Monkey patch KFrag repr for better debugging.
    KFrag.__repr__ = lambda kfrag: "KFrag: {}".format(bytes(kfrag)[:10].hex())

    # Setup the policy details
    n = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    # Create the Policy, Grating access to Bob
    policy = federated_alice.grant(federated_bob, label, m=2, n=n, expiration=policy_end_datetime)

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
        retrieved_kfrag = KFrag.from_bytes(retrieved_policy.k_frag)

        assert kfrag == retrieved_kfrag
