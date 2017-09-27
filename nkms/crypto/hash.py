import sha3


# TODO: Replace these with actual hash functions.
def signature_hash(hash_input):
    return sha3.keccak_256(hash_input).digest()


def content_hash(hash_input):
    return sha3.keccak_256(hash_input).digest()