def test_alice_enacts_policies_in_policy_group_via_rest(enacted_federated_policy):
    """
    Now that Alice has made a PolicyGroup, she can enact its policies, using Ursula's Public Key to encrypt each offer
    and transmitting them via REST.
    """
    arrangement = list(enacted_federated_policy._accepted_arrangements)[0]
    ursula = arrangement.ursula
    policy_arrangement = ursula.datastore.get_policy_arrangement(arrangement.id.hex().encode())
    assert bool(policy_arrangement)  # TODO: This can be a more poignant assertion.
