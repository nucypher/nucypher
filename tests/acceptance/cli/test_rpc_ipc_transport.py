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

import json
from collections import deque

import pytest
import sys

from nucypher.cli.processes import JSONRPCLineReceiver


class TransportTrap:
    """Temporarily diverts system standard output"""

    def __init__(self):
        self.___stdout = sys.stdout
        self.buffer = deque()

    def __enter__(self):
        """Diversion"""
        sys.stdout = self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Return to normal"""
        sys.stdout = self.___stdout

    def read(self, lines: int = 1):

        # Read from faked buffer
        results = list()
        for readop in range(lines):
            results.append(self.buffer.popleft())

        # return the popped values
        if not lines > 1:
            results = results[0]
        return results

    def write(self, data) -> int:
        if data != '\n':
            self.buffer.append(data)
        size = len(data)
        return size

    def flush(self) -> None:
        pass


@pytest.fixture(scope='module')
def rpc_protocol(federated_alice):
    rpc_controller = federated_alice.make_rpc_controller()
    protocol = JSONRPCLineReceiver(rpc_controller=rpc_controller, capture_output=True)
    yield protocol


def test_alice_rpc_controller_creation(federated_alice):
    rpc_controller = federated_alice.make_rpc_controller()
    protocol = JSONRPCLineReceiver(rpc_controller=rpc_controller)
    assert protocol.rpc_controller == federated_alice.controller


def test_rpc_invalid_input(rpc_protocol, federated_alice):
    """
    Example test data fround here: https://www.jsonrpc.org/specification
    """

    semi_valid_collection = dict(

        # description = (input, error code)

        # Semi-valid
        number_only=(42, -32600),
        empty_batch_request=([], -32600),
        empty_request=({}, -32600),
        bogus_input=({'bogus': 'input'}, -32600),
        non_existent_method=({"jsonrpc": "2.0", "method": "llamas", "id": "9"}, -32601),
        invalid_request=({"jsonrpc": "2.0", "method": 1, "params": "bar"}, -32600),

        # Malformed
        invalid_json=(b'{"jsonrpc": "2.0", "method": "foobar, "params": "bar", "baz]', -32700),

        invalid_batch=(b'[{"jsonrpc": "2.0", "method": "sum", "params": [1,2,4], "id": "1"}, '
                       b'{"jsonrpc": "2.0", "method"]', -32700)
    )

    with TransportTrap():

        for description, payload in semi_valid_collection.items():
            request, expected_error_code = payload

            # Allow malformed input to passthrough
            if not isinstance(request, bytes):
                request = bytes(json.dumps(request), encoding='utf-8')

            rpc_protocol.lineReceived(line=request)

            stdout = sys.stdout.read(lines=1)
            deserialized_response = json.loads(stdout)
            assert 'jsonrpc' in deserialized_response

            actual_error_code = int(deserialized_response['error']['code'])
            assert (actual_error_code == expected_error_code), str(request)
