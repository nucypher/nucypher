from marshmallow import fields
from base64 import b64decode, b64encode
from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from nucypher.characters.control.specifications.fields.base import BaseField
from nucypher.crypto.signing import Signature
from nucypher.crypto.constants import KECCAK_DIGEST_LENGTH
from nucypher.crypto.kits import UmbralMessageKit


class TreasureMap(BaseField, fields.Field):

    def _serialize(self, value, attr, obj, **kwargs):
        return b64encode(bytes(value)).decode()

    def _deserialize(self, value, attr, data, **kwargs):
        return b64decode(value)

    def _validate(self, value):
        # TODO: we don't currently accept any treasuremap as input so this is not
        # used.
        splitter = BytestringSplitter(Signature,
                                  (bytes, KECCAK_DIGEST_LENGTH),  # hrac
                                  (UmbralMessageKit, VariableLengthBytestring)
                                  )
        try:
            signature, hrac, tmap_message_kit = splitter(value)
            return True
        except:
            return False

