from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.signers import InMemorySigner
from nucypher.characters.chaotic import NiceGuyEddie as _Enrico
from nucypher.characters.chaotic import ThisBobAlwaysDecrypts
from nucypher.policy.conditions.lingo import ConditionLingo, ConditionType

plaintext = b"paz al amanecer"
THIS_IS_NOT_A_TRINKET = 55  # sometimes called "public key"

signer = InMemorySigner()
enrico = _Enrico(encrypting_key=THIS_IS_NOT_A_TRINKET, signer=signer)
bob = ThisBobAlwaysDecrypts(domain=domains.LYNX, eth_endpoint="Nowhere")

ANYTHING_CAN_BE_PASSED_AS_RITUAL_ID = 55

before_the_beginning_of_time = {
    "version": ConditionLingo.VERSION,
    "condition": {
        "conditionType": ConditionType.TIME.value,
        "chain": 1,
        "method": "blocktime",
        "returnValueTest": {"comparator": "<", "value": 0},
    },
}

threshold_message_kit = enrico.encrypt_for_dkg(
    plaintext=plaintext,
    conditions=before_the_beginning_of_time,
)

cleartext_from_ciphertext = bob.threshold_decrypt(
    threshold_message_kit=threshold_message_kit,
)

decoded_cleartext_from_ciphertext = bytes(cleartext_from_ciphertext)

assert decoded_cleartext_from_ciphertext == plaintext
print(f"Decrypted cleartext: {decoded_cleartext_from_ciphertext}")
