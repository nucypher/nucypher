from nkms.crypto import api

def verify(signature, message, pubkey):
    msg_digest = api.keccak_digest(message)
    ecdsa_sig = api.ecdsa_load_sig(signature)
    return api.ecdsa_verify(*ecdsa_sig, msg_digest, pubkey)