from examples.tdec.demo_utilities.demo_sample_conditions import ten_oclock_florida_time
from nucypher.characters.chaotic import BobGonnaBob, NiceGuyEddie

plaintext = b"PEACE AD DAWN"
THIS_IS_NOT_A_TRINKET = 55

enrico = NiceGuyEddie(encrypting_key=THIS_IS_NOT_A_TRINKET)
bob = BobGonnaBob(domain="lynx")

aad = "my-aad".encode()

ANYTHING_CAN_BE_PASSED_AS_RITUAL_DATA = 55

ciphertext, tdr = enrico.encrypt_for_dkg_and_produce_decryption_request(
    plaintext=plaintext,
    conditions=[ten_oclock_florida_time],
    ritual_id=ANYTHING_CAN_BE_PASSED_AS_RITUAL_DATA,
)

decrypted_cleartext_from_ciphertext_list = bob.threshold_decrypt(
    ciphertext=ciphertext,
    ritual_id=ANYTHING_CAN_BE_PASSED_AS_RITUAL_DATA,
    conditions=[ten_oclock_florida_time],
)



cohort = bob._dkg_insight.fake_ritual.fake_nodes

decrypted_cleartext_from_tdr_list = bob.decrypt_using_existing_decryption_request(
    tdr,
    participant_public_keys=bob._dkg_insight.fake_ritual.participant_public_keys,
    cohort=cohort,
    threshold=1,
    params=bob._dkg_insight.dkg.public_params,
)


decrypted_cleartext_from_ciphertext = bytes(decrypted_cleartext_from_ciphertext_list)
decrypted_cleartext_from_ciphertext_list = bytes(decrypted_cleartext_from_tdr_list)

assert decrypted_cleartext_from_ciphertext == plaintext
assert plaintext == decrypted_cleartext_from_ciphertext_list
print(f"Decrypted cleartext: {decrypted_cleartext_from_ciphertext}")
