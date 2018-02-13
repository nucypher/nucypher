def test_alice_enacts_policies_in_policy_group_via_rest(enacted_policy):
    """
    Now that Alice has made a PolicyGroup, she can enact its policies, using Ursula's Public Key to encrypt each offer
    and transmitting them via REST.
    """
    ursula = list(enacted_policy._accepted_contracts.values())[0].ursula
    policy_contract = ursula.keystore.get_policy_contract(enacted_policy.hrac().hex().encode())
    assert bool(policy_contract)  # TODO: This can be a more poignant assertion.
