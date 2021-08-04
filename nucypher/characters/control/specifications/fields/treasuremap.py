"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

from base64 import b64decode, b64encode

from marshmallow import fields

from nucypher.characters.control.specifications.exceptions import InvalidNativeDataTypes
from nucypher.control.specifications.exceptions import InvalidInputData
from nucypher.control.specifications.fields.base import BaseField


class TreasureMap(BaseField, fields.Field):
    """
    JSON Parameter representation of TreasureMap.

    Requires that either federated or non-federated (blockchain) treasure maps are expected to function correcty. This
    information is indicated either:
    - At creation time of the field via constructor parameter 'federated_only' (takes precedence)
    OR
    - Via the parent Schema context it is running in. In this case, the parent Schema context dictionary should have a
    key-value entry in it with the IS_FEDERATED_CONTEXT_KEY class constant as the key, and a value of True/False.

    If neither is provided, the TreasureMap is assumed to be a SignedTreasureMap. The federated/non-federated context
    of the TreasureMap only applies to deserialization and validation since the received value is in base64 encoded
    bytes.
    """
    IS_FEDERATED_CONTEXT_KEY = 'federated'

    def __init__(self, federated_only=None, *args, **kwargs):
        self.federated_only = federated_only
        BaseField.__init__(self, *args, **kwargs)
        fields.Field.__init__(self, *args, **kwargs)

    def _serialize(self, value, attr, obj, **kwargs):
        return b64encode(bytes(value)).decode()

    def _deserialize(self, value, attr, data, **kwargs):
        try:
            return b64decode(value)
        except InvalidNativeDataTypes as e:
            raise InvalidInputData(f"Could not parse {self.name}: {e}")

    def _validate(self, value):
        from nucypher.policy.maps import SignedTreasureMap
        from nucypher.policy.maps import TreasureMap as UnsignedTreasureMap

        # determine context: federated or non-federated defined by field or schema
        is_federated_context = False  # default to non-federated
        if self.federated_only is not None:
            # defined by field itself
            is_federated_context = self.federated_only
        else:
            # defined by schema
            if self.parent is not None and self.parent.context.get('federated') is not None:
                is_federated_context = self.context.get('federated')

        try:
            splitter = SignedTreasureMap.get_splitter(value) if not is_federated_context else UnsignedTreasureMap.get_splitter(value)
            _ = splitter(value)
            return True
        except InvalidNativeDataTypes as e:
            # store exception
            raise InvalidInputData(f"Could not parse {self.name} (federated={is_federated_context}): {e}")
