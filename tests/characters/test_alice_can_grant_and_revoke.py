import datetime

import maya
import pytest
from apistar.test import TestClient

from nucypher.characters import Ursula
from nucypher.crypto.api import keccak_digest
from nucypher.crypto.powers import SigningPower, EncryptingPower, CryptoPower
from tests.utilities import _ALL_URSULAS
from umbral.fragments import KFrag


class MockPolicyCreation:
    """
    Simple mock logic to avoid repeated hammering of blockchain policies.
    """
    waited_for_receipt = False
    tx_hash = "THIS HAS BEEN A TRANSACTION!"

    def __init__(self, *args, **kwargs):
        # TODO: Test that proper arguments are passed here once 316 is closed.
        pass

    def transact(self, payload):
        # TODO: Make a meaningful assertion regarding the value.
        assert payload['from'] == alice._ether_address
        return self.tx_hash

    @classmethod
    def wait_for_receipt(cls, tx_hash):
        assert tx_hash == cls.tx_hash
        cls.waited_for_receipt = True


def test_grant(alice, bob, three_agents):
    # Monkey patch KFrag repr for better debugging.
    KFrag.__repr__ = lambda kfrag: "KFrag: {}".format(bytes(kfrag)[:10].hex())

    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    n = 3
    label = b"this_is_the_path_to_which_access_is_being_granted"
    _token_agent, _miner_agent, policy_agent = three_agents

    policy_agent.blockchain.wait_for_receipt = MockPolicyCreation.wait_for_receipt
    policy_agent.contract.functions.createPolicy = MockPolicyCreation

    policy = alice.grant(bob, label, m=2, n=n,
                         expiration=policy_end_datetime,
                         )

    # The number of accepted arrangements at least the number of Ursulas we're using (n)
    assert len(policy._accepted_arrangements) >= n

    # The number of actually enacted arrangements is exactly equal to n.
    assert len(policy._enacted_arrangements) == n

    # Let's look at the enacted arrangements.
    for kfrag in policy.kfrags:
        arrangement = policy._enacted_arrangements[kfrag]
        ursula = _ALL_URSULAS[arrangement.ursula.rest_interface.port]

        # Get the Arrangement from Ursula's datastore, looking up by hrac.
        # This will be changed in 180, when we use the Arrangement ID.
        proper_hrac = keccak_digest(bytes(alice.stamp) + bytes(bob.stamp) + label)
        retrieved_policy = ursula.datastore.get_policy_arrangement(arrangement.id.hex().encode())
        retrieved_kfrag = KFrag.from_bytes(retrieved_policy.k_frag)

        assert kfrag == retrieved_kfrag


@pytest.mark.usefixtures('testerchain')
def test_alice_can_get_ursulas_keys_via_rest(ursulas):
    ursula = ursulas.pop()
    mock_client = TestClient(ursula.rest_app)
    response = mock_client.get('http://localhost/public_information')
    signature, signing_key, encrypting_key, public_address = Ursula.public_information_splitter(response.content)
    public_keys = {SigningPower: signing_key, EncryptingPower: encrypting_key}
    stranger_ursula_from_public_keys = Ursula.from_public_keys(public_keys,
                                                               rest_port=5000,
                                                               rest_host="not real")
    assert stranger_ursula_from_public_keys == ursula

