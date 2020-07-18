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

import os

import pytest
from eth_utils import to_canonical_address
from web3 import Web3

from nucypher.blockchain.eth.aragon import CallScriptCodec


def test_callscriptcodec():
    assert CallScriptCodec.CALLSCRIPT_ID == bytes.fromhex("00000001")


def test_callscript_encoding_empty():
    actions = tuple()

    callscript_data = CallScriptCodec.encode_actions(actions)
    expected_callscript = CallScriptCodec.CALLSCRIPT_ID
    assert expected_callscript == callscript_data


@pytest.mark.parametrize('data_length', range(0, 100, 5))
def test_callscript_encoding_one_action(get_random_checksum_address, data_length):
    # Action is a byte string
    target = get_random_checksum_address()
    data = os.urandom(data_length)
    actions = [(target, data)]

    callscript_data = CallScriptCodec.encode_actions(actions)
    expected_callscript = b''.join((CallScriptCodec.CALLSCRIPT_ID,
                                    to_canonical_address(target),
                                    data_length.to_bytes(4, 'big'),
                                    data))
    assert expected_callscript == callscript_data

    # Action is a hex string
    data = Web3.toHex(data)
    actions = [(target, data)]
    callscript_data = CallScriptCodec.encode_actions(actions)
    assert expected_callscript == callscript_data
