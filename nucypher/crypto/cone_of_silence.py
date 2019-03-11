"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import os
import pathlib
from typing import List

from twisted.internet import endpoints, reactor
from twisted.protocols.basic import LineReceiver
from umbral.keys import derive_key_from_password

from nucypher.config.constants import IPC_SOCKETS_DIR
from nucypher.config.keyring import (
    _read_keyfile, _PrivateKeySerializer,
    _derive_wrapping_key_from_key_material
)
from nucypher.crypto import powers
from tubes.listening import Listener
from tubes.protocol import flowFromEndpoint, flowFountFromEndpoint
from tubes.tube import series, tube


def socket_dir_for_this_process():
    return os.path.join(IPC_SOCKETS_DIR, str(os.getpid()))


def socket_for_function(f):
    return os.path.join(socket_dir_for_this_process(), f.__qualname__)


class ConeOfSilence(LineReceiver):
    """
    A compartment (like a SCIF) to perform sensitive cryptographic operations.
    """

    encoding = 'utf-8'

    class IncompatibleKeyfile(Exception):
        """
        Raised when the Keyfiles provided to the ConeOfSilence have different
        master salts and can't be decrypted with the same passphrase.
        """
        pass

    def __init__(self, passphrase: str, key_files: List[str]) -> None:
        """
        When the Cone of Silence is created, it will derive a key from the
        passphrase provided to decrypt keyfiles on the disk and implement
        their powers.
        """
        self.__crypto_power_set = powers.CryptoPowerSet()

        key_files = dict()
        master_salt = None
        for key_file in key_files:
            key_data = _read_keyfile(key_file, _PrivateKeySerializer())
            if master_salt is not None and master_salt != key_data['master_salt']:
                raise ConeOfSilence.IncompatibleKeyFile(
                    "The master salt in {key_file} doesn't match the other keyfiles provided.")

            if 'root' in key_file:
                key_files['DecryptingPower'] = key_data
            elif 'delegating' in key_file:
                key_files['DelegatingPower'] = key_data
            elif 'signing' in key_file:
                key_files['SigningPower'] = key_data
            else:
                raise ConeOfSilence.IncompatibleKeyFile("The keyfile {key_file} doesn't match any known Powers.")
            master_salt = key_data['master_salt']
        self.__derived_key = derive_key_from_password(passphrase, master_salt)

        for power_up_class, key_data in key_files.items():
            wrapping_key = _derive_wrapping_key_from_key_material(
                key_data['wrap_salt'],
                self.__derived_key)
            power_up = getattr(powers, power_up_class)(
                key_bytes=key_data['key'],
                wrapping_key=wrapping_key)
            self.__crypto_power_set.consume_power_up(power_up)

    def lineReceived(self, line):
        pass


@tube
class InsideTheCone:
    socket_path = socket_dir_for_this_process()

    def __init__(self, socket_path="what are we doing here"):
        pathlib.Path(self.socket_path).mkdir(parents=True, exist_ok=True)
        return

    def __call__(self, f):
        self.func = f
        self.endpoint = endpoints.UNIXServerEndpoint(reactor, f.__qualname__, mode=0o600)
        d = flowFountFromEndpoint(self.endpoint)
        d.addCallback(self.llamas)
        return f

    def listener(self, flow):
        flow.fount.flowTo(series(self)).flowTo(flow.drain)

    def llamas(self, caller_fount):
        caller_fount.flowTo(Listener(self.listener))

    def received(self, line):
        yield self.func(line)


@tube
class OutsideTheCone:
    def __init__(self, socket_path):
        # self.endpoint = endpoints.UNIXClientEndpoint(reactor, socket_path, timeout=2)
        return

    def __call__(self, f):
        # Send call across the wire.
        self.endpoint = endpoints.UNIXClientEndpoint(reactor, f.__qualname__, timeout=2)
        self.func = f
        return self._call_across_wire

    def _call_across_wire(self, *args, **kwargs):
        d = flowFromEndpoint(self.endpoint).addCallback(self._handle_flow, *args, **kwargs).addErrback(
            self._handle_errors)
        result = succeed(d)
        return d

    def _handle_flow(self, flow, line, *args, **kwargs):
        flow.fount.flowTo(series(self))
        a = flow.drain.receive(line)
        return

    def _handle_errors(self, failure):
        assert False

    def received(self, line):
        return line
