import sys
from contextlib import contextmanager

import pytest
from io import StringIO

from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.config import GroupGeneralConfig
from nucypher.cli.processes import UrsulaCommandProtocol

# Override environment variables
GroupGeneralConfig.log_to_sentry = False
GroupGeneralConfig.log_to_file = False


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

    # Ensure all commands are in the help text
    result = out.getvalue()
    for command in protocol.commands:
        assert command in result, '{} is missing from help text'.format(command)

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
