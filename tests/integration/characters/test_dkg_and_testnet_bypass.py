import pytest

from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.characters.chaotic import (
    NiceGuyEddie,
    ThisBobAlwaysDecrypts,
    ThisBobAlwaysFails,
)
from nucypher.characters.lawful import Ursula
from nucypher.policy.conditions.lingo import ConditionLingo
from tests.constants import (
    MOCK_ETH_PROVIDER_URI,
    MOCK_REGISTRY_FILEPATH,
    TESTERCHAIN_CHAIN_ID,
)


def _attempt_decryption(BobClass, plaintext, testerchain):
    trinket = 80  # Doens't matter.

    signer = Web3Signer(client=testerchain.client)
    enrico = NiceGuyEddie(encrypting_key=trinket, signer=signer)
    bob = BobClass(
        registry=MOCK_REGISTRY_FILEPATH,
        domain="lynx",
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
    )

    definitely_false_condition = {
        "version": ConditionLingo.VERSION,
        "condition": {
            "conditionType": "time",
            "chain": TESTERCHAIN_CHAIN_ID,
            "method": "blocktime",
            "returnValueTest": {"comparator": "<", "value": 0},
        },
    }

    threshold_message_kit = enrico.encrypt_for_dkg(
        plaintext=plaintext,
        conditions=definitely_false_condition,
    )

    decrypted_cleartext = bob.threshold_decrypt(
        threshold_message_kit=threshold_message_kit,
    )

    return decrypted_cleartext


@pytest.mark.usefixtures("mock_sign_message")
def test_user_controls_success(testerchain):
    plaintext = b"ever thus to deadbeats"
    result = _attempt_decryption(ThisBobAlwaysDecrypts, plaintext, testerchain)
    assert bytes(result) == bytes(plaintext)


@pytest.mark.usefixtures("mock_sign_message")
def test_user_controls_failure(testerchain):
    plaintext = b"ever thus to deadbeats"
    with pytest.raises(Ursula.NotEnoughUrsulas):
        _ = _attempt_decryption(ThisBobAlwaysFails, plaintext, testerchain)
