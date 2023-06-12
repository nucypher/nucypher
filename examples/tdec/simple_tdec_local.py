from examples.tdec.demo_utilities.demo_sample_conditions import ten_oclock_florida_time
from nucypher.characters.chaotic import BobGonnaBob, NiceGuyEddie

plaintext = b"PEACE AD DAWN"
THIS_IS_NOT_A_TRINKET = 55

enrico = NiceGuyEddie(encrypting_key=THIS_IS_NOT_A_TRINKET)
bob = BobGonnaBob(domain="lynx")

aad = "my-aad".encode()

ANYTHING_CAN_BE_PASSED_AS_RITUAL_ID_HERE = 55

ciphertext, tdr = enrico.encrypt_for_dkg_and_produce_decryption_request(
    plaintext=plaintext,
    conditions=[ten_oclock_florida_time],
    ritual_id=ANYTHING_CAN_BE_PASSED_AS_RITUAL_ID_HERE,
)
decrypted_cleartext_from_ciphertext = bob.threshold_decrypt(ciphertext=ciphertext)
decrypted_cleartext_from_tdr = (
    bob.get_decryption_shares_using_existing_decryption_request(tdr)
)

assert (
    decrypted_cleartext_from_ciphertext
    == plaintext
    == decrypted_cleartext_from_ciphertext
)
