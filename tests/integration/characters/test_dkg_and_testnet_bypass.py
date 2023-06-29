from nucypher.characters.chaotic import NiceGuyEddie, ThisBobAlwaysDecrypts
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.policy.conditions.lingo import ConditionLingo
from tests.constants import (
    MOCK_ETH_PROVIDER_URI,
    MOCK_REGISTRY_FILEPATH,
    TESTERCHAIN_CHAIN_ID,
)


def test_always_success():
    trinket = 80  # Doens't matter.

    enrico = NiceGuyEddie(encrypting_key=trinket)
    bob = ThisBobAlwaysDecrypts(
        registry=MOCK_REGISTRY_FILEPATH,
        domain="lynx",
        eth_provider_uri=MOCK_ETH_PROVIDER_URI,
    )

    ANYTHING_CAN_BE_PASSED_AS_RITUAL_DATA = 55

    plaintext = b"ever thus to deadbeats"

    definitely_false_condition = {
        "version": ConditionLingo.VERSION,
        "condition": {
            "chain": TESTERCHAIN_CHAIN_ID,
            "method": "blocktime",
            "returnValueTest": {"comparator": "<", "value": 0},
        },
    }

    ciphertext, tdr = enrico.encrypt_for_dkg_and_produce_decryption_request(
        plaintext=plaintext,
        conditions=definitely_false_condition,
        ritual_id=ANYTHING_CAN_BE_PASSED_AS_RITUAL_DATA,
    )

    decrypted_cleartext_from_ciphertext_list = bob.threshold_decrypt(
        ciphertext=ciphertext,
        ritual_id=ANYTHING_CAN_BE_PASSED_AS_RITUAL_DATA,
        conditions=definitely_false_condition,
    )

    assert bytes(decrypted_cleartext_from_ciphertext_list) == bytes(plaintext)
