from npre.umbral import RekeyFrag


class PFrag(object):
    pass


class KFrag(bytes):

    _EXPECTED_LENGTH = 66
    _id_length = 33
    _key_length = 33

    def __init__(self, id_plus_key):
        kfrag_id = id_plus_key[self._id_length:]
        kfrag_key = id_plus_key[:self._key_length]
        self._umbral_kfrag = RekeyFrag.from_bytes(id_plus_key)

    def __bytes__(self):
        return bytes(self._umbral_kfrag)


class CFrag(object):
    pass
