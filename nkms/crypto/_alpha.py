def pubkey_tuple_to_bytes(pub_key):
    return b''.join(i.to_bytes(32, 'big') for i in pub_key)