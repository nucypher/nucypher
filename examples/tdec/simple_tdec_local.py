from nucypher.characters.chaotic import NiceGuyEddie, ThisBobAlwaysDecrypts
from nucypher.policy.conditions.lingo import ConditionLingo

plaintext = b"paz al amanecer"
THIS_IS_NOT_A_TRINKET = 55

enrico = NiceGuyEddie(encrypting_key=THIS_IS_NOT_A_TRINKET)
bob = ThisBobAlwaysDecrypts(domain="lynx", eth_provider_uri="Nowhere")

ANYTHING_CAN_BE_PASSED_AS_RITUAL_ID = 55

before_the_beginning_of_time = {
    "version": ConditionLingo.VERSION,
    "condition": {
        "chain": 1,
        "method": "blocktime",
        "returnValueTest": {"comparator": "<", "value": 0},
    },
}

ciphertext, tdr = enrico.encrypt_for_dkg_and_produce_decryption_request(
    plaintext=plaintext,
    conditions=before_the_beginning_of_time,
    ritual_id=ANYTHING_CAN_BE_PASSED_AS_RITUAL_ID,
)

cleartest_from_tdr = bob.threshold_decrypt(
    ciphertext=ciphertext,
    ritual_id=ANYTHING_CAN_BE_PASSED_AS_RITUAL_ID,
    conditions=before_the_beginning_of_time,
)



cohort = bob._dkg_insight.fake_ritual.fake_nodes

cleartext_from_ciphertext = bob.decrypt_using_existing_decryption_request(
    tdr,
    participant_public_keys=bob._dkg_insight.fake_ritual.participant_public_keys,
    cohort=cohort,
    threshold=1,
)

decoded_cleartext_from_ciphertext = bytes(cleartext_from_ciphertext)
decoded_cleartext_from_tdr = bytes(cleartest_from_tdr)

assert decoded_cleartext_from_ciphertext == plaintext
assert plaintext == decoded_cleartext_from_tdr
print(f"Decrypted cleartext: {decoded_cleartext_from_ciphertext}")
