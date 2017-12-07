def test_alice_enacts_policies_in_policy_group_via_rest(enacted_policy_group):
    """
    Now that Alice has made a PolicyGroup, she can enact its policies, using Ursula's Public Key to encrypt each offer
    and transmitting them via REST.
    """
    ursula = enacted_policy_group.policies[0].ursula
    kfrag_that_was_set = ursula.keystore.get_kfrag(enacted_policy_group.hrac())
    assert bool(kfrag_that_was_set)  # TODO: This can be a more poignant assertion.
