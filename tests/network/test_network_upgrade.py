def test_alice_enacts_policies_in_policy_group_via_rest(enacted_federated_policy):
    """
    Now that Alice has made a PolicyGroup, she can enact its policies, using Ursula's Public Key to encrypt each offer
    and transmitting them via REST.
    """
    ursula = list(enacted_federated_policy._accepted_arrangements)[0].ursula
    policy_arrangement = ursula.datastore.get_policy_arrangement(enacted_federated_policy.hrac().hex().encode())
    assert bool(policy_arrangement)  # TODO: This can be a more poignant assertion.
