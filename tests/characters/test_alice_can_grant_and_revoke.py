import datetime

import maya
import pytest
from apistar.test import TestClient
from bytestring_splitter import BytestringSplitter
from constant_sorrow import constants
from umbral.fragments import KFrag
from umbral.keys import UmbralPublicKey

from nucypher.characters import Ursula
from nucypher.crypto.api import keccak_digest
from nucypher.crypto.powers import SigningPower, EncryptingPower


def test_grant(alice, bob, mining_ursulas, three_agents):

    ursula, *other_ursulas = mining_ursulas

    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    n = 3
    label = b"this_is_the_path_to_which_access_is_being_granted"
    _token_agent, _miner_agent, policy_agent = three_agents

    class MockPolicyCreation:

        waited_for_receipt = False
        tx_hash = "THIS HAS BEEN A TRANSACTION!"

        def __init__(self, *args, **kwargs):
            # TODO: Test that proper arguments are passed here once 316 is closed.
            pass

        def transact(self, payload):
            # TODO: Make a meaningful assertion regarding the value.
            assert payload['from'] == alice.ether_address
            return self.tx_hash

        @classmethod
        def wait_for_receipt(cls, tx_hash):
            assert tx_hash == cls.tx_hash
            cls.waited_for_receipt = True

    policy_agent.blockchain.wait_for_receipt = MockPolicyCreation.wait_for_receipt

    policy_agent.contract.functions.createPolicy = MockPolicyCreation

    policy = alice.grant(bob, label, m=2, n=n, expiration=policy_end_datetime)

    # The number of accepted arrangements is equal to the number of Ursulas we're using (n)
    assert len(policy._accepted_arrangements) == n

    # Let's look at the first Ursula.
    ursula = policy._accepted_arrangements[0].ursula

    # Get the Arrangement from Ursula's datastore, looking up by hrac.
    # This will be changed in 180, when we use the Arrangement ID.
    proper_hrac = keccak_digest(bytes(alice.stamp) + bytes(bob.stamp) + label)
    retrieved_policy = ursula.datastore.get_policy_arrangement(proper_hrac.hex().encode())
    retrieved_k_frag = KFrag.from_bytes(retrieved_policy.k_frag)

    # TODO: Implement KFrag.__eq__
    found = False
    for k_frag in policy.kfrags:
        if bytes(k_frag) == bytes(retrieved_k_frag):
            found = True
    assert found


@pytest.mark.usefixtures('deployed_testerchain')
def test_alice_can_get_ursulas_keys_via_rest(ursulas):
    mock_client = TestClient(ursulas[0].rest_app)
    response = mock_client.get('http://localhost/public_keys')
    splitter = BytestringSplitter(
        (UmbralPublicKey, constants.PUBLIC_KEY_LENGTH),
        (UmbralPublicKey, constants.PUBLIC_KEY_LENGTH)
    )
    signing_key, encrypting_key = splitter(response.content)
    public_keys = {SigningPower: signing_key, EncryptingPower: encrypting_key}
    stranger_ursula_from_public_keys = Ursula.from_public_keys(public_keys)
    assert stranger_ursula_from_public_keys == ursulas[0]

