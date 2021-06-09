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

from contextlib import contextmanager

import pytest
import sys
from io import StringIO

from nucypher.control.emitters import StdoutEmitter
from nucypher.cli.processes import UrsulaCommandProtocol


@contextmanager
def capture_output():
    new_out, new_err = StringIO(), StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = new_out, new_err
        yield sys.stdout, sys.stderr
    finally:
        sys.stdout, sys.stderr = old_out, old_err


@pytest.fixture(scope='module')
def ursula(federated_ursulas):
    ursula = federated_ursulas.pop()
    return ursula


@pytest.fixture(scope='module')
def protocol(ursula):
    emitter = StdoutEmitter()
    protocol = UrsulaCommandProtocol(ursula=ursula, emitter=emitter)
    return protocol


def test_ursula_command_protocol_creation(ursula):

    emitter = StdoutEmitter()
    protocol = UrsulaCommandProtocol(ursula=ursula, emitter=emitter)

    assert protocol.ursula == ursula
    assert b'Ursula' in protocol.prompt


def test_ursula_command_help(protocol, ursula):

    class FakeTransport:
        """This is a transport"""

        mock_output = b''

        @staticmethod
        def write(data: bytes):
            FakeTransport.mock_output += data

    protocol.transport = FakeTransport

    with capture_output() as (out, err):
        protocol.lineReceived(line=b'bananas')

    commands = protocol.commands
    commands = list(set(commands) - set(protocol._hidden_commands))

    # Ensure all commands are in the help text
    result = out.getvalue()
    assert "Invalid input" in result
    for command in commands:
        assert command in result, '{} is missing from help text'.format(command)
    for command in protocol._hidden_commands:
        assert command not in result, f'Hidden command {command} in help text'

    # Try again with valid 'help' command
    with capture_output() as (out, err):
        protocol.lineReceived(line=b'help')

    result = out.getvalue()
    assert "Invalid input" not in result
    for command in commands:
        assert command in result, '{} is missing from help text'.format(command)
    for command in protocol._hidden_commands:
        assert command not in result, f'Hidden command {command} in help text'

    # Blank lines are OK!
    with capture_output() as (out, err):
        protocol.lineReceived(line=b'')
    assert protocol.prompt in FakeTransport.mock_output


def test_ursula_command_status(protocol, ursula):

    with capture_output() as (out, err):
        protocol.paintStatus()
    result = out.getvalue()
    assert ursula.checksum_address in result
    assert '...' in result
    assert 'Known Nodes' in result


def test_ursula_command_known_nodes(protocol, ursula):

    with capture_output() as (out, err):
        protocol.paintKnownNodes()
    result = out.getvalue()
    assert 'Known Nodes' in result
    assert ursula.checksum_address not in result
