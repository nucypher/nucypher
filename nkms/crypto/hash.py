import sha3


def content_hash(*hash_inputs):
    hash = sha3.keccak_256()
    for hash_input in hash_inputs:
        hash.update(hash_input)
    return hash.digest()


signature_hash = content_hash
