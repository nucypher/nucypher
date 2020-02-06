from marshmallow import fields
from base64 import b64decode, b64encode
from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from nucypher.characters.control.specifications.fields.base import BaseField
from nucypher.characters.control.specifications.exceptions import InvalidInputData, InvalidNativeDataTypes
from nucypher.crypto.signing import Signature
from nucypher.crypto.constants import KECCAK_DIGEST_LENGTH
from nucypher.crypto.kits import UmbralMessageKit


class TreasureMap(BaseField, fields.Field):

    def _serialize(self, value, attr, obj, **kwargs):
        return b64encode(bytes(value)).decode()

    def _deserialize(self, value, attr, data, **kwargs):
        try:
            return b64decode(value)
        except InvalidNativeDataTypes as e:
            raise InvalidInputData(f"Could not parse {self.name}: {e}")

    def _validate(self, value):

        splitter = BytestringSplitter(Signature,
                                  (bytes, KECCAK_DIGEST_LENGTH),  # hrac
                                  (UmbralMessageKit, VariableLengthBytestring)
                                  )  # TODO: USe the one from TMap
        try:
            signature, hrac, tmap_message_kit = splitter(value)
            return True
        except InvalidNativeDataTypes as e:
            raise InvalidInputData(f"Could not parse {self.name}: {e}")


