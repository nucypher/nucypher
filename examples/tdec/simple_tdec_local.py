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
print(f"After encryption: {enrico.policy_pubkey}")
decrypted_cleartext_from_ciphertext_list = bob.threshold_decrypt(
    ciphertext=ciphertext,
    ritual_id=ANYTHING_CAN_BE_PASSED_AS_RITUAL_DATA,
    conditions=[ten_oclock_florida_time],
)



# decrypted_cleartext_from_tdr = bob.get_decryption_shares_using_existing_decryption_request(tdr,
#                                                                                            participant_public_keys=THESE_CAN_BE_FAKE_FOR_THE_PURPOSES_OF_THIS_DEMO,
#                                                                                            cohort=THESE_CAN_BE_FAKE_FOR_THE_PURPOSES_OF_THIS_DEMO,
#                                                                                            threshold=ANYTHING_CAN_BE_PASSED_AS_RITUAL_DATA)

decrypted_cleartext_from_ciphertext = bytes(decrypted_cleartext_from_ciphertext_list)

assert decrypted_cleartext_from_ciphertext == plaintext
assert plaintext == decrypted_cleartext_from_ciphertext
