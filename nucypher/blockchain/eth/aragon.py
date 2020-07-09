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
from typing import Iterable, Tuple

from eth_utils import to_canonical_address
from web3 import Web3


class CallScriptCodec:

    CALLSCRIPT_ID = Web3.toBytes(hexstr='0x00000001')

    @classmethod
    def encode(cls, actions: Iterable[Tuple[str, bytes]]):
        callscript = [cls.CALLSCRIPT_ID]

        for target, action_data in actions:
            encoded_action = (to_canonical_address(target),
                              len(action_data).to_bytes(4, 'big'),
                              action_data)
            callscript.extend(encoded_action)

        callscript_data = b''.join(callscript)
        return callscript_data
