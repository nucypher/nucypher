from npre.constants import UNKNOWN_KFRAG
from npre.umbral import RekeyFrag


class PFrag(object):
    pass


class KFrag(object):

    _EXPECTED_LENGTH = 66
    _is_unknown_kfrag = False

    def __init__(self, id_plus_key_as_bytes=None, umbral_kfrag=None):
        if all((id_plus_key_as_bytes, umbral_kfrag)):
            raise ValueError("Pass either the id/key or an umbral_kfrag (or neither for UNKNOWN_KFRAG).  Not both.")
        elif id_plus_key_as_bytes:
            self._umbral_kfrag = RekeyFrag.from_bytes(id_plus_key_as_bytes)
        elif umbral_kfrag:
            self._umbral_kfrag = umbral_kfrag
        else:
            self._is_unknown_kfrag = True

    def __bytes__(self):
        return bytes(self._umbral_kfrag)

    def __eq__(self, other_kfrag):
        if other_kfrag is UNKNOWN_KFRAG:
            return bool(self._is_unknown_kfrag)
        else:
            return bytes(self) == bytes(other_kfrag)

    def __add__(self, other):
        return bytes(self) + other

    def __radd__(self, other):
        return other + bytes(self)

    def __getitem__(self, slice):
        return bytes(self)[slice]

    @property
    def key(self):
        return self._umbral_kfrag.key

    @property
    def id(self):
        return self._umbral_kfrag.id


class CFrag(object):
    pass
